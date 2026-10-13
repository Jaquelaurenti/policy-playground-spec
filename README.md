# Policy Playground — Technical Spec (Spec-Driven Development)

Entrega documental do **Policy Playground** para o hackathon (AWS Builders League). Este repositório contém a especificação técnica do projeto seguindo o fluxo de Spec-Driven Development do Kiro: **Requirements → Design → Tasks**.

> **Entrega documental.** Esta entrega é a especificação. Ela **não** inclui código funcional nem as Tasks implementadas — as Tasks são um plano de implementação, não evidência de que o produto já foi construído.

## O que é o Policy Playground

Um ambiente interativo para especialistas de política de crédito testarem hipóteses de negócio sem escrever SQL ou Python, visualizarem impacto com evidência e investigarem cenários não previstos com apoio de agentes de IA.

Princípio central do produto:

> **AI proposes. Deterministic execution proves. Humans decide.**
>
> A IA interpreta intenção, estrutura hipóteses e sugere investigações. A execução determinística é a única fonte dos números de impacto. A decisão final é sempre humana.

## Os três artefatos

| # | Documento | O que contém |
|---|-----------|--------------|
| 📋 | [requirements.md](./requirements.md) | Requisitos (R1–R16) + NFRs em formato EARS: o que a solução deve fazer, com critérios de aceite, premissas e questões em aberto. |
| 🎨 | [design.md](./design.md) | Desenho da solução: arquitetura de aplicação única com módulos internos, modelo de dados, fluxos, execução determinística, investigação por IA, governança e um diagrama de visão geral (Mermaid). |
| ✅ | [tasks.md](./tasks.md) | Plano de implementação: tarefas incrementais e verificáveis, vinculadas a Requirements e Design, com as tarefas condicionais (dependentes de acesso ao SYN) separadas do núcleo do MVP. |

## Material de apoio

- [working-backwards.md](./working-backwards.md) — documento Working Backwards (press release / FAQ) que originou o produto. Contexto de negócio, não é um dos três artefatos.
- [`fixtures/`](./fixtures/) — fixture **100% sintético** usado como contrato de referência do MVP demonstrativo.
  - [policy-playground-demo-policy.json](./fixtures/policy-playground-demo-policy.json) — exemplo reduzido de uma Policy Spec.
  - [policy-playground-demo-policy-README.md](./fixtures/policy-playground-demo-policy-README.md) — propósito e limites do fixture.

> ⚠️ **Sobre o fixture:** é um exemplo **totalmente fictício**, criado para a fase de Design. Não representa a política real de Microcrédito nem dados, código, regras, valores ou resultados do Itaú/FICO. Não deve ser usado para decisões de crédito.

## Ordem de leitura sugerida

1. `requirements.md` (o quê e por quê)
2. `design.md` (como) — comece pela seção **"Solution Overview — Mermaid"** no fim para a visão geral
3. `tasks.md` (o plano de trabalho)
