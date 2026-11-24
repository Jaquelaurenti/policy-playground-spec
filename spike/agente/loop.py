"""SPIKE (descartável) — loop do Agente Investigador sobre a Converse API do Bedrock.

O cliente é injetável: nos testes entra um stub roteirizado; no CloudShell, boto3 `bedrock-runtime`.
Saída: achados presos a execuções + recomendação em texto, também checada contra as evidências.
"""
from __future__ import annotations

import json
import re

from tool_registry import TOOL_SPECS, ToolError, ToolRegistry, unbound_numbers

_THINK = re.compile(r"<thinking>.*?</thinking>", re.S)


def _visible(text: str) -> str:
    """Remove blocos <thinking> (o Nova os emite) do texto final; o raciocínio fica só na trilha."""
    return _THINK.sub("", text).strip()

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
9. Termine com "RECOMENDAÇÃO:" em português, curta, usando só números que vieram das execuções."""


def investigate(client, model_id: str, registry: ToolRegistry, intent: str, overrides: dict,
                max_steps: int = 12, max_tokens: int = 1000, token_cap: int = 60000) -> dict:
    user = (f"Intenção do especialista: {intent}\nCenário confirmado (overrides): "
            f"{json.dumps(overrides)}\nInvestigue e registre os achados.")
    msgs = [{"role": "user", "content": [{"text": user}]}]
    tool_cfg = {"tools": [{"toolSpec": t} for t in TOOL_SPECS]}
    tokens, nudged = 0, set()

    def result(status, summary="", step=0):
        return {"status": status, "summary": summary, "steps": step, "tokens": tokens,
                "findings": registry.findings, "calls": registry.calls}

    for step in range(1, max_steps + 1):
        if tokens >= token_cap:
            return result("limited", "teto de tokens atingido", step - 1)
        r = client.converse(modelId=model_id, system=[{"text": SYSTEM}], messages=msgs, toolConfig=tool_cfg,
                            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2})
        u = r.get("usage", {})
        tokens += int(u.get("inputTokens", 0)) + int(u.get("outputTokens", 0))
        out = r["output"]["message"]
        msgs.append(out)
        text = "".join(c.get("text", "") for c in out["content"])
        if r.get("stopReason") != "tool_use":
            registry.note(text)
            final = _visible(text)
            # checklist antes de aceitar a conclusão (cada item cobrado uma única vez)
            if len(registry.executions) < 2 and "sensitivity" not in nudged \
                    and len(registry.executions) < registry.max_simulations:
                nudged.add("sensitivity")
                registry.note("checklist: falta a análise de sensibilidade")
                msgs.append({"role": "user", "content": [{"text":
                    "Antes de concluir: teste ao menos uma variação do cenário com run_scenario, compare as duas "
                    "execuções com compare e registre o que mudou, se for relevante."}]})
                continue
            evidence = [{"overrides": x["overrides"], "comparison": x["comparison"]}
                        for x in registry.executions.values()] + registry.base_evidence()
            unbound = unbound_numbers(final, evidence)
            if (unbound or "RECOMENDA" not in final.upper()) and "recommendation" not in nudged:
                nudged.add("recommendation")
                why = (f"cita números sem evidência: {unbound}" if unbound
                       else "não começa com \"RECOMENDAÇÃO:\"")
                registry.note(f"recomendação recusada: {why}")
                msgs.append({"role": "user", "content": [{"text":
                    f"Sua resposta final {why}. Escreva só a linha \"RECOMENDAÇÃO: ...\" em português, sem "
                    "<thinking>, usando apenas números das execuções ou nenhum número."}]})
                continue
            if unbound or not final:
                return result("done", "Recomendação omitida: sem formato válido ou com números sem evidência.", step)
            return result("done", final, step)
        registry.note(text)                       # plano / raciocínio visível na timeline
        results = []
        for c in out["content"]:
            if "toolUse" not in c:
                continue
            tu = c["toolUse"]
            try:
                res, status = {"json": registry.call(tu["name"], tu.get("input") or {})}, "success"
            except ToolError as e:
                res, status = {"text": f"erro: {e}"}, "error"
            results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": [res], "status": status}})
        msgs.append({"role": "user", "content": results})
    return result("limited", f"limite de {max_steps} passos atingido", max_steps)
