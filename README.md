# Policy Playground — Technical Spec (Spec-Driven Development)

Entrega documental do **Policy Playground** para o hackathon (AWS Builders League). Este repositório contém a especificação técnica do projeto seguindo o fluxo de Spec-Driven Development do Kiro: **Requirements → Design → Tasks**.

> **Especificação + MVP de demonstração.** Além do spec, o repositório traz um MVP funcional sobre o fixture **sintético** (`app/`), com o `SimulatedRunner`: todo número exibido leva o selo SIMULADO e não é impacto real. Os condicionais C1–C5 (runner real, PR real etc.) não estão implementados.

## O que é o Policy Playground

Um ambiente interativo para especialistas de política de crédito testarem hipóteses de negócio sem escrever SQL ou Python, visualizarem impacto com evidência e investigarem cenários não previstos com apoio de agentes de IA.

Princípio central do produto:

> **AI proposes. Deterministic execution proves. Humans decide.**
>
> A IA interpreta intenção, estrutura hipóteses e sugere investigações. A execução determinística é a única fonte dos números de impacto. A decisão final é sempre humana.

## Estrutura do repositório

```
.
├── .kiro/
│   └── specs/
│       └── policy-playground/          ← spec reconhecido pelo Kiro
│           ├── requirements.md
│           ├── design.md
│           ├── tasks.md
│           └── fixtures/
│               ├── policy-playground-demo-policy.json      ← Policy Spec (não alterado)
│               ├── policy-playground-demo-extensions.json  ← metadados do Playground
│               ├── policy-playground-demo-dataset.json     ← propostas sintéticas
│               └── policy-playground-demo-policy-README.md
├── app/
│   ├── backend/                        ← domínio, motor determinístico, API (FastAPI) e testes
│   ├── frontend/                       ← React 18 + Vite: DAG, hipóteses, achados, decisões, auditoria
│   └── Dockerfile                      ← mesma imagem local e na Lambda
├── infra/                              ← CDK (Python): perfil demo de custo zero (ADR-19)
├── scripts/                            ← bootstrap no CloudShell e criação de usuários da demo
├── .github/workflows/                  ← CI, deploy e destroy via OIDC
├── docs/
│   └── working-backwards.md            ← PR/FAQ de origem (contexto de negócio)
└── README.md
```

Os três artefatos ficam em `.kiro/specs/policy-playground/`, que é o caminho em que o Kiro procura specs. Ao abrir o repositório no Kiro, o spec aparece no painel **Specs** e cada item de `tasks.md` pode ser iniciado pela ação _Start task_.

## Rodar a demo

### Local (sem AWS)

```bash
cd app/frontend && npm ci && npm run build && cd ../backend
pip install -r requirements.txt
python -m uvicorn policy_playground.api.app:app --port 8000
```

Abra http://localhost:8000. O seletor no topo troca o perfil (Policy Specialist, Risk Approver, Data Analyst, Viewer). Tudo fica em memória, sem modelo de IA: as sugestões vêm só dos geradores determinísticos G1 e G2. Para desenvolver o front com recarga automática, rode `npm run dev` em `app/frontend` com o backend ligado.

Testes: `python -m unittest discover -s tests` na raiz (validador do Policy Spec) e em `app/backend` (domínio, API e adaptadores AWS com `moto`; instale `requirements-dev.txt`).

### Na AWS, com custo zero (ADR-19)

Sem chave de acesso em lugar nenhum: o GitHub Actions assume um papel da conta via OIDC.

1. **CloudShell** (console da AWS, ícone `>_`), uma vez por conta:
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/Jaquelaurenti/policy-playground-spec/main/scripts/cloudshell-bootstrap.sh
   bash cloudshell-bootstrap.sh Jaquelaurenti/policy-playground-spec us-east-1
   ```
2. **GitHub** → Settings → Secrets and variables → Actions → *Variables*: crie `AWS_ROLE_ARN` (o script imprime o valor), `AWS_REGION` e `ALERT_EMAIL`. `PP_MODEL_ID=us.amazon.nova-lite-v1:0` é opcional (habilite o modelo no console do Bedrock antes).
3. **Actions → Deploy demo (AWS) → Run workflow.** O resumo da execução mostra a URL.
4. **Usuários**, de novo no CloudShell (a senha temporária vai direto para o e-mail da pessoa):
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/Jaquelaurenti/policy-playground-spec/main/scripts/create-demo-user.sh
   bash create-demo-user.sh pessoa@exemplo.com policy-specialist
   ```
