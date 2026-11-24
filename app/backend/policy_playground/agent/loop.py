"""Loop do Agente Investigador (R17, design §10.4).

O modelo entra por uma porta (`converse`), então o mesmo loop roda com o Bedrock (adapters/aws.py),
com um modelo roteirizado nos testes, ou falha cedo com `ModelUnavailable` (sem modelo configurado).
A cada passo o chamador recebe o registro (`on_step`) para gravar eventos e mostrar progresso.
"""
from __future__ import annotations

import json
import re

from ..ports import ModelUnavailable  # noqa: F401  (reexporta para quem trata a falha)
from .tools import TOOL_SPECS, ToolError, ToolRegistry, unbound_numbers

_THINK = re.compile(r"<thinking>.*?</thinking>", re.S)

SYSTEM = """Você é o Agente Investigador do Policy Playground. Apoia um especialista de política de crédito
sobre uma política SINTÉTICA. O especialista já confirmou um cenário; sua tarefa é investigar efeitos
que ele não pediu para olhar.

Regras obrigatórias:
1. Comece escrevendo "PLANO:" com 2 a 4 passos curtos, e então chame as ferramentas.
2. Você nunca estima impacto. Números permitidos: os das execuções (run_scenario/compare, citando o executionId),
   os valores atuais (baseline) dos parâmetros e os fatos devolvidos por get_candidates.
3. Entenda a política antes de simular (get_policy, preview_subdag, trace_output).
4. Use get_candidates como ponto de partida e decida quais vale testar; os achados estruturais do G2 costumam
   ser os que ninguém pediu para olhar. Use read_audit para não repetir trabalho.
5. Teste ao menos uma variação do cenário e compare as duas execuções (sensibilidade).
6. Se uma ferramenta devolver erro (ex. cannot_calculate), tente uma alternativa.
7. Registre de 1 a 3 achados com register_finding. Se a tool recusar, corrija e tente de novo.
8. Você não altera a política e não decide: os achados vão para revisão humana.
9. Para citar variações use o campo deltas (de, para, delta) das execuções; não faça contas por conta própria.
10. Termine chamando submit_recommendation com uma recomendação curta em português."""

_SENSITIVITY = ("Antes de concluir: teste ao menos uma variação do cenário com run_scenario, compare as duas "
                "execuções com compare, registre o que mudou e chame submit_recommendation.")


def _visible(text: str) -> str:
    """Remove blocos <thinking> (o Nova os emite) do texto final; o raciocínio fica só na trilha."""
    return _THINK.sub("", text).strip()


def tool_config(tools=None) -> dict:
    """toolSpec da Converse. Com um cliente MCP, os nomes e descrições vêm do `tools/list` do servidor
    (descoberta); o schema de entrada usa o contrato do registro, que é o mesmo do servidor."""
    if tools is None or not hasattr(tools, "list_tools"):
        return {"tools": [{"toolSpec": t} for t in TOOL_SPECS]}
    specs = {t["name"]: t for t in TOOL_SPECS}
    listed = tools.list_tools()
    return {"tools": [{"toolSpec": {"name": t["name"], "description": t.get("description") or specs.get(t["name"], {}).get("description", ""),
                                    "inputSchema": specs[t["name"]]["inputSchema"] if t["name"] in specs
                                    else {"json": t["inputSchema"]}}} for t in listed]}


def investigate(model, registry: ToolRegistry, intent: str, overrides: dict, *, max_steps: int = 14,
                max_tokens: int = 1000, token_cap: int = 40000, on_step=None, tools=None) -> dict:
    """Roda a investigação. Levanta `ModelUnavailable` se o modelo não responder já no primeiro passo.
    `tools`: cliente MCP (padrão no produto) ou None para chamar o registro direto (testes, fallback)."""
    user = (f"Intenção do especialista: {intent}\nCenário confirmado (overrides): "
            f"{json.dumps(overrides)}\nInvestigue e registre os achados.")
    msgs = [{"role": "user", "content": [{"text": user}]}]
    tool_cfg = tool_config(tools)
    caller = tools if tools is not None else registry
    tokens, nudged = 0, set()

    def result(status, summary="", step=0):
        return {"status": status, "summary": summary, "steps": step, "tokens": tokens,
                "findings": registry.findings, "calls": registry.calls,
                "transport": getattr(caller, "transport", "direct"), "toolsDiscovered": len(tool_cfg["tools"])}

    def needs_sensitivity():
        return (len(registry.executions) < 2 and "sensitivity" not in nudged
                and len(registry.executions) < registry.max_simulations)

    for step in range(1, max_steps + 1):
        if tokens >= token_cap:
            return result("limited", "teto de tokens da investigação atingido", step - 1)
        r = model.converse(system=SYSTEM, messages=msgs, tool_config=tool_cfg, max_tokens=max_tokens)
        u = r.get("usage", {})
        tokens += int(u.get("inputTokens", 0)) + int(u.get("outputTokens", 0))
        out = r["output"]["message"]
        msgs.append(out)
        text = "".join(c.get("text", "") for c in out["content"])
        registry.note(text)                        # plano / raciocínio visível na timeline

        if r.get("stopReason") != "tool_use":
            final = _visible(text)
            if needs_sensitivity():
                nudged.add("sensitivity")
                registry.note("checklist: falta a análise de sensibilidade")
                msgs.append({"role": "user", "content": [{"text": _SENSITIVITY}]})
                _notify(on_step, registry)
                continue
            evidence = [{"overrides": x["overrides"], "comparison": x["comparison"]}
                        for x in registry.executions.values()] + registry.base_evidence()
            unbound = unbound_numbers(final, evidence)
            if (unbound or "RECOMENDA" not in final.upper()) and "recommendation" not in nudged:
                nudged.add("recommendation")
                why = f"cita números sem evidência: {unbound}" if unbound else "não trouxe a recomendação"
                registry.note(f"recomendação recusada: {why}")
                msgs.append({"role": "user", "content": [{"text":
                    f"Sua resposta final {why}. Chame submit_recommendation com a recomendação em português, "
                    "usando apenas números das execuções ou nenhum número."}]})
                _notify(on_step, registry)
                continue
            _notify(on_step, registry)
            if unbound or not final:
                return result("done", "Recomendação omitida: sem formato válido ou com números sem evidência.", step)
            return result("done", final, step)

        results = []
        for c in out["content"]:
            if "toolUse" not in c:
                continue
            tu = c["toolUse"]
            try:
                res, status = {"json": caller.call(tu["name"], tu.get("input") or {})}, "success"
            except ToolError as e:
                res, status = {"text": f"erro: {e}"}, "error"
            results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": [res], "status": status}})
        msgs.append({"role": "user", "content": results})
        if registry.recommendation:
            if needs_sensitivity():
                nudged.add("sensitivity")
                registry.recommendation = None
                registry.note("checklist: falta a análise de sensibilidade")
                msgs.append({"role": "user", "content": [{"text": _SENSITIVITY}]})
                _notify(on_step, registry)
                continue
            _notify(on_step, registry)
            return result("done", registry.recommendation, step)
        _notify(on_step, registry)
    return result("limited", f"limite de {max_steps} passos atingido", max_steps)


def _notify(on_step, registry):
    if on_step:
        on_step(registry)
