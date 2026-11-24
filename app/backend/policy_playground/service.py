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
    agent_via_mcp: bool = True            # o agente chama as tools pelo protocolo MCP (R17.6)


def _now():
    t = time.time()
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds"), t


_ALLOWED_TOKENS = re.compile(r"\b[RP]\d{3}\b")


def _main_scenario(rec: dict) -> dict | None:
    """Último cenário confirmado pelo especialista que NÃO veio de um achado (R9 cria cenários derivados)."""
    main = [s for s in rec["scenarios"] if not s.get("derivedFromFinding")]
    return main[-1] if main else None


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
        sc = next((s for s in rec["scenarios"] if s["scenarioId"] == scenario_id), None) or _main_scenario(rec)
        key = engine.idempotency_key(self.model, sc["overrides"], sc.get("slice"))
        attempt = 1 + sum(1 for e in rec["executions"] if e.get("scenarioId") == sc["scenarioId"])
        eid = "E-" + uuid.uuid4().hex[:8]
        data = {"executionId": eid, "scenarioId": sc["scenarioId"], "overrides": sc["overrides"], "slice": sc.get("slice"),
                "idempotencyKey": key,
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
                out = engine.simulate(self.model, ex["overrides"], ex.get("slice"))
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
        self._emit(hid, "SuggestionsRequested", {"jobId": jid, "scenarioId": _main_scenario(rec)["scenarioId"]}, actor.id)
        self.dispatcher.dispatch({"kind": "suggestions", "hypothesisId": hid, "jobId": jid, "actor": actor.id})
        return {"jobId": jid, "state": "pending"}

    def run_suggestions_job(self, job: dict) -> None:
        hid, jid = job["hypothesisId"], job["jobId"]
        rec = self._record(hid)
        if any(j["jobId"] == jid and j["state"] == "done" for j in rec["suggestionJobs"]):
            return
        sc = next((s for s in rec["scenarios"] if s["scenarioId"] == next(
            (j["scenarioId"] for j in rec["suggestionJobs"] if j["jobId"] == jid), None)), None) or _main_scenario(rec)
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
        sc = _main_scenario(rec)
        jid = "J-" + uuid.uuid4().hex[:8]
        self._emit(hid, "InvestigationRequested", {"jobId": jid, "scenarioId": sc["scenarioId"],
                                                   "overrides": sc["overrides"], "model": self.ai.name}, actor.id)
        self.dispatcher.dispatch({"kind": "investigation", "hypothesisId": hid, "jobId": jid,
                                  "actor": actor.id, "roles": sorted(actor.roles)})
        return {"jobId": jid, "state": "pending"}

    def run_investigation_job(self, job: dict) -> None:
        from .agent.loop import investigate
        from .agent.tools import ToolRegistry
        from .domain.engine import deltas as _deltas

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
                                                    "error": c.get("error"), "via": c.get("via")}, "agent")
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
                main_ov = {k: float(v) for k, v in sc["overrides"].items()}
                variation = next((r.executions[e]["overrides"] for e in f["executionIds"] if e in r.executions
                                  and {k: float(v) for k, v in r.executions[e]["overrides"].items()} != main_ov), None)
                self._emit(hid, "FindingSuggested", {**f, "jobId": jid, "hypothesisId": hid, "scenarioId": sc["scenarioId"],
                                                     "proposedScenario": {"overrides": variation} if variation else None},
                           "agent")
            sent["findings"] = len(r.findings)

        mcp_client = None
        try:
            try:                                      # o agente usa o motor pelo protocolo MCP (R17.6)
                from .agent.mcp_client import McpToolClient
                mcp_client = McpToolClient(reg) if self.cfg.agent_via_mcp else None
            except ImportError:
                mcp_client = None                     # sem o pacote mcp: chamadas diretas ao registro
            out = investigate(self.ai, reg, rec["hypothesis"]["intent"], sc["overrides"],
                              max_steps=self.cfg.agent_max_steps, token_cap=self.cfg.agent_token_cap, on_step=flush,
                              tools=mcp_client)
            flush(reg)
            self._emit(hid, "InvestigationCompleted", {"jobId": jid, "status": out["status"], "steps": out["steps"],
                                                       "tokens": out["tokens"], "recommendation": out["summary"],
                                                       "model": self.ai.name, "transport": out["transport"],
                                                       "toolsDiscovered": out["toolsDiscovered"]}, "agent")
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
        finally:
            if mcp_client is not None:
                mcp_client.close()

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
        return self.request_execution(actor, hid, _main_scenario(self._record(hid))["scenarioId"], finding_id=fid)

    def run_finding_scenario(self, actor: Actor, hid: str, fid: str) -> dict:
        """R9: confirma o cenário próprio do achado (gate humano: este clique) e o simula pelo mesmo caminho."""
        actor.require(ROLES_WRITE, "simular o cenário de um achado")
        f = self._finding(hid, fid)
        ps = f.get("proposedScenario")
        if not ps:
            raise Conflict("Este achado não tem cenário próprio: use 'Vincular evidência' com o cenário confirmado")
        if f["investigationState"] == "suggested":
            self._emit(hid, "FindingTransitioned", {"findingId": fid, "to": "under_investigation",
                                                    "reason": "Cenário do achado confirmado"}, actor.id)
        elif f["investigationState"] not in ("under_investigation", "executed", "accepted"):
            raise InvalidTransition("Reabra o achado antes de simular o cenário dele")
        elif f["investigationState"] in ("executed", "accepted"):
            self._emit(hid, "FindingTransitioned", {"findingId": fid, "to": "under_investigation",
                                                    "reason": "Nova simulação do cenário do achado"}, actor.id)
        ov = validate_overrides(self.model, ps["overrides"]) if not ps.get("slice") else \
            {k: float(v) for k, v in ps["overrides"].items() if k in self.model.parameters}
        rec = self._record(hid)
        existing = next((s for s in rec["scenarios"] if s.get("derivedFromFinding") == fid), None)
        if existing:
            sid = existing["scenarioId"]
        else:
            sid = f"S-{len(rec['scenarios']) + 1}"
            self._emit(hid, "ScenarioConfirmed", {"scenarioId": sid, "baselineVersion": self.model.policy_version,
                                                  "overrides": ov, "slice": ps.get("slice"), "derivedFromFinding": fid,
                                                  "affectedSubDag": engine.affected_subdag(self.model, list(ov)).as_dict()},
                       actor.id)
        return self.request_execution(actor, hid, sid, finding_id=fid)

    def assess(self, actor: Actor, hid: str, fid: str, relevant: bool) -> dict:
        actor.require(ROLES_WRITE, "avaliar findings")
        f = self._finding(hid, fid)
        self._emit(hid, "FindingAssessed", {"findingId": fid, "relevant": bool(relevant),
                                            "kind": f.get("generator") or "ai_suggestion"}, actor.id)
        return self._record(hid)

    def decide(self, actor: Actor, hid: str, outcome: str, rationale: str, evidence_refs: list[str],
               scenario_id: str | None = None) -> dict:
        actor.require(ROLES_DECIDE, "registrar decisões")
        if outcome not in DECISION_OUTCOMES:
            raise ValueError(f"Decisão deve ser uma de {sorted(DECISION_OUTCOMES)}")
        if not (rationale or "").strip():
            raise ValueError("A justificativa é obrigatória")
        rec = self._record(hid)
        main = _main_scenario(rec)
        scenario_id = scenario_id or (main["scenarioId"] if main else None)
        prev = rec["decisions"][-1]["decisionId"] if rec["decisions"] else None
        self._emit(hid, "DecisionRecorded", {"decisionId": "D-" + uuid.uuid4().hex[:8], "outcome": outcome,
                                             "rationale": rationale.strip(), "evidenceRefs": evidence_refs or [],
                                             "scenarioId": scenario_id,
                                             "supersedes": prev,
                                             "note": "Aceitar não aprova mudança em produção (R10.4)."}, actor.id)
        return self._record(hid)

    # ---- pacote de mudança para engenharia (R10.2, R11, R12 na forma do MVP) ------------
    def generate_change_package(self, actor: Actor, hid: str) -> dict:
        """Só depois de uma decisão de aceite; determinístico e idempotente por decisão (R10.3)."""
        from .domain import change_package as cp

        actor.require(ROLES_WRITE, "gerar o pacote de mudança")
        rec = self._record(hid)
        if not rec["decisions"] or rec["decisions"][-1]["outcome"] != "accept":
            raise Conflict("O pacote só é gerado depois de uma decisão de aceite (a última decisão precisa ser 'aceitar')")
        decision = rec["decisions"][-1]
        done = next((p for p in rec["changePackages"] if p["decisionId"] == decision["decisionId"]), None)
        if done:
            return self.change_package(actor, hid, done["packageId"])
        sc = next((s for s in rec["scenarios"] if s["scenarioId"] == decision.get("scenarioId")), None) or _main_scenario(rec)
        if sc.get("slice"):
            raise Conflict("Um recorte de população não é uma mudança de política: decida sobre um cenário de parâmetro")
        execs = [e for e in rec["executions"] if e.get("jobState") == "done" and e.get("status") == "ok"
                 and not e.get("slice")                   # evidência do pacote cobre todas as propostas
                 and {k: float(v) for k, v in (e.get("overrides") or {}).items()} == {k: float(v) for k, v in sc["overrides"].items()}]
        if not execs:
            raise Conflict("Simule o cenário confirmado antes de gerar o pacote: falta uma execução com evidência")
        ev = execs[-1]
        full = self.kv.get(f"exec#{ev['executionId']}") or {}
        if not full.get("rows"):
            raise Conflict(f"A execução {ev['executionId']} não tem as linhas guardadas para derivar os testes")
        patch = cp.build_patch(self.model, sc["overrides"])
        tests = cp.build_tests(self.model, full["rows"])
        verification = cp.verify(self.model, patch, tests)
        comparison = full.get("comparison") or ev.get("comparison")
        manifest = {
            "packageVersion": cp.PACKAGE_VERSION, "hypothesisId": hid, "intent": rec["hypothesis"]["intent"],
            "scenario": {"scenarioId": sc["scenarioId"], "overrides": sc["overrides"],
                         "confirmedBy": sc.get("confirmedBy"), "confirmedAt": sc.get("confirmedAt")},
            "evidence": {"executionId": ev["executionId"], "mode": "SIMULADO", "source": ev.get("source", "deterministic"),
                         "deltas": engine.deltas(comparison)},
            "findingsAccepted": [{"findingId": f["findingId"], "title": f.get("title"), "source": f.get("source"),
                                  "evidenceLevel": f.get("evidenceLevel")}
                                 for f in rec["findings"] if f.get("investigationState") == "accepted"],
            "decision": {k: decision.get(k) for k in ("decisionId", "outcome", "rationale", "decidedBy", "decidedAt", "evidenceRefs")},
            "versions": {"policy": self.model.policy_version, "dataset": self.model.dataset_version,
                         "runner": engine.RUNNER_VERSION, "patchedPolicy": verification["patchedPolicyVersion"]},
        }
        body = {"manifest": manifest, "patch": patch, "tests": tests, "verification": verification}
        body["pullRequest"] = cp.pr_preview(self.model, manifest, patch, tests, verification)
        body["testFile"] = {"path": f"app/backend/tests/generated/test_change_{hid}.py",
                            "content": cp.pytest_source(self.model, hid, patch, tests)}
        pid = cp.package_id(body)
        at, _ = _now()
        package = {"packageId": pid, "status": "nao_submetido", "generatedAt": at, "generatedBy": actor.id, **body}
        self.kv.put(f"change#{hid}#{pid}", package)
        self._emit(hid, "ChangePackageGenerated", {
            "packageId": pid, "decisionId": decision["decisionId"], "scenarioId": sc["scenarioId"],
            "executionId": ev["executionId"], "testsPassed": verification["passed"], "testsTotal": verification["total"],
            "changes": [op["_meta"] for op in patch if op["op"] == "replace"], "status": "nao_submetido"}, actor.id)
        return package

    def change_package(self, actor: Actor, hid: str, pid: str) -> dict:
        actor.require(ROLES_READ, "ver o pacote de mudança")
        pkg = self.kv.get(f"change#{hid}#{pid}")
        if not pkg:
            raise NotFound(f"Pacote {pid} não encontrado")
        return pkg

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
