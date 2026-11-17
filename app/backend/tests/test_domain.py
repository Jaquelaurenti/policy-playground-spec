import copy
import json
import unittest
from pathlib import Path

from policy_playground.domain import engine, expr, generators
from policy_playground.domain.model import PolicyInvalid, load_from_folder, load_policy
from policy_playground.domain.record import (InvalidTransition, check_transition, evidence_level, structure_intent,
                                             validate_overrides)

FIX = Path(__file__).resolve().parents[3] / ".kiro" / "specs" / "policy-playground" / "fixtures"


def raw():
    spec = json.loads((FIX / "policy-playground-demo-policy.json").read_text())
    ext = json.loads((FIX / "policy-playground-demo-extensions.json").read_text())
    ds = json.loads((FIX / "policy-playground-demo-dataset.json").read_text())
    return spec, ext, ds


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.m = load_from_folder(FIX)

    def test_fixture_loads_clean(self):
        self.assertTrue(self.m.report.ok)
        self.assertTrue(self.m.report.can_execute)
        self.assertEqual(self.m.policy_version, "microcredito-demo@synthetic-demo-v1")

    def test_consumed_by_derived(self):
        self.assertEqual(sorted(self.m.consumed_by["renda_mensal"]), ["R005", "R007"])

    def test_cycle_blocks(self):
        spec, ext, ds = raw()
        next(r for r in spec["rules"] if r["id"] == "R001")["depends_on"] = ["R009"]
        with self.assertRaises(PolicyInvalid) as cm:
            load_policy(spec, ext, ds)
        self.assertIn("Ciclo no DAG", cm.exception.report.errors[0])

    def test_unknown_logic_type_blocks(self):
        spec, ext, ds = raw()
        spec["rules"][0]["logic"]["type"] = "sql_livre"
        with self.assertRaises(PolicyInvalid):
            load_policy(spec, ext, ds)

    def test_free_sql_condition_blocks(self):
        spec, ext, ds = raw()
        spec["rules"][4]["logic"]["branches"][0]["when"] = "renda_mensal >= (SELECT 1)"
        with self.assertRaises(PolicyInvalid) as cm:
            load_policy(spec, ext, ds)
        self.assertIn("gramática", " ".join(cm.exception.report.errors))

    def test_dataset_problem_blocks_execution_not_exploration(self):
        spec, ext, ds = raw()
        ds["records"] = ds["records"][:3]
        m = load_policy(spec, ext, ds)
        self.assertTrue(m.report.ok)
        self.assertFalse(m.report.can_execute)
        with self.assertRaises(engine.CannotCalculate):
            engine.simulate(m, {"P001": 3000})

    def test_policy_spec_never_mutated(self):
        before = self.m.spec_snapshot()
        engine.simulate(self.m, {"P001": 3000})
        self.assertEqual(before, self.m.spec_snapshot())
        self.assertEqual(json.loads((FIX / "policy-playground-demo-policy.json").read_text()), before)


