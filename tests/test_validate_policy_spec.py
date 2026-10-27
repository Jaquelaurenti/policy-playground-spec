"""Testes do validador do Policy Spec contra o fixture real e versões quebradas dele."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / ".kiro/specs/policy-playground/fixtures"
VALIDATOR = ROOT / "tools/policy_spec/validate.py"
SPEC = "policy-playground-demo-policy.json"


def run(folder: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(VALIDATOR), str(folder / SPEC)],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )


class ValidatePolicySpecTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for f in FIXTURES.glob("*.json"):
            shutil.copy(f, self.tmp / f.name)
        self.spec = json.loads((self.tmp / SPEC).read_text(encoding="utf-8"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, spec):
        (self.tmp / SPEC).write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")

    def test_fixture_real_e_valido(self):
        r = run(FIXTURES)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("Válido", r.stdout)

    def test_ciclo_no_dag_bloqueia(self):
        spec = copy.deepcopy(self.spec)
        r001 = next(r for r in spec["rules"] if r["id"] == "R001")
        r001["depends_on"] = ["R009"]
        self.write(spec)
        r = run(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Ciclo no DAG", r.stdout)

    def test_depends_on_inexistente_bloqueia(self):
        spec = copy.deepcopy(self.spec)
        spec["rules"][4]["depends_on"].append("R999")
        self.write(spec)
        r = run(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("R999", r.stdout)

    def test_logic_type_desconhecido_bloqueia(self):
        spec = copy.deepcopy(self.spec)
        spec["rules"][0]["logic"]["type"] = "sql_livre"
        self.write(spec)
        r = run(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("sql_livre", r.stdout)

    def test_baseline_fora_do_dominio_bloqueia(self):
        spec = copy.deepcopy(self.spec)
        next(p for p in spec["parameters"] if p["id"] == "P001")["value"] = 25000
        self.write(spec)
        r = run(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("fora do domínio", r.stdout)

    def test_policy_spec_nao_e_alterado(self):
        antes = (FIXTURES / SPEC).read_bytes()
        run(FIXTURES)
        self.assertEqual(antes, (FIXTURES / SPEC).read_bytes())


if __name__ == "__main__":
    unittest.main()
