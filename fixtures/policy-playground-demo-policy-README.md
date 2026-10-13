# Policy Playground — insumo sintético para Kiro Design

## Propósito
Fixture **100% fictício**, criado para a fase de **Design** do Kiro Spec-Driven Development. Não representa a política real de Microcrédito, nem dados, código, regras, valores, parâmetros ou resultados do Itaú/FICO. **Não usar para decisões de crédito.**

## Base conceitual
O relatório fotografado da Syn descreve um JSON com nove seções: `policy`, `stages`, `rules`, `variables`, `parameters`, `dag`, `motivos`, `validation_map`, `output_vars`. O artefato analisado no relatório tinha 109 regras, quatro etapas e dependências. Este fixture reduz a escala para **9 regras**, **4 etapas**, **10 variáveis**, **2 parâmetros** e **3 motivos**, preservando o formato conceitual. Os valores e a lógica das regras foram inventados para demonstração.

## Fluxo demonstrativo
1. Extrair renda, idade e comprometimento de um payload sintético.
2. Aplicar filtros de elegibilidade por idade, renda mínima e comprometimento.
3. Classificar faixa e consultar uma matriz fictícia de oferta.
4. Consolidar um resultado simulado e rastrear os motivos.

## Cenário-chave para a interface
O especialista seleciona a política, abre a regra **R005**, altera `renda_minima` de **2500** para **3000**, compara baseline e cenário, vê as dependências e pede uma investigação complementar. O agente pode propor hipóteses, mas **não inventa evidências**. Os estudos determinísticos reais não estão conectados a este fixture: qualquer resultado demonstrado precisa ser identificado como **simulado**.

## Decisões de design a explorar
- Visualização de regras atômicas, parâmetros e DAG.
- Editor de thresholds com preview, validação e diff baseline/cenário.
- Interpretação de `json_extract`, `case_when` e `matrix_lookup`.
- Trilhas de auditoria: regra, variável, parâmetro, origem e motivo.
- Findings de IA separados entre *hipótese sem comprovação* e *finding com evidência*.
- Estados de UI para erro de schema, dependência ausente, execução indisponível e ausência de evidência.

## Gaps observados no relatório
- `consumed_by` não vem preenchido: derivar invertendo os `inputs` das regras.
- Parâmetros extraídos automaticamente podem duplicar os parâmetros conhecidos: deduplicar.
- Ordem de execução e fluxos paralelos precisam ser representados explicitamente.

## Limites do fixture
Este arquivo **não é uma implementação executável**. Expressões são strings para apoiar o desenho do contrato; ainda será preciso decidir parser/avaliador e semântica de nulos, casting e erros. `perfil` é uma entrada externa sintética para demonstrar `matrix_lookup`. A estrutura de notebooks e DAG é simplificada.

## Princípio do produto
**AI proposes. Studies prove. Humans decide.**

## Sugestão de uso no Kiro
Adicione ambos os arquivos ao repositório local como material de referência. Na fase de design, peça ao Kiro para usar o JSON como fixture, mantendo `requirements.md` como fonte dos requisitos e documentando decisões, contratos, componentes, fluxos e trade-offs em `design.md`. Não apresente a política sintética como extração real da Syn.
