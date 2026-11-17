"""Adaptadores AWS do perfil demo: DynamoDB (log de eventos + chave-valor), S3 (lago de
auditoria), Bedrock Converse (Amazon Nova) e self-invoke assíncrono da Lambda."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ..ports import ModelUnavailable


def _to_ddb(v):
    return json.loads(json.dumps(v), parse_float=Decimal)


def _from_ddb(v):
    if isinstance(v, list):
        return [_from_ddb(i) for i in v]
    if isinstance(v, dict):
        return {k: _from_ddb(i) for k, i in v.items()}
    if isinstance(v, Decimal):
        return int(v) if v == int(v) else float(v)
    return v


class DynamoEventStore:
    """Tabela única: pk=HYP#id / sk=EVT#000001 (só PutItem condicional: append-only)."""

    def __init__(self, table: str):
        self.t = boto3.resource("dynamodb").Table(table)

    def append(self, stream, event):
        for _ in range(5):
            last = self.t.query(KeyConditionExpression=Key("pk").eq(f"HYP#{stream}") & Key("sk").begins_with("EVT#"),
                                ScanIndexForward=False, Limit=1, ConsistentRead=True)["Items"]
            seq = int(last[0]["seq"]) + 1 if last else 1
            item = {"pk": f"HYP#{stream}", "sk": f"EVT#{seq:06d}", "seq": seq, "event": _to_ddb(event)}
            try:
                self.t.put_item(Item=item, ConditionExpression="attribute_not_exists(sk)")
                return {**event, "seq": seq}
            except ClientError as e:
                if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
        raise RuntimeError("Concorrência alta demais ao gravar o evento")

    def list(self, stream):
        items, kw = [], {"KeyConditionExpression": Key("pk").eq(f"HYP#{stream}") & Key("sk").begins_with("EVT#"), "ConsistentRead": True}
        while True:
            r = self.t.query(**kw)
            items += r["Items"]
            if "LastEvaluatedKey" not in r:
                break
            kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]
        return [{**_from_ddb(i["event"]), "seq": int(i["seq"])} for i in items]

    def index(self, stream, summary):
        self.t.put_item(Item={"pk": "INDEX#HYP", "sk": stream, "summary": _to_ddb(summary)})

    def streams(self):
        r = self.t.query(KeyConditionExpression=Key("pk").eq("INDEX#HYP"))
        return [_from_ddb(i["summary"]) for i in r["Items"]]


class DynamoKV:
    def __init__(self, table: str):
        self.t = boto3.resource("dynamodb").Table(table)

    def get(self, key):
        i = self.t.get_item(Key={"pk": f"KV#{key}", "sk": "_"}, ConsistentRead=True).get("Item")
        return _from_ddb(i["value"]) if i else None

    def put(self, key, value):
        self.t.put_item(Item={"pk": f"KV#{key}", "sk": "_", "value": _to_ddb(value)})

    def put_if_absent(self, key, value):
        try:
            self.t.put_item(Item={"pk": f"KV#{key}", "sk": "_", "value": _to_ddb(value)}, ConditionExpression="attribute_not_exists(pk)")
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise


class S3Audit:
    """Um objeto JSON por evento. O papel da aplicação só tem s3:PutObject neste bucket."""

    def __init__(self, bucket: str):
        self.s3, self.bucket = boto3.client("s3"), bucket

    def write(self, event):
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"events/dt={day}/{event['stream']}/{event['seq']:06d}-{event['type']}.json"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=json.dumps(event, ensure_ascii=False).encode(), ContentType="application/json")


PROMPT = """Você apoia um especialista de política de crédito. Recebe só o sub-DAG afetado de uma política SINTÉTICA e um cenário.
Sugira até {cap} investigações complementares que o especialista ainda não pediu.
Regras obrigatórias:
- Não estime impacto. Não escreva números, percentuais nem contagens de propostas.
- Cite apenas ids de regra (R00x) e parâmetro (P00x) que existem no contexto.
- Responda SOMENTE com JSON: {{"suggestions":[{{"title":"...","text":"...","ruleRefs":["R00x"]}}]}}

Contexto:
{context}"""


class BedrockModel:
    """Amazon Nova via Converse. Modelo e teto vêm de configuração (ADR-14), não do código."""

    def __init__(self, model_id: str, max_tokens: int = 600):
        self.name = model_id
        self.max_tokens = max_tokens
        self.client = boto3.client("bedrock-runtime")

    def suggest(self, context, cap):
        try:
            r = self.client.converse(modelId=self.name,
                                     messages=[{"role": "user", "content": [{"text": PROMPT.format(cap=cap, context=json.dumps(context, ensure_ascii=False))}]}],
                                     inferenceConfig={"maxTokens": self.max_tokens, "temperature": 0.2})
        except ClientError as e:
            raise ModelUnavailable(f"Bedrock indisponível: {e.response['Error'].get('Code')}") from e
        text = "".join(c.get("text", "") for c in r["output"]["message"]["content"])
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ModelUnavailable("Resposta do modelo fora do formato JSON pedido")
        usage = r.get("usage", {})
        return json.loads(m.group(0)).get("suggestions", [])[:cap], int(usage.get("inputTokens", 0)) + int(usage.get("outputTokens", 0))


class LambdaSelfDispatcher:
    """Tira o job do caminho da requisição (ADR-02): invoca a própria função de forma assíncrona.
    O Lambda Web Adapter entrega eventos não HTTP em POST /events."""

    def __init__(self, function_name: str | None = None):
        self.fn = function_name or os.environ["AWS_LAMBDA_FUNCTION_NAME"]
        self.client = boto3.client("lambda")

    def dispatch(self, job):
        self.client.invoke(FunctionName=self.fn, InvocationType="Event", Payload=json.dumps({"ppJob": job}).encode())
