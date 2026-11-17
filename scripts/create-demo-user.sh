#!/usr/bin/env bash
# Cria um usuário da demo no Cognito. A senha temporária vai direto para o e-mail da pessoa
# (ninguém a digita em chat ou em código); ela define a própria senha no primeiro login.
#   bash create-demo-user.sh <email> <policy-specialist|risk-approver|data-analyst|viewer> [stack]
set -euo pipefail
EMAIL="${1:?e-mail}"; GROUP="${2:?grupo}"; STACK="${3:-PolicyPlaygroundDemo}"
POOL="$(aws cloudformation describe-stacks --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text)"
aws cognito-idp admin-create-user --user-pool-id "$POOL" --username "$EMAIL" \
  --user-attributes Name=email,Value="$EMAIL" Name=email_verified,Value=true --desired-delivery-mediums EMAIL >/dev/null
aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL" --username "$EMAIL" --group-name "$GROUP"
echo "Convite enviado para $EMAIL (grupo $GROUP)."
