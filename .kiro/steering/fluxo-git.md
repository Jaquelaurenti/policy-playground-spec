---
inclusion: auto
name: fluxo-git
description: Convenções de branch, commit e pull request do time CredIA Girls. Use ao criar branch, escrever mensagem de commit, abrir ou revisar PR.
---

# Fluxo de trabalho no Git

- **Nunca commite direto no `main`.** O branch é protegido: merge só por PR com 1 aprovação.
- **Branch por issue:** `tipo/numero-descricao-curta`, por exemplo `feat/7-validador-policy-spec` ou `docs/4-steering`.
- **Commits** no padrão Conventional Commits, em português: `feat(validador): bloqueia ciclo no DAG`. Tipos: `feat`, `fix`, `docs`, `test`, `chore`, `refactor`.
- **PR** pelo template de `.github/pull_request_template.md`, citando a issue (`Closes #7`) e os requisitos tocados (R1–R16, NFRs, ADRs).
- **Review:** o `CODEOWNERS` pede revisão de quem cuida da pasta. Comente com sugestão concreta; aprove só depois de rodar os testes.
- Antes de abrir o PR, rode `python3 -m unittest discover -s tests -v`.

Detalhes em #[[file:docs/colaboracao/fluxo-de-trabalho.md]].
