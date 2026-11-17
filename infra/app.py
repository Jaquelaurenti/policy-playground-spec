#!/usr/bin/env python3
"""Perfil demo de custo zero (ADR-19): tudo serverless e pago por uso, dentro do free tier / créditos.

Contexto (-c chave=valor ou cdk.json):
  alertEmail  e-mail que recebe os alertas de orçamento (vazio = sem orçamento)
  modelId     modelo do Bedrock, ex. us.amazon.nova-lite-v1:0 (vazio = só geradores determinísticos)
  budgetUsd   teto mensal do alerta de orçamento (padrão 5; alerta também em 20% = US$ 1)
"""
import os

import aws_cdk as cdk

from stack import PolicyPlaygroundDemo

app = cdk.App()
ctx = app.node.try_get_context
PolicyPlaygroundDemo(
    app, ctx("stackName") or "PolicyPlaygroundDemo",
    alert_email=ctx("alertEmail") or "",
    model_id=ctx("modelId") or "",
    budget_usd=float(ctx("budgetUsd") or 5),
    env=cdk.Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT"), region=os.environ.get("CDK_DEFAULT_REGION")),
)
cdk.Tags.of(app).add("project", "policy-playground")
cdk.Tags.of(app).add("environment", "demo")
cdk.Tags.of(app).add("owner", "credia-girls")
app.synth()
