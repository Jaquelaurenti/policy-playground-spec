"""R17: Agente Investigador no produto (tools, loop, job, eventos, rota, MCP), com modelo roteirizado."""
import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from policy_playground.adapters.memory import (MemoryAudit, MemoryEventStore, MemoryKV, NoModel, ScriptedModel,
                                               ThreadDispatcher)
from policy_playground.agent.tools import TOOL_SPECS, ToolError, ToolRegistry
from policy_playground.api.app import create_app
from policy_playground.domain.model import load_from_folder
from policy_playground.roles import Actor
from policy_playground.service import Playground

FIX = Path(__file__).resolve().parents[3] / ".kiro" / "specs" / "policy-playground" / "fixtures"
MODEL = load_from_folder(FIX)
SPECIALIST = {"X-Demo-User": "ana", "X-Demo-Roles": "Policy Specialist"}
VIEWER = {"X-Demo-User": "bia", "X-Demo-Roles": "Viewer"}


def _exec_ids(msgs):
    ids = []
    for m in msgs:
        for c in m["content"]:
            j = c.get("toolResult", {}).get("content", [{}])[0].get("json", {})
            if "executionId" in j and j["executionId"] not in ids:
                ids.append(j["executionId"])
    return ids


def demo_steps():
    """O fluxo da demo, como o Nova se comportou no Bedrock, já com as correções."""
    return [
        lambda m: ("PLANO: 1) entender R005 2) simular 3000 e 2800 3) comparar 4) registrar",
                   [("get_policy", {}), ("get_candidates", {"overrides": {"P001": 3000}})]),
        lambda m: ("", [("run_scenario", {"overrides": {"P001": 3000}}), ("run_scenario", {"overrides": {"P001": 2800}})]),
        lambda m: ("", [("compare", {"execution_id": _exec_ids(m)[0], "against_execution_id": _exec_ids(m)[1]})]),
        lambda m: ("", [("register_finding", {"title": "Reprovação sobe 42%", "text": "Sobe 42%", "ruleRefs": ["R005"],
                                              "executionIds": [_exec_ids(m)[0]]})]),
        lambda m: ("Corrigindo.", [
            ("register_finding", {"title": "Faixa BASICA sem uso para aprovados",
                                  "text": "Com renda_minima 2500 → 3000, nenhuma proposta aprovada cai na faixa BASICA "
                                          "de R007; a linha BASICA da matriz de R008 (A=1000, B=500) deixa de ser usada.",
                                  "ruleRefs": ["R007", "R008"], "executionIds": [_exec_ids(m)[0]]}),
            ("register_finding", {"title": "Reprovações vão de 4 para 7 com renda mínima 3000",
                                  "text": "O motivo 102 vai de 1 para 5 (delta 4).",
                                  "ruleRefs": ["R005", "R009"], "executionIds": [_exec_ids(m)[0]]})]),
        lambda m: ("", [("submit_recommendation",
                         {"text": "Com 3000 as reprovações vão de 4 para 7; com 2800 o efeito é menor. Revisar antes de decidir."})]),
    ]


def make(ai):
    pg = Playground(MODEL, MemoryEventStore(), MemoryKV(), MemoryAudit(), ai, None)
    pg.dispatcher = ThreadDispatcher(pg.run_job, synchronous=True)
    return pg, TestClient(create_app(pg))


