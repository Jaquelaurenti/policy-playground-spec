# Policy Playground

_Explore o que você já sabe, descubra o que você não sabe._

# 1. Press Release

### Policy Playground: especialistas de crédito testam hipóteses de política e descobrem riscos ocultos em horas, sem escrever código

**Um novo ambiente combina a intenção do especialista com agentes de IA que desafiam a política e comprovam cada descoberta usando os estudos determinísticos que já existem.**

Hoje o time de Crédito PF disponibiliza o Policy Playground. Nele, o especialista de políticas de crédito descreve o que quer testar, em linguagem natural ou editando a regra visualmente, e vê no mesmo lugar o impacto da mudança e os comportamentos que ninguém tinha pensado em investigar.

Até agora, testar uma hipótese simples, como subir a renda mínima de R$ 2.500 para R$ 3.000, exigia traduzir a intenção de negócio para SQL/Python, depender de outras pessoas para executar o estudo e esperar alguns dias pelo resultado. Além disso, a validação cobria apenas as perguntas que o especialista já sabia fazer. Combinações de regras e edge cases ficavam de fora até aparecerem em produção.

Com o Policy Playground, o especialista abre a política e diz o que quer testar. O agente transforma essa intenção em uma hipótese estruturada, aciona os estudos atuais, que continuam sendo a fonte de verdade do cálculo, e apresenta o impacto com evidências rastreáveis. Ao mesmo tempo, a IA desafia a política e sugere novos cenários para investigar. A decisão continua sempre com o especialista.

> "Queremos que o conhecimento de negócio chegue à evidência sem passar por uma fila técnica. A IA acelera a investigação, mas quem decide continua sendo o especialista." — Liderança de Crédito PF (citação ilustrativa)

> "Eu levava dias para saber o impacto de uma mudança de corte. Agora testo na hora e ainda recebo cenários que eu não teria pensado em olhar." — Especialista de políticas de crédito (citação ilustrativa)

**Como começar:** o especialista acessa o Policy Playground, escolhe uma política e escreve a primeira hipótese.

---

# 2. As 5 perguntas do cliente

## Quem é o cliente?

**Cliente principal: o especialista de políticas de crédito.** Ele domina a regra de negócio, mas não escreve SQL/Python no dia a dia. É quem quer mudar a política e hoje depende de outras pessoas para testar essa mudança.

| Perfil                                       | Papel                               | O que precisa do Playground                                               |
| -------------------------------------------- | ----------------------------------- | ------------------------------------------------------------------------- |
| **Especialista de políticas (principal)**    | Formula hipóteses e propõe mudanças | Testar a intenção sem código e entender as consequências antes de decidir |
| Analistas de estudos e dados (secundário)    | Executam e reproduzem estudos       | Menos pedidos avulsos e estudos reutilizados de forma governada           |
| Aprovadores de política e risco (secundário) | Decidem se a mudança segue          | Evidência rastreável para aprovar ou rejeitar                             |
| Engenharia do motor de decisão (secundário)  | Implementa a política               | Especificação sem ambiguidade e, no futuro, código e testes gerados       |

**Beneficiário organizacional:** a operação de crédito, que passa a ter um único fluxo ligando intenção, evidência, decisão e implementação.

## Qual é o problema?

**Problema 1: barreira técnica.** Para testar uma hipótese, o especialista precisa primeiro transformar a intenção de negócio em SQL/Python. Isso cria dependência técnica e vários handoffs, e aumenta o tempo entre a hipótese e a validação.

**Problema 2: o que ninguém perguntou.** A validação começa pelas hipóteses que o especialista já sabe formular. Combinações de regras, edge cases, segmentos e comportamentos inesperados deixam de ser investigados só porque ninguém pensou em perguntar.

<aside>
🎯

**Em uma frase:** hoje o especialista só consegue testar o que sabe traduzir em código e só investiga o que sabe perguntar.

</aside>

## Qual é o benefício principal?

