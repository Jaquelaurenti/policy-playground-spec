"""R10.2/R11/R12 (forma do MVP): pacote de mudança determinístico após decisão de aceite."""
import ast
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from policy_playground.adapters.memory import MemoryAudit, MemoryEventStore, MemoryKV, NoModel, ThreadDispatcher
from policy_playground.api.app import create_app
from policy_playground.domain import change_package as cp
from policy_playground.domain.model import load_from_folder
from policy_playground.service import Playground

FIX = Path(__file__).resolve().parents[3] / ".kiro" / "specs" / "policy-playground" / "fixtures"
MODEL = load_from_folder(FIX)
SPECIALIST = {"X-Demo-User": "ana", "X-Demo-Roles": "Policy Specialist"}
APPROVER = {"X-Demo-User": "rui", "X-Demo-Roles": "Risk Approver"}
VIEWER = {"X-Demo-User": "bia", "X-Demo-Roles": "Viewer"}


def make():
    pg = Playground(MODEL, MemoryEventStore(), MemoryKV(), MemoryAudit(), NoModel(), None)
    pg.dispatcher = ThreadDispatcher(pg.run_job, synchronous=True)
    return pg, TestClient(create_app(pg))


class ChangePackageTest(unittest.TestCase):
    def setUp(self):
        self.pg, self.c = make()
        h = self.c.post("/api/hypotheses", json={"intent": "aumentar a renda mínima para 3000"}, headers=SPECIALIST).json()
        self.hid = h["hypothesis"]["hypothesisId"]
        self.c.post(f"/api/hypotheses/{self.hid}/scenarios", json={"overrides": {"P001": 3000}}, headers=SPECIALIST)
        self.c.post(f"/api/hypotheses/{self.hid}/executions", json={}, headers=SPECIALIST)

    def decide(self, outcome, h=SPECIALIST):
        return self.c.post(f"/api/hypotheses/{self.hid}/decisions",
                           json={"outcome": outcome, "rationale": "Evidência suficiente", "evidenceRefs": []}, headers=h)

    def gen(self, h=SPECIALIST):
        return self.c.post(f"/api/hypotheses/{self.hid}/change-package", headers=h)

    def test_sem_aceite_nao_gera(self):
        self.assertEqual(self.gen().status_code, 409)
        self.decide("defer")
        self.assertEqual(self.gen().status_code, 409)

    def test_pacote_completo_e_testes_passam(self):
        self.decide("accept", APPROVER)
        r = self.gen()
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()
        self.assertEqual(p["status"], "nao_submetido")
        # 1. patch
        rep = [op for op in p["patch"] if op["op"] == "replace"]
        self.assertEqual(rep[0]["_meta"]["from"], 2500)
        self.assertEqual(rep[0]["_meta"]["to"], 3000)
        # 2. testes: as três propostas que mudam vêm primeiro
        muda = [t["recordId"] for t in p["tests"] if t["kind"] == "muda"]
        self.assertEqual(muda, ["S02", "S03", "S04"])
        self.assertEqual(len(p["tests"]), 12)
        # 3. prova independente
        self.assertTrue(p["verification"]["ok"])
        self.assertEqual((p["verification"]["passed"], p["verification"]["total"]), (12, 12))
        # 4. manifesto rastreável
        m = p["manifest"]
        self.assertEqual(m["decision"]["outcome"], "accept")
        self.assertEqual(m["decision"]["decidedBy"], "rui")
        self.assertEqual(m["evidence"]["deltas"]["resultado"]["REPROVACAO_SIMULADA"]["delta"], 3)
        # 5. prévia do PR
        self.assertIn("NÃO SUBMETIDO", p["pullRequest"]["body"])
        self.assertIn("renda_minima 2500 → 3000", p["pullRequest"]["title"])
        # o arquivo de teste gerado é Python válido
        ast.parse(p["testFile"]["content"])
        # aparece no record e pode ser relido
        rec = self.c.get(f"/api/hypotheses/{self.hid}", headers=VIEWER).json()
        self.assertEqual(rec["changePackages"][0]["testsPassed"], 12)
        again = self.c.get(f"/api/hypotheses/{self.hid}/change-package/{p['packageId']}", headers=VIEWER)
        self.assertEqual(again.json()["packageId"], p["packageId"])

    def test_idempotente_por_decisao(self):
        self.decide("accept")
        a, b = self.gen().json(), self.gen().json()
        self.assertEqual(a["packageId"], b["packageId"])
        rec = self.c.get(f"/api/hypotheses/{self.hid}", headers=SPECIALIST).json()
        self.assertEqual(len(rec["changePackages"]), 1)

    def test_deterministico_entre_instancias(self):
        """Mesma entrada → mesmo conteúdo (o id ignora carimbos de hora e quem gerou)."""
        self.decide("accept")
        p = self.gen().json()
        tests = cp.build_tests(MODEL, self.pg.kv.get(f"exec#{p['manifest']['evidence']['executionId']}")["rows"])
        self.assertEqual(tests, p["tests"])
        self.assertEqual(cp.build_patch(MODEL, {"P001": 3000}), p["patch"])

    def test_papeis(self):
        self.decide("accept")
        self.assertEqual(self.gen(VIEWER).status_code, 403)
        self.assertEqual(self.gen(APPROVER).status_code, 403)

    def test_patch_detecta_politica_alterada(self):
        patch = cp.build_patch(MODEL, {"P001": 3000})
        spec = MODEL.spec_snapshot()
        spec["parameters"][0]["value"] = 2700
        with self.assertRaises(cp.ChangePackageError):
            cp.apply_patch(spec, patch)

    def test_verificacao_acusa_teste_errado(self):
        patch = cp.build_patch(MODEL, {"P001": 3000})
        rows = self.pg.kv.get(f"exec#{self.pg._record(self.hid)['executions'][-1]['executionId']}")["rows"]
        tests = cp.build_tests(MODEL, rows)
        tests[0]["expected"]["resultado"] = "APROVACAO_SIMULADA"   # S02 reprova com 3000
        v = cp.verify(MODEL, patch, tests)
        self.assertFalse(v["ok"])
        self.assertEqual(v["passed"], 11)


if __name__ == "__main__":
    unittest.main()
