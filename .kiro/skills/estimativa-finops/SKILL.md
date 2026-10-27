---
name: estimativa-finops
description: Estima o custo mensal e o custo por hipótese do Policy Playground (infraestrutura AWS e tokens do Bedrock) usando o MCP de preços da AWS. Use quando uma mudança alterar serviços, capacidade, modelo de IA, tamanho de prompt ou volume de uso, ou quando pedirem o impacto de custo de uma decisão.
---

# Estimativa de FinOps

## Premissas de referência

Parta das premissas da seção 8 de `arquitetura/arquitetura-da-aplicacao.md`:

- 50 especialistas, 10 hipóteses por dia, 22 dias úteis: 11 mil hipóteses por mês.
- Até 32 mil tokens por hipótese (teto da seção 9.1); cerca de 10 mil no fixture.
- Infraestrutura de produção perto de US$ 210 por mês, quase toda fixa.
- Meta de custo por hipótese: US$ 0,05.

Se o usuário der outros números, use os dele e diga quais mudaram.

## Passos

1. Liste os componentes afetados pela mudança.
2. Consulte os preços com o MCP `aws-pricing` (região us-east-1). Se ele não estiver conectado, diga isso e use os preços citados no documento de arquitetura, marcando-os como "preço de referência, conferir".
3. Calcule:
   - custo mensal da infraestrutura, antes e depois;
   - custo de tokens por hipótese pela fórmula da seção 8.1 (entrada sem cache, leitura de cache, saída, escrita de cache dividida pelas hipóteses da sessão);
   - custo por hipótese total = tokens + infraestrutura ÷ hipóteses no mês.
4. Confira a cota do Bedrock: `cota ≥ hipóteses/min no pico × tokens por hipótese ÷ 0,7 ÷ 0,8`.

## Saída

| Item | Antes (US$/mês) | Depois (US$/mês) | Diferença |
| --- | --- | --- | --- |

Depois da tabela: custo por hipótese antes e depois, comparado com a meta de US$ 0,05, e a cota necessária. Feche com uma frase sobre o pilar de Otimização de custos e se a mudança vale o que custa.

## Regras

- Mostre a conta. Não arredonde antes do final.
- Nunca apresente estimativa como preço confirmado.