<aside>
⭐

**O especialista de políticas testa qualquer hipótese e descobre comportamentos não previstos em horas, sem escrever código, com evidência determinística antes de a mudança chegar à produção.**

</aside>

**Como esse benefício se sustenta**

- **Autonomia:** o especialista expressa a intenção de negócio sem traduzi-la para SQL/Python.
- **Descoberta:** a IA desafia a política e procura hipóteses, combinações e comportamentos que não tinham sido considerados.
- **Confiança:** o impacto é calculado pelos estudos atuais, com dados governados. A IA não calcula.
- **Velocidade:** hipótese, evidência e decisão acontecem em uma única experiência.

**Princípio:** AI proposes. Studies prove. Humans decide.

## Como validamos a necessidade?

### O que já observamos (evidência interna)

- O time de política conhece o negócio, mas experimentar exige conhecimento técnico para transformar a intenção em SQL/Python.
- O processo atual passa por várias traduções: intenção, estudo, especificação, parametrização e implementação.
- Entender como a política da especificação vira comportamento no motor de decisão exige conhecimento específico.
- Os estudos atuais já conseguem representar e reproduzir decisões. Isso dá ao Playground uma base determinística.

### Como será a experiência do usuário?

O especialista usa uma única experiência, sem escolher entre modos. Ele testa o que quer e, na mesma tela, a IA faz o papel de "red team": desafia a política procurando falhas, como faria um time adversário.

**Passo a passo (MVP)**

1. **Abrir a política:** o especialista escolhe a política e vê as regras, variáveis, dependências e contexto.
2. **Expressar a intenção:** altera uma regra visualmente ou escreve, por exemplo: "Quero testar o que acontece se a renda mínima passar de R$ 2.500 para R$ 3.000".
3. **Estruturar a hipótese:** o agente transforma a intenção em uma hipótese estruturada e identifica os estudos necessários.
4. **Desafiar:** enquanto isso, os agentes procuram conflitos, lacunas, edge cases e combinações inesperadas.
5. **Executar:** a hipótese vira um experimento, executado pelos estudos atuais.
6. **Evidenciar:** o Playground mostra o impacto, as regras relacionadas, os dados usados e o contexto necessário para investigar o resultado.
7. **Transformar a descoberta em cenário:** um finding da IA vira um novo cenário que pode ser explorado no próprio Playground.
8. **Decidir:** o especialista aceita ou rejeita a hipótese e decide se a política deve mudar.
9. **Implementar (evolução futura, fora do MVP):** depois da aprovação, a solução gera código, testes e Pull Request para revisão.

**Exemplo**

O especialista escreve: _"Quero testar o que acontece se a renda mínima passar de R$ 2.500 para R$ 3.000."_ O Playground estrutura a hipótese, aciona o estudo correspondente e mostra o impacto. Em seguida, desafia a política e encontra, por exemplo, uma combinação de regras que a hipótese original não cobria. Esse finding vira um cenário explorável, e o especialista decide se ele é relevante.

### Quando a IA erra ou gera ruído

- Cada finding mostra a regra, os dados e o estudo que o sustentam. Sem evidência, ele aparece como hipótese não comprovada.
- O especialista marca cada finding como relevante ou irrelevante, e essa marcação ajuda a priorizar os próximos.
- Os findings são agrupados, ordenados por impacto e limitados por sessão, para não sobrecarregar o especialista com alertas.

---

# 3. Métricas de sucesso

| Métrica                                                   | Linha de base | Meta                       |
| --------------------------------------------------------- | ------------- | -------------------------- |
| Lead time entre hipótese e evidência                      | 3 dias        | 1 dia                      |
| Handoffs por hipótese                                     | 3             | 1 (o próprio especialista) |
| % de hipóteses testadas sem apoio técnico                 | 25 %          | 75 %                       |
| % de findings da IA marcados como relevantes              | —             | 55 %                       |
| Comportamentos não previstos detectados antes da produção | 33 %          | 60 %                       |

