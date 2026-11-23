# Spike: Agente Investigador (descartável, não vai para o `main`)

Prova de conceito feita **antes** do hackathon para validar a abordagem da R17 (design §10.4). O código definitivo é **reescrito no sprint** dentro de `app/backend/`, nas tasks 25–29, um PR por integrante. A regra 2 do guia pede código novo, então este diretório serve só de referência e de ensaio.

## O que o spike comprovou

| Pergunta | Resultado |
|---|---|
| O motor atual serve de tool sem mudanças? | Sim. As 8 tools (`get_policy`, `preview_subdag`, `trace_output`, `run_scenario`, `compare`, `get_candidates`, `read_audit`, `register_finding`) só embrulham funções existentes |
| O loop da Converse com `toolConfig` fecha? | Sim, com um modelo stub roteirizado contra o motor real (11 testes): plano, sensibilidade com `compare`, recusa e correção do achado, reescrita da recomendação |
| `cannot_calculate` e RBAC? | `cannot_calculate` vira erro recuperável e o agente tenta outra via; um Viewer lê, mas não executa |
| Dá para impedir número inventado? | Sim. `register_finding` recusa número ausente das execuções citadas; a recomendação final passa pelo mesmo teste |
| Tool errada ou parâmetro inexistente quebra o loop? | Não. Vira `toolResult status=error` |
| O mesmo registro vira servidor MCP? | Sim. FastMCP em Streamable HTTP stateless; um cliente MCP listou as 8 tools, rodou `run_scenario` e `compare` e recebeu `isError` na recusa |
| Conflito de dependências? | **Sim.** `mcp` 2.x puxa Starlette 1.x e quebra o `fastapi==0.115.6`. Fixar `mcp==1.9.4` |
| Funciona no Bedrock real? | **Ainda não testado.** Rodar `run_bedrock.py` no CloudShell hoje (passo 2 abaixo) |

## Como rodar

```bash
# na raiz do repo
pip install -r app/backend/requirements.txt "mcp==1.9.4"

# 1. testes do loop (sem AWS)
python -m unittest discover -s spike/agente

# 2. contra o Bedrock (CloudShell, com o Nova Lite habilitado no console do Bedrock)
python spike/agente/run_bedrock.py --model us.amazon.nova-lite-v1:0 \
  --intent "aumentar a renda mínima para 3000" --set P001=3000

# 3. servidor MCP local + smoke test
uvicorn --app-dir spike/agente mcp_server:app --port 8765 &
python spike/agente/mcp_smoke.py http://127.0.0.1:8765/mcp
```

No passo 2, o esperado é: o agente escreve o PLANO, lê a política, simula `P001=3000` e pelo menos uma variação, compara as duas, registra 1 a 3 achados citando `executionIds` e termina com a RECOMENDAÇÃO. Se o Nova Lite errar o formato das tools com frequência, testar `--model us.anthropic.claude-3-5-haiku-20241022-v1:0` (precisa estar habilitado na conta) e anotar a escolha para o `PP_MODEL_ID`.

---

O plano do sprint, a divisão em frentes, os contratos, o cronograma e o roteiro da demo estão em `docs/proposta-hackathon.md` (versão unificada com a proposta da Jessica).
