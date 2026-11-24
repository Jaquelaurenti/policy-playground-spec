"""InvestigationRecord só de acréscimo (design §6.2, §10.1, §11, §12).

O estado é sempre uma projeção dos eventos: nada é editado, uma mudança de
ideia vira um evento novo. `evidenceLevel` é derivado de `mode`+`status` da
execução corrente e nunca é atribuído por quem chama.
"""
from __future__ import annotations

import re

FINDING_TRANSITIONS = {
    "suggested": {"under_investigation", "rejected"},
    "under_investigation": {"executed", "rejected"},
    "executed": {"accepted", "rejected", "under_investigation"},
    "accepted": {"under_investigation"},
    "rejected": set(),
}
DECISION_OUTCOMES = {"accept", "reject", "defer"}


class InvalidTransition(ValueError):
    pass


def evidence_level(mode: str | None, status: str | None) -> str:
    if mode == "SIMULADO" and status == "ok":
        return "simulated"
    if mode == "REAL" and status == "validated":
        return "study_validated"
    return "none"


def check_transition(current: str, target: str) -> None:
    if target not in FINDING_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"Transição inválida de '{current}' para '{target}'")


_NUM = re.compile(r"(\d{1,3}(?:[.\s]\d{3})+|\d+(?:,\d+)?)")
_STOP = {"de", "do", "da", "o", "a", "e", "para", "pra", "testar", "mudar", "alterar", "em", "r", "brl"}


def structure_intent(model, intent: str) -> dict:
    """Estrutura uma intenção em linguagem natural sem modelo: casa nomes/descrições de
    parâmetros editáveis e o último número citado. O resultado é só uma PROPOSTA:
    nada é executado sem confirmação humana (task 11)."""
    text = intent.lower()
    words = {w for w in re.findall(r"[a-zà-ú_]+", text) if w not in _STOP}
    best, score = None, 0
    for p in model.parameters.values():
        vocab = set(re.findall(r"[a-zà-ú]+", (p.name.replace("_", " ") + " " + p.description).lower())) - _STOP
        s = len(words & vocab) + (3 if p.id.lower() in text or p.name in text else 0)
        if s > score:
            best, score = p, s
    nums = [float(n.replace(".", "").replace(" ", "").replace(",", ".")) for n in _NUM.findall(intent)]
    if not best:
        return {"understood": False, "message": "Não identifiquei um parâmetro editável na intenção. Escolha o parâmetro e o valor no editor."}
    proposal = {"understood": True, "parameterId": best.id, "parameterName": best.name, "baseline": best.value,
                "unit": best.unit, "usedBy": list(best.used_by)}
    candidates = [n for n in nums if n != best.value]
    if candidates:
        proposal["proposedValue"] = candidates[-1]
    else:
        proposal["message"] = "Identifiquei o parâmetro, mas não o novo valor. Informe o valor no editor."
    return proposal


def validate_overrides(model, overrides: dict) -> dict[str, float]:
    if not overrides:
        raise ValueError("Informe ao menos um parâmetro alterado")
    out = {}
    for pid, v in overrides.items():
        p = model.parameters.get(pid)
        if not p:
            raise ValueError(f"Parâmetro inexistente: {pid}")
        if not p.domain or not p.domain.get("editable"):
            raise ValueError(f"{pid} é somente leitura no MVP")
        v = float(v)
        lo, hi = p.domain.get("min", float("-inf")), p.domain.get("max", float("inf"))
        if not lo <= v <= hi:
            raise ValueError(f"{pid}={v:g} fora do domínio [{lo:g}, {hi:g}]")
        if p.domain.get("step") and (v - lo) % p.domain["step"] != 0:
            raise ValueError(f"{pid}={v:g} precisa variar em passos de {p.domain['step']:g}")
        if v == p.value:
            raise ValueError(f"{pid}={v:g} é igual ao baseline; não há o que comparar")
        out[pid] = v
    return out


