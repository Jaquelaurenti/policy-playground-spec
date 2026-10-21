# Trade-offs das decisões — AWS Well-Architected

Time **CredIA Girls** · AWS Builders League · 20/10/2026

A arquitetura do Policy Playground prioriza **Confiabilidade**, **Segurança** e **Otimização de custos**. O preço é pago principalmente em **Excelência operacional**: há mais peças para operar (Pipes, Firehose, AppConfig, duas tabelas, filas por tipo). O segundo custo está em **Eficiência de desempenho** durante rajadas com a cota mínima do Bedrock. Nenhuma decisão contraria as escolhas do time na inception (D-Q1 a D-DQ4). Quatro delas são difíceis de desfazer e estão marcadas na seção 5.

Este documento complementa a [arquitetura da aplicação](arquitetura-da-aplicacao.md), que tem o detalhe de cada ADR. Para o vocabulário dos pilares, ver o [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html). Para IA generativa, ver a [Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html).

## Como ler

| Sigla | Pilar |
| --- | --- |
| OPS | Excelência operacional |
| SEC | Segurança |
| REL | Confiabilidade |
| PERF | Eficiência de desempenho |
| COST | Otimização de custos |
| SUS | Sustentabilidade |

Nas tabelas, **▲** quer dizer que a decisão favorece o pilar, **▼** que cobra um preço nele, e **·** que o efeito é neutro ou desprezível.

## 1. Mapa de impacto

| ADR | Decisão | OPS | SEC | REL | PERF | COST | SUS |
| --- | --- | :-: | :-: | :-: | :-: | :-: | :-: |
| ADR-01 | Monólito modular, uma imagem ARM, papéis `api` e `worker-*` | ▲ | · | ▲ | ▲ | ▲ | ▲ |
| ADR-02 | Estruturação, sugestões e execução como jobs assíncronos | ▼ | · | ▲ | ▲ | · | · |
| ADR-03 | Uma escrita por comando; Streams → Pipes → filas e Firehose | ▼ | ▲ | ▲ | · | · | · |
| ADR-04 | `pp-events` imutável e `pp-state` mutável | ▼ | ▲ | ▲ | · | ▼ | · |
| ADR-05 | Idempotência de requisição + cache de resultado por hash | · | · | ▲ | ▲ | ▲ | ▲ |
| ADR-06 | Workers em Fargate Spot, base sob demanda só no `worker-llm` | ▼ | · | ▼ | ▼ | ▲ | ▲ |
| ADR-07 | VPC sem NAT, endpoints de interface em 2 AZs | ▼ | ▲ | ▲ | · | ▼ | · |
| ADR-08 | SLO de 99,5% por canary; DR por backup e restore | ▲ | · | ▲ | · | ▲ | ▲ |
| ADR-09 | JWT authorizer validando o Entra ID por OIDC, sem Cognito | ▲ | ▲ | ▲ | ▲ | ▲ | · |
| ADR-10 | Modelo por tarefa escolhido por eval; cache de prompt | ▼ | · | · | ▲ | ▲ | ▲ |
| ADR-11 | Orçamento de tokens por usuário e "modo econômico" | ▲ | ▲ | ▲ | ▼ | ▲ | ▲ |
| ADR-12 | us-east-1 no hackathon; sa-east-1 só com residência verificada | · | ▼ | · | ▲ | ▲ | · |
| ADR-13 | Prompt montado do sub-DAG, com tetos de bytes, regras e tokens | · | ▲ | ▲ | ▲ | ▲ | ▲ |
| ADR-14 | Limites e IA como feature flags no AppConfig | ▲ | · | ▲ | · | ▲ | · |
| ADR-15 | Vazão do `worker-llm` derivada da cota mínima, com token bucket | · | · | ▲ | ▼ | ▲ | · |
| ADR-16 | Retenção da auditoria por ambiente: compliance em produção | ▼ | ▲ | · | · | ▼ | ▼ |
| ADR-17 | MVP sintético; Motivo de Decisão só no C1 | ▲ | ▲ | · | · | ▲ | · |
| ADR-18 | PR real por Lambda fora da VPC | ▼ | ▼ | · | · | ▲ | · |

