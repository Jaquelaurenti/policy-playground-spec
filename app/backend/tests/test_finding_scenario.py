"""R9: achado vira cenário próprio (variação do agente ou recorte do G2) e segue o mesmo caminho."""
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from policy_playground.adapters.memory import (MemoryAudit, MemoryEventStore, MemoryKV, NoModel, ScriptedModel,
                                               ThreadDispatcher)
from policy_playground.api.app import create_app
from policy_playground.domain import engine, generators
from policy_playground.domain.model import load_from_folder
from policy_playground.service import Playground

FIX = Path(__file__).resolve().parents[3] / ".kiro" / "specs" / "policy-playground" / "fixtures"
MODEL = load_from_folder(FIX)
SPECIALIST = {"X-Demo-User": "ana", "X-Demo-Roles": "Policy Specialist"}
VIEWER = {"X-Demo-User": "bia", "X-Demo-Roles": "Viewer"}


def make(ai):
    pg = Playground(MODEL, MemoryEventStore(), MemoryKV(), MemoryAudit(), ai, None)
    pg.dispatcher = ThreadDispatcher(pg.run_job, synchronous=True)
    return pg, TestClient(create_app(pg))


def agent_steps():
    """Agente simula 3000 e a variação 3500 e registra um achado sobre a variação."""
    def ids(m):
        out = []
        for msg in m:
            for c in msg["content"]:
                j = c.get("toolResult", {}).get("content", [{}])[0].get("json", {})
                if "executionId" in j and j["executionId"] not in out:
                    out.append(j["executionId"])
        return out
    return [
        lambda m: ("PLANO: simular 3000 e 3500", [("run_scenario", {"overrides": {"P001": 3000}}),
                                                  ("run_scenario", {"overrides": {"P001": 3500}})]),
        lambda m: ("", [("register_finding", {"title": "Com 3500 mais 2 propostas são reprovadas",
                                              "text": "Indo para 3500, S05 e S12 também passam a reprovadas.",
                                              "ruleRefs": ["R005"], "executionIds": [ids(m)[1], ids(m)[0]]})]),
        lambda m: ("", [("submit_recommendation", {"text": "Comparar 3000 e 3500 antes de decidir."})]),
    ]


class FindingScenarioTest(unittest.TestCase):
    def setUp(self):
        self.pg, self.c = make(ScriptedModel(agent_steps()))
        h = self.c.post("/api/hypotheses", json={"intent": "aumentar a renda mínima para 3000"}, headers=SPECIALIST).json()
        self.hid = h["hypothesis"]["hypothesisId"]
        self.c.post(f"/api/hypotheses/{self.hid}/scenarios", json={"overrides": {"P001": 3000}}, headers=SPECIALIST)
        self.c.post(f"/api/hypotheses/{self.hid}/executions", json={}, headers=SPECIALIST)

    def rec(self):
        return self.c.get(f"/api/hypotheses/{self.hid}", headers=SPECIALIST).json()

    def run_fs(self, fid, h=SPECIALIST):
        return self.c.post(f"/api/hypotheses/{self.hid}/findings/{fid}/scenario-executions", headers=h)

    def test_recorte_do_g2_prova_quem_perde_a_faixa(self):
        self.c.post(f"/api/hypotheses/{self.hid}/suggestions", headers=SPECIALIST)
        g2 = next(f for f in self.rec()["findings"] if f.get("generator") == "G2")
        self.assertEqual(g2["proposedScenario"]["slice"]["label"], "renda_mensal ∈ [2500, 3000)")
        r = self.run_fs(g2["findingId"])
        self.assertEqual(r.status_code, 200, r.text)
        ex = self.c.get(f"/api/executions/{r.json()['executionId']}", headers=SPECIALIST).json()
        self.assertEqual(ex["slice"]["variable"], "renda_mensal")
        changed = ex["comparison"]["outputs"]["resultado"]["changedRecords"]
        self.assertEqual(changed, ["S02", "S03", "S04"])
        self.assertEqual(ex["comparison"]["outputs"]["resultado"]["scenario"].get("APROVACAO_SIMULADA", 0), 0)
        f = next(x for x in self.rec()["findings"] if x["findingId"] == g2["findingId"])
        self.assertEqual((f["investigationState"], f["evidenceLevel"]), ("executed", "simulated"))

    def test_variacao_do_agente_vira_cenario_proprio(self):
        self.c.post(f"/api/hypotheses/{self.hid}/investigations", headers=SPECIALIST)
        af = next(f for f in self.rec()["findings"] if f.get("source") == "agent")
        self.assertEqual(af["proposedScenario"], {"overrides": {"P001": 3500.0}})
        r = self.run_fs(af["findingId"])
        self.assertEqual(r.status_code, 200, r.text)
        rec = self.rec()
        derived = next(s for s in rec["scenarios"] if s.get("derivedFromFinding") == af["findingId"])
        self.assertEqual(derived["overrides"], {"P001": 3500.0})
        ex = self.c.get(f"/api/executions/{r.json()['executionId']}", headers=SPECIALIST).json()
        self.assertEqual(ex["comparison"]["outputs"]["resultado"]["scenario"]["REPROVACAO_SIMULADA"], 9)
        # o cenário principal continua sendo o 3000: nova simulação principal e o agente usam ele
        r2 = self.c.post(f"/api/hypotheses/{self.hid}/executions", json={}, headers=SPECIALIST).json()
        main_ex = self.c.get(f"/api/executions/{r2['executionId']}", headers=SPECIALIST).json()
        self.assertEqual(main_ex["overrides"], {"P001": 3000.0})

    def test_sugestao_sem_cenario_so_vincula_evidencia(self):
        self.c.post(f"/api/hypotheses/{self.hid}/suggestions", headers=SPECIALIST)
        g1 = next(f for f in self.rec()["findings"] if f.get("generator") == "G1")
        self.assertIsNone(g1.get("proposedScenario"))
        self.assertEqual(self.run_fs(g1["findingId"]).status_code, 409)

    def test_viewer_nao_simula_cenario_de_achado(self):
        self.c.post(f"/api/hypotheses/{self.hid}/suggestions", headers=SPECIALIST)
        g2 = next(f for f in self.rec()["findings"] if f.get("generator") == "G2")
        self.assertEqual(self.run_fs(g2["findingId"], VIEWER).status_code, 403)

    def test_pacote_usa_o_cenario_da_decisao_nao_o_derivado(self):
        self.c.post(f"/api/hypotheses/{self.hid}/suggestions", headers=SPECIALIST)
        g2 = next(f for f in self.rec()["findings"] if f.get("generator") == "G2")
        self.run_fs(g2["findingId"])                       # cria cenário derivado (recorte) depois do principal
        self.c.post(f"/api/hypotheses/{self.hid}/decisions",
                    json={"outcome": "accept", "rationale": "ok", "evidenceRefs": []}, headers=SPECIALIST)
        p = self.c.post(f"/api/hypotheses/{self.hid}/change-package", headers=SPECIALIST).json()
        self.assertEqual(p["manifest"]["scenario"]["scenarioId"], "S-1")
        self.assertEqual(p["verification"]["total"], 12)    # todas as propostas, não só o recorte

    def test_chave_de_idempotencia_distingue_recorte(self):
        sl = generators.g2_reachability(MODEL, {"P001": 3000})[0]["proposedScenario"]["slice"]
        self.assertNotEqual(engine.idempotency_key(MODEL, {"P001": 3000}),
                            engine.idempotency_key(MODEL, {"P001": 3000}, sl))


if __name__ == "__main__":
    unittest.main()