class AgentApiTest(unittest.TestCase):
    def _confirmed(self, c):
        h = c.post("/api/hypotheses", json={"intent": "aumentar a renda mínima para 3000"}, headers=SPECIALIST).json()
        hid = h["hypothesis"]["hypothesisId"]
        c.post(f"/api/hypotheses/{hid}/scenarios", json={"overrides": {"P001": 3000}}, headers=SPECIALIST)
        return hid

    def test_fluxo_da_demo_pela_api(self):
        pg, c = make(ScriptedModel(demo_steps()))
        hid = self._confirmed(c)
        r = c.post(f"/api/hypotheses/{hid}/investigations", headers=SPECIALIST)
        self.assertEqual(r.status_code, 202)
        rec = c.get(f"/api/hypotheses/{hid}", headers=SPECIALIST).json()
        inv = rec["investigations"][0]
        self.assertEqual((inv["state"], inv["outcome"]), ("done", "done"))
        self.assertIn("de 4 para 7", inv["recommendation"])
        tools = [s["tool"] for s in inv["timeline"]]
        self.assertEqual(tools[0], "_plan")
        self.assertIn("compare", tools)
        self.assertEqual(sum(1 for s in inv["timeline"] if s["status"] == "error"), 1)   # a recusa do 42%
        self.assertEqual(len(inv["executionIds"]), 2)
        agent_findings = [f for f in rec["findings"] if f.get("source") == "agent"]
        self.assertEqual(len(agent_findings), 2)
        for f in agent_findings:
            self.assertEqual(f["evidenceLevel"], "simulated")
            self.assertIn(f["currentExecutionId"], {e["executionId"] for e in rec["executions"]})
        self.assertGreater(rec["metrics"]["modelTokens"], 0)
        # R17.6: o agente chamou cada tool pelo protocolo MCP, com as tools descobertas no servidor
        self.assertEqual((inv["transport"], inv["toolsDiscovered"]), ("mcp", 9))
        self.assertTrue(all(s.get("via") == "mcp" for s in inv["timeline"] if s["tool"] != "_plan"))
        recusa = next(s for s in inv["timeline"] if s["status"] == "error")
        self.assertIn("números sem evidência", recusa["error"])     # a mensagem atravessa o MCP intacta
        self.assertIsNotNone(rec["metrics"]["hypothesisToEvidenceSeconds"])
        # a execução do agente pode ser aberta como qualquer outra
        ex = c.get(f"/api/executions/{inv['executionIds'][0]}", headers=SPECIALIST).json()
        self.assertEqual((ex["mode"], ex["evidenceLevel"]), ("SIMULADO", "simulated"))
        # achado do agente segue o mesmo ciclo de revisão humana
        fid = agent_findings[0]["findingId"]
        self.assertEqual(c.post(f"/api/hypotheses/{hid}/findings/{fid}/transitions", json={"to": "rejected"},
                                headers=SPECIALIST).status_code, 200)

    def test_sem_modelo_cai_para_g1_g2(self):
        _, c = make(NoModel())
        hid = self._confirmed(c)
        c.post(f"/api/hypotheses/{hid}/investigations", headers=SPECIALIST)
        rec = c.get(f"/api/hypotheses/{hid}", headers=SPECIALIST).json()
        inv = rec["investigations"][0]
        self.assertEqual(inv["outcome"], "model_unavailable")
        self.assertTrue(any(f.get("generator") == "G2" for f in rec["findings"]))

    def test_precisa_de_cenario_confirmado_e_papel(self):
        _, c = make(ScriptedModel(demo_steps()))
        h = c.post("/api/hypotheses", json={"intent": "aumentar a renda mínima para 3000"}, headers=SPECIALIST).json()
        hid = h["hypothesis"]["hypothesisId"]
        self.assertEqual(c.post(f"/api/hypotheses/{hid}/investigations", headers=SPECIALIST).status_code, 409)
        c.post(f"/api/hypotheses/{hid}/scenarios", json={"overrides": {"P001": 3000}}, headers=SPECIALIST)
        self.assertEqual(c.post(f"/api/hypotheses/{hid}/investigations", headers=VIEWER).status_code, 403)

    def test_limite_de_investigacoes_por_hipotese(self):
        pg, c = make(ScriptedModel(demo_steps() * 4))
        pg.cfg.agent_max_runs = 1
        hid = self._confirmed(c)
        c.post(f"/api/hypotheses/{hid}/investigations", headers=SPECIALIST)
        self.assertEqual(c.post(f"/api/hypotheses/{hid}/investigations", headers=SPECIALIST).status_code, 409)

    def test_job_repetido_nao_roda_de_novo(self):
        pg, c = make(ScriptedModel(demo_steps()))
        hid = self._confirmed(c)
        jid = c.post(f"/api/hypotheses/{hid}/investigations", headers=SPECIALIST).json()["jobId"]
        before = len(pg.events.list(hid))
        pg.run_job({"kind": "investigation", "hypothesisId": hid, "jobId": jid, "actor": "ana",
                    "roles": ["Policy Specialist"]})
        self.assertEqual(len(pg.events.list(hid)), before)

    def test_erro_inesperado_nao_prende_o_job(self):
        def boom(m):
            raise RuntimeError("falha simulada")
        _, c = make(ScriptedModel([boom]))
        hid = self._confirmed(c)
        c.post(f"/api/hypotheses/{hid}/investigations", headers=SPECIALIST)
        inv = c.get(f"/api/hypotheses/{hid}", headers=SPECIALIST).json()["investigations"][0]
        self.assertEqual((inv["state"], inv["outcome"]), ("done", "error"))


