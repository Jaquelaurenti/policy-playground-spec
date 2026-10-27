---
inclusion: always
---

# Tecnologia

## Stack

- **Backend:** Python 3.12, FastAPI e Pydantic, como monólito modular numa única imagem ARM (ADR-01). O domínio não importa `boto3`, FastAPI nem nenhum adaptador.
- **Frontend:** SPA em React + Vite, com React Flow para o DAG da política.
- **Infraestrutura:** AWS CDK, um stack por ambiente, região us-east-1 (ADR-12).
- **Runtime:** ECS Fargate (API sob demanda em 2 AZs, workers em Spot), DynamoDB, S3, SQS, EventBridge Pipes, Firehose, Athena, Bedrock (Converse + Guardrails), AppConfig.
- **Testes:** `unittest` da biblioteca padrão enquanto não houver dependências; cada porta tem adaptador em memória para testar sem rede.

## Restrições técnicas

- Nenhuma rota síncrona chama o Bedrock: o timeout do API Gateway HTTP API é de 30 s e não pode ser ajustado (ADR-02).
- Toda mudança de estado leva o header `Idempotency-Key`.
- Uma escrita por comando: só o log de eventos. Filas e auditoria derivam do stream (ADR-03).
- A VPC não tem rota para a internet (ADR-07). Integração externa nova precisa de decisão de arquitetura.
- Limites de uso e modelos vêm de feature flags no AppConfig, nunca de constantes no código (ADR-14).
- O prompt nunca leva o Policy Spec inteiro: só o sub-DAG afetado, com teto de 30 mil tokens (ADR-13).

## Comandos

```bash
python3 tools/policy_spec/validate.py .kiro/specs/policy-playground/fixtures/policy-playground-demo-policy.json
python3 -m unittest discover -s tests -v
```

## Referência

- #[[file:arquitetura/arquitetura-da-aplicacao.md]]
- #[[file:arquitetura/tradeoffs-well-architected.md]]
