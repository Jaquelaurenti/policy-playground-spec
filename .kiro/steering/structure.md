---
inclusion: always
---

# Estrutura do repositório

```
.kiro/
  specs/policy-playground/   requirements.md, design.md, tasks.md e fixtures/ (Policy Spec sintético)
  steering/                  regras que o agente segue em toda conversa
  hooks/                     automações disparadas quando o agente salva arquivos
  skills/                    fluxos sob demanda: /teste-de-mesa, /adr, /estimativa-finops
  settings/mcp.json          servidores MCP do projeto (sem segredos)
arquitetura/                 documento de arquitetura, trade-offs, imagens, simulador e fontes
docs/                        working backwards e fluxo de colaboração
tools/                       utilitários de linha de comando (ex.: validador do Policy Spec)
tests/                       testes automatizados
.github/                     template de PR e CODEOWNERS
```

## Convenções

- Nomes de arquivos e pastas em minúsculas, com hífen (`teste-de-mesa.html`). Módulos Python com underscore.
- Documentação e mensagens para o usuário em português. Identificadores de código e eventos em inglês (`HypothesisStructured`, `ExecutionCompleted`).
- O Policy Spec em `fixtures/` é entrada de outra etapa e **nunca** é alterado pelo Playground (R16.3). Metadados próprios ficam no arquivo de extensions.
- Uma decisão de arquitetura nova vira ADR na seção 10 de `arquitetura/arquitetura-da-aplicacao.md` (use a skill `/adr`).
- Uma tarefa nova vem de `tasks.md` e começa pelo *Start task* do Kiro.
