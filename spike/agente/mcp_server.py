"""SPIKE (descartável) — o mesmo ToolRegistry exposto como servidor MCP (R17.6).

Valida para o sprint:
1. As 8 tools delegam ao MESMO registro usado pela Converse (nenhuma lógica duplicada).
2. O servidor sobe em Streamable HTTP stateless com resposta JSON, que funciona atrás do
   Lambda Web Adapter, e pode ser montado no FastAPI existente.

Compatibilidade: mcp==1.9.4 funciona com fastapi==0.115.6 (starlette 0.41). O mcp 2.x puxa
starlette 1.x e quebra o FastAPI fixado em app/backend/requirements.txt.

Local:  uvicorn --app-dir spike/agente mcp_server:app --port 8765   →  POST http://localhost:8765/mcp
"""
# sem `from __future__ import annotations`: o FastMCP inspeciona as anotações em runtime

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / "app" / "backend"), str(HERE)]

from mcp.server.fastmcp import FastMCP  # noqa: E402

from policy_playground.domain.model import load_from_folder  # noqa: E402
from policy_playground.service import Actor  # noqa: E402
from tool_registry import TOOL_SPECS, ToolError, ToolRegistry  # noqa: E402

DESC = {t["name"]: t["description"] for t in TOOL_SPECS}


def build_mcp(reg: ToolRegistry) -> FastMCP:
    mcp = FastMCP("policy-playground", stateless_http=True, json_response=True)

    def call(name, **kw):
        try:
            return reg.call(name, {k: v for k, v in kw.items() if v is not None})
        except ToolError as e:
            raise ValueError(str(e)) from e          # vira isError=true no protocolo

    @mcp.tool(description=DESC["get_policy"])
    def get_policy(rule_ids: list[str] | None = None) -> dict:
        return call("get_policy", rule_ids=rule_ids)

    @mcp.tool(description=DESC["preview_subdag"])
    def preview_subdag(overrides: dict[str, float]) -> dict:
        return call("preview_subdag", overrides=overrides)

    @mcp.tool(description=DESC["trace_output"])
    def trace_output(output_var: str) -> dict:
        return call("trace_output", output_var=output_var)

    @mcp.tool(description=DESC["run_scenario"])
    def run_scenario(overrides: dict[str, float]) -> dict:
        return call("run_scenario", overrides=overrides)

    @mcp.tool(description=DESC["compare"])
    def compare(execution_id: str, against_execution_id: str | None = None) -> dict:
        return call("compare", execution_id=execution_id, against_execution_id=against_execution_id)

    @mcp.tool(description=DESC["get_candidates"])
    def get_candidates(overrides: dict[str, float], generators: list[str] | None = None) -> dict:
        return call("get_candidates", overrides=overrides, generators=generators)

    @mcp.tool(description=DESC["read_audit"])
    def read_audit() -> dict:
        return call("read_audit")

    @mcp.tool(description=DESC["register_finding"])
    def register_finding(title: str, text: str, ruleRefs: list[str], executionIds: list[str]) -> dict:
        return call("register_finding", title=title, text=text, ruleRefs=ruleRefs, executionIds=executionIds)

    return mcp


def _default_registry() -> ToolRegistry:
    # Spike: ator fixo. No sprint, o ator vem do JWT do Cognito da requisição MCP (R17.10).
    actor = Actor("mcp-demo", {"Policy Specialist"})
    return ToolRegistry(load_from_folder(ROOT / ".kiro" / "specs" / "policy-playground" / "fixtures"), actor)


mcp = build_mcp(_default_registry())
app = mcp.streamable_http_app()          # Starlette ASGI; endpoint em /mcp
