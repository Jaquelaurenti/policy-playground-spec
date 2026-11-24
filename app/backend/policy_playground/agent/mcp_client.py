"""Cliente MCP do Agente Investigador (R17.6).

O agente não chama o registro de tools direto: abre uma sessão MCP com o servidor do Playground
(mesmo servidor de /mcp/stream) pelo transporte em memória do SDK e usa `tools/list` e `tools/call`.
Assim o agente consome o motor exatamente como qualquer outro cliente MCP (o Kiro, por exemplo),
e as regras ficam no servidor.

A sessão roda num laço de eventos próprio, numa thread dedicada, porque o job pode ser executado
de dentro de um handler assíncrono (Lambda Web Adapter → POST /events).
"""
# sem `from __future__ import annotations`: o FastMCP do servidor inspeciona anotações em runtime
import asyncio
import json
import threading

from mcp.shared.memory import create_connected_server_and_client_session

from .mcp_server import build_mcp
from .tools import ToolError, ToolRegistry

_ERR_PREFIX = "Error executing tool "


class McpToolClient:
    """Interface síncrona (`list_tools`, `call`) sobre uma sessão MCP assíncrona em memória."""

    transport = "mcp"

    def __init__(self, registry: ToolRegistry, timeout_s: float = 60.0):
        registry.transport = "mcp"
        self._server = build_mcp(lambda: registry)._mcp_server
        self._timeout = timeout_s
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="pp-mcp-client", daemon=True)
        self._thread.start()
        self._cm = None
        self._session = None
        self._run(self._open())

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(self._timeout)

    async def _open(self):
        self._cm = create_connected_server_and_client_session(self._server)
        self._session = await self._cm.__aenter__()

    def list_tools(self) -> list[dict]:
        res = self._run(self._session.list_tools())
        return [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in res.tools]

    def call(self, name: str, args: dict) -> dict:
        res = self._run(self._session.call_tool(name, args or {}))
        text = "".join(getattr(c, "text", "") for c in res.content)
        if res.isError:
            msg = text[len(_ERR_PREFIX):].split(": ", 1)[-1] if text.startswith(_ERR_PREFIX) else text
            raise ToolError(msg or f"erro na tool {name}")
        try:
            return json.loads(text) if text else {}
        except ValueError:
            return {"text": text}

    def close(self) -> None:
        try:
            if self._cm is not None:
                self._run(self._cm.__aexit__(None, None, None))
        except Exception:                       # encerrar a sessão nunca derruba a investigação
            pass
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
