"""Registro único das tools do Agente Investigador (R17, design §10.4).

Cada tool embrulha uma função determinística que já existe em `domain/`. O agente nunca calcula
impacto: ele só pede execuções e cita números que vieram delas (R17.4). O mesmo registro gera o
`toolSpec` da Converse e as tools do servidor MCP (R17.6). O agente age com as permissões de quem
o acionou (R17.10).
"""
from __future__ import annotations

import json
import re
import uuid

from ..domain import engine, generators
from ..domain.engine import CannotCalculate
from ..domain.engine import deltas as _deltas
from ..roles import ROLES_READ, ROLES_WRITE, Actor, Forbidden

_IDS = re.compile(r"\b(?:[RPEF]-?[0-9a-f]{3,8}|[RP]\d{3})\b")   # ids de regra/parâmetro/execução/achado
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


class ToolError(Exception):
    """Erro devolvido ao agente como toolResult status=error (ele pode se corrigir)."""


def _obj(props: dict, required: list[str]) -> dict:
    return {"json": {"type": "object", "properties": props, "required": required}}


_OVERRIDES = {"type": "object", "description": "Mapa id_do_parâmetro → novo valor, ex. {\"P001\": 3000}",
              "additionalProperties": {"type": "number"}}

TOOL_SPECS = [
    {"name": "get_policy",
     "description": "Lê parâmetros editáveis, regras (entradas, saídas, dependências), DAG e saídas da política sintética.",
     "inputSchema": _obj({"rule_ids": {"type": "array", "items": {"type": "string"},
                                       "description": "Opcional: restringe às regras citadas"}}, [])},
    {"name": "preview_subdag",
     "description": "O que pode mudar com uma mudança de parâmetros (sub-DAG afetado). Não executa e não traz números.",
     "inputSchema": _obj({"overrides": _OVERRIDES}, ["overrides"])},
    {"name": "trace_output",
     "description": "Dependências reversas: quais regras decidem uma saída (ex. 'resultado').",
     "inputSchema": _obj({"output_var": {"type": "string"}}, ["output_var"])},
    {"name": "run_scenario",
     "description": "Executa baseline vs. cenário no dataset SINTÉTICO (SimulatedRunner, selo SIMULADO). Única fonte de "
                    "números. Retorna executionId e um resumo; use compare para o detalhe.",
     "inputSchema": _obj({"overrides": _OVERRIDES}, ["overrides"])},
    {"name": "compare",
     "description": "Detalhe de uma execução contra o baseline, ou de duas execuções entre si (sensibilidade).",
     "inputSchema": _obj({"execution_id": {"type": "string"},
                          "against_execution_id": {"type": "string",
                                                   "description": "Opcional: compara cenário x cenário"}},
                         ["execution_id"])},
    {"name": "get_candidates",
     "description": "Candidatos dos geradores determinísticos: G1 (regras que leem o mesmo insumo) e "
                    "G2 (ramos que ficam inalcançáveis ou passam a ser alcançáveis).",
     "inputSchema": _obj({"overrides": _OVERRIDES,
                          "generators": {"type": "array", "items": {"type": "string", "enum": ["G1", "G2"]},
                                         "description": "Opcional: padrão G1 e G2"}}, ["overrides"])},
    {"name": "read_audit",
     "description": "Trilha desta investigação e achados anteriores da hipótese, para não repetir trabalho.",
     "inputSchema": _obj({}, [])},
    {"name": "submit_recommendation",
     "description": "Encerra a investigação com a recomendação ao especialista (texto curto em português). "
                    "Só números de execuções, valores de baseline ou candidatos. Chame por último.",
     "inputSchema": _obj({"text": {"type": "string"}}, ["text"])},
    {"name": "register_finding",
     "description": "Registra um achado para revisão humana. Todo número do texto precisa estar no resultado de uma "
                    "das execuções citadas; caso contrário a tool recusa.",
     "inputSchema": _obj({"title": {"type": "string"}, "text": {"type": "string"},
                          "ruleRefs": {"type": "array", "items": {"type": "string"}},
                          "executionIds": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
                         ["title", "text", "ruleRefs", "executionIds"])},
]

_WRITE_TOOLS = {"run_scenario", "register_finding"}


class ToolRegistry:
    def __init__(self, model, actor: Actor, max_simulations: int = 6, prior_findings=None):
        self.model = model
        self.actor = actor
        self.max_simulations = max_simulations
        self.executions: dict[str, dict] = {}
        self.findings: list[dict] = []
        self.prior_findings = list(prior_findings or [])
        self.calls: list[dict] = []          # no sprint: evento AgentToolCalled no event store
        self.recommendation: str | None = None
        self.facts: list[dict] = []          # fatos estruturais devolvidos pelos geradores nesta investigação

    # ---- despacho + permissões + auditoria ------------------------------------------
    def call(self, name: str, args: dict) -> dict:
        fn = getattr(self, "t_" + name, None)
        entry = {"step": len(self.calls) + 1, "tool": name, "input": args}
        try:
            if fn is None or name not in {t["name"] for t in TOOL_SPECS}:
                raise ToolError(f"tool desconhecida: {name}")
            try:
                self.actor.require(ROLES_WRITE if name in _WRITE_TOOLS else ROLES_READ, f"usar {name}")
            except Forbidden as e:
                raise ToolError(f"sem permissão: {e}") from e
            out = fn(**(args or {}))
            entry["status"] = "success"
            return out
        except ToolError as e:
            entry["status"], entry["error"] = "error", str(e)
            raise
        except CannotCalculate as e:         # cannot_calculate vira erro recuperável: o agente tenta outra via
            entry["status"], entry["error"] = "error", f"cannot_calculate: {e}"
            raise ToolError(entry["error"]) from e
        except TypeError as e:               # argumentos fora do schema
            entry["status"], entry["error"] = "error", f"argumentos inválidos: {e}"
            raise ToolError(entry["error"]) from e
        finally:
            self.calls.append(entry)

    def base_evidence(self) -> list:
        """Números legítimos fora das execuções: valores de baseline dos parâmetros e fatos estruturais
        que os geradores determinísticos devolveram nesta investigação (não são estimativas de impacto)."""
        return [{"baseline": {pid: p.value for pid, p in self.model.parameters.items()}}, {"facts": self.facts}]

    def note(self, text: str) -> None:
        """Texto do agente entre chamadas (plano, raciocínio) entra na trilha (R17.7)."""
        if text.strip():
            self.calls.append({"step": len(self.calls) + 1, "tool": "_plan", "input": {"text": text.strip()[:600]},
                               "status": "note"})

    def _overrides(self, overrides) -> dict[str, float]:
        if not isinstance(overrides, dict) or not overrides:
            raise ToolError("overrides precisa ser um objeto não vazio {id: valor}")
        out = {}
        for pid, v in overrides.items():
            if pid not in self.model.parameters:
                raise ToolError(f"parâmetro inexistente: {pid}; válidos: {sorted(self.model.parameters)}")
            try:
                out[pid] = float(v)
            except (TypeError, ValueError):
                raise ToolError(f"valor não numérico para {pid}: {v!r}")
        return out

    def _execution(self, eid) -> dict:
        ex = self.executions.get(eid)
        if not ex:
            raise ToolError(f"executionId desconhecido: {eid}. Rode run_scenario antes.")
        return ex

    # ---- tools -----------------------------------------------------------------------
    def t_get_policy(self, rule_ids=None):
        m = self.model
        ids = [r for r in (rule_ids or m.order) if r in m.rules]
        return {"parameters": {pid: {"name": p.name, "value": p.value, "usedBy": list(p.used_by)}
                               for pid, p in m.parameters.items()},
                "rules": [{"id": r, "name": m.rules[r].name, "inputs": list(m.rules[r].inputs),
                           "outputs": list(m.rules[r].outputs), "dependsOn": list(m.rules[r].depends_on)} for r in ids],
                "executionOrder": [r for r in m.order if r in ids],
                "outputVars": list(m.output_vars), "records": len(m.dataset["records"]), "mode": "SIMULADO"}

    def t_preview_subdag(self, overrides):
        sub = engine.affected_subdag(self.model, list(self._overrides(overrides))).as_dict()
        return {"subDag": sub, "isResult": False}

    def t_trace_output(self, output_var):
        if output_var not in self.model.output_vars:
            raise ToolError(f"saída inexistente: {output_var}; válidas: {list(self.model.output_vars)}")
        return {"outputVar": output_var, "rules": engine.required_for_output(self.model, output_var)}

    def t_run_scenario(self, overrides):
        if len(self.executions) >= self.max_simulations:
            raise ToolError(f"orçamento de {self.max_simulations} simulações por investigação atingido (FinOps); "
                            "registre os achados com o que já tem")
        ov = self._overrides(overrides)
        res = engine.simulate(self.model, ov)
        eid = "E-" + uuid.uuid4().hex[:8]
        self.executions[eid] = {"executionId": eid, "mode": "SIMULADO", "overrides": ov,
                                "comparison": res["comparison"], "rows": res["rows"]}
        res_cmp = res["comparison"]["outputs"]
        return {"executionId": eid, "mode": "SIMULADO", "overrides": ov, "records": res["comparison"]["records"],
                "changedRecords": {o: len(v["changedRecords"]) for o, v in res_cmp.items()},
                "deltas": _deltas(res["comparison"]),
                "hint": "cite variações pelo campo deltas (de, para, delta); use compare para o detalhe"}

    def t_compare(self, execution_id, against_execution_id=None):
        a = self._execution(execution_id)
        if not against_execution_id:
            return {"executionId": execution_id, "mode": "SIMULADO", "vs": "baseline",
                    "deltas": _deltas(a["comparison"]), "comparison": a["comparison"]}
        b = self._execution(against_execution_id)
        diff = {}
        for o in self.model.output_vars:
            sa = {r["recordId"]: r["scenario"][o] for r in a["rows"]}
            sb = {r["recordId"]: r["scenario"][o] for r in b["rows"]}
            diff[o] = sorted(k for k in sa if sa[k] != sb.get(k))
        return {"executionId": execution_id, "againstExecutionId": against_execution_id, "mode": "SIMULADO",
                "overrides": {"a": a["overrides"], "b": b["overrides"]},
                "recordsThatDiffer": diff,
                "motivos": {code: {"name": m["name"], "a": m["scenario"],
                                   "b": b["comparison"]["motivos"][code]["scenario"],
                                   "delta_a_menos_b": m["scenario"] - b["comparison"]["motivos"][code]["scenario"]}
                            for code, m in a["comparison"]["motivos"].items()},
                "recordsThatDifferCount": {o: len(v) for o, v in diff.items()}}

    def t_get_candidates(self, overrides, **kw):
        gens = kw.pop("generators", None) or ["G1", "G2"]   # "generators" sombrearia o módulo
        if kw:
            raise ToolError(f"argumentos inválidos: {sorted(kw)}")
        ov = self._overrides(overrides)
        cands = []
        if "G1" in gens:
            cands += generators.g1_shared_input(self.model, ov)
        if "G2" in gens:
            cands += generators.g2_reachability(self.model, ov)
        out = [{"generator": c["generator"], "title": c["title"], "text": c.get("text", ""), "ruleRefs": c["ruleRefs"]}
               for c in cands]
        self.facts.extend({"title": c["title"], "text": c["text"]} for c in out)
        return {"candidates": out}

    def t_read_audit(self):
        return {"calls": [{k: c[k] for k in ("step", "tool", "status")} for c in self.calls],
                "executions": [{"executionId": e, "overrides": x["overrides"]} for e, x in self.executions.items()],
                "findingsThisInvestigation": [{"title": f["title"], "executionIds": f["executionIds"]}
                                              for f in self.findings],
                "priorFindings": [{"title": f.get("title"), "state": f.get("state")} for f in self.prior_findings]}

    def t_submit_recommendation(self, text):
        text = (text or "").strip()
        if not text:
            raise ToolError("recomendação vazia")
        ev = [_evidence(x) for x in self.executions.values()] + self.base_evidence()
        unbound = unbound_numbers(text, ev)
        if unbound:
            raise ToolError(f"números sem evidência na recomendação: {unbound}. Reescreva sem eles.")
        self.recommendation = text[:600]
        return {"status": "recebida", "next": "encerre a investigação"}

    def t_register_finding(self, title, text, ruleRefs, executionIds):
        if isinstance(executionIds, str):
            executionIds = [executionIds]
        if not executionIds:
            raise ToolError("cite ao menos um executionId")
        exs = [self._execution(e) for e in executionIds]
        bad_refs = [r for r in ruleRefs if r not in self.model.rules and r not in self.model.parameters]
        if bad_refs:
            raise ToolError(f"ruleRefs inexistentes: {bad_refs}")
        unbound = unbound_numbers(f"{title} {text}", [_evidence(x) for x in exs] + self.base_evidence())
        if unbound:
            raise ToolError(f"números sem evidência nas execuções {executionIds}: {unbound}. "
                            "Cite só números das execuções citadas, dos valores de baseline ou dos candidatos G1/G2; "
                            "se não tiver a fonte, reescreva sem o número.")
        if any(f["title"] == title for f in self.findings):
            raise ToolError("achado repetido; registre algo novo ou conclua")
        f = {"findingId": "F-" + uuid.uuid4().hex[:8], "title": title[:160], "text": text[:800],
             "ruleRefs": ruleRefs, "executionIds": executionIds, "source": "agent",
             "evidenceLevel": "simulated", "state": "suggested", "createdBy": self.actor.id}
        self.findings.append(f)
        return {"findingId": f["findingId"], "state": "suggested", "awaits": "revisão humana"}


def _evidence(ex: dict) -> dict:
    return {"overrides": ex["overrides"], "comparison": ex["comparison"], "deltas": _deltas(ex["comparison"])}


def _norm(n: str) -> str:
    v = float(n.replace(",", "."))
    return str(int(v)) if v.is_integer() else str(v)


def numbers_in(obj) -> set[str]:
    s = _IDS.sub("", json.dumps(obj, ensure_ascii=False))
    return {_norm(n) for n in _NUM.findall(s)}


def unbound_numbers(text: str, evidence: list) -> list[str]:
    allowed = set().union(*(numbers_in(e) for e in evidence)) if evidence else set()
    return sorted({_norm(n) for n in _NUM.findall(_IDS.sub("", text))} - allowed)
