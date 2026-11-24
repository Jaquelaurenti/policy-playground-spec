"""Servidor MCP do Policy Playground (R17.6, design §10.4).

Expõe as MESMAS tools do Agente Investigador (um único registro em `tools.py`) por Streamable HTTP
stateless com resposta JSON, montado em /mcp no FastAPI (endpoint /mcp/stream). Funciona atrás do Lambda Web Adapter porque
cada requisição é independente.

Identidade: cada requisição MCP resolve o ator do mesmo jeito que a API (JWT do Cognito via API Gateway,
ou headers X-Demo-* localmente) e as tools aplicam as permissões dele (R17.10).

Estado: as execuções de um cliente MCP ficam num registro em memória por ator, com validade curta. Numa
Lambda fria ou em outro container o registro recomeça e um executionId antigo volta como erro recuperável.

Compatibilidade: mcp==1.9.4 com fastapi==0.115.6 (Starlette 0.41). O mcp 2.x exige Starlette 1.x.
Sem `from __future__ import annotations`: o FastMCP inspeciona as anotações em tempo de execução.
"""
import contextvars
import time
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .tools import TOOL_SPECS, ToolError, ToolRegistry

DESC = {t["name"]: t["description"] for t in TOOL_SPECS}
_current_actor = contextvars.ContextVar("pp_mcp_actor")
REGISTRY_TTL_S = 30 * 60


def build_mcp(get_registry) -> FastMCP:
    """Servidor MCP com as tools do agente. `get_registry()` devolve o ToolRegistry da chamada:
    por ator (clientes externos em /mcp/stream) ou o da investigação (agente, em memória)."""

    def call(name, **kw):
        try:
            return get_registry().call(name, {k: v for k, v in kw.items() if v is not None})
        except ToolError as e:
            raise ValueError(str(e)) from e      # vira isError=true no protocolo

    mcp = FastMCP("policy-playground", stateless_http=True, json_response=True,
                  streamable_http_path="/stream")  # /mcp/stream casa com a rota /mcp/{proxy+}

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

    @mcp.tool(description=DESC["submit_recommendation"])
    def submit_recommendation(text: str) -> dict:
        return call("submit_recommendation", text=text)

    @mcp.tool(description=DESC["register_finding"])
    def register_finding(title: str, text: str, ruleRefs: list[str], executionIds: list[str]) -> dict:
        return call("register_finding", title=title, text=text, ruleRefs=ruleRefs, executionIds=executionIds)

    return mcp


def build_mcp_asgi(get_model, resolve_actor):
    """Devolve (app ASGI para montar em /mcp, lifespan para o FastAPI)."""
    registries: dict = {}

    def registry() -> ToolRegistry:
        actor = _current_actor.get()
        key = (actor.id, tuple(sorted(actor.roles)))
        now = time.time()
        for k in [k for k, (_, t) in registries.items() if now - t > REGISTRY_TTL_S]:
            registries.pop(k, None)
        reg = registries.get(key, (None, 0))[0] or ToolRegistry(get_model(), actor)
        reg.transport = "mcp"
        registries[key] = (reg, now)
        return reg

    mcp = build_mcp(registry)
    inner = mcp.streamable_http_app()

    async def app(scope, receive, send):
        if scope["type"] != "http":
            return await inner(scope, receive, send)
        try:
            actor = resolve_actor(Request(scope))
        except Exception as e:                     # sem sessão válida: 401 antes de chegar às tools
            detail = getattr(e, "detail", "Sessão inválida")
            return await JSONResponse({"detail": detail}, getattr(e, "status_code", 401))(scope, receive, send)
        token = _current_actor.set(actor)
        try:
            await inner(scope, receive, send)
        finally:
            _current_actor.reset(token)

    @asynccontextmanager
    async def lifespan(_app):
        async with mcp.session_manager.run():
            yield

    return app, lifespan