5. Ao terminar: **Actions → Destroy demo (AWS)** com a confirmação `destruir`.

Confira em Billing → Credits se os créditos cobrem os serviços usados e acompanhe os alertas de orçamento (US$ 1 e US$ 5).

### Na sua própria conta AWS (outra pessoa do time)

Cada pessoa sobe a demo **no próprio fork**, ligado à **própria conta AWS**. Nenhum arquivo de código precisa mudar: tudo o que é pessoal fica em variáveis do GitHub e nos argumentos do script de bootstrap.

**O que você muda e onde**

| O quê | Onde | Valor |
| --- | --- | --- |
| Repositório | Botão **Fork** no GitHub | `<seu-usuario>/policy-playground-spec` |
| Conta e região da AWS | Argumentos do `cloudshell-bootstrap.sh` | `<seu-usuario>/policy-playground-spec` e a região, ex. `us-east-1` |
| Papel que o deploy assume | Fork → Settings → Secrets and variables → Actions → aba **Variables** → `AWS_ROLE_ARN` | O ARN que o script imprime no final |
| Região do deploy | Mesma tela → `AWS_REGION` | A mesma região do bootstrap |
| Alertas de custo | Mesma tela → `ALERT_EMAIL` | O seu e-mail |
| Modelo de IA (opcional) | Mesma tela → `PP_MODEL_ID` | `us.amazon.nova-lite-v1:0`, ou não crie a variável para rodar sem IA |
| Quem pode fazer deploy | Fork → Settings → **Environments** → `demo` | *Deployment branches*: só `main`. *Required reviewers*: você, se quiser aprovar cada deploy |

**O que não muda:** `app/`, `infra/` e os workflows. Conta, região e repositório não estão escritos no código.

**Passo a passo**