Contagem de ▼ por pilar: OPS 8, SEC 2, REL 1, PERF 3, COST 3, SUS 1. A conta operacional é a mais alta, e é a que o time paga todo dia. Por isso a seção 6 concentra as ações de mitigação nela.

## 2. Trade-offs por decisão

### Computação e execução

| ADR | Em vez de | Ganhamos | Pagamos | Revisitar quando |
| --- | --- | --- | --- | --- |
| ADR-01 Monólito modular | Microsserviços por fronteira, ou Go + Python separados (§17 do design) | Um build, um deploy e uma imagem; menos custo fixo; o domínio fica testável sem rede | Um bug no núcleo afeta API e workers ao mesmo tempo; o escalonamento é por papel, não por módulo | Mais de um time passar a mexer no código, ou um módulo precisar de outra linguagem |
| ADR-02 Jobs assíncronos | Chamar o Bedrock dentro da requisição | A API não depende da IA; o timeout de 30 s do HTTP API deixa de importar; disponibilidade composta de 99,82% em vez de 99,72% | Polling, estados de job, lease e reconciliador; a UX precisa mostrar progresso | Respostas em streaming virarem requisito; aí entra WebSocket ou SSE |
| ADR-06 Fargate Spot | Fargate sob demanda para todos os workers | Até 70% menos no compute dos workers; Spot usa capacidade ociosa da AWS | Interrupções com aviso de 2 min; dependemos de lease e retry para não perder trabalho | A taxa de interrupção afetar o P95, ou o compute estável justificar Savings Plans |

### Dados, eventos e auditoria

| ADR | Em vez de | Ganhamos | Pagamos | Revisitar quando |
| --- | --- | --- | --- | --- |
| ADR-03 Outbox por Streams e Pipes | Escrita dupla (DynamoDB e depois S3, DynamoDB e depois `RunTask`) | Nenhum evento se perde se a task cair; replay pelo arquivo do EventBridge | Mais serviços na cadeia; entrega *at-least-once*, então a auditoria precisa de deduplicação no Athena; atraso de segundos | A latência do stream incomodar o usuário; nunca para voltar à escrita dupla |
| ADR-04 Log imutável + projeções | Uma tabela de estado com histórico embutido | Imutabilidade verificável por IAM; reconstrução do estado a partir dos eventos; concorrência otimista por `seq` | Duas tabelas; *upcasters* para evoluir o esquema dos eventos; armazenamento cresce sem parar | O volume de eventos pesar no custo; aí entra TTL nas projeções ou snapshot |
| ADR-05 Duas idempotências | Uma única chave para tudo | Retry seguro; um cálculo por entrada, mesmo com corrida; resultados maiores que 400 KB no S3 | Duas estruturas a manter; o hash precisa incluir *todas* as entradas, ou o cache entrega resultado errado | Mudar o que define uma execução (novo runner, novo dataset) |
| ADR-16 Retenção por ambiente | Mesma retenção em todos os ambientes, ou sem Object Lock | Garantia de auditoria exigida em produção; estudos baratos e descartáveis | Em compliance, a retenção não pode ser reduzida; anos de dados guardados | Mudança regulatória; a retenção só pode crescer |
| ADR-17 MVP sintético | Comparar com o histórico real já no MVP | Nenhum número sem critério de validação (OQ-6); sem risco de dado real no hackathon | O MVP mostra só evidência `simulated`; o valor real fica para o C1 | A OQ-6 for respondida e as entradas das propostas estiverem disponíveis |

### Rede, identidade e região