---

# 4. FAQ externo (especialista de políticas)

**Preciso saber SQL ou Python?**

Não. Você descreve a intenção em linguagem natural ou altera a regra visualmente. O agente faz a tradução técnica.

**Posso confiar no número de impacto?**

Sim. O impacto é calculado pelos estudos atuais, os mesmos que já são usados hoje. A IA interpreta a intenção e organiza a execução, mas não calcula o resultado.

**A IA pode mudar a política sozinha?**

Não. A IA propõe e investiga. Aprovar ou rejeitar é sempre decisão do especialista, e nada é alterado em produção de forma autônoma.

**E se a IA sugerir algo sem sentido?**

Você rejeita o finding com um clique. Todo finding mostra a evidência que o sustenta, e a sua avaliação ajuda a priorizar as próximas sugestões.

**Preciso escolher entre testar minha hipótese e deixar a IA desafiar a política?**

Não. As duas coisas acontecem na mesma experiência.

---

# 5. FAQ interno

**Qual é o papel da IA e onde ela não entra?**

A IA não é um chatbot que só responde perguntas. Ela interpreta um objetivo, consulta o contexto da política, escolhe ferramentas, formula hipóteses, executa investigações e encadeia os resultados.

**O que a IA faz**

- Entende a intenção do especialista.
- Transforma a intenção em uma hipótese estruturada.
- Identifica quais estudos e ferramentas acionar.
- Desafia a política e gera hipóteses de investigação.
- Analisa as evidências produzidas pelos estudos.
- Apresenta findings rastreáveis às regras e aos dados.

**O que a IA não faz**

- Não decide se a política deve ser aprovada.
- Não substitui o especialista.
- Não é a fonte de verdade do cálculo de impacto.
- Não altera a política em produção de forma autônoma.
- Não trata como fato uma hipótese do modelo sem evidência.

**Por que uma experiência, e não dois produtos (Playground + Red Team)?**

Porque o especialista não deveria ter que decidir de antemão se quer testar ou ser desafiado. A mesma sessão que valida a hipótese dele já é o melhor contexto para a IA procurar o que ficou de fora.

**Quais são os principais riscos e como mitigamos?**

| Risco                          | Mitigação                                                                                                     |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| Alucinação ou finding sem base | O cálculo é sempre feito pelos estudos determinísticos, e um finding só vira fato com evidência rastreável    |
| Dados sensíveis (LGPD)         | Uso apenas de dados governados, acesso por perfil e minimização de dados pessoais nas interações com o modelo |
| Custo de inferência (FinOps)   | Limite de investigações por sessão, reaproveitamento de resultados e monitoramento do custo por hipótese      |
| Governança e auditoria         | Registro de hipótese, estudo, dados e decisão, com aprovação humana obrigatória                               |
| Excesso de findings            | Priorização por impacto, limite por sessão e feedback do especialista                                         |

**O que fica fora do escopo do MVP?**

- Geração de código, testes e Pull Request (passo 9), que é evolução futura.
- Qualquer alteração em produção.
- Criação de novos estudos: o MVP usa apenas os estudos que já existem.
- Políticas e produtos cobertos na primeira versão: definir.

**Do que dependemos?**

- Acesso programático aos estudos atuais para executar e reproduzir decisões.
- Dados governados disponíveis para os experimentos.
- Uma representação das regras da política que o agente consiga ler.

---

# 6. Síntese

O Policy Playground cria uma nova interface para a engenharia de políticas de crédito. O especialista diz o que quer testar, e a inteligência agentic ajuda a descobrir o que ainda não foi perguntado. Os estudos atuais continuam sendo a camada determinística de execução e evidência, e o especialista continua responsável pela decisão.

**EXPLORAR → DESAFIAR → PROVAR → DECIDIR → EVOLUIR**

_Policy Playground — Working Backwards | AWS Builders League_
