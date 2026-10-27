---
name: teste-de-mesa
description: Faz o teste de mesa de uma mudança na arquitetura ou no fluxo do Policy Playground. Percorre o caminho passo a passo, registra o estado de tabelas, filas e buckets e confere cada passo contra os requisitos do SDD. Use quando alguém propuser mudar um componente, um fluxo, uma regra de idempotência ou um limite, ou pedir para validar se a arquitetura para de pé.
---

# Teste de mesa da arquitetura

Você vai validar uma mudança como um teste de mesa clássico: estado inicial, um passo por vez, o que muda em cada passo e a verificação contra o requisito.

## Antes de começar

1. Leia a mudança proposta pelo usuário e diga em uma frase o que ela altera.
2. Leia `arquitetura/arquitetura-da-aplicacao.md`, em especial as seções 4 (fluxo assíncrono), 5 (dados) e 6 (falhas).
3. Identifique quais dos 9 cenários do simulador a mudança afeta: fluxo ponta a ponta, retry com a mesma chave, reuso por hash, Bedrock fora do ar, interrupção do Spot, queda da AZ a, rajada com a cota mínima, usuário sem acesso, pipeline de auditoria parado. O simulador está em `arquitetura/simulador/teste-de-mesa.html`.

## Como montar o teste

Para cada cenário afetado, monte uma tabela com estas colunas:

| # | Componente | Ação | Estado alterado | Verificação |
| --- | --- | --- | --- | --- |

- **Estado alterado** cita o que muda de fato: evento em `pp-events` (com `seq`), item em `pp-state`, mensagem na fila `llm` ou `sim`, objeto em `results/`, linha na auditoria.
- **Verificação** cita o requisito ou ADR (por exemplo `R14.5`, `NFR Reliability 3`, `ADR-05`) e diz ✓, ✗ ou ⚠ (limitação conhecida).

## Regras

- Não invente latência nem custo. Se precisar de número, diga que é premissa e de onde vem.
- Toda falha (✗) vira uma recomendação concreta: qual ADR muda e como.
- Confira sempre as invariantes de `.kiro/steering/principios-ia-e-evidencia.md`.
- Se a mudança afetar o simulador, diga qual cenário em `arquitetura/simulador/teste-de-mesa.html` precisa ser atualizado e quais verificações acrescentar.

## Saída

1. Veredito em uma linha: "para de pé", "para de pé com limitação" ou "não para de pé".
2. As tabelas por cenário.
3. Lista de ações, se houver.