class McpClientTest(unittest.TestCase):
    """O cliente MCP em memória que o agente usa (R17.6)."""

    def test_descobre_e_chama_pelo_protocolo(self):
        from policy_playground.agent.mcp_client import McpToolClient
        reg = ToolRegistry(MODEL, Actor("a", {"Policy Specialist"}))
        with McpToolClient(reg) as cli:
            names = {t["name"] for t in cli.list_tools()}
            self.assertEqual(names, {t["name"] for t in TOOL_SPECS})
            r = cli.call("run_scenario", {"overrides": {"P001": 3000}})
            self.assertEqual(r["deltas"]["motivos"]["102"]["delta"], 4)
            with self.assertRaises(ToolError) as e:
                cli.call("register_finding", {"title": "x", "text": "sobe 42", "ruleRefs": ["R005"],
                                              "executionIds": [r["executionId"]]})
            self.assertIn("42", str(e.exception))
        self.assertEqual(reg.calls[0]["via"], "mcp")
        self.assertIn(r["executionId"], reg.executions)           # o servidor usou o registro da investigação

    def test_funciona_dentro_de_um_laco_assincrono(self):
        """Na Lambda, o job roda dentro do handler assíncrono POST /events."""
        import asyncio
        pg, c = make(ScriptedModel(demo_steps()))
        h = c.post("/api/hypotheses", json={"intent": "aumentar a renda mínima para 3000"}, headers=SPECIALIST).json()
        hid = h["hypothesis"]["hypothesisId"]
        c.post(f"/api/hypotheses/{hid}/scenarios", json={"overrides": {"P001": 3000}}, headers=SPECIALIST)
        pg.dispatcher = type("NoDispatch", (), {"dispatch": lambda self, job: None})()
        jid = pg.request_investigation(Actor("ana", {"Policy Specialist"}), hid)["jobId"]

        async def handler():
            pg.run_job({"kind": "investigation", "hypothesisId": hid, "jobId": jid, "actor": "ana",
                        "roles": ["Policy Specialist"]})
        asyncio.run(handler())
        inv = pg.hypothesis(Actor("ana", {"Policy Specialist"}), hid)["investigations"][0]
        self.assertEqual((inv["outcome"], inv["transport"]), ("done", "mcp"))


class ToolsTest(unittest.TestCase):
    def test_deltas(self):
        d = ToolRegistry(MODEL, Actor("a", {"Policy Specialist"})).call("run_scenario", {"overrides": {"P001": 3000}})["deltas"]
        self.assertEqual(d["motivos"][102]["delta"], 4)
        self.assertEqual(d["resultado"]["REPROVACAO_SIMULADA"]["delta"], 3)

    def test_viewer_le_mas_nao_executa(self):
        reg = ToolRegistry(MODEL, Actor("v", {"Viewer"}))
        reg.call("get_policy", {})
        with self.assertRaises(ToolError):
            reg.call("run_scenario", {"overrides": {"P001": 3000}})

    def test_nove_tools(self):
        self.assertEqual(len(TOOL_SPECS), 9)


class McpTest(unittest.TestCase):
    """O servidor MCP montado em /mcp/stream responde ao protocolo (JSON-RPC sobre Streamable HTTP)."""

    def rpc(self, c, method, params, h=SPECIALIST, rid=1):
        r = c.post("/mcp/stream", json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params},
                   headers={**h, "Accept": "application/json, text/event-stream", "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_lista_e_executa_tools(self):
        _, c = make(NoModel())
        with c:                                     # dispara o lifespan (session manager do MCP)
            init = self.rpc(c, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                              "clientInfo": {"name": "teste", "version": "0"}})
            self.assertEqual(init["result"]["serverInfo"]["name"], "policy-playground")
            names = {t["name"] for t in self.rpc(c, "tools/list", {}, rid=2)["result"]["tools"]}
            self.assertEqual(names, {t["name"] for t in TOOL_SPECS})
            res = self.rpc(c, "tools/call", {"name": "run_scenario", "arguments": {"overrides": {"P001": 3000}}}, rid=3)
            body = json.loads(res["result"]["content"][0]["text"])
            self.assertEqual(body["mode"], "SIMULADO")
            # a mesma execução é comparável na chamada seguinte (registro por ator)
            cmp = self.rpc(c, "tools/call", {"name": "compare", "arguments": {"execution_id": body["executionId"]}}, rid=4)
            self.assertFalse(cmp["result"].get("isError"))

    def test_viewer_pelo_mcp_nao_executa(self):
        _, c = make(NoModel())
        with c:
            self.rpc(c, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                       "clientInfo": {"name": "teste", "version": "0"}}, h=VIEWER)
            res = self.rpc(c, "tools/call", {"name": "run_scenario", "arguments": {"overrides": {"P001": 3000}}},
                           h=VIEWER, rid=2)
            self.assertTrue(res["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
