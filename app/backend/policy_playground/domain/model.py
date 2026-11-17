"""Modelo interno da política (design §6.2) e validação no carregamento (§7.1).

O Policy Spec é entrada de outra etapa e nunca é alterado (R16.3): o modelo é
construído a partir de uma cópia e todos os objetos expostos são imutáveis.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from . import expr

REQUIRED_SECTIONS = ["policy", "stages", "rules", "variables", "parameters", "dag", "motivos", "validation_map", "output_vars"]
REQUIRED_RULE_FIELDS = ["id", "logic", "inputs", "outputs"]
KNOWN_LOGIC_TYPES = {"json_extract", "case_when", "matrix_lookup"}
POLICY_AREAS = {"Extraction", "ETL", "Hard filters", "Final base"}


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extension_errors: list[str] = field(default_factory=list)
    dataset_errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def can_execute(self) -> bool:
        return self.ok and not self.extension_errors and not self.dataset_errors

    def as_dict(self) -> dict:
        return {"ok": self.ok, "canExecute": self.can_execute, "errors": self.errors, "warnings": self.warnings,
                "extensionErrors": self.extension_errors, "datasetErrors": self.dataset_errors}


class PolicyInvalid(Exception):
    def __init__(self, report: ValidationReport):
        super().__init__("; ".join(report.errors))
        self.report = report


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    type: str
    stage_id: str
    logic: MappingProxyType
    inputs: tuple
    outputs: tuple
    depends_on: tuple
    parameters: tuple
    conditions: tuple = ()  # case_when: ((ast, then), ...)


@dataclass(frozen=True)
class Parameter:
    id: str
    name: str
    value: float
    unit: str
    description: str
    used_by: tuple
    domain: MappingProxyType | None  # None => somente leitura


class PolicyModel:
    """Baseline imutável carregado do Policy Spec + extensions + dataset."""

    def __init__(self, spec: dict, ext: dict | None, dataset: dict | None, report: ValidationReport):
        self._spec = copy.deepcopy(spec)
        self.report = report
        self.meta = MappingProxyType(dict(self._spec["policy"]))
        self.extensions = copy.deepcopy(ext or {})
        self.dataset = copy.deepcopy(dataset) if dataset else None
        domains = self.extensions.get("parameter_domains", {})
        self.rules: dict[str, Rule] = {}
        for r in self._spec["rules"]:
            conds = ()
            if r["logic"]["type"] == "case_when":
                conds = tuple((expr.parse(b["when"]), b["then"]) for b in r["logic"]["branches"])
            self.rules[r["id"]] = Rule(r["id"], r.get("name", r["id"]), r.get("type", ""), r.get("stage_id", ""),
                                       MappingProxyType(copy.deepcopy(r["logic"])), tuple(r["inputs"]), tuple(r["outputs"]),
                                       tuple(r.get("depends_on", [])), tuple(r.get("parameters", [])), conds)
        self.parameters: dict[str, Parameter] = {
            p["id"]: Parameter(p["id"], p["name"], p["value"], p.get("unit", ""), p.get("description", ""),
                               tuple(p.get("used_by", [])), MappingProxyType(domains[p["id"]]) if p["id"] in domains else None)
            for p in self._spec["parameters"]}
        self.variables = {v["name"]: dict(v) for v in self._spec["variables"]}
        self.order: list[str] = [rid for layer in self._spec["dag"]["execution_order"] for rid in layer]
        self.layers: list[list[str]] = [list(layer) for layer in self._spec["dag"]["execution_order"]]
        self.motivos = [dict(m) for m in self._spec["motivos"]]
        self.output_vars = [o["name"] for o in self._spec["output_vars"]]
        self.stages = [{"id": s["id"], "name": s["name"], "area": self.extensions.get("stage_area", {}).get(s["id"])}
                       for s in self._spec["stages"]]
        self.consumed_by: dict[str, list[str]] = {}
        for r in self.rules.values():
            for v in r.inputs:
                self.consumed_by.setdefault(v, []).append(r.id)
        self.producer: dict[str, str] = {o: r.id for r in self.rules.values() for o in r.outputs}

    # ---- identidade e versões -------------------------------------------------
    @property
    def policy_version(self) -> str:
        return f"{self.meta['id']}@{self.meta.get('source_commit', 'unknown')}"

    @property
    def dataset_version(self) -> str | None:
        return self.dataset.get("dataset_version") if self.dataset else None

    def param_by_name(self, name: str) -> Parameter | None:
        return next((p for p in self.parameters.values() if p.name == name), None)

    def baseline_params(self) -> dict[str, float]:
        return {p.name: p.value for p in self.parameters.values()}

    def spec_snapshot(self) -> dict:
        """Cópia do Policy Spec original (para provar que nunca muda)."""
        return copy.deepcopy(self._spec)

    # ---- visão para a interface ----------------------------------------------
    def view(self) -> dict:
        area = self.extensions.get("stage_area", {})
        return {
            "policy": dict(self.meta), "policyVersion": self.policy_version, "datasetVersion": self.dataset_version,
            "stages": self.stages,
            "rules": [{"id": r.id, "name": r.name, "type": r.type, "stageId": r.stage_id, "area": area.get(r.stage_id),
                       "logic": json.loads(json.dumps(dict(r.logic))), "inputs": list(r.inputs), "outputs": list(r.outputs),
                       "dependsOn": list(r.depends_on), "parameters": list(r.parameters),
                       "readOnlyThresholds": _literal_thresholds(r)} for r in self.rules.values()],
            "parameters": [{"id": p.id, "name": p.name, "value": p.value, "unit": p.unit, "description": p.description,
                            "usedBy": list(p.used_by), "editable": bool(p.domain and p.domain.get("editable")),
                            "domain": dict(p.domain) if p.domain else None} for p in self.parameters.values()],
            "variables": [{**v, "consumedBy": self.consumed_by.get(v["name"], [])} for v in self.variables.values()],
            "executionOrder": self.layers, "motivos": self.motivos, "outputVars": self.output_vars,
            "validation": self.report.as_dict(),
            "dataset": {"version": self.dataset_version, "records": len(self.dataset["records"]) if self.dataset else 0,
                        "kind": self.dataset.get("kind") if self.dataset else None},
        }


def _literal_thresholds(r: Rule) -> list[str]:
    """Limiares escritos como literal dentro da regra (ex.: R007): exibidos como somente leitura."""
    out = []
    for ast, then in r.conditions:
        for c in _cmps(ast):
            if isinstance(c.right, expr.Lit) and isinstance(c.right.value, float) and isinstance(c.left, expr.Ref):
                out.append(f"{c.left.name} {c.op} {c.right.value:g} → {then}")
    return out


def _cmps(node):
    if isinstance(node, expr.Cmp):
        return [node]
    return [c for i in node.items for c in _cmps(i)]


# ---- validação ------------------------------------------------------------------

def validate_spec(spec: dict, rep: ValidationReport) -> None:
    for s in REQUIRED_SECTIONS:
        if s not in spec:
            rep.errors.append(f"Seção obrigatória ausente: '{s}'")
    if not rep.ok:
        return
    rule_ids = [r.get("id") for r in spec["rules"]]
    if len(rule_ids) != len(set(rule_ids)):
        rep.errors.append("Há ids de regra duplicados")
    rule_set, param_ids = set(rule_ids), {p["id"] for p in spec["parameters"]}
    stage_ids = {s["id"] for s in spec["stages"]}
    names = {v["name"] for v in spec["variables"]} | {p["name"] for p in spec["parameters"]}
    for r in spec["rules"]:
        rid = r.get("id", "?")
        for f in REQUIRED_RULE_FIELDS:
            if f not in r:
                rep.errors.append(f"Regra {rid}: campo obrigatório ausente '{f}'")
        if "logic" not in r:
            continue
        lt = r["logic"].get("type")
        if lt not in KNOWN_LOGIC_TYPES:
            rep.errors.append(f"Regra {rid}: tipo de lógica desconhecido '{lt}'. Tipos suportados: {', '.join(sorted(KNOWN_LOGIC_TYPES))}")
        if lt == "case_when":
            for b in r["logic"].get("branches", []):
                try:
                    unknown = expr.refs(expr.parse(b["when"])) - names
                    if unknown:
                        rep.errors.append(f"Regra {rid}: condição usa nomes não declarados {sorted(unknown)}")
                except expr.ExpressionError as e:
                    rep.errors.append(f"Regra {rid}: condição fora da gramática suportada ({e})")
        if lt == "matrix_lookup":
            for k in ("row_key", "col_key", "matrix"):
                if k not in r["logic"]:
                    rep.errors.append(f"Regra {rid}: matrix_lookup sem '{k}'")
        for d in r.get("depends_on", []):
            if d not in rule_set:
                rep.errors.append(f"Regra {rid}: depends_on aponta para regra inexistente '{d}'")
        for p in r.get("parameters", []):
            if p not in param_ids:
                rep.errors.append(f"Regra {rid}: parâmetro inexistente '{p}'")
        if r.get("stage_id") and r["stage_id"] not in stage_ids:
            rep.errors.append(f"Regra {rid}: stage_id '{r['stage_id']}' não existe")
    for v in spec["variables"]:
        pb = v.get("produced_by")
        if pb and pb != "external" and pb not in rule_set:
            rep.errors.append(f"Variável {v.get('name')}: produced_by aponta para regra inexistente '{pb}'")
    for p in spec["parameters"]:
        for u in p.get("used_by", []):
            if u not in rule_set:
                rep.errors.append(f"Parâmetro {p['id']}: used_by aponta para regra inexistente '{u}'")
    for m in spec["motivos"]:
        if m.get("rule_id") not in rule_set:
            rep.errors.append(f"Motivo {m.get('code')}: rule_id inexistente '{m.get('rule_id')}'")
    deps = {r["id"]: list(r.get("depends_on", [])) for r in spec["rules"] if "id" in r}
    cycle = find_cycle(deps)
    if cycle:
        rep.errors.append("Ciclo no DAG: " + " → ".join(cycle))
        return
    layer_of = {rid: i for i, layer in enumerate(spec["dag"].get("execution_order", [])) for rid in layer}
    for rid in rule_set - set(layer_of):
        rep.errors.append(f"Regra {rid} não aparece em dag.execution_order")
    for rid, ds in deps.items():
        for d in ds:
            if rid in layer_of and d in layer_of and layer_of[d] >= layer_of[rid]:
                rep.errors.append(f"execution_order inconsistente: {rid} depende de {d}, que não roda antes")


def find_cycle(deps: dict[str, list[str]]) -> list[str] | None:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in deps}
    stack: list[str] = []

    def visit(n):
        color[n] = GRAY
        stack.append(n)
        for m in deps.get(n, []):
            if color.get(m) == GRAY:
                return stack[stack.index(m):] + [m]
            if color.get(m, BLACK) == WHITE:
                c = visit(m)
                if c:
                    return c
        stack.pop()
        color[n] = BLACK
        return None

    for n in deps:
        if color[n] == WHITE:
            c = visit(n)
            if c:
                return c
    return None


def validate_extensions(spec: dict, ext: dict, rep: ValidationReport) -> None:
    ex = ext.get("extends", {})
    if ex.get("policy_id") != spec["policy"].get("id"):
        rep.extension_errors.append(f"extensions.extends.policy_id '{ex.get('policy_id')}' ≠ policy.id '{spec['policy'].get('id')}'")
    if ex.get("source_commit") != spec["policy"].get("source_commit"):
        rep.extension_errors.append("extensions.extends.source_commit difere do source_commit do Policy Spec")
    stage_ids = {s["id"] for s in spec["stages"]}
    for sid, area in ext.get("stage_area", {}).items():
        if sid not in stage_ids:
            rep.extension_errors.append(f"stage_area cita estágio inexistente '{sid}'")
        if area not in POLICY_AREAS:
            rep.warnings.append(f"Estágio {sid}: área '{area}' fora de {sorted(POLICY_AREAS)}")
    for sid in stage_ids - set(ext.get("stage_area", {})):
        rep.warnings.append(f"Estágio {sid} sem área da política informada")
    params = {p["id"]: p for p in spec["parameters"]}
    for pid, dom in ext.get("parameter_domains", {}).items():
        if pid not in params:
            rep.extension_errors.append(f"parameter_domains cita parâmetro inexistente '{pid}'")
            continue
        v = params[pid]["value"]
        if not (dom.get("min", float("-inf")) <= v <= dom.get("max", float("inf"))):
            rep.extension_errors.append(f"{pid}: valor de baseline {v} fora do domínio [{dom.get('min')}, {dom.get('max')}]")
    for pid in set(params) - set(ext.get("parameter_domains", {})):
        rep.warnings.append(f"{pid} sem domínio declarado: exibido como somente leitura")


def validate_dataset(ext: dict, dataset: dict | None, rep: ValidationReport) -> None:
    refs = ext.get("datasets", [])
    if not refs:
        rep.dataset_errors.append("Nenhum dataset referenciado nas extensions")
        return
    meta = refs[0]
    if dataset is None:
        rep.dataset_errors.append(f"Dataset '{meta.get('file')}' não encontrado")
        return
    if meta.get("contains_pii") is not False or dataset.get("contains_pii") is not False:
        rep.dataset_errors.append("Dataset precisa declarar contains_pii: false")
    if len(dataset.get("records", [])) != meta.get("record_count"):
        rep.dataset_errors.append(f"Dataset tem {len(dataset.get('records', []))} registros; extensions declara {meta.get('record_count')}")
    if dataset.get("dataset_version") != meta.get("dataset_version"):
        rep.dataset_errors.append("dataset_version difere entre dataset e extensions")


def load_policy(spec: dict, ext: dict | None, dataset: dict | None) -> PolicyModel:
    rep = ValidationReport()
    validate_spec(spec, rep)
    if not rep.ok:
        raise PolicyInvalid(rep)
    if ext is not None:
        validate_extensions(spec, ext, rep)
        validate_dataset(ext, dataset, rep)
    else:
        rep.extension_errors.append("Arquivo de extensions ausente")
    return PolicyModel(spec, ext, dataset, rep)


def load_from_folder(folder: Path, name: str = "policy-playground-demo") -> PolicyModel:
    folder = Path(folder)
    spec = json.loads((folder / f"{name}-policy.json").read_text(encoding="utf-8"))
    ext_p, ds_p = folder / f"{name}-extensions.json", folder / f"{name}-dataset.json"
    ext = json.loads(ext_p.read_text(encoding="utf-8")) if ext_p.exists() else None
    ds = None
    if ext and ext.get("datasets"):
        p = folder / ext["datasets"][0]["file"]
        ds = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return load_policy(spec, ext, ds)