class ExprTest(unittest.TestCase):
    def test_and_or_precedence(self):
        ast = expr.parse("a = 1 OR b = 2 AND c = 3")
        self.assertTrue(expr.evaluate(ast, {"a": 1, "b": 0, "c": 0}))
        self.assertFalse(expr.evaluate(ast, {"a": 0, "b": 2, "c": 0}))

    def test_strings(self):
        self.assertTrue(expr.evaluate(expr.parse("s = 'ELEGIVEL'"), {"s": "ELEGIVEL"}))

    def test_rejects_functions(self):
        with self.assertRaises(expr.ExpressionError):
            expr.parse("upper(x) = 'A'")


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.m = load_from_folder(FIX)

    def test_reverse_discovery_worked_example(self):
        sd = engine.affected_subdag(self.m, ["P001"])
        self.assertEqual(sd.seed, ["R005"])
        self.assertEqual(sd.forward, ["R009"])
        self.assertEqual(sd.execution_set, ["R001", "R005", "R009"])
        self.assertEqual(sd.affected_outputs, ["resultado"])
        self.assertEqual([m["code"] for m in sd.affected_motivos], [102])

    def test_required_for_output(self):
        self.assertEqual(engine.required_for_output(self.m, "limite_sugerido"), ["R001", "R007", "R008"])

    def test_simulation_p001_3000(self):
        r = engine.simulate(self.m, {"P001": 3000})
        c = r["comparison"]
        self.assertEqual(c["outputs"]["resultado"]["baseline"]["APROVACAO_SIMULADA"], 8)
        self.assertEqual(c["outputs"]["resultado"]["scenario"]["APROVACAO_SIMULADA"], 5)
        self.assertEqual(c["outputs"]["resultado"]["changedRecords"], ["S02", "S03", "S04"])
        self.assertEqual(c["motivos"][102]["baseline"], 1)
        self.assertEqual(c["motivos"][102]["scenario"], 5)
        self.assertEqual(c["outputs"]["limite_sugerido"]["changedRecords"], [])

    def test_baseline_equals_full_recompute(self):
        """Recalcular só o caminho alterado dá o mesmo que recalcular tudo."""
        params = engine.overrides_to_params(self.m, {"P001": 3000})
        for rec in self.m.dataset["records"]:
            payload = {"cliente": rec["cliente"]}
            full = engine.run_record(self.m, payload, params)
            base = engine.run_record(self.m, payload, self.m.baseline_params())
            sub = engine.run_record(self.m, payload, params, only={"R001", "R005", "R009"}, base_env=base)
            self.assertEqual({o: full[o] for o in self.m.output_vars}, {o: sub[o] for o in self.m.output_vars})

    def test_idempotency_key_stable(self):
        self.assertEqual(engine.idempotency_key(self.m, {"P001": 3000}), engine.idempotency_key(self.m, {"P001": 3000.0}))
        self.assertNotEqual(engine.idempotency_key(self.m, {"P001": 3000}), engine.idempotency_key(self.m, {"P001": 3100}))


class GeneratorsTest(unittest.TestCase):
    def setUp(self):
        self.m = load_from_folder(FIX)

    def test_g1(self):
        g1 = generators.g1_shared_input(self.m, {"P001": 3000})
        self.assertEqual([c["ruleRefs"] for c in g1], [["R007", "R008"]])

    def test_g2_basica_unreachable(self):
        g2 = generators.g2_reachability(self.m, {"P001": 3000})
        self.assertEqual(len(g2), 1)
        self.assertIn("BASICA", g2[0]["title"])
        self.assertEqual(g2[0]["structuralBasis"]["reachableBaseline"], ["[2500, 3000)"])
        self.assertEqual(g2[0]["structuralBasis"]["reachableScenario"], [])
        self.assertEqual(g2[0]["evidenceLevel"], "none")

    def test_ranking_smoothing_and_cap(self):
        cands = [{"source": "ai_suggestion"}, {"source": "deterministic_analysis", "generator": "G2"}]
        ranked = generators.rank(copy.deepcopy(cands), [], cap=1)
        self.assertEqual(ranked[0]["generator"], "G2")
        self.assertEqual(ranked[0]["score"], 0.8)


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.m = load_from_folder(FIX)

    def test_evidence_map(self):
        self.assertEqual(evidence_level("SIMULADO", "ok"), "simulated")
        self.assertEqual(evidence_level("REAL", "validated"), "study_validated")
        for st in ("cannot_calculate", "executed_unvalidated", "validation_failed"):
            self.assertEqual(evidence_level("REAL", st), "none")

    def test_transitions(self):
        check_transition("suggested", "under_investigation")
        with self.assertRaises(InvalidTransition):
            check_transition("suggested", "accepted")
        with self.assertRaises(InvalidTransition):
            check_transition("rejected", "under_investigation")

    def test_structure_intent(self):
        p = structure_intent(self.m, "Testar renda mínima de R$ 2.500 para R$ 3.000")
        self.assertEqual(p["parameterId"], "P001")
        self.assertEqual(p["proposedValue"], 3000.0)

    def test_overrides_domain(self):
        self.assertEqual(validate_overrides(self.m, {"P001": 3000}), {"P001": 3000.0})
        for bad in ({"P001": 25000}, {"P001": 3050}, {"P001": 2500}, {"P999": 1}):
            with self.assertRaises(ValueError):
                validate_overrides(self.m, bad)


if __name__ == "__main__":
    unittest.main()
