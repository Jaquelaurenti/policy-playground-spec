# Proposta para o Hackathon: do Policy Playground ao Policy Investigator Agent

Status: **para aprovação do time** · versão unificada (proposta da Jessica + spec R17 e spike da Jaque)
Base: Guia para equipes · Hackathon (BR), análise do repositório e spike em `spike/agente/`.
Horários em **BRT** (Brasília) com o horário da Colômbia (COT, usado no guia) entre parênteses. BRT = COT + 2h.

## 1. Contexto

No hackathon, o júri da AWS avalia a solução em 4 critérios, de 1 a 5 cada: Negócio, Execução técnica, Colaboração e Apresentação (máximo de 20 pontos por jurado). Pontos do guia que mais afetam o projeto:

- A demo precisa estar **implantada e ao vivo**. Demo gravada não é aceita.
- A nota 5 em Execução técnica pede um agente conectado a **várias ferramentas via MCP**, com regras claras e 3 ou mais serviços AWS.
- Soluções sem componente agêntico não são permitidas.
- Pitch de 5 min mais 2 de perguntas, cortado aos 7. Sprint até **14:35 BRT (12:35 COT)**; freeze de código às **15:05 BRT (13:05 COT)**.
- Desempate: completude da demo, autonomia do agente e maturidade.
- A regra 2 pede código novo: o código do agente é escrito **no sprint**. Antes do dia, só spec, testes, docs e o spike descartável.

## 2. Onde estamos

**Já temos**
- Spec completo (requirements, design, tasks), steering, hooks e arquitetura.
- MVP funcional: motor determinístico, DAG de regras, hipóteses, cenários, execução assíncrona e idempotente, achados, decisões e auditoria. 36 testes passando.
- Infra em CDK com Lambda, API Gateway, DynamoDB, S3, Cognito, CloudFront e Bedrock, com deploy e destroy por GitHub Actions (OIDC).
- Narrativa de negócio no Working Backwards, com métricas de linha de base e meta.
- **Novo:** spec da camada agêntica (R17, design §10.4, tasks 24.1–29) e **spike validado** do agente e do servidor MCP (seção 3.6).

**Lacunas frente à rubrica**

| # | Lacuna | Impacto |
| --- | --- | --- |
| 1 | O "agente" é uma única chamada `converse` ao Bedrock que devolve texto. Não há tool use, loop de decisão nem MCP no runtime. Os MCPs de `.kiro/settings/mcp.json` servem só ao desenvolvimento. | Risco em "componente agêntico", "Autonomia do agente" e "várias ferramentas via MCP" |
| 2 | Números do Working Backwards parecem premissas e o dataset é sintético | Nota de Negócio ("problema validado com evidências") |
| 3 | Deploy ativo não confirmado; modelo do Bedrock desligado por padrão (`PP_MODEL_ID` opcional) | Execução técnica; sem modelo não há agente na demo |
| 4 | Fluxo de demo longo, com muitos passos manuais | Completude da demo e Apresentação |
| 5 | Commits concentrados: 18 e 11 em duas pessoas, 2 e 2 nas outras | Colaboração |
| 6 | O repositório existe desde 13/10 e o MVP entrou em 17/11 | Confirmar com a organização que é aceito (o spec nasceu na liga) |
| 7 | Lambda com timeout de 29 s | O loop do agente não cabe; subir para 120 s |

## 3. Proposta

Manter o princípio do produto, **"IA propõe, execução determinística prova, humano decide"**, e fazer a IA agir de verdade dentro desse limite.

### 3.1 Agente investigador com tool use (prioridade 1)

Trocar a chamada única por um loop de tool use no **Bedrock Converse com `toolConfig`**. Strands/AgentCore ficam como evolução: acrescentam dependência e custo ao perfil de custo zero e risco num sprint de 3 h. O agente recebe o cenário confirmado pelo especialista e:

1. **Planeja** a investigação (começa com "PLANO:", que aparece na tela).
2. Chama ferramentas, lê os resultados e decide o próximo passo, incluindo testar por conta própria uma variação do cenário e comparar as duas.
3. Trata exceções, por exemplo `cannot_calculate`, tentando uma alternativa.
4. Registra **achados presos a execuções** e termina com uma **recomendação** curta. A decisão final é humana.

**Ferramentas expostas como servidor MCP do Playground** (mesmo registro para o agente e para o MCP)

| Ferramenta | Função | Permissão |
| --- | --- | --- |
| `get_policy` | Lê regras, parâmetros e DAG | leitura |
| `preview_subdag` | Mostra o que pode mudar com um parâmetro | leitura |
| `trace_output` | Mostra quais regras decidem uma saída (dependências reversas) | leitura |
| `run_scenario` | Executa de forma determinística (selo SIMULADO) e devolve `executionId` | Policy Specialist |
| `compare` | Compara execução x baseline, ou duas execuções entre si (sensibilidade) | leitura |
| `get_candidates` | Candidatos determinísticos G1 e/ou G2 (`generators: ["G1","G2"]`) | leitura |
| `read_audit` | Lê a trilha da investigação e achados anteriores | leitura |
| `register_finding` | Registra um achado para revisão humana, citando as execuções | Policy Specialist |