def project(events: list[dict]) -> dict:
    """Reconstrói o InvestigationRecord a partir do log de eventos."""
    rec = {"hypothesis": None, "scenarios": [], "executions": {}, "findings": {}, "decisions": [], "assessments": [],
           "suggestionJobs": [], "investigations": [], "events": len(events), "metrics": {}}
    invs: dict[str, dict] = {}
    for e in events:
        t, d = e["type"], e["data"]
        if t == "HypothesisCreated":
            rec["hypothesis"] = {**d, "submittedAt": e["at"], "state": "proposed"}
        elif t == "ScenarioConfirmed":
            rec["scenarios"].append({**d, "confirmedAt": e["at"], "confirmedBy": e["actor"]})
            rec["hypothesis"]["state"] = "confirmed"
        elif t == "ExecutionRequested":
            rec["executions"][d["executionId"]] = {**d, "jobState": "pending", "requestedAt": e["at"]}
        elif t == "ExecutionCompleted":
            ex = rec["executions"].setdefault(d["executionId"], {})
            ex.update({**d, "jobState": "done", "completedAt": e["at"],
                       "evidenceLevel": evidence_level(d.get("mode"), d.get("status"))})
            fid = ex.get("findingId")
            if fid and fid in rec["findings"]:
                f = rec["findings"][fid]
                f["executionIds"].append(d["executionId"])
                f["currentExecutionId"] = d["executionId"]
                f["investigationState"] = "executed"
                f["evidenceLevel"] = ex["evidenceLevel"]
            if not rec["metrics"].get("hypothesisToEvidenceSeconds") and ex["evidenceLevel"] != "none":
                rec["metrics"]["hypothesisToEvidenceSeconds"] = round(e["at_epoch"] - rec["hypothesis"]["submittedAtEpoch"], 2)
        elif t == "SuggestionsRequested":
            rec["suggestionJobs"].append({**d, "state": "pending", "requestedAt": e["at"]})
        elif t == "SuggestionsCompleted":
            for j in rec["suggestionJobs"]:
                if j["jobId"] == d["jobId"]:
                    j.update({"state": "done", "modelStatus": d.get("modelStatus"), "tokens": d.get("tokens", 0)})
            rec["metrics"]["modelTokens"] = rec["metrics"].get("modelTokens", 0) + d.get("tokens", 0)
        elif t == "FindingSuggested":
            agent = d.get("source") == "agent" and d.get("executionIds")
            ex_ids = list(d.get("executionIds") or []) if agent else []
            rec["findings"][d["findingId"]] = {**d, "investigationState": "suggested",
                                               # achado do agente nasce com a evidência da execução que cita (R17.11)
                                               "evidenceLevel": "simulated" if agent else "none",
                                               "executionIds": ex_ids, "currentExecutionId": ex_ids[-1] if ex_ids else None,
                                               "history": []}
            if d.get("jobId") in invs:
                invs[d["jobId"]]["findingIds"].append(d["findingId"])
        elif t == "InvestigationRequested":
            invs[d["jobId"]] = {**d, "state": "pending", "requestedAt": e["at"], "requestedBy": e["actor"],
                                "timeline": [], "executionIds": [], "findingIds": []}
        elif t == "InvestigationStarted":
            invs[d["jobId"]]["state"] = "running"
        elif t == "AgentToolCalled":
            invs[d["jobId"]]["timeline"].append({**d, "at": e["at"]})
        elif t == "AgentExecutionCompleted":
            rec["executions"][d["executionId"]] = {**d, "jobState": "done", "completedAt": e["at"],
                                                   "evidenceLevel": evidence_level(d.get("mode"), d.get("status"))}
            invs[d["jobId"]]["executionIds"].append(d["executionId"])
            if not rec["metrics"].get("hypothesisToEvidenceSeconds"):
                rec["metrics"]["hypothesisToEvidenceSeconds"] = round(e["at_epoch"] - rec["hypothesis"]["submittedAtEpoch"], 2)
        elif t == "InvestigationCompleted":
            invs[d["jobId"]].update({"state": "done", "outcome": d["status"], "steps": d.get("steps"),
                                     "tokens": d.get("tokens", 0), "recommendation": d.get("recommendation"),
                                     "reason": d.get("reason"), "completedAt": e["at"]})
            rec["metrics"]["modelTokens"] = rec["metrics"].get("modelTokens", 0) + d.get("tokens", 0)
        elif t == "FindingTransitioned":
            f = rec["findings"][d["findingId"]]
            f["history"].append({"from": f["investigationState"], "to": d["to"], "reason": d.get("reason"), "by": e["actor"], "at": e["at"]})
            f["investigationState"] = d["to"]
        elif t == "FindingAssessed":
            rec["assessments"].append({**d, "by": e["actor"], "at": e["at"]})
            if d["findingId"] in rec["findings"]:
                rec["findings"][d["findingId"]]["assessment"] = d["relevant"]
        elif t == "DecisionRecorded":
            rec["decisions"].append({**d, "decidedBy": e["actor"], "decidedAt": e["at"]})
    if rec["decisions"]:
        rec["hypothesis"]["latestDecision"] = rec["decisions"][-1]
    assessed = len(rec["assessments"])
    rec["metrics"]["relevantFindingShare"] = round(sum(a["relevant"] for a in rec["assessments"]) / assessed, 3) if assessed else None
    rec["investigations"] = list(invs.values())
    rec["findings"] = list(rec["findings"].values())
    rec["executions"] = list(rec["executions"].values())
    return rec