| ADR | Em vez de | Ganhamos | Pagamos | Revisitar quando |
| --- | --- | --- | --- | --- |
| ADR-07 Sem NAT, com endpoints | NAT Gateway (~US$ 70/mês) ou subnets públicas (~US$ 15/mês) | Nenhuma rota para a internet; padrão bancário sem depender de filtro de saída | ~US$ 102/mês, metade da infraestrutura; cada serviço novo pede um endpoint; integrações externas exigem outro caminho (ADR-18) | Surgirem integrações externas frequentes; aí entra NAT com Network Firewall |
| ADR-09 Entra ID direto | Cognito federado por SAML | Um serviço a menos no caminho síncrono; aprovado pela segurança | Papéis dependem do claim de grupos do Entra; trocar de IdP mexe no authorizer | A organização exigir outro IdP ou MFA por passo |
| ADR-12 us-east-1 | sa-east-1 desde o início | Mais modelos, preço menor e aprovação do time para o hackathon | Dados fora do país; para produção, a residência precisa ser verificada por inference profile | Antes de qualquer dado derivado de produção |
| ADR-18 Lambda de PR | NAT para toda a VPC, ou repositório por PrivateLink | Escopo mínimo; a VPC continua fechada | Uma função com token de Git fora da VPC, que precisa de rotação de segredo e permissão mínima | A rede corporativa oferecer caminho privado para o Git |

### Confiabilidade

| ADR | Em vez de | Ganhamos | Pagamos | Revisitar quando |
| --- | --- | --- | --- | --- |
| ADR-08 SLO 99,5% e backup/restore | Promessa de 99,9% ou DR multirregião ativo-passivo | Meta defensável pela conta dos SLAs; DR quase sem custo | RTO de 4 h e RPO de 24 h em perda de região | O Playground influenciar decisão de crédito em produção ou atender mais áreas |

### IA, custo e controle

| ADR | Em vez de | Ganhamos | Pagamos | Revisitar quando |
| --- | --- | --- | --- | --- |
| ADR-10 Modelo por eval | Um único modelo grande para tudo | Diferença de até 7× no custo mensal sem perder qualidade medida | Manter um conjunto de avaliação e rodá-lo a cada troca de modelo | Lançamento de modelo novo ou queda de qualidade nos findings marcados como relevantes |
| ADR-11 Orçamento de tokens | Pagar o que vier e revisar a fatura | Custo limitado por construção; abuso ou loop não estoura o mês | Usuário intenso esbarra no limite e recebe `429` | O share de findings relevantes justificar limites maiores |
| ADR-13 Contexto do sub-DAG | Mandar o Policy Spec inteiro no prompt | Menos tokens, menos latência e menos dado exposto ao modelo | A IA pode não ver uma regra relevante fora do recorte; o corte precisa ser avisado | Os findings da IA perderem relevância por falta de contexto |
| ADR-14 Feature flags | Limites fixos no código | Ajuste sem deploy; modo grupo para workshops; rollback por alarme | Mais um serviço e mais uma superfície de erro de configuração (mitigada por JSON Schema) | Quase nunca; flags são baratas |
| ADR-15 Cota mínima de TPM | Pedir aumento de cota antes de medir | Nenhum erro de throttling; custo previsível | Em rajada, P95 de 175 s com 200 mil tokens/min; com o teto de 32 mil tokens, o pico normal já forma fila | Antes da demo, ou se o P95 do pico normal passar de 30 s |

## 3. Leitura por pilar

### Excelência operacional

- **Como a arquitetura atende:** infraestrutura como código (CDK, um stack por ambiente); deploy com circuit breaker e rollback por alarme; feature flags com validação e rollback; métricas de produto e de custo por hipótese; testes de falha com AWS FIS; teste de mesa executável.
- **Onde paga:** é o pilar com mais ▼. Event sourcing exige disciplina de esquema. O outbox adiciona Pipes, barramento e Firehose. Os jobs assíncronos exigem reconciliador e DLQ.
- **Ação:** runbooks para DLQ, `IteratorAge` e circuit breaker aberto; um painel único com as 7 métricas da seção 8.5 da arquitetura; testes de contrato para cada versão de evento.