1. Faça o **fork** do repositório e, no fork, abra a aba **Actions** e clique em *I understand my workflows, go ahead and enable them*. Forks vêm com os workflows desligados.
2. No **CloudShell da sua conta** (ícone `>_` no console, na região escolhida), rode o bootstrap apontando para o **seu fork**:
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/<seu-usuario>/policy-playground-spec/main/scripts/cloudshell-bootstrap.sh
   bash cloudshell-bootstrap.sh <seu-usuario>/policy-playground-spec us-east-1
   ```
   O script valida o `<dono>/<repo>` e a região antes de mexer na conta. Depois cria o provedor OIDC do GitHub, ou acrescenta a audience `sts.amazonaws.com` se o provedor já existir sem ela, e cria o papel `policy-playground-github-deploy`, que só o seu fork pode assumir. Por fim, faz o bootstrap do CDK.

   O GitHub pode identificar o repositório no token em dois formatos: o clássico (`repo:dono/repo`) e o imutável, com IDs numéricos. Por padrão, o papel aceita os dois. A variável `PP_SUB_FORMAT` muda isso:
   - `PP_SUB_FORMAT=immutable` aceita só o formato imutável. É a opção mais segura, porque fica presa aos IDs e não ao nome do repositório.
   - `PP_SUB_FORMAT=classic` aceita só o formato clássico. Use para fork privado, porque a API pública do GitHub não devolve os IDs dele. Nos outros formatos, sem os IDs, o script para com erro.
3. No fork, crie as **variáveis** da tabela acima (aba *Variables*, não *Secrets*) e o environment **`demo`** restrito à `main`.
4. Rode **Actions → Deploy demo (AWS) → Run workflow** no fork. Se o environment exigir revisão, aprove em *Review deployments*. A URL aparece no resumo da execução.
5. Crie os usuários com `scripts/create-demo-user.sh`, como no passo 4 da seção anterior, e ao terminar rode **Destroy demo (AWS)**.

**Problemas comuns**

- **`Not authorized to perform sts:AssumeRoleWithWebIdentity`**: o papel não confia no seu fork. Rode o bootstrap de novo com o `<seu-usuario>/repo` certo. Se você usou `PP_SUB_FORMAT=immutable` ou `classic`, confirme que o formato bate com o do seu repositório. Na dúvida, rode sem a variável para aceitar os dois.
- **`Your account must be verified before you can add new CloudFront resources`**: a conta é nova e ainda está em verificação, o que também impede o CloudShell de abrir. Confira a forma de pagamento e os dados da conta e, se passar de dois dias, abra um chamado gratuito em *Support → Account and billing*. Depois, apague a pilha `PolicyPlaygroundDemo` que ficou em `ROLLBACK_COMPLETE` (CloudFormation → Excluir) e rode o deploy de novo.
- **CloudShell não abre**: é a mesma verificação de conta. Os três passos do bootstrap também podem ser feitos no console: IAM → Provedores de identidade, IAM → Funções e CloudFormation com o modelo de `npx aws-cdk@2.173.4 bootstrap --show-template`.

## Os três artefatos

| #   | Documento                                                          | O que contém                                                                                                                                                                                                                                                                                                                                                             |
| --- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 📋  | [requirements.md](./.kiro/specs/policy-playground/requirements.md) | Requisitos (R1–R16) + NFRs em formato EARS: o que a solução deve fazer, com critérios de aceite, premissas e questões em aberto.                                                                                                                                                                                                                                         |
| 🎨  | [design.md](./.kiro/specs/policy-playground/design.md)             | Desenho da solução: aplicação única com módulos internos, modelo de dados, fluxos, execução determinística, investigação por IA (incluindo geradores determinísticos de candidatos), governança, execução assíncrona e idempotente, visão de implantação AWS (ECS Fargate) com caminho de escalabilidade, alternativas não adotadas e diagrama de visão geral (Mermaid). |
| ✅  | [tasks.md](./.kiro/specs/policy-playground/tasks.md)               | Plano de implementação: tarefas incrementais e verificáveis, vinculadas a Requirements e Design, com as tarefas condicionais (dependentes de acesso ao POLITICA DE CREDITO) separadas do núcleo do MVP.                                                                                                                                                                  |

## Material de apoio

- [docs/working-backwards.md](./docs/working-backwards.md) — documento Working Backwards (press release / FAQ) que originou o produto. Contexto de negócio, não é um dos três artefatos.
- [`fixtures/`](./.kiro/specs/policy-playground/fixtures/) — fixture **100% sintético** usado como contrato de referência do MVP demonstrativo.
  - [policy-playground-demo-policy.json](./.kiro/specs/policy-playground/fixtures/policy-playground-demo-policy.json) — exemplo reduzido de uma Policy Spec, mantido exatamente como foi recebido.
  - [policy-playground-demo-extensions.json](./.kiro/specs/policy-playground/fixtures/policy-playground-demo-extensions.json) — metadados do Playground que complementam o Policy Spec sem alterá-lo: proveniência Git, áreas POLITICA DE CREDITO, domínios dos parâmetros e referência ao dataset.
  - [policy-playground-demo-dataset.json](./.kiro/specs/policy-playground/fixtures/policy-playground-demo-dataset.json) — 12 propostas sintéticas versionadas, usadas pelo `SimulatedRunner`.
  - [policy-playground-demo-policy-README.md](./.kiro/specs/policy-playground/fixtures/policy-playground-demo-policy-README.md) — propósito e limites do fixture.

> ⚠️ **Sobre o fixture:** é um exemplo **totalmente fictício**, criado para a fase de Design. Não representa a política real de Microcrédito nem dados, código, regras, valores ou resultados do Politica/FICO. Não deve ser usado para decisões de crédito.

## Status dos documentos

| Documento       | Versão | Status                                          |
| --------------- | ------ | ----------------------------------------------- |
| requirements.md | 1.2    | 1.0 aprovado; revisões 1.1 e 1.2 em revisão     |
| design.md       | 1.2    | 1.0 aprovado; revisões 1.1 e 1.2 em revisão     |
| tasks.md        | 1.2    | Rascunho em revisão; implementação não iniciada |

O que mudou em cada revisão está na seção **Revision History** de cada documento. A revisão 1.2 incorpora as decisões que o time registrou na fase de inception; elas estão no **Decision Log** do `requirements.md`, e as alternativas avaliadas e não adotadas estão no §17 do `design.md`.

## Ordem de leitura sugerida

1. `requirements.md` (o quê e por quê)
2. `design.md` (como) — comece pela seção **"Solution Overview — Mermaid"** no fim para a visão geral
3. `tasks.md` (o plano de trabalho)
