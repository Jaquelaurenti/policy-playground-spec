"""SPIKE — testes do loop com um modelo stub roteirizado contra o motor determinístico REAL.

Rodar na raiz do repo:  python -m unittest discover -s spike/agente
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / "app" / "backend"), str(HERE)]

from loop import investigate  # noqa: E402
from policy_playground.domain.engine import CannotCalculate  # noqa: E402
from policy_playground.domain.model import load_from_folder  # noqa: E402
from policy_playground.service import Actor  # noqa: E402
from tool_registry import TOOL_SPECS, ToolError, ToolRegistry  # noqa: E402

MODEL = load_from_folder(ROOT / ".kiro" / "specs" / "policy-playground" / "fixtures")
SPECIALIST = Actor("ana", {"Policy Specialist"})


def _results(msg):
    return [c["toolResult"] for c in msg["content"] if "toolResult" in c]


def _exec_ids(msgs):
    ids = []
    for m in msgs:
        for c in m["content"]:
            j = c.get("toolResult", {}).get("content", [{}])[0].get("json", {})
            if "executionId" in j and j["executionId"] not in ids:
                ids.append(j["executionId"])
    return ids


class ScriptedClient:
    """Cada passo: função (msgs) -> (texto, [(tool, input)]) ou str (resposta final)."""

    def __init__(self, steps):
        self.steps, self.i, self.seen = steps, 0, []

    def converse(self, modelId, system, messages, toolConfig, inferenceConfig):
        assert {t["toolSpec"]["name"] for t in toolConfig["tools"]} == {t["name"] for t in TOOL_SPECS}
        self.seen.append(messages[-1])            # snapshot: a lista é mutada pelo loop
        step = self.steps[self.i](messages)
        self.i += 1
        usage = {"inputTokens": 100, "outputTokens": 20}
        if isinstance(step, str):
            return {"stopReason": "end_turn", "usage": usage,
                    "output": {"message": {"role": "assistant", "content": [{"text": step}]}}}
        text, calls = step
        content = ([{"text": text}] if text else []) + [
            {"toolUse": {"toolUseId": f"t{self.i}-{k}", "name": n, "input": inp}} for k, (n, inp) in enumerate(calls)]
        return {"stopReason": "tool_use", "usage": usage, "output": {"message": {"role": "assistant", "content": content}}}


def demo_script():
    """Roteiro da demo: plano → leitura → candidatos → 2 cenários → compare → achado (1 recusa) → recomendação."""
    return [
        lambda m: ("PLANO: 1) entender R005 e dependências 2) simular 3000 e 2800 3) comparar 4) registrar achados",
                   [("get_policy", {}), ("preview_subdag", {"overrides": {"P001": 3000}})]),
        lambda m: ("", [("get_candidates", {"overrides": {"P001": 3000}}), ("read_audit", {}),
                        ("run_scenario", {"overrides": {"P001": 3000}})]),
        lambda m: ("Vou testar uma alternativa intermediária.", [("run_scenario", {"overrides": {"P001": 2800}})]),
        lambda m: ("", [("compare", {"execution_id": _exec_ids(m)[0]}),
                        ("compare", {"execution_id": _exec_ids(m)[0], "against_execution_id": _exec_ids(m)[1]})]),
        lambda m: ("", [("register_finding", {"title": "Reprovação por renda sobe", "text": "Sobe 42%",
                                              "ruleRefs": ["R005"], "executionIds": [_exec_ids(m)[0]]})]),
        lambda m: ("Corrigindo com números da execução.",
                   [("register_finding", {"title": "Motivo 102 vai de 1 para 5 propostas com renda mínima 3000",
                                          "text": "Com P001 em 3000, 3 propostas mudam de resultado e o motivo 102 "
                                                  "(renda insuficiente) vai de 1 para 5.",
                                          "ruleRefs": ["R005", "R009"], "executionIds": [_exec_ids(m)[0]]})]),
        lambda m: "RECOMENDAÇÃO: 3000 reprova 3 propostas a mais que hoje; vale comparar com 2800 antes de decidir.",
    ]


class AgentLoopTest(unittest.TestCase):
    def test_fluxo_da_demo(self):
        reg = ToolRegistry(MODEL, SPECIALIST)
        client = ScriptedClient(demo_script())
        out = investigate(client, "stub", reg, "aumentar a renda mínima para 3000", {"P001": 3000})

        self.assertEqual(out["status"], "done")
        self.assertTrue(out["summary"].startswith("RECOMENDAÇÃO"))
        self.assertEqual(len(reg.executions), 2)
        self.assertEqual(len(out["findings"]), 1)
        f = out["findings"][0]
        self.assertEqual((f["evidenceLevel"], f["state"], f["createdBy"]), ("simulated", "suggested", "ana"))
        # plano visível na trilha
        self.assertEqual(out["calls"][0]["tool"], "_plan")
        self.assertIn("PLANO", out["calls"][0]["input"]["text"])
        # a recusa do número inventado voltou como erro e ficou na trilha
        rejected = [c for c in out["calls"] if c["status"] == "error"]
        self.assertEqual(len(rejected), 1)
        self.assertIn("42", rejected[0]["error"])
        self.assertEqual(_results(client.seen[5])[0]["status"], "error")
        # números do achado batem com o motor determinístico
        comp = reg.executions[f["executionIds"][0]]["comparison"]
        self.assertEqual((comp["motivos"][102]["baseline"], comp["motivos"][102]["scenario"]), (1, 5))
        self.assertEqual(len(comp["outputs"]["resultado"]["changedRecords"]), 3)

    def test_compare_entre_cenarios(self):
        reg = ToolRegistry(MODEL, SPECIALIST)
        a = reg.call("run_scenario", {"overrides": {"P001": 3000}})["executionId"]
        b = reg.call("run_scenario", {"overrides": {"P001": 2800}})["executionId"]
        d = reg.call("compare", {"execution_id": a, "against_execution_id": b})
        self.assertEqual(d["mode"], "SIMULADO")
        self.assertIn("resultado", d["recordsThatDiffer"])

    def test_recomendacao_com_numero_inventado_e_reescrita(self):
        steps = [lambda m: ("PLANO: simular", [("run_scenario", {"overrides": {"P001": 3000}})]),
                 lambda m: "RECOMENDAÇÃO: aprova 17% a menos.",
                 lambda m: "RECOMENDAÇÃO: 3000 muda o resultado de 3 propostas; revisar antes de decidir."]
        out = investigate(ScriptedClient(steps), "stub", ToolRegistry(MODEL, SPECIALIST), "x", {"P001": 3000})
        self.assertEqual(out["status"], "done")
        self.assertNotIn("17", out["summary"])
        self.assertTrue(any("recomendação recusada" in c["input"].get("text", "") for c in out["calls"]))

    def test_cannot_calculate_agente_tenta_alternativa(self):
        reg = ToolRegistry(MODEL, SPECIALIST)
        real = __import__("tool_registry").engine.simulate
        calls = {"n": 0}

        def flaky(model, ov):
            calls["n"] += 1
            if calls["n"] == 1:
                raise CannotCalculate("validação bloqueia")
            return real(model, ov)

        steps = [lambda m: ("", [("run_scenario", {"overrides": {"P001": 3000}})]),
                 lambda m: ("Erro; tento de novo com outro valor.", [("run_scenario", {"overrides": {"P001": 2900}})]),
                 lambda m: "RECOMENDAÇÃO: revisar."]
        with mock.patch("tool_registry.engine.simulate", side_effect=flaky):
            out = investigate(ScriptedClient(steps), "stub", reg, "x", {"P001": 3000})
        self.assertEqual([c["status"] for c in out["calls"] if c["tool"] == "run_scenario"], ["error", "success"])
        self.assertTrue(out["calls"][0]["error"].startswith("cannot_calculate"))

    def test_permissoes_de_quem_acionou(self):
        viewer = ToolRegistry(MODEL, Actor("vic", {"Viewer"}))
        viewer.call("get_policy", {})                                    # leitura pode
        with self.assertRaises(ToolError):
            viewer.call("run_scenario", {"overrides": {"P001": 3000}})   # execução não
        self.assertIn("sem permissão", viewer.calls[-1]["error"])

    def test_tool_desconhecida_e_parametro_invalido_viram_erro_recuperavel(self):
        steps = [lambda m: ("", [("apagar_politica", {}), ("run_scenario", {"overrides": {"P999": 1}})]),
                 lambda m: "RECOMENDAÇÃO: nada a registrar."]
        reg = ToolRegistry(MODEL, SPECIALIST)
        out = investigate(ScriptedClient(steps), "stub", reg, "x", {"P001": 3000})
        self.assertEqual([c["status"] for c in out["calls"]], ["error", "error"])
        self.assertEqual(reg.executions, {})

    def test_orcamento_de_simulacoes(self):
        reg = ToolRegistry(MODEL, SPECIALIST, max_simulations=2)
        reg.call("run_scenario", {"overrides": {"P001": 2600}})
        reg.call("run_scenario", {"overrides": {"P001": 2700}})
        with self.assertRaises(ToolError):
            reg.call("run_scenario", {"overrides": {"P001": 2800}})

    def test_achado_sem_execucao_e_recusado(self):
        reg = ToolRegistry(MODEL, SPECIALIST)
        with self.assertRaises(ToolError):
            reg.call("register_finding", {"title": "t", "text": "x", "ruleRefs": ["R005"], "executionIds": ["E-nada"]})

    def test_limite_de_passos_encerra_em_limited(self):
        loop_forever = [lambda m: ("", [("get_policy", {})])] * 3
        out = investigate(ScriptedClient(loop_forever), "stub", ToolRegistry(MODEL, SPECIALIST), "x",
                          {"P001": 3000}, max_steps=3)
        self.assertEqual(out["status"], "limited")

    def test_read_audit_mostra_achados_anteriores(self):
        reg = ToolRegistry(MODEL, SPECIALIST, prior_findings=[{"title": "R007 BASICA inalcançável", "state": "accepted"}])
        a = reg.call("read_audit", {})
        self.assertEqual(a["priorFindings"][0]["state"], "accepted")

    def test_baseline_intacto_apos_investigacao(self):
        before = MODEL.baseline_params()
        ToolRegistry(MODEL, SPECIALIST).call("run_scenario", {"overrides": {"P001": 3000, "P002": 30}})
        self.assertEqual(MODEL.baseline_params(), before)


if __name__ == "__main__":
    unittest.main()
