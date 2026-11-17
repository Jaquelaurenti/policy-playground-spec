"""Task 20: fluxo ponta a ponta do exemplo R005/P001 em modo SIMULADO, pela API."""
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from policy_playground.adapters.memory import FakeModel, MemoryAudit, MemoryEventStore, MemoryKV, NoModel, ThreadDispatcher
from policy_playground.api.app import create_app
from policy_playground.domain.model import load_from_folder
from policy_playground.service import Playground

FIX = Path(__file__).resolve().parents[3] / ".kiro" / "specs" / "policy-playground" / "fixtures"
SPECIALIST = {"X-Demo-User": "ana", "X-Demo-Roles": "Policy Specialist"}
VIEWER = {"X-Demo-User": "bia", "X-Demo-Roles": "Viewer"}


def make(ai=None):
    pg = Playground(load_from_folder(FIX), MemoryEventStore(), MemoryKV(), MemoryAudit(), ai or FakeModel(), None)
    pg.dispatcher = ThreadDispatcher(pg.run_job, synchronous=True)
    return pg, TestClient(create_app(pg))


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.pg, self.c = make()

    def post(self, url, json=None, h=SPECIALIST, key=None):
        headers = dict(h)
        if key:
            headers["Idempotency-Key"] = key
        return self.c.post(url, json=json if json is not None else {}, headers=headers)

    def test_worked_example_end_to_end(self):
        pol = self.c.get("/api/policy", headers=SPECIALIST).json()
        self.assertTrue(pol["validation"]["ok"])
        prev = self.post("/api/preview", {"overrides": {"P001": 3000}}).json()
        self.assertFalse(prev["isResult"])
        self.assertEqual(prev["subDag"]["executionSet"], ["R001", "R005", "R009"])

        h = self.post("/api/hypotheses", {"intent": "Testar renda mínima de R$ 2.500 para R$ 3.000"}, key="k1").json()
        hid = h["hypothesis"]["hypothesisId"]
        self.assertEqual(h["hypothesis"]["proposedOverrides"], {"P001": 3000.0})
        # nada executa sem confirmação
        self.assertEqual(self.post(f"/api/hypotheses/{hid}/executions").status_code, 409)

        self.post(f"/api/hypotheses/{hid}/scenarios", {"overrides": {"P001": 3000}}, key="c1")
        ex = self.post(f"/api/hypotheses/{hid}/executions", key="e1").json()
        res = self.c.get(f"/api/executions/{ex['executionId']}", headers=SPECIALIST).json()
        self.assertEqual(res["jobState"], "done")
        self.assertEqual(res["mode"], "SIMULADO")
        self.assertEqual(res["evidenceLevel"], "simulated")
        self.assertEqual(res["comparison"]["outputs"]["resultado"]["changedRecords"], ["S02", "S03", "S04"])

        sj = self.post(f"/api/hypotheses/{hid}/suggestions", key="s1").json()
        rec = self.c.get(f"/api/hypotheses/{hid}", headers=SPECIALIST).json()
        kinds = [f.get("generator") or f["source"] for f in rec["findings"]]
        self.assertEqual(kinds[:2], ["G1", "G2"])           # determinísticos primeiro no ranking
        self.assertIn("ai_suggestion", kinds)
        self.assertTrue(all(f["evidenceLevel"] == "none" for f in rec["findings"]))
        self.assertEqual(rec["suggestionJobs"][0]["jobId"], sj["jobId"])

        g2 = next(f for f in rec["findings"] if f.get("generator") == "G2")
        fid = g2["findingId"]
        self.assertEqual(self.post(f"/api/hypotheses/{hid}/findings/{fid}/transitions", {"to": "accepted"}).status_code, 409)
        self.post(f"/api/hypotheses/{hid}/findings/{fid}/transitions", {"to": "under_investigation"})
        self.post(f"/api/hypotheses/{hid}/findings/{fid}/executions")
        rec = self.c.get(f"/api/hypotheses/{hid}", headers=SPECIALIST).json()
        f = next(x for x in rec["findings"] if x["findingId"] == fid)
        self.assertEqual((f["investigationState"], f["evidenceLevel"]), ("executed", "simulated"))
        self.assertTrue(rec["executions"][-1]["reused"])     # mesma chave de idempotência: não recalcula

        self.post(f"/api/hypotheses/{hid}/findings/{fid}/assessments", {"relevant": True})
        self.post(f"/api/hypotheses/{hid}/findings/{fid}/transitions", {"to": "accepted", "reason": "faz sentido"})
        self.assertEqual(self.post(f"/api/hypotheses/{hid}/decisions", {"outcome": "accept", "rationale": ""}).status_code, 422)
        self.post(f"/api/hypotheses/{hid}/decisions", {"outcome": "defer", "rationale": "Esperar estudo real", "evidenceRefs": [ex["executionId"]]})
        rec = self.post(f"/api/hypotheses/{hid}/decisions", {"outcome": "accept", "rationale": "Corte 3.000 é promissor"}).json()
        self.assertEqual(rec["decisions"][1]["supersedes"], rec["decisions"][0]["decisionId"])
        self.assertEqual(rec["hypothesis"]["latestDecision"]["outcome"], "accept")
        self.assertEqual(rec["metrics"]["relevantFindingShare"], 1.0)
        self.assertIsNotNone(rec["metrics"]["hypothesisToEvidenceSeconds"])

        trail = self.c.get(f"/api/hypotheses/{hid}/audit", headers=SPECIALIST).json()
        self.assertEqual([e["seq"] for e in trail], list(range(1, len(trail) + 1)))
        self.assertEqual(len(self.pg.audit.events), len(trail))   # lago de auditoria recebeu cada evento

    def test_idempotency_key_replays(self):
        a = self.post("/api/hypotheses", {"intent": "renda mínima 3000"}, key="same").json()
        b = self.post("/api/hypotheses", {"intent": "renda mínima 3000"}, key="same").json()
        self.assertEqual(a["hypothesis"]["hypothesisId"], b["hypothesis"]["hypothesisId"])
        self.assertEqual(len(self.c.get("/api/hypotheses", headers=SPECIALIST).json()), 1)

    def test_viewer_cannot_write(self):
        self.assertEqual(self.c.get("/api/policy", headers=VIEWER).status_code, 200)
        self.assertEqual(self.post("/api/hypotheses", {"intent": "x 3000"}, h=VIEWER).status_code, 403)

    def test_domain_violation(self):
        hid = self.post("/api/hypotheses", {"intent": "renda mínima"}).json()["hypothesis"]["hypothesisId"]
        r = self.post(f"/api/hypotheses/{hid}/scenarios", {"overrides": {"P001": 99999}})
        self.assertEqual(r.status_code, 422)
        self.assertIn("fora do domínio", r.json()["detail"])

    def test_model_unavailable_keeps_deterministic(self):
        pg, c = make(NoModel())
        h = {"X-Demo-User": "ana", "X-Demo-Roles": "Policy Specialist"}
        hid = c.post("/api/hypotheses", json={"intent": "renda mínima 3000"}, headers=h).json()["hypothesis"]["hypothesisId"]
        c.post(f"/api/hypotheses/{hid}/scenarios", json={"overrides": {"P001": 3000}}, headers=h)
        c.post(f"/api/hypotheses/{hid}/suggestions", json={}, headers=h)
        rec = c.get(f"/api/hypotheses/{hid}", headers=h).json()
        self.assertTrue(rec["suggestionJobs"][0]["modelStatus"].startswith("unavailable"))
        self.assertEqual(sorted(f["generator"] for f in rec["findings"]), ["G1", "G2"])

    def test_ai_numbers_are_dropped(self):
        pg, c = make(FakeModel([{"title": "Aprovação cai 20%", "text": "Perde 3 propostas", "ruleRefs": ["R005"]},
                                {"title": "Olhar R006", "text": "Comprometimento pode compensar R005", "ruleRefs": ["R006", "R999"]}]))
        h = {"X-Demo-User": "ana", "X-Demo-Roles": "Policy Specialist"}
        hid = c.post("/api/hypotheses", json={"intent": "renda mínima 3000"}, headers=h).json()["hypothesis"]["hypothesisId"]
        c.post(f"/api/hypotheses/{hid}/scenarios", json={"overrides": {"P001": 3000}}, headers=h)
        c.post(f"/api/hypotheses/{hid}/suggestions", json={}, headers=h)
        ai = [f for f in c.get(f"/api/hypotheses/{hid}", headers=h).json()["findings"] if f["source"] == "ai_suggestion"]
        self.assertEqual([f["title"] for f in ai], ["Olhar R006"])
        self.assertEqual(ai[0]["ruleRefs"], ["R006"])

    def test_suggestion_cap(self):
        hid = self.post("/api/hypotheses", {"intent": "renda mínima 3000"}).json()["hypothesis"]["hypothesisId"]
        self.post(f"/api/hypotheses/{hid}/scenarios", {"overrides": {"P001": 3000}})
        for _ in range(3):
            self.assertEqual(self.post(f"/api/hypotheses/{hid}/suggestions").status_code, 200)
        self.assertEqual(self.post(f"/api/hypotheses/{hid}/suggestions").status_code, 409)


if __name__ == "__main__":
    unittest.main()
