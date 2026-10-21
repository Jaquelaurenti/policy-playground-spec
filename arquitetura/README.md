# Arquitetura do Policy Playground

Entregáveis de arquitetura do time **CredIA Girls** (AWS Builders League) para o Policy Playground, derivados do SDD em [`.kiro/specs/policy-playground/`](../../.kiro/specs/policy-playground/).

![Arquitetura da solução na AWS](img/arquitetura-solucao.png)

## Entregáveis

| Entregável | Arquivo | O que é |
| --- | --- | --- |
| Imagem da arquitetura | [`img/arquitetura-solucao.png`](img/arquitetura-solucao.png) | Diagrama 4K (3840×2160) com os ícones oficiais da AWS e o fluxo principal numerado de 1 a 9 |
| Vídeo explicativo | [`video/CredIA-Girls_Policy-Playground_Arquitetura.mp4`](video/CredIA-Girls_Policy-Playground_Arquitetura.mp4) | 4 min 16 s, 1080p, narração em português e legendas embutidas ([`.srt`](video/CredIA-Girls_Policy-Playground_Arquitetura.srt) separado) |
| Arquitetura da aplicação | [`arquitetura-da-aplicacao.md`](arquitetura-da-aplicacao.md) | Documento vigente: containers, portas e adaptadores, contrato da API, dados, alta disponibilidade, escalabilidade, FinOps, limites, 18 ADRs e rastreabilidade com o SDD |
| Simulador de teste de mesa | [`simulador/teste-de-mesa.html`](simulador/teste-de-mesa.html) | Página única, sem dependências: 9 cenários passo a passo com 64 verificações contra o SDD e simulação de carga e custo da hora de pico |
| Análise inicial do SDD | [`analise-sdd-arquitetura-aws.md`](analise-sdd-arquitetura-aws.md) | Primeira análise (15/10), mantida como histórico das decisões |
| Fontes | [`fontes/`](fontes/) | Scripts que geram a imagem e o vídeo |

## Resultado do teste de mesa

- 9 de 9 cenários aprovados e 63 de 64 verificações.
- No pico normal (50 especialistas, cota de 200 mil tokens/min, cerca de 10 mil tokens por hipótese), o P95 até a hipótese estruturada é de 15 s.
- Limitação conhecida: numa rajada de 50 hipóteses, o P95 sobe para 175 s. Nada se perde, mas as hipóteses esperam na fila. Com o teto de 32 mil tokens por hipótese, a cota precisa ser de cerca de 238 mil tokens/min para o pico normal não formar fila.

Para usar o simulador, abra `simulador/teste-de-mesa.html` no navegador. As regras e os 12 registros vêm do fixture sintético do repositório; latências e cotas são premissas ajustáveis na aba *Carga e custo*.

## Como regenerar a imagem e o vídeo

Os scripts em `fontes/` foram escritos no ambiente de geração e usam caminhos absolutos na variável `S` no topo de cada arquivo; ajuste-a antes de rodar.

1. `arch.py` gera o HTML do diagrama a partir dos ícones em `fontes/icons/`; `render.py` exporta o PNG com Playwright (`python render.py architecture.html saida.png 2400 1350 1.6`).
2. `script.py` contém o roteiro do vídeo; `make_audio.py` sintetiza a narração com o sherpa-onnx (voz Kokoro `pf_dora`); `slides.py` gera os quadros; o vídeo é montado com ffmpeg a partir de `frames.txt`, `narration.wav` e `legendas.srt`.

Os ícones são do conjunto oficial *AWS Architecture Icons*, obtidos pelo pacote npm `aws-icons` (licença MIT).
