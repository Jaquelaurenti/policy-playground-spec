"""SPIKE — smoke test do servidor MCP. Suba o servidor (ver mcp_server.py) e rode: python spike/agente/mcp_smoke.py [url]"""
import asyncio, json, sys
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
async def main():
    async with streamablehttp_client((sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/mcp")) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools(); print([t.name for t in tools.tools])
            res = await s.call_tool("run_scenario", {"overrides": {"P001": 3000}})
            d = json.loads(res.content[0].text); print(d["executionId"], d["changedRecords"])
            cmp = json.loads((await s.call_tool("compare", {"execution_id": d["executionId"]})).content[0].text)
            print("motivo 102:", cmp["comparison"]["motivos"]["102"])
            bad = await s.call_tool("register_finding", {"title":"x","text":"sobe 42","ruleRefs":["R005"],"executionIds":[d["executionId"]]})
            print("isError:", bad.isError, bad.content[0].text[:90])
asyncio.run(main())