G1 e G2 ficam numa só ferramenta com filtro: menos ferramentas para um modelo pequeno escolher, mesmo poder.

Opcional, se sobrar tempo: um segundo servidor MCP (documentação AWS ou fonte de dados) para mostrar "várias ferramentas". O Kiro também se conecta ao `/mcp` do Playground, o que dá para mostrar em 20 s na demo.

**Regras e limites que continuam valendo**
- Nenhum número de impacto vem do modelo. Isso é garantido por código: `register_finding` recusa qualquer número que não esteja na execução citada, e a recomendação final passa pelo mesmo teste (uma chance de reescrever; se insistir, é omitida) (R5.10, R17.4, R17.9).
- Teto de passos (12), de simulações (6) e de tokens por investigação (FinOps), com o limite atual de pedidos por hipótese. Atingir um teto encerra em `limited`.
- Toda ação do agente, inclusive o plano, entra no log de eventos e na auditoria.
- Papéis (RBAC) respeitados: o agente age com as permissões de quem o acionou. Um Viewer lê, mas o agente não executa cenários em seu nome.
- O agente nunca registra decisão e nunca altera produção.

Isso exige uma pequena revisão do design, que hoje exclui o "loop autônomo". **Já escrita para aprovação:** R17 com 11 critérios, decisão D-17, nota da R8 revisada e design §10.2/§10.4.

### 3.2 Implantar cedo (prioridade 2)
- Hoje à noite: habilitar o modelo no Bedrock, definir `PP_MODEL_ID` e fazer um deploy de ensaio.
- Subir o estado atual nos primeiros 20 min do sprint, para ter a URL e os usuários de demo prontos (task 24.1).
- Redeploy depois de cada marco. O Destroy só roda depois da apresentação.

### 3.3 Negócio com evidência (prioridade 3)
- Citar a fonte de cada número do Working Backwards, ou rotulá-lo como estimativa com premissas.
- Medir ao vivo o tempo da hipótese até a evidência, contra a linha de base de 3 dias.
- Mostrar o custo por investigação (tokens do agente), usando o FinOps que já existe.

### 3.4 Colaboração visível (prioridade 4)
- Cada integrante assume uma parte do pitch e ensaia a parte de outra pessoa.
- Antes do dia: commits e PRs de todas em spec, testes e docs. **O PR da spec R17 deve ser aberto por quem tem menos commits**, para não concentrar ainda mais.
- No sprint: um PR por frente, cada um de uma pessoa.

### 3.5 Plano B
- Cenário pré-confirmado que roda em menos de 30 s.
- Sem Bedrock ou com conta instável, o motor determinístico e os geradores G1/G2 continuam funcionando, a tela informa que o agente não rodou, e narramos o resto. Sem gravação.
- O backend local (`uvicorn`) aberto como segunda opção.

### 3.6 O que o spike já comprovou

| Pergunta | Resultado |
| --- | --- |
| O motor atual serve de ferramenta sem mudanças? | Sim. As 8 tools só embrulham funções existentes |
| O loop fecha com plano, sensibilidade, recusa e correção? | Sim, com modelo stub roteirizado contra o motor real (11 testes) |
| Número inventado é barrado? | Sim, no achado e na recomendação |
| `cannot_calculate` derruba o loop? | Não. Vira erro recuperável e o agente tenta outra via |
| RBAC? | Viewer lê, não executa |
| O mesmo registro vira servidor MCP? | Sim. Cliente MCP listou as 8 tools, rodou `run_scenario` e `compare` e recebeu a recusa |
| Dependências | `mcp` 2.x quebra o FastAPI do projeto. **Fixar `mcp==1.9.4`** |
| Bedrock real | **Pendente:** rodar `spike/agente/run_bedrock.py` no CloudShell hoje |

## 4. Divisão de trabalho (a confirmar)

| Frente | Task | Responsável | Entrega |
| --- | --- | --- | --- |
| 1. Agente com tool use | 25, 26 | _a definir_ | Registro das 8 tools, loop, limites, job, eventos e testes (caminho crítico) |
| 2. Servidor MCP | 27 | _a definir_ | `/mcp` do mesmo registro, `mcp==1.9.4`, Kiro conectado, timeout 120 s |
| 3. Front do agente | 28 | _a definir_ | Tela com plano, ferramentas chamadas, achados, recomendação e custo |
| 4. Deploy e infra | 24.1, 29 | _a definir_ | Permissões do Bedrock, URL estável, usuários, redeploys, plano B |
| 5. Negócio e pitch | 28.1 | _a definir_ (dividida) | Números com fonte, roteiro e ensaio com cronômetro |

Com 4 pessoas, a frente 5 fica com quem tiver as frentes 2 e 4, que liberam mais cedo.

**Contratos para trabalhar em paralelo**

