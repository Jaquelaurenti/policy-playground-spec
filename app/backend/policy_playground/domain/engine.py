"""Avaliador fechado (§7.2), descoberta reversa (§8.2), SimulatedRunner (§9) e comparação (§11).

Nada aqui chama modelo, rede ou banco: é o caminho determinístico que produz
todo número que a interface mostra.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from . import expr
from .model import PolicyModel, Rule

RUNNER_VERSION = "simulated-runner/1.0"


class CannotCalculate(Exception):
    pass


# ---- avaliador ------------------------------------------------------------------

def _json_path(payload: dict, path: str):
    if not path.startswith("$."):
        raise CannotCalculate(f"Caminho fora do formato suportado: {path}")
    cur = payload
    for part in path[2:].split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def evaluate_rule(rule: Rule, env: dict, payload: dict):
    lt = rule.logic["type"]
    if lt == "json_extract":
        v = _json_path(payload, rule.logic["path"])
        if v is not None and rule.logic.get("cast") == "number":
            v = float(v)
        elif v is not None and rule.logic.get("cast") == "string":
            v = str(v)
        return v
    if lt == "case_when":
        for ast, then in rule.conditions:
            try:
                if expr.evaluate(ast, env):
                    return then
            except expr.MissingValue as e:
                raise CannotCalculate(f"{rule.id}: valor ausente para {e}") from e
        return rule.logic.get("else")
    if lt == "matrix_lookup":
        row, col = env.get(rule.logic["row_key"]), env.get(rule.logic["col_key"])
        cell = rule.logic["matrix"].get(row, {}).get(col) if row is not None and col is not None else None
        if cell is None:
            raise CannotCalculate(f"{rule.id}: célula ({row}, {col}) inexistente na matriz")
        return float(cell)
    raise CannotCalculate(f"{rule.id}: tipo de lógica não suportado {lt}")


def _external_inputs(model: PolicyModel, payload: dict) -> dict:
    env = {}
    for v in model.variables.values():
        if v.get("produced_by") == "external" and v.get("payload_path"):
            env[v["name"]] = _json_path(payload, v["payload_path"])
    return env


def run_record(model: PolicyModel, payload: dict, params: dict, only: set[str] | None = None, base_env: dict | None = None) -> dict:
    """Avalia as regras em execution_order. Com `only`, recalcula só essas regras e reaproveita `base_env` no resto."""
    env = dict(base_env) if base_env else {}
    env.update(_external_inputs(model, payload))
    env.update(params)
    for rid in model.order:
        if only is not None and rid not in only:
            continue
        rule = model.rules[rid]
        val = evaluate_rule(rule, env, payload)
        for o in rule.outputs:
            env[o] = val
    return env


# ---- descoberta reversa ------------------------------------------------------------

@dataclass
class SubDag:
    changed_params: list[str]
    seed: list[str]
    forward: list[str]
    upstream: list[str]
    execution_set: list[str]
    affected_outputs: list[str]
    affected_motivos: list[dict]
    edges: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self):
        return {"changedParams": self.changed_params, "seed": self.seed, "forward": self.forward, "upstream": self.upstream,
                "executionSet": self.execution_set, "affectedOutputs": self.affected_outputs,
                "affectedMotivos": self.affected_motivos, "path": [list(e) for e in self.edges]}


def affected_subdag(model: PolicyModel, param_ids: list[str]) -> SubDag:
    seed = sorted({r for pid in param_ids for r in model.parameters[pid].used_by})
    forward, edges, frontier = [], [], list(seed)
    for pid in param_ids:
        for r in model.parameters[pid].used_by:
            edges.append((pid, r))
    seen = set(seed)
    while frontier:
        rid = frontier.pop(0)
        for out in model.rules[rid].outputs:
            edges.append((rid, out))
            for consumer in model.consumed_by.get(out, []):
                edges.append((out, consumer))
                if consumer not in seen:
                    seen.add(consumer)
                    forward.append(consumer)
                    frontier.append(consumer)
    upstream, stack = set(), list(seed)
    while stack:
        for d in model.rules[stack.pop()].depends_on:
            if d not in upstream:
                upstream.add(d)
                stack.append(d)
    ex = set(seed) | set(forward) | upstream
    order = [r for r in model.order if r in ex]
    outs = [o for r in seed + forward for o in model.rules[r].outputs if o in model.output_vars]
    motivos = [m for m in model.motivos if m["rule_id"] in set(seed) | set(forward)]
    return SubDag(param_ids, seed, forward, sorted(upstream, key=model.order.index), order, outs, motivos, edges)


def required_for_output(model: PolicyModel, output_var: str) -> list[str]:
    """Descoberta a partir do objetivo: fechamento de depends_on da regra que produz a saída."""
    rid = model.producer.get(output_var)
    if not rid:
        return []
    need, stack = {rid}, [rid]
    while stack:
        for d in model.rules[stack.pop()].depends_on:
            if d not in need:
                need.add(d)
                stack.append(d)
    return [r for r in model.order if r in need]


# ---- execução simulada -------------------------------------------------------------

def idempotency_key(model: PolicyModel, overrides: dict[str, float], slice_: dict | None = None) -> str:
    norm = sorted((k, float(v)) for k, v in overrides.items())   # 3000 e 3000.0 são o mesmo cenário
    raw = json.dumps([model.policy_version, norm, model.dataset_version, RUNNER_VERSION]
                     + ([slice_["variable"], slice_["intervals"]] if slice_ else []), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def overrides_to_params(model: PolicyModel, overrides: dict[str, float]) -> dict:
    params = model.baseline_params()
    for pid, v in overrides.items():
        params[model.parameters[pid].name] = float(v)
    return params


def simulate(model: PolicyModel, overrides: dict[str, float], slice_: dict | None = None) -> dict:
    """Roda baseline e cenário sobre o dataset sintético. Sempre mode=SIMULADO.
    Com `slice_`, só entram as propostas cujo valor da variável no baseline cai no recorte (R9, achado G2)."""
    from .generators import in_slice
    if not model.report.can_execute:
        raise CannotCalculate("Validação bloqueia a execução: " + "; ".join(model.report.extension_errors + model.report.dataset_errors))
    sub = affected_subdag(model, list(overrides))
    base_params, scen_params = model.baseline_params(), overrides_to_params(model, overrides)
    rows = []
    for rec in model.dataset["records"]:
        payload = {k: v for k, v in rec.items() if k not in ("record_id", "cobertura")}
        base = run_record(model, payload, base_params)
        if slice_ and not in_slice(base.get(slice_["variable"]), slice_):
            continue
        scen = run_record(model, payload, scen_params, only=set(sub.execution_set), base_env=base)
        rows.append({"recordId": rec["record_id"], "cobertura": rec.get("cobertura"),
                     "baseline": {o: base.get(o) for o in model.output_vars},
                     "scenario": {o: scen.get(o) for o in model.output_vars},
                     "baselineMotivos": _motivos_hit(model, base), "scenarioMotivos": _motivos_hit(model, scen)})
    out = {"rows": rows, "subDag": sub.as_dict(), "comparison": compare(model, rows)}
    if slice_:
        out["slice"] = slice_
    return out


def _motivos_hit(model: PolicyModel, env: dict) -> list[int]:
    hit = []
    for m in model.motivos:
        outs = model.rules[m["rule_id"]].outputs
        if any(env.get(o) == "REPROVADO" for o in outs):
            hit.append(m["code"])
    return hit


def compare(model: PolicyModel, rows: list[dict]) -> dict:
    out = {}
    for var in model.output_vars:
        kind = model.variables.get(var, {}).get("data_type")
        b = [r["baseline"][var] for r in rows]
        s = [r["scenario"][var] for r in rows]
        changed = [r["recordId"] for r in rows if r["baseline"][var] != r["scenario"][var]]
        if kind == "number":
            out[var] = {"type": "number", "baselineSum": sum(x or 0 for x in b), "scenarioSum": sum(x or 0 for x in s), "changedRecords": changed}
        else:
            cats = sorted({str(x) for x in b + s})
            out[var] = {"type": "category", "baseline": {c: sum(1 for x in b if str(x) == c) for c in cats},
                        "scenario": {c: sum(1 for x in s if str(x) == c) for c in cats}, "changedRecords": changed}
    mot = {}
    for m in model.motivos:
        mot[m["code"]] = {"name": m["name"], "ruleId": m["rule_id"],
                          "baseline": sum(1 for r in rows if m["code"] in r["baselineMotivos"]),
                          "scenario": sum(1 for r in rows if m["code"] in r["scenarioMotivos"])}
    # limite oferecido só faz sentido para quem foi aprovado
    approved_limit = {
        "baseline": sum(r["baseline"].get("limite_sugerido") or 0 for r in rows if r["baseline"].get("resultado") == "APROVACAO_SIMULADA"),
        "scenario": sum(r["scenario"].get("limite_sugerido") or 0 for r in rows if r["scenario"].get("resultado") == "APROVACAO_SIMULADA"),
    }
    return {"outputs": out, "motivos": mot, "approvedLimitSum": approved_limit, "records": len(rows)}


def deltas(cmp: dict) -> dict:
    """Variações já calculadas pelo motor, para o agente não fazer aritmética (evita 'de 1 para 5' virar '5 novas')."""
    out = {}
    for o, v in cmp["outputs"].items():
        if v["type"] == "category":
            cats = sorted(set(v["baseline"]) | set(v["scenario"]))
            out[o] = {c: {"de": v["baseline"].get(c, 0), "para": v["scenario"].get(c, 0),
                          "delta": v["scenario"].get(c, 0) - v["baseline"].get(c, 0)} for c in cats}
        else:
            out[o] = {"de": v["baselineSum"], "para": v["scenarioSum"], "delta": v["scenarioSum"] - v["baselineSum"]}
    out["motivos"] = {code: {"nome": m["name"], "de": m["baseline"], "para": m["scenario"],
                             "delta": m["scenario"] - m["baseline"]} for code, m in cmp["motivos"].items()}
    return out