### Segurança

- **Como a arquitetura atende:** autenticação pelo Entra ID na borda; ACL por política e quatro papéis checados na API; VPC sem rota para a internet; IAM com papéis separados (só o `worker-llm` chama o Bedrock, ninguém apaga a auditoria); KMS em repouso; Guardrails e nenhuma linha do Motivo de Decisão no prompt; auditoria imutável em compliance.
- **Onde paga:** ADR-12 tira dados do país no hackathon (aceitável só com dados sintéticos). ADR-18 coloca um token de Git fora da VPC.
- **Ação:** rotação automática do token no Secrets Manager com escopo mínimo de repositório; verificação de residência de dados antes de produção; revisão com a [Responsible AI Lens](https://infoq.com/news/2025/12/aws-expands-well-architected/) quando o C1 trouxer dados reais.

### Confiabilidade

- **Como a arquitetura atende:** estabilidade estática (cada AZ cobre o pico); bulkhead por fila; idempotência em dois níveis; lease e retry; degradação sem IA; DR por backup e restore; o teste de mesa prova os cenários de falha.
- **Onde paga:** Spot interrompe jobs, mitigado por lease. O DR tem RTO de horas.
- **Ação:** medir o SLO pelo canary desde o primeiro deploy; ensaiar o restore em segunda região uma vez antes de produção.

### Eficiência de desempenho

- **Como a arquitetura atende:** API sem estado e leve; o trabalho pesado fica fora da requisição; cache de resultado por hash; cache de prompt; contexto mínimo no prompt; Graviton.
- **Onde paga:** a vazão de IA fica presa à cota do Bedrock (ADR-15). O teste de mesa mostrou P95 de 175 s numa rajada de 50 hipóteses. Com o teto de 32 mil tokens por hipótese, mesmo o pico normal forma fila.
- **Ação:** dimensionar a cota pela regra `cota ≥ hipóteses/min no pico × tokens por hipótese ÷ 0,7 ÷ 0,8`, que dá cerca de 74 mil tokens/min com 10 mil tokens por hipótese e 238 mil com 32 mil. Medir os tokens reais com o Policy Spec real antes de pedir aumento.

### Otimização de custos

- **Como a arquitetura atende:** ARM e Spot; DynamoDB on-demand; reuso por hash; modelo por tarefa; orçamento de tokens; tags obrigatórias e inference profiles por caso de uso; Budgets com "modo econômico"; ciclo de vida para Glacier.
- **Onde paga:** os endpoints de interface custam ~US$ 102/mês para manter a VPC fechada. A auditoria em compliance acumula anos de dados.
- **Ação:** acompanhar o custo por hipótese (meta US$ 0,05); levar a auditoria para Deep Archive após 2 anos; destruir o stack de dev fora dos ciclos.

### Sustentabilidade

- **Como a arquitetura atende:** Graviton (mais desempenho por watt); Spot usa capacidade que já estaria ligada; workers escalam a zero; o reuso por hash e o cache de prompt evitam recomputar; o contexto mínimo e os modelos menores reduzem inferência; dados frios vão para classes de armazenamento de menor energia.
- **Onde paga:** duas AZs com capacidade cheia cada uma mantêm capacidade ociosa por desenho. Anos de auditoria em compliance ficam armazenados.
- **Ação:** reduzir a base sob demanda do `worker-llm` fora do horário comercial; preferir o modelo menor que passar no eval.

## 4. Tensões entre pilares

| Tensão | Onde aparece | Como resolvemos |
| --- | --- | --- |
| SEC × COST | Endpoints de interface (ADR-07) custam ~US$ 30/mês a mais que NAT | Ficamos com SEC: é o padrão de um banco e evita gastar ~US$ 290 por AZ por mês em Network Firewall |
| REL × COST | Duas tasks de API sempre ligadas, cada uma dimensionada para o pico | Ficamos com REL: são US$ 29/mês por estabilidade estática |
| REL × SUS | Capacidade ociosa nas 2 AZs | REL vence para a API; os workers escalam a zero |
| PERF × COST | Cota mínima de TPM (ADR-15) e Spot nos workers (ADR-06) | COST vence fora do pico; uma base sob demanda e o modo grupo protegem o P95 quando importa |
| PERF × COST | Sonnet × Haiku | Decidido por eval (ADR-10), não por preferência |
| OPS × REL | Outbox, event sourcing e filas aumentam o que operar | REL vence: a alternativa perde auditoria em silêncio |
| SEC × OPS | Object Lock em compliance não pode ser desfeito | Só em produção e só depois de a governança fechar o prazo |
| SEC × PERF | Contexto mínimo no prompt pode tirar informação útil da IA | O corte é avisado ao usuário e medido pelo share de findings relevantes |

## 5. Decisões difíceis de desfazer

A maior parte das decisões é reversível com um deploy. Quatro não são, e por isso pedem cuidado antes do primeiro uso em produção:

1. **Retenção em compliance (ADR-16).** Depois de aplicada, não pode ser reduzida nem pelo root. Fechar o número de anos antes.
2. **Esquema dos eventos (ADR-04).** O log é imutável; toda evolução precisa ser aditiva, com *upcasters*. Revisar o esquema inicial com cuidado.
3. **Chave de idempotência (ADR-05).** Mudar o que entra no hash invalida o reuso de todos os resultados anteriores. Incluir desde já `policyVersion`, overrides, `datasetVersion` e `runnerVersion`.
4. **Região dos dados (ADR-12).** Migrar dados e auditoria entre regiões é caro. Decidir a região de produção antes de existir dado real.

## 6. Riscos residuais

| Risco | Pilar | Mitigação | Gatilho |
| --- | --- | --- | --- |
| Rajada com a cota mínima estoura o P95 | PERF | Modo grupo, Haiku na estruturação e pedido de aumento de cota antes da demo | P95 da fila `llm` acima de 20 s |
| Policy Spec real muito maior que o fixture | COST, PERF | Tetos da seção 9.1 da arquitetura; medir antes de escolher o modelo | Prompt acima de 30 mil tokens |
| Erro de esquema de evento em produção | OPS, REL | Testes de contrato; `schemaVersion`; *upcasters* | Qualquer mudança no domínio |
| Token de Git vazado na Lambda de PR | SEC | Escopo mínimo, rotação automática, alarme de uso fora do padrão | Uso do token fora do evento de seleção |
| Pipeline de auditoria parado por mais de 24 h | REL, SEC | Alarme de `IteratorAge` acima de 60 s e runbook | `IteratorAge` acima de 60 s |
| Dados fora do país com o C1 | SEC | Verificação de residência e decisão de região antes do C1 | Primeiro uso de dado derivado de produção |

## 7. Próximo passo

Antes de produção, rodar uma revisão formal no AWS Well-Architected Tool com a Generative AI Lens, importada como lente customizada a partir do repositório `aws-samples/sample-well-architected-custom-lens`. Somar a Financial Services Industry Lens, por ser um workload de crédito, e registrar os riscos altos como itens do backlog.

## Fontes

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
- [Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html)
- [Announcing the AWS Well-Architected Generative AI Lens](https://aws.amazon.com/blogs/architecture/announcing-the-aws-well-architected-generative-ai-lens)
- [AWS expands Well-Architected (InfoQ, dez/2025)](https://infoq.com/news/2025/12/aws-expands-well-architected/)
- [Arquitetura da aplicação](arquitetura-da-aplicacao.md) e [teste de mesa](simulador/teste-de-mesa.html) deste repositório
