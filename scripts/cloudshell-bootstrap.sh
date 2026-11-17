#!/usr/bin/env bash
# Rode UMA vez no AWS CloudShell da conta que vai hospedar a demo (console → ícone >_ no topo).
# Serve para qualquer conta e qualquer fork: passe o SEU <dono/repo> e a SUA região.
# Cria: (1) o provedor OIDC do GitHub, (2) um papel que SÓ a branch main desse repositório pode assumir,
# com permissão apenas para assumir os papéis do CDK, e (3) o bootstrap do CDK na região.
# Nenhuma chave de acesso é criada nem sai da conta.
#
#   bash cloudshell-bootstrap.sh <owner/repo> [regiao]
#   ex.: bash cloudshell-bootstrap.sh Jaquelaurenti/policy-playground-spec us-east-1
#
# Formato do "sub" do token do GitHub na confiança do papel (variável PP_SUB_FORMAT):
#   both      (padrão) aceita o clássico (repo:dono/repo:...) e o imutável (repo:dono@ID/repo@ID:...)
#   immutable só o imutável, preso aos IDs numéricos: mais seguro se o repositório usa esse formato
#   classic   só o clássico, para repositório privado (a API pública não devolve os IDs)
# Sem o formato certo, o deploy falha com "Not authorized to perform sts:AssumeRoleWithWebIdentity".
set -euo pipefail
REPO="${1:?informe owner/repo, ex. Jaquelaurenti/policy-playground-spec}"
REGION="${2:-us-east-1}"
SUB_FORMAT="${PP_SUB_FORMAT:-both}"
ROLE="policy-playground-github-deploy"

# Valida as entradas antes de tocar na conta: um curinga em REPO abriria o papel para qualquer repositório.
if ! [[ "$REPO" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$ ]]; then
  echo "Erro: '$REPO' não é um <dono>/<repositório> do GitHub válido." >&2; exit 1
fi
if ! [[ "$REGION" =~ ^[a-z]{2}(-[a-z]+)+-[0-9]+$ ]]; then
  echo "Erro: '$REGION' não é uma região AWS válida (ex.: us-east-1)." >&2; exit 1
fi
case "$SUB_FORMAT" in both|immutable|classic) ;; *)
  echo "Erro: PP_SUB_FORMAT deve ser both, immutable ou classic." >&2; exit 1;;
esac

# IDs numéricos do repositório, necessários para o formato imutável.
IMM=""
if [ "$SUB_FORMAT" != "classic" ]; then
  IDS="$(curl -fsSL "https://api.github.com/repos/${REPO}" 2>/dev/null | REPO="$REPO" python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    sys.exit(1)
if d["full_name"].lower() != os.environ["REPO"].lower():
    sys.exit("o GitHub devolveu " + d["full_name"] + "; use o nome atual do repositório")
print(d["full_name"], d["owner"]["login"], d["owner"]["id"], d["name"], d["id"])' || true)"
  if [ -z "$IDS" ]; then
    echo "Erro: não consegui ler os IDs de ${REPO} na API pública do GitHub." >&2
    echo "      Confira o nome e se o repositório é público. Para repositório privado, rode com PP_SUB_FORMAT=classic." >&2
    exit 1
  fi
  read -r REPO OWNER OWNER_ID NAME REPO_ID <<<"$IDS"   # nome canônico: o sub diferencia maiúsculas
  IMM="repo:${OWNER}@${OWNER_ID}/${NAME}@${REPO_ID}"
fi

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
OIDC="arn:aws:iam::${ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"

echo "Conta ${ACCOUNT}, região ${REGION}, repositório ${REPO}, formato do sub: ${SUB_FORMAT}"

if CLIENT_IDS="$(aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC" --query ClientIDList --output text 2>/dev/null)"; then
  if ! tr '\t' '\n' <<<"$CLIENT_IDS" | grep -qx "sts.amazonaws.com"; then
    aws iam add-client-id-to-open-id-connect-provider --open-id-connect-provider-arn "$OIDC" --client-id sts.amazonaws.com
    echo "Audience sts.amazonaws.com adicionada ao provedor OIDC existente."
  fi
else
  aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 >/dev/null
  echo "Provedor OIDC do GitHub criado."
fi

# A política é montada por um codificador JSON, nunca por concatenação de texto.
OIDC="$OIDC" REPO="$REPO" IMM="$IMM" SUB_FORMAT="$SUB_FORMAT" python3 -c '
import json, os
repo, imm, fmt = os.environ["REPO"], os.environ["IMM"], os.environ["SUB_FORMAT"]
bases = ([f"repo:{repo}"] if fmt in ("both", "classic") else []) + ([imm] if fmt in ("both", "immutable") else [])
subs = [f"{b}:{s}" for b in bases for s in ("ref:refs/heads/main", "environment:demo")]
print(json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
    "Principal": {"Federated": os.environ["OIDC"]}, "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
                  "StringLike": {"token.actions.githubusercontent.com:sub": subs}}}]}))' > /tmp/trust.json
cat > /tmp/policy.json <<JSON
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"sts:AssumeRole",
 "Resource":"arn:aws:iam::${ACCOUNT}:role/cdk-hnb659fds-*-${ACCOUNT}-${REGION}"}]}
JSON
if aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam update-assume-role-policy --role-name "$ROLE" --policy-document file:///tmp/trust.json
else
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document file:///tmp/trust.json \
    --tags Key=project,Value=policy-playground Key=environment,Value=demo >/dev/null
fi
aws iam put-role-policy --role-name "$ROLE" --policy-name assume-cdk-roles --policy-document file:///tmp/policy.json

npx --yes aws-cdk@2.173.4 bootstrap "aws://${ACCOUNT}/${REGION}" --tags project=policy-playground --tags environment=demo

echo
echo "Pronto. No GitHub de ${REPO}: Settings → Secrets and variables → Actions → aba Variables, crie:"
echo "  AWS_ROLE_ARN = arn:aws:iam::${ACCOUNT}:role/${ROLE}"
echo "  AWS_REGION   = ${REGION}"
echo "  ALERT_EMAIL  = <e-mail para alertas de orçamento>"
echo "  PP_MODEL_ID  = us.amazon.nova-lite-v1:0   (opcional; habilite o modelo no console do Bedrock antes)"
