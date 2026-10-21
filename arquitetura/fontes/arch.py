"""Gera o diagrama de arquitetura do Policy Playground (SVG em HTML) e renderiza PNG 4K."""
import sys, html
from pathlib import Path

OUT = Path(sys.argv[1])  # pasta arch/ (contém icons/)
W, H = 2400, 1350

INK, SEC = "#16191F", "#545B64"
ARROW = "#545B64"
ACCENT = "#C2185B"          # cor do time (badges do fluxo)
CLOUD, REGION, VPC, SUBNET, AZ = "#232F3E", "#00A4A6", "#8C4FFF", "#00A4A6", "#147EBA"

parts = []
def add(s): parts.append(s)
def esc(s): return html.escape(s)

def text(x, y, s, size=16, weight=400, color=INK, anchor="start"):
    add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{esc(s)}</text>')

def icon(name, x, y, s):
    add(f'<image href="icons/{name}.svg" x="{x}" y="{y}" width="{s}" height="{s}"/>')

def group(x, y, w, h, label, color, icon_name=None, dash=None, fill="none", label_color=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{color}" stroke-width="2"{d}/>')
    tx = x + 12
    if icon_name:
        icon(icon_name, x, y, 36)
        tx = x + 46
    text(tx, y + 25, label, 17, 600, label_color or color)

def node(x, y, w, h, icons, name, lines, dashed=False, isz=60):
    d = ' stroke-dasharray="8 6"' if dashed else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#FFFFFF" stroke="#D5DBDB" stroke-width="1.5"{d}/>')
    total = len(icons) * isz + (len(icons) - 1) * 10
    ix = x + (w - total) / 2
    for nm in icons:
        icon(nm, ix, y + 14, isz)
        ix += isz + 10
    cx = x + w / 2
    ty = y + 14 + isz + 26
    text(cx, ty, name, 18, 700, INK, "middle")
    for i, ln in enumerate(lines):
        text(cx, ty + 22 * (i + 1), ln, 15.5, 400, SEC, "middle")

def arrow(d, dashed=False, color=ARROW, width=2.2):
    da = ' stroke-dasharray="8 6"' if dashed else ""
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{da} marker-end="url(#arr)"/>')

def label(x, y, s, anchor="middle"):
    text(x, y, s, 14.5, 500, SEC, anchor)

def badge(x, y, n):
    add(f'<circle cx="{x}" cy="{y}" r="17" fill="{ACCENT}"/>')
    text(x, y + 6, str(n), 17, 700, "#FFFFFF", "middle")

# ---------------- cabeçalho
text(60, 62, "Policy Playground — Arquitetura da Solução na AWS", 40, 700)
text(60, 100, "us-east-1 · 2 zonas de disponibilidade · AI proposes, deterministic execution proves, humans decide", 20, 400, SEC)
text(2340, 62, "CredIA Girls", 36, 800, ACCENT, "end")
text(2340, 98, "AWS Builders League", 20, 500, SEC, "end")

# ---------------- coluna externa
node(60, 200, 270, 150, ["Users"], "Especialistas", ["políticas de crédito e risco"])
node(60, 440, 270, 150, ["Corporatedatacenter"], "Microsoft Entra ID", ["login corporativo (OIDC)"])

# legenda do fluxo
add(f'<rect x="60" y="640" width="270" height="650" rx="10" fill="#F7F8F8" stroke="#D5DBDB" stroke-width="1.5"/>')
text(80, 676, "Fluxo principal", 19, 700)
steps = [
    ("Login no Entra ID; SPA", "via CloudFront + WAF"),
    ("API Gateway valida o JWT", "e aplica throttling"),
    ("VPC Link → ALB → API", "task em 2 AZs"),
    ("API grava 1 evento no", "DynamoDB e responde 202"),
    ("DynamoDB Streams aciona", "o EventBridge Pipes"),
    ("Pipes roteia o job para", "a fila SQS do tipo certo"),
    ("Workers Spot consomem;", "resultado por hash no S3"),
    ("worker-llm chama o Bedrock", "com cache e limites"),
    ("Auditoria: Firehose →", "S3 Object Lock → Athena"),
]
for i, (a, b) in enumerate(steps):
    yy = 718 + i * 63
    badge(96, yy, i + 1)
    text(124, yy - 3, a, 14.5, 500, INK)
    text(124, yy + 16, b, 14.5, 400, SEC)

# ---------------- grupos AWS
group(380, 130, 1960, 1180, "AWS Cloud", CLOUD, "AWSCloudlogo", label_color=CLOUD)
group(400, 178, 1920, 1112, "Region us-east-1", REGION, "Region", dash="10 6")

# borda
node(440, 215, 240, 150, ["AmazonCloudFront", "AWSWAF"], "CloudFront + WAF", ["SPA e /api no mesmo domínio"], isz=54)
node(440, 460, 240, 170, ["AmazonAPIGateway"], "API Gateway", ["HTTP API · JWT Entra ID", "timeout 30 s: rotas curtas"])
node(440, 700, 240, 140, ["AmazonSimpleStorageService"], "Amazon S3", ["SPA estática (OAC)"], isz=54)

# observabilidade / segurança / finops
add(f'<rect x="420" y="890" width="290" height="385" rx="10" fill="#F7F8F8" stroke="#D5DBDB" stroke-width="1.5"/>')
text(438, 920, "Operação, segurança e FinOps", 16.5, 700)
ops = [("AmazonCloudWatch", "CloudWatch", "logs, métricas, canary"),
       ("AWSXRay", "X-Ray", "tracing distribuído"),
       ("AWSKeyManagementService", "KMS", "criptografia em repouso"),
       ("AWSBudgets", "Budgets", "custo por hipótese, alertas"),
       ("AWSBackup", "AWS Backup", "DR em segunda região")]
for i, (ic, a, b) in enumerate(ops):
    yy = 940 + i * 66
    icon(ic, 438, yy, 44)
    text(494, yy + 19, a, 15.5, 700)
    text(494, yy + 39, b, 14, 400, SEC)

# VPC
group(740, 215, 800, 680, "VPC privada · sem NAT · sem IP público", VPC, "VirtualprivatecloudVPC")
node(900, 255, 280, 140, ["ElasticLoadBalancingApplicationLoadBalancer"], "ALB interno", ["2 AZs · health check"], isz=54)
node(1250, 255, 270, 150, ["AmazonVPCEndpoints"], "VPC endpoints", ["S3, DynamoDB, ECR, Logs,", "SQS, Bedrock, AppConfig"], isz=54)
for gx, az in ((758, "a"), (1148, "b")):
    group(gx, 432, 374, 448, f"AZ {az}", AZ, dash="8 6")
    add(f'<rect x="{gx+12}" y="470" width="350" height="398" fill="#F2FAFA" stroke="{SUBNET}" stroke-width="2"/>')
    if az == "a":
        icon("Privatesubnet", gx + 118, 832, 36)
        text(gx + 160, 857, "Private subnet", 16, 600, SUBNET)
    else:
        icon("Privatesubnet", gx + 326, 832, 36)
        text(gx + 318, 857, "Private subnet", 16, 600, SUBNET, "end")
    node(gx + 28, 520, 152, 220, ["AWSFargate"], "Task API", ["Fargate ARM", "stateless", "100% do pico"], isz=56)
    node(gx + 194, 520, 152, 220, ["AWSFargate"], "Workers", ["Fargate Spot", "llm · sim · ingest", "lease + retry"], isz=56)

# IA e assíncrono
group(1575, 215, 725, 680, "IA, filas e controle", "#7D8998", dash="8 6", label_color=SEC)
node(1610, 260, 300, 175, ["AmazonBedrock"], "Amazon Bedrock", ["Converse + Guardrails", "prompt cache · teto de tokens"])
node(1610, 560, 300, 150, ["AmazonSimpleQueueService"], "Amazon SQS", ["llm · sim · ingest + DLQ"])
node(1680, 735, 230, 150, ["AWSLambda"], "Lambda · PR (C3)", ["fora da VPC, por evento", "token no Secrets Manager"], dashed=True, isz=50)
node(1960, 260, 310, 150, ["AWSAppConfig"], "AWS AppConfig", ["feature flags e limites"])
node(1960, 450, 310, 150, ["AmazonSimpleStorageService"], "Amazon S3", ["policy · results/hash · artifacts"])
node(1960, 640, 310, 205, ["AWSStepFunctions", "AWSLakeFormation"], "Execução real (C1)", ["Step Functions + Lake Formation", "lê Motivo de Decisão · OQ-4"], dashed=True, isz=54)

# dados, eventos e auditoria
group(740, 930, 1560, 345, "", "#7D8998", dash="8 6", label_color=SEC)
text(2288, 955, "Dados, eventos e auditoria", 17, 600, SEC, "end")
bx = [765, 1105, 1385, 1665, 1945]
node(bx[0], 985, 310, 190, ["AmazonDynamoDB"], "Amazon DynamoDB", ["events imutável + state", "Motivo de Decisão (só leitura)", "Streams · PITR"])
node(bx[1], 985, 250, 190, ["AmazonEventBridgePipes"], "EventBridge Pipes", ["stream → filas e auditoria"])
node(bx[2], 985, 250, 190, ["AmazonDataFirehose"], "Data Firehose", ["eventos → Parquet"])
node(bx[3], 985, 250, 190, ["AmazonSimpleStorageServiceGlacier"], "S3 audit", ["Object Lock por ambiente", "Glacier no longo prazo"])
node(bx[4], 985, 250, 190, ["AmazonAthena"], "Amazon Athena", ["consulta da trilha"])

# legenda visual
add('<rect x="1080" y="1222" width="44" height="26" rx="6" fill="#fff" stroke="#7D8998" stroke-width="1.5" stroke-dasharray="8 6"/>')
text(1134, 1241, "condicional (OQ-4, OQ-9)", 15, 400, SEC)
badge(1420, 1235, "n")
text(1446, 1241, "passo do fluxo principal", 15, 400, SEC)
add('<path d="M1680 1235 H1730" stroke="#545B64" stroke-width="2.2" stroke-dasharray="8 6" marker-end="url(#arr)"/>')
text(1742, 1241, "autenticação / leitura", 15, 400, SEC)

# ---------------- setas
arrow("M330 290 H436")                                  # 1 users -> cf
badge(355, 262, 1)
arrow("M195 350 V436", dashed=True); label(205, 400, "login", "start")
arrow("M560 365 V456")                                  # 2 cf -> apigw
badge(560, 410, 2)
arrow("M440 540 H334", dashed=True); label(376, 530, "JWKS", "end")
arrow("M440 330 H424 V770 H436")                        # cf -> s3 spa
arrow("M680 560 H722 V325 H896")                        # 3 apigw -> alb
badge(722, 450, 3); label(812, 314, "VPC Link")
arrow("M1040 395 V412 H862 V516")                       # alb -> api a
arrow("M1040 412 H1252 V516")                           # alb -> api b
arrow("M862 740 V981")                                  # 4 api -> dynamodb
badge(862, 800, 4); label(874, 920, "1 escrita por comando", "start")
arrow("M1075 1070 H1101")                               # 5 dynamo -> pipes
badge(1090, 1040, 5)
arrow("M1060 740 V981", dashed=True); label(1072, 960, "lê Motivo (C1)", "start")
arrow("M1230 985 V915 H1640 V714")                      # 6 pipes -> sqs
badge(1500, 915, 6)
arrow("M1610 640 H1498")                                # 7 sqs -> workers b
badge(1560, 612, 7)
arrow("M1420 520 V414 H1558 V345 H1606")                # 8 workers -> bedrock
badge(1558, 380, 8)
arrow("M1355 1070 H1381")                               # 9 pipes -> firehose
badge(1370, 1040, 9)
arrow("M1635 1070 H1661")
arrow("M1915 1070 H1941"); label(1928, 1058, "SQL")

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
       '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
       f'<path d="M0 0L10 5L0 10z" fill="{ARROW}"/></marker></defs>'
       f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>' + "".join(parts) + "</svg>")
page = ("<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;padding:0;background:#fff}"
        "svg{display:block;font-family:Inter,'DejaVu Sans',sans-serif}</style></head><body>" + svg + "</body></html>")
(OUT / "architecture.html").write_text(page, encoding="utf-8")
print("ok")
