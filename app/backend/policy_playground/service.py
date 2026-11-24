"""Orquestração (design §4–§5): liga o domínio às portas. Toda mudança de estado vira
evento no log (uma escrita por comando) e cópia no lago de auditoria."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from .domain import engine, generators
from .domain.record import (DECISION_OUTCOMES, InvalidTransition, check_transition, project, structure_intent,
                            validate_overrides)
from .ports import AuditSink, Dispatcher, EventStore, KeyValue, ModelPort, ModelUnavailable

from .roles import ROLES_DECIDE, ROLES_READ, ROLES_WRITE, Actor, Forbidden  # noqa: E402,F401  (reexporta)


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


@dataclass
class Config:
    suggestion_cap: int = 5               # N de §10.2
    max_suggestion_requests: int = 3      # teto de investigações de IA por hipótese (FinOps)
    model_token_budget: int = 30000       # teto de contexto (ADR-13)
    agent_max_runs: int = 3               # investigações do agente por hipótese (FinOps, R17.5)
    agent_max_steps: int = 14             # passos do loop por investigação
    agent_max_simulations: int = 6        # simulações por investigação
    agent_token_cap: int = 40000          # teto de tokens por investigação


def _now():
    t = time.time()
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds"), t


_ALLOWED_TOKENS = re.compile(r"\b[RP]\d{3}\b")


def _clip(obj, limit: int = 400):
    """Entrada de tool resumida para o evento (a trilha não precisa do texto inteiro)."""
    s = json.dumps(obj, ensure_ascii=False)
    return obj if len(s) <= limit else {"resumo": s[:limit] + "…"}


def sanitize_ai(s: dict, model, cap_refs: set) -> dict | None:
    """Sugestão de IA nunca carrega número de impacto (R5.10, R7): descarta texto com dígitos fora de ids."""
    title, text = str(s.get("title", "")).strip(), str(s.get("text", "")).strip()
    if not title or not text:
        return None
    if re.search(r"\d", _ALLOWED_TOKENS.sub("", title + " " + text)):
        return None
    refs = [r for r in s.get("ruleRefs", []) if r in model.rules]
    return {"title": title[:160], "text": text[:600], "ruleRefs": refs, "source": "ai_suggestion", "evidenceLevel": "none"}


class Playground:
    def __init__(self, model, events: EventStore, kv: KeyValue, audit: AuditSink, ai: ModelPort, dispatcher: Dispatcher,
                 config: Config | None = None):
        self.model, self.events, self.kv, self.audit, self.ai = model, events, kv, audit, ai
        self.dispatcher, self.cfg = dispatcher, config or Config()

    # ---- infraestrutura de eventos ------------------------------------------------
    def _emit(self, stream: str, type_: str, data: dict, actor: str) -> dict:
        at, epoch = _now()
        ev = self.events.append(stream, {"stream": stream, "type": type_, "data": data, "actor": actor, "at": at, "at_epoch": epoch})
        self.audit.write(ev)
        return ev

    def _record(self, hid: str) -> dict:
        evs = self.events.list(hid)
        if not evs:
            raise NotFound(f"Hipótese {hid} não encontrada")
        return project(evs)

    def idempotent(self, key: str | None, scope: str, fn):
        """Header Idempotency-Key: a mesma chave devolve a mesma resposta sem repetir o comando."""
        if not key:
            return fn()
        k = f"idem#{scope}#{key}"
        prev = self.kv.get(k)
        if prev is not None:
            return prev
        res = fn()
        self.kv.put(k, res)
        return res

    # ---- política -------------------------------------------------------------------
    def policy(self, actor: Actor) -> dict:
        actor.require(ROLES_READ, "ver a política")
        return self.model.view()

    def preview(self, actor: Actor, overrides: dict) -> dict:
        """Impacto potencial nas dependências: NÃO é resultado calculado (R5.1)."""
        actor.require(ROLES_READ, "ver dependências")
        ov = {k: float(v) for k, v in overrides.items() if k in self.model.parameters}
        return {"subDag": engine.affected_subdag(self.model, list(ov)).as_dict(), "isResult": False,
                "note": "Regras e saídas que podem mudar. Nenhum número é calculado antes da confirmação e da execução."}

    # ---- hipótese -------------------------------------------------------------------
    def create_hypothesis(self, actor: Actor, intent: str, overrides: dict | None) -> dict:
        actor.require(ROLES_WRITE, "criar hipóteses")
        intent = (intent or "").strip()
        if not intent:
            raise ValueError("Descreva a hipótese")
        proposal = structure_intent(self.model, intent)
        proposed = dict(overrides or {})
        if not proposed and proposal.get("proposedValue") is not None:
            proposed = {proposal["parameterId"]: proposal["proposedValue"]}
        sub = engine.affected_subdag(self.model, [p for p in proposed if p in self.model.parameters]).as_dict() if proposed else None
        hid = "H-" + uuid.uuid4().hex[:8]
        at, epoch = _now()
        data = {"hypothesisId": hid, "intent": intent, "structuring": proposal, "proposedOverrides": proposed,
                "policyVersion": self.model.policy_version, "datasetVersion": self.model.dataset_version,
                "potentialImpact": sub, "submittedAtEpoch": epoch}
        self._emit(hid, "HypothesisCreated", data, actor.id)
        self.events.index(hid, {"hypothesisId": hid, "intent": intent, "createdBy": actor.id, "createdAt": at})
        return self._record(hid)

    def confirm(self, actor: Actor, hid: str, overrides: dict) -> dict:
        """Confirmação humana do cenário proposto (task 11): sem ela nada executa."""
        actor.require(ROLES_WRITE, "confirmar cenários")
        rec = self._record(hid)
        ov = validate_overrides(self.model, overrides)
        sid = f"S-{len(rec['scenarios']) + 1}"
        self._emit(hid, "ScenarioConfirmed", {"scenarioId": sid, "baselineVersion": self.model.policy_version,
                                              "overrides": ov, "affectedSubDag": engine.affected_subdag(self.model, list(ov)).as_dict()}, actor.id)
        return self._record(hid)

    # ---- execução (contrato assíncrono e idempotente, §9.4) ----------------------------
    def request_execution(self, actor: Actor, hid: str, scenario_id: str | None = None, finding_id: str | None = None) -> dict:
        actor.require(ROLES_WRITE, "executar cenários")
        rec = self._record(hid)
        if not rec["scenarios"]:
            raise Conflict("Confirme um cenário antes de executar")
        sc = next((s for s in rec["scenarios"] if s["scenarioId"] == scenario_id), rec["scenarios"][-1])
        key = engine.idempotency_key(self.model, sc["overrides"])
        attempt = 1 + sum(1 for e in rec["executions"] if e.get("scenarioId") == sc["scenarioId"])
        eid = "E-" + uuid.uuid4().hex[:8]
        data = {"executionId": eid, "scenarioId": sc["scenarioId"], "overrides": sc["overrides"], "idempotencyKey": key,
                "attempt": attempt, "findingId": finding_id, "policyVersion": self.model.policy_version,
                "datasetVersion": self.model.dataset_version, "runnerVersion": engine.RUNNER_VERSION}
        self._emit(hid, "ExecutionRequested", data, actor.id)
        self.kv.put(f"exec#{eid}", {"hypothesisId": hid, "jobState": "pending", **data})
        self.dispatcher.dispatch({"kind": "execution", "hypothesisId": hid, "executionId": eid, "actor": actor.id})
        return {"executionId": eid, "jobState": "pending", "idempotencyKey": key}

    def run_execution_job(self, job: dict) -> None:
        hid, eid = job["hypothesisId"], job["executionId"]
        ex = self.kv.get(f"exec#{eid}")
        if not ex or ex["jobState"] == "done":
            return
        self.kv.put(f"exec#{eid}", {**ex, "jobState": "running"})
        cached = self.kv.get(f"result#{ex['idempotencyKey']}")
        if cached and cached.get("status") == "ok":
            result, reused = cached, True                       # reaproveita: não roda de novo
        else:
            reused = False
            try:
                out = engine.simulate(self.model, ex["overrides"])
                result = {"status": "ok", "mode": "SIMULADO", "source": "deterministic", **out}
                self.kv.put_if_absent(f"result#{ex['idempotencyKey']}", result)
            except engine.CannotCalculate as e:
                result = {"status": "cannot_calculate", "mode": "SIMULADO", "source": "deterministic", "reason": str(e)}
        summary = {k: result[k] for k in ("status", "mode", "source") if k in result}
        summary.update({"executionId": eid, "reused": reused, "comparison": result.get("comparison"), "reason": result.get("reason"),
                        "validation": {"validated": False, "method": "none",
                                       "notes": "SimulatedRunner: dados sintéticos, sem etapa de validação contra Motivo de Decisão"}})
        self.kv.put(f"exec#{eid}", {**ex, "jobState": "done", **summary, "rows": result.get("rows"), "subDag": result.get("subDag")})
        self._emit(hid, "ExecutionCompleted", summary, job.get("actor", "system"))

    def execution(self, actor: Actor, eid: str) -> dict:
        actor.require(ROLES_READ, "ver execuções")
        ex = self.kv.get(f"exec#{eid}")
        if not ex:
            raise NotFound(f"Execução {eid} não encontrada")
        if ex.get("jobState") == "done":
            from .domain.record import evidence_level
            ex["evidenceLevel"] = evidence_level(ex.get("mode"), ex.get("status"))
        return ex

    # ---- investigação assistida (limitada, §10) ----------------------------------------
    def request_suggestions(self, actor: Actor, hid: str) -> dict:
        actor.require(ROLES_WRITE, "pedir investigações")
        rec = self._record(hid)
        if not rec["scenarios"]:
            raise Conflict("Confirme um cenário antes de pedir investigações")
        if len(rec["suggestionJobs"]) >= self.cfg.max_suggestion_requests:
            raise Conflict(f"Limite de {self.cfg.max_suggestion_requests} pedidos de investigação por hipótese atingido (FinOps)")
        jid = "J-" + uuid.uuid4().hex[:8]
        self._emit(hid, "SuggestionsRequested", {"jobId": jid, "scenarioId": rec["scenarios"][-1]["scenarioId"]}, actor.id)
        self.dispatcher.dispatch({"kind": "suggestions", "hypothesisId": hid, "jobId": jid, "actor": actor.id})
        return {"jobId": jid, "state": "pending"}

    def run_suggestions_job(self, job: dict) -> None:
        hid, jid = job["hypothesisId"], job["jobId"]
        rec = self._record(hid)
        if any(j["jobId"] == jid and j["state"] == "done" for j in rec["suggestionJobs"]):
            return
        sc = rec["scenarios"][-1]
        ov = sc["overrides"]
        cands = generators.g1_shared_input(self.model, ov) + generators.g2_reachability(self.model, ov)
        tokens, model_status = 0, "ok"
        try:
            sub = engine.affected_subdag(self.model, list(ov))
            ctx_rules = sorted(set(sub.execution_set) | {r for c in cands for r in c["ruleRefs"]}, key=self.model.order.index)
            context = {"scenario": {pid: {"name": self.model.parameters[pid].name, "from": self.model.parameters[pid].value, "to": v}
                                    for pid, v in ov.items()},
                       "rules": [{"id": r, "name": self.model.rules[r].name, "logic": dict(self.model.rules[r].logic),
                                  "inputs": list(self.model.rules[r].inputs), "outputs": list(self.model.rules[r].outputs)} for r in ctx_rules]}
            raw, tokens = self.ai.suggest(json.loads(json.dumps(context)), self.cfg.suggestion_cap)
            seen = {c["title"] for c in cands}
            for s in raw:
                clean = sanitize_ai(s, self.model, set(ctx_rules))
                if clean and clean["title"] not in seen:
                    cands.append(clean)
        except ModelUnavailable as e:
            model_status = f"unavailable: {e}"
        ranked = generators.rank(cands, rec["assessments"], self.cfg.suggestion_cap)
        for c in ranked:
            self._emit(hid, "FindingSuggested", {"findingId": "F-" + uuid.uuid4().hex[:8], "jobId": jid,
                                                 "hypothesisId": hid, "scenarioId": sc["scenarioId"], **c}, "system")
        self._emit(hid, "SuggestionsCompleted", {"jobId": jid, "count": len(ranked), "modelStatus": model_status,
                                                 "model": self.ai.name, "tokens": tokens}, "system")

    def run_job(self, job: dict) -> None:
        {"execution": self.run_execution_job, "suggestions": self.run_suggestions_job,
         "investigation": self.run_investigation_job}[job["kind"]](job)

    # ---- Agente Investigador (R17, design §10.4) ----------------------------------------
    def request_investigation(self, actor: Actor, hid: str) -> dict:
        """Dispara o agente sobre o cenário confirmado. Só quem pode executar cenários (R17.10)."""
        actor.require(ROLES_WRITE, "acionar o agente")
        rec = self._record(hid)
        if not rec["scenarios"]:
            raise Conflict("Confirme um cenário antes de acionar o agente")
        running = [i for i in rec["investigations"] if i["state"] in ("pending", "running")]
        if running:
            return {"jobId": running[-1]["jobId"], "state": running[-1]["state"]}
        if len(rec["investigations"]) >= self.cfg.agent_max_runs:
            raise Conflict(f"Limite de {self.cfg.agent_max_runs} investigações do agente por hipótese atingido (FinOps)")
        sc = rec["scenarios"][-1]
        jid = "J-" + uuid.uuid4().hex[:8]
        self._emit(hid, "InvestigationRequested", {"jobId": jid, "scenarioId": sc["scenarioId"],
                                                   "overrides": sc["overrides"], "model": self.ai.name}, actor.id)
        self.dispatcher.dispatch({"kind": "investigation", "hypothesisId": hid, "jobId": jid,
                                  "actor": actor.id, "roles": sorted(actor.roles)})
        return {"jobId": jid, "state": "pending"}

    def run_investigation_job(self, job: dict) -> None:
        from .agent.loop import investigate
        from .agent.tools import ToolRegistry, _deltas

        hid, jid = job["hypothesisId"], job["jobId"]
        rec = self._record(hid)
        inv = next((i for i in rec["investigations"] if i["jobId"] == jid), None)
        if not inv or inv["state"] not in ("pending",):
            return                                        # idempotente: job repetido não roda de novo
        actor = Actor(job.get("actor", "system"), set(job.get("roles") or []))
        sc = next(s for s in rec["scenarios"] if s["scenarioId"] == inv["scenarioId"])
        reg = ToolRegistry(self.model, actor, max_simulations=self.cfg.agent_max_simulations,
                           prior_findings=[{"title": f.get("title"), "state": f.get("investigationState")}
                                           for f in rec["findings"]])
        self._emit(hid, "InvestigationStarted", {"jobId": jid}, "agent")
        sent = {"calls": 0, "execs": set(), "findings": 0}

        def flush(r: ToolRegistry):
            for c in r.calls[sent["calls"]:]:
                self._emit(hid, "AgentToolCalled", {"jobId": jid, "step": c["step"], "tool": c["tool"],
                                                    "input": _clip(c["input"]), "status": c["status"],
                                                    "error": c.get("error")}, "agent")
            sent["calls"] = len(r.calls)
            for eid, ex in r.executions.items():
                if eid in sent["execs"]:
                    continue
                self._emit(hid, "AgentExecutionCompleted", {
                    "jobId": jid, "executionId": eid, "scenarioId": sc["scenarioId"], "overrides": ex["overrides"],
                    "status": "ok", "mode": "SIMULADO", "source": "agent", "comparison": ex["comparison"],
                    "deltas": _deltas(ex["comparison"]), "runnerVersion": engine.RUNNER_VERSION}, "agent")
                self.kv.put(f"exec#{eid}", {"hypothesisId": hid, "executionId": eid, "jobState": "done", "status": "ok",
                                            "mode": "SIMULADO", "source": "agent", "jobId": jid,
                                            "overrides": ex["overrides"], "comparison": ex["comparison"],
                                            "rows": ex.get("rows")})
                sent["execs"].add(eid)
            for f in r.findings[sent["findings"]:]:
                self._emit(hid, "FindingSuggested", {**f, "jobId": jid, "hypothesisId": hid,
                                                     "scenarioId": sc["scenarioId"]}, "agent")
            sent["findings"] = len(r.findings)

        try:
            out = investigate(self.ai, reg, rec["hypothesis"]["intent"], sc["overrides"],
                              max_steps=self.cfg.agent_max_steps, token_cap=self.cfg.agent_token_cap, on_step=flush)
            flush(reg)
            self._emit(hid, "InvestigationCompleted", {"jobId": jid, "status": out["status"], "steps": out["steps"],
                                                       "tokens": out["tokens"], "recommendation": out["summary"],
                                                       "model": self.ai.name}, "agent")
        except ModelUnavailable as e:
            flush(reg)
            fallback = generators.rank(generators.g1_shared_input(self.model, sc["overrides"])
                                       + generators.g2_reachability(self.model, sc["overrides"]),
                                       rec["assessments"], self.cfg.suggestion_cap)
            for c in fallback:                            # R17.8: sem modelo, seguem os candidatos determinísticos
                self._emit(hid, "FindingSuggested", {"findingId": "F-" + uuid.uuid4().hex[:8], "jobId": jid,
                                                     "hypothesisId": hid, "scenarioId": sc["scenarioId"], **c}, "system")
            self._emit(hid, "InvestigationCompleted", {"jobId": jid, "status": "model_unavailable", "steps": 0,
                                                       "tokens": 0, "recommendation": None, "model": self.ai.name,
                                                       "reason": str(e)[:300], "fallbackCount": len(fallback)}, "system")
        except Exception as e:                            # nunca deixa a investigação presa em "running"
            flush(reg)
            self._emit(hid, "InvestigationCompleted", {"jobId": jid, "status": "error", "steps": 0, "tokens": 0,
                                                       "recommendation": None, "model": self.ai.name,
                                                       "reason": f"{type(e).__name__}: {str(e)[:250]}"}, "system")

    # ---- findings e decisões --------------------------------------------------------
    def _finding(self, hid: str, fid: str) -> dict:
        rec = self._record(hid)
        f = next((x for x in rec["findings"] if x["findingId"] == fid), None)
        if not f:
            raise NotFound(f"Finding {fid} não encontrado")
        return f

    def transition(self, actor: Actor, hid: str, fid: str, to: str, reason: str | None) -> dict:
        actor.require(ROLES_WRITE, "mudar o estado de findings")
        f = self._finding(hid, fid)
        if to == "executed":
            raise InvalidTransition("Um finding só chega a 'executed' por uma execução determinística")
        check_transition(f["investigationState"], to)
        self._emit(hid, "FindingTransitioned", {"findingId": fid, "to": to, "reason": reason}, actor.id)
        return self._record(hid)

    def execute_finding(self, actor: Actor, hid: str, fid: str) -> dict:
        """Finding → cenário investigável (R9): mesmo caminho de confirmação e execução."""
        f = self._finding(hid, fid)
        if f["investigationState"] != "under_investigation":
            raise InvalidTransition("Coloque o finding em investigação antes de executar")
        return self.request_execution(actor, hid, f.get("scenarioId"), finding_id=fid)

    def assess(self, actor: Actor, hid: str, fid: str, relevant: bool) -> dict:
        actor.require(ROLES_WRITE, "avaliar findings")
        f = self._finding(hid, fid)
        self._emit(hid, "FindingAssessed", {"findingId": fid, "relevant": bool(relevant),
                                            "kind": f.get("generator") or "ai_suggestion"}, actor.id)
        return self._record(hid)

    def decide(self, actor: Actor, hid: str, outcome: str, rationale: str, evidence_refs: list[str]) -> dict:
        actor.require(ROLES_DECIDE, "registrar decisões")
        if outcome not in DECISION_OUTCOMES:
            raise ValueError(f"Decisão deve ser uma de {sorted(DECISION_OUTCOMES)}")
        if not (rationale or "").strip():
            raise ValueError("A justificativa é obrigatória")
        rec = self._record(hid)
        prev = rec["decisions"][-1]["decisionId"] if rec["decisions"] else None
        self._emit(hid, "DecisionRecorded", {"decisionId": "D-" + uuid.uuid4().hex[:8], "outcome": outcome,
                                             "rationale": rationale.strip(), "evidenceRefs": evidence_refs or [],
                                             "supersedes": prev,
                                             "note": "Aceitar não aprova mudança em produção (R10.4)."}, actor.id)
        return self._record(hid)

    # ---- leitura --------------------------------------------------------------------
    def hypothesis(self, actor: Actor, hid: str) -> dict:
        actor.require(ROLES_READ, "ver hipóteses")
        return self._record(hid)

    def hypotheses(self, actor: Actor) -> list[dict]:
        actor.require(ROLES_READ, "listar hipóteses")
        return sorted(self.events.streams(), key=lambda s: s["createdAt"], reverse=True)

    def audit_trail(self, actor: Actor, hid: str) -> list[dict]:
        actor.require(ROLES_READ, "ver a trilha de auditoria")
        return [{k: e[k] for k in ("seq", "type", "actor", "at")} for e in self.events.list(hid)]
