---
inclusion: always
---

# IA propõe, execução determinística comprova, pessoas decidem

Estas regras valem para todo código, prompt, teste e documento deste projeto. Se um pedido contrariar alguma delas, pare e explique o conflito antes de seguir.

## A IA nunca produz número de impacto

- Número de impacto só sai de um `ExecutionResult` com `source = deterministic` (R5.1, R5.10).
- Saída de modelo é gravada como `source = ai_suggestion`, nasce com `evidenceLevel = none` e **não tem campo numérico de impacto**.
- Se a execução falhar, o resultado é `cannot_calculate`. Nunca substitua por estimativa (R5.7).

## Evidência é derivada, nunca atribuída

| `mode` | `status` | `evidenceLevel` |
| --- | --- | --- |
| SIMULADO | ok | simulated |
| REAL | validated | study_validated |
| qualquer | qualquer outro | none |

- Um resultado SIMULADO nunca chega a `study_validated`.
- Todo número SIMULADO aparece com o selo SIMULADO na interface.
- Aceitar um finding muda o `investigationState`, nunca o `evidenceLevel`.

## Pessoas decidem

- Toda modificação proposta pela IA passa por confirmação humana antes de virar cenário (R4).
- Decisões são Accept, Reject ou Defer, com justificativa obrigatória, e nunca são editadas: uma nova decisão substitui a anterior por `supersedes` (R10.5, R10.6).
- Nada altera política em produção. PR é pedido de revisão, nunca merge ou deploy (R12.2).

## Dados e privacidade

- Nenhuma linha do `Motivo de Decisão` entra no prompt (R15.2). No MVP, só o runner real do C1 lê essa tabela (ADR-17).
- O avaliador de regras é fechado: só `json_extract`, `case_when` com gramática validada e `matrix_lookup`. Nunca execute expressão gerada pelo modelo (D-6).