```text
POST /api/hypotheses/{hid}/investigations            → 202 {"jobId": "J-…", "state": "pending"}
GET  /api/hypotheses/{hid}                           → record com "investigations": [...]

Eventos no stream da hipótese:
  InvestigationRequested {jobId, scenarioId}
  AgentToolCalled        {jobId, step, tool, input, status: success|error|note, error?}   # note = plano/raciocínio
  FindingSuggested       {findingId, jobId, source: "agent", evidenceLevel: "simulated",
                          executionIds, title, text, ruleRefs}
  InvestigationCompleted {jobId, status: done|limited|model_unavailable, steps, tokens, recommendation}
```

## 5. Cronograma do sprint (3 h)

| BRT | COT | Tempo | Entrega |
| --- | --- | --- | --- |
| 11:35–11:55 | 9:35–9:55 | 0:00–0:20 | Deploy do estado atual, URL e usuários criados (frente 4); demais criam branches |
| 11:55–13:25 | 9:55–11:25 | 0:20–1:50 | Frentes 1 e 2 no backend (merge da task 25 até 12:35 BRT, para destravar 26 e 27); frente 3 com dados mockados pelos contratos; frente 5 em roteiro e métricas |
| 13:25–14:05 | 11:25–12:05 | 1:50–2:30 | Merge de 26, 27 e 28, redeploy, fluxo completo 3 vezes, plano B ensaiado |
| 14:05–14:35 | 12:05–12:35 | 2:30–3:00 | Atualizar `tasks.md` e README, ensaio com cronômetro, último deploy; congelar o código |
| 15:05 | 13:05 | — | Freeze oficial |

## 6. Roteiro do pitch (7 min)

1. **Problema e cliente (1 min):** o especialista espera 3 dias por apoio técnico para testar uma hipótese de política. Número e fonte na tela.
2. **Solução agêntica (1 min):** diagrama com as 8 ferramentas MCP, as regras e os limites do agente.
3. **Demo ao vivo (3 min):**
   - O especialista escreve "aumentar a renda mínima para 3000" e confirma `P001=3000`. **Gate humano 1.**
   - O agente mostra o plano, lê a política, simula 3000 e, por conta própria, 2800, e compara as duas.
   - Achado inesperado: com 3000, nenhuma proposta aprovada cai na faixa BASICA (R007) e a linha BASICA da matriz de R008 fica sem uso.
   - Mostrar a recusa: o agente tenta citar um número sem evidência, a ferramenta recusa e ele corrige.
   - O especialista decide com a evidência na tela e a trilha de auditoria. **Gate humano 2.**
   - Se der tempo, 20 s do Kiro chamando `run_scenario` pelo mesmo `/mcp`.
4. **Impacto (1 min):** tempo da hipótese à evidência medido ao vivo, custo por investigação, serviços AWS usados e próximo passo (ligar ao runner real).

## 7. Riscos

| Risco | Mitigação |
| --- | --- |
| Loop do agente não fica estável a tempo | Spike já valida o desenho; contratos fixados; fallback para G1/G2 |
| Nova Lite chamar ferramentas com argumentos errados | Erros recuperáveis e teto de passos; testar o Claude Haiku hoje como alternativa |
| Bedrock sem acesso ao modelo na conta | Habilitar o modelo hoje; plano B sem modelo |
| Lambda estourar 29 s no job | Subir o timeout para 120 s (task 27); o HTTP API continua em 30 s |
| `mcp` 2.x quebrar o FastAPI | Fixar `mcp==1.9.4` |
| Conta nova em verificação (CloudFront, CloudShell) | Validar a conta antes do dia ou usar o ambiente efêmero da organização |
| Custo de tokens em loop | Teto de passos e de tokens, alerta de Budgets |
| Mexer em muita coisa e perder estabilidade | Escopo mínimo: um fluxo ponta a ponta bem feito, freeze respeitado |
| Código pré-existente questionado | Agente escrito no sprint; spike fica fora do `main`; pergunta enviada à organização |

## 8. Decisões que precisamos do time

- [ ] Aprovar o agente com tool use (Converse) e o servidor MCP como foco do sprint.
- [ ] Aprovar a revisão do design para permitir o loop limitado e auditável (R17, D-17).
- [ ] Aprovar a lista unificada de 8 ferramentas.
- [ ] Definir os responsáveis por frente (seção 4) e quem abre o PR da spec.
- [ ] Definir quem valida as fontes dos números de negócio.
- [ ] Confirmar com a organização se código pré-existente à data do hackathon é aceito.
- [ ] Confirmar onde a demo será implantada (conta própria ou ambiente efêmero).

## Hoje à noite

- [ ] Revisar e aprovar este documento e a spec R17
- [ ] Habilitar o modelo no Bedrock e rodar `spike/agente/run_bedrock.py` no CloudShell
- [ ] Definir `PP_MODEL_ID` e fazer um deploy de ensaio
- [ ] Enviar a pergunta à organização
- [ ] Marcar no `tasks.md` as tasks 1–20 que o MVP já cumpre
