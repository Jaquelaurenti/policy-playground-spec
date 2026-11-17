#!/usr/bin/env bash
# Rode UMA vez no AWS CloudShell da conta que vai hospedar a demo (console → ícone >_ no topo).
# Serve para qualquer conta e qualquer fork: passe o SEU <dono/repo> e a SUA região.
# Cria: (1) o provedor OIDC do GitHub, (2) um papel que SÓ a branch main desse repositório pode assumir,
# com permissão apenas para assumir os papéis do CDK, e (3) o bootstrap do CDK na região.
# Nenhuma chave de acesso é criada nem sai da conta.
#
#   bash cloudshell-bootstrap.sh <owner/repo> [regiao]
#   ex.: bash cloudshell-bootstrap.sh Jaquelaurenti/policy-playground-spec us-east-1
set -euo pipefail
REPO="${1:?informe owner/repo, ex. Jaquelaurenti/policy-playground-spec}"
REGION="${2:-us-east-1}"
ROLE="policy-playground-github-deploy"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
OIDC="arn:aws:iam::${ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"

echo "Conta ${ACCOUNT}, região ${REGION}, repositório ${REPO}"

if ! aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC" >/dev/null 2>&1; then
  aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 >/dev/null
  echo "Provedor OIDC do GitHub criado."
fi

# O GitHub pode emitir o "sub" do token em dois formatos: o clássico (repo:dono/repo:...) e o
# imutável, com os IDs numéricos (repo:dono@ID/repo@ID:...). Aceitamos os dois, senão o deploy
# falha com "Not authorized to perform sts:AssumeRoleWithWebIdentity".
SUBS="\"repo:${REPO}:ref:refs/heads/main\",\"repo:${REPO}:environment:demo\""
IDS="$(curl -fsSL "https://api.github.com/repos/${REPO}" 2>/dev/null \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["owner"]["login"], d["owner"]["id"], d["name"], d["id"])' 2>/dev/null || true)"
if [ -n "$IDS" ]; then
  read -r OWNER OWNER_ID NAME REPO_ID <<<"$IDS"
  IMM="repo:${OWNER}@${OWNER_ID}/${NAME}@${REPO_ID}"
  SUBS="${SUBS},\"${IMM}:ref:refs/heads/main\",\"${IMM}:environment:demo\""
else
  echo "Aviso: não consegui ler os IDs do repositório na API do GitHub (repositório privado?)."
  echo "       Se o deploy falhar ao assumir o papel, rode de novo com o repositório público ou ajuste a confiança."
fi

cat > /tmp/trust.json <<JSON
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Federated":"${OIDC}"},
 "Action":"sts:AssumeRoleWithWebIdentity",
 "Condition":{"StringEquals":{"token.actions.githubusercontent.com:aud":"sts.amazonaws.com"},
  "StringLike":{"token.actions.githubusercontent.com:sub":[${SUBS}]}}}]}
JSON
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
