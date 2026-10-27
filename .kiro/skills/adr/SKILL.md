---
name: adr
description: Registra uma nova decisão de arquitetura (ADR) do Policy Playground no formato do time, com alternativas, trade-offs pelos seis pilares do AWS Well-Architected e o que muda na spec. Use quando o time decidir trocar um serviço, um padrão, um limite ou uma premissa da arquitetura.
---

# Registrar uma decisão de arquitetura

## Passos

1. Leia a tabela de ADRs na seção 10 de `arquitetura/arquitetura-da-aplicacao.md` e descubra o próximo número livre (hoje vai até ADR-18).
2. Confira se a nova decisão contradiz ou substitui uma existente. Se substituir, diga qual e por quê; a antiga não é apagada.
3. Pergunte ao usuário o que faltar entre: problema, opção escolhida, alternativas consideradas e motivo.

## O que escrever

**Na tabela de ADRs** (seção 10 da arquitetura), uma linha:

| ADR | Decisão | Motivo principal | Revisa no design.md |

**Em `arquitetura/tradeoffs-well-architected.md`:**
- uma linha no mapa de impacto (seção 1), com ▲, ▼ ou · para OPS, SEC, REL, PERF, COST e SUS;
- uma linha na tabela do tema certo da seção 2: *Em vez de*, *Ganhamos*, *Pagamos*, *Revisitar quando*;
- se a decisão for difícil de desfazer, um item na seção 5.

**Na spec**, liste quais seções de `design.md` e quais tasks de `tasks.md` precisam mudar. Não edite a spec sem confirmação do usuário.

## Regras

- Escreva em português, frases curtas, com números e nomes de serviço reais.
- Todo ▼ precisa aparecer em *Pagamos*. Não deixe pilar prejudicado sem explicação.
- Se a decisão mexer em custo, rode também a skill `/estimativa-finops`.
- Se mexer em fluxo ou falha, rode também a skill `/teste-de-mesa`.
