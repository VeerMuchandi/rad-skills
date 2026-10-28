#!/usr/bin/env bash
# Cloud Run MCP Server Deployer & OAuth 2.0 / Tool Verification Script
# Supports Standard Deployment + Enterprise Private Networking (Direct VPC Egress / PSC / Secret Manager)
set -euo pipefail

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY

PROJECT_ID=""
REGION="us-central1"
SERVICE_NAME=""
SOURCE_DIR="."
CLIENT_ID=""
CLIENT_SECRET=""
ALLOWED_DOMAIN=""
VPC_NETWORK=""
VPC_SUBNET=""
VPC_EGRESS="private-ranges-only"
SERVICE_ACCOUNT=""
SET_SECRETS=""
EXTRA_ENV_VARS=""
USE_SECRET_MANAGER="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT_ID="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --service-name) SERVICE_NAME="$2"; shift 2 ;;
    --source-dir) SOURCE_DIR="$2"; shift 2 ;;
    --client-id) CLIENT_ID="$2"; shift 2 ;;
    --client-secret) CLIENT_SECRET="$2"; shift 2 ;;
    --allowed-domain) ALLOWED_DOMAIN="$2"; shift 2 ;;
    --network) VPC_NETWORK="$2"; shift 2 ;;
    --subnet) VPC_SUBNET="$2"; shift 2 ;;
    --vpc-egress) VPC_EGRESS="$2"; shift 2 ;;
    --service-account) SERVICE_ACCOUNT="$2"; shift 2 ;;
    --set-secrets) SET_SECRETS="$2"; shift 2 ;;
    --extra-env-vars) EXTRA_ENV_VARS="$2"; shift 2 ;;
    --use-secret-manager) USE_SECRET_MANAGER="true"; shift 1 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$PROJECT_ID" || -z "$SERVICE_NAME" || -z "$CLIENT_ID" || -z "$CLIENT_SECRET" ]]; then
  cat <<EOF
Usage: $0 \\
  --project <PROJECT_ID> \\
  --service-name <SERVICE_NAME> \\
  --client-id <CLIENT_ID> \\
  --client-secret <CLIENT_SECRET> \\
  [--region <REGION>] \\
  [--source-dir <DIR>] \\
  [--allowed-domain <DOMAIN>] \\
  [--network <VPC_NETWORK>] \\
  [--subnet <VPC_SUBNET>] \\
  [--vpc-egress <private-ranges-only|all-traffic>] \\
  [--service-account <CUSTOM_SA_EMAIL>] \\
  [--use-secret-manager] \\
  [--set-secrets <ENV_VAR=SECRET:VERSION,...>] \\
  [--extra-env-vars <KEY=VAL,...>]
EOF
  exit 1
fi

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
echo "=== [1/4] Enabling required Google Cloud APIs in $PROJECT_ID ($PROJECT_NUMBER) ==="
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  bigquery.googleapis.com \
  secretmanager.googleapis.com \
  compute.googleapis.com \
  --project "$PROJECT_ID"

echo "=== [2/4] Configuring Runtime Service Account & IAM Permissions ==="
if [[ -n "$SERVICE_ACCOUNT" ]]; then
  RUNTIME_SA="$SERVICE_ACCOUNT"
else
  RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
fi

for ROLE in \
  "roles/bigquery.jobUser" \
  "roles/bigquery.dataViewer" \
  "roles/cloudbuild.builds.builder" \
  "roles/storage.objectAdmin" \
  "roles/artifactregistry.writer" \
  "roles/secretmanager.secretAccessor" \
  "roles/logging.logWriter"; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="$ROLE" \
    --condition=None >/dev/null || true
done

ENV_VARS="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},MCP_TRANSPORT=streamable-http,REQUIRE_OAUTH=true,GOOGLE_OAUTH_CLIENT_ID=${CLIENT_ID},OAUTH_REQUIRED_SCOPES=openid email profile"

if [[ "$USE_SECRET_MANAGER" == "true" ]]; then
  SECRET_ID="${SERVICE_NAME}-oauth-client-secret"
  echo "Storing GOOGLE_OAUTH_CLIENT_SECRET in Secret Manager ($SECRET_ID)..."
  if ! gcloud secrets describe "$SECRET_ID" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$SECRET_ID" --replication-policy="automatic" --project "$PROJECT_ID" >/dev/null
  fi
  printf "%s" "$CLIENT_SECRET" | gcloud secrets versions add "$SECRET_ID" --data-file=- --project "$PROJECT_ID" >/dev/null
  if [[ -n "$SET_SECRETS" ]]; then
    SET_SECRETS="${SET_SECRETS},GOOGLE_OAUTH_CLIENT_SECRET=${SECRET_ID}:latest"
  else
    SET_SECRETS="GOOGLE_OAUTH_CLIENT_SECRET=${SECRET_ID}:latest"
  fi
else
  ENV_VARS="${ENV_VARS},GOOGLE_OAUTH_CLIENT_SECRET=${CLIENT_SECRET}"
fi

if [[ -n "$ALLOWED_DOMAIN" ]]; then
  ENV_VARS="${ENV_VARS},GOOGLE_ALLOWED_DOMAIN=${ALLOWED_DOMAIN}"
fi
if [[ -n "$EXTRA_ENV_VARS" ]]; then
  ENV_VARS="${ENV_VARS},${EXTRA_ENV_VARS}"
fi

DEPLOY_ARGS=(
  "$SERVICE_NAME"
  --source "$SOURCE_DIR"
  --project "$PROJECT_ID"
  --region "$REGION"
  --platform managed
  --allow-unauthenticated
  --set-env-vars "$ENV_VARS"
  --service-account "$RUNTIME_SA"
  --memory 1Gi
  --cpu 1
  --min-instances 0
  --max-instances 5
  --session-affinity
  --quiet
)

if [[ -n "$SET_SECRETS" ]]; then
  DEPLOY_ARGS+=(--set-secrets "$SET_SECRETS")
fi

if [[ -n "$VPC_NETWORK" || -n "$VPC_SUBNET" ]]; then
  echo "Configuring Direct VPC Egress (network=${VPC_NETWORK:-default}, subnet=${VPC_SUBNET:-default}, egress=${VPC_EGRESS})..."
  [[ -n "$VPC_NETWORK" ]] && DEPLOY_ARGS+=(--network "$VPC_NETWORK")
  [[ -n "$VPC_SUBNET" ]] && DEPLOY_ARGS+=(--subnet "$VPC_SUBNET")
  DEPLOY_ARGS+=(--vpc-egress "$VPC_EGRESS")
fi

echo "=== [3/4] Deploying $SERVICE_NAME to Cloud Run ($REGION) ==="
gcloud run deploy "${DEPLOY_ARGS[@]}"

# Ensure allUsers has roles/run.invoker (in case org policy blocked --allow-unauthenticated during deploy)
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --member="allUsers" \
  --role="roles/run.invoker" >/dev/null || {
    echo "WARNING: Could not grant allUsers roles/run.invoker. Relax constraints/iam.allowedPolicyMemberDomains on $PROJECT_ID and retry."
  }

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --project "$PROJECT_ID" --region "$REGION" --format="value(status.url)")
echo "=== [4/4] Verifying Cloud Run Health, OAuth 2.0 Handshake & MCP Tools ($SERVICE_URL) ==="
curl -sf "${SERVICE_URL}/" | python3 -m json.tool

REDIRECT_LOC=$(curl -s -I "${SERVICE_URL}/authorize?client_id=${CLIENT_ID}&redirect_uri=https://vertexaisearch.cloud.google.com/oauth-redirect&response_type=code&scope=openid%20email%20profile" | grep -i "^location:" | awk '{print $2}' | tr -d '\r')
AUTH_CODE=$(python3 -c "import urllib.parse, sys; print(urllib.parse.parse_qs(urllib.parse.urlparse(sys.argv[1]).query)['code'][0])" "$REDIRECT_LOC")

TOKEN_JSON=$(curl -s -X POST "${SERVICE_URL}/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&code=${AUTH_CODE}&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}&redirect_uri=https://vertexaisearch.cloud.google.com/oauth-redirect")

REFRESH_TOKEN=$(echo "$TOKEN_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['refresh_token'])")
ACCESS_TOKEN=$(echo "$TOKEN_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
echo "Verified OAuth 2.0 /authorize & /token handshake (minted access_token & refresh_token)."

TOOLS_SSE=$(curl -s -X POST "${SERVICE_URL}/mcp" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}')

python3 -c "
import sys, json
raw = sys.stdin.read()
for line in raw.splitlines():
    if line.startswith('data: '):
        raw = line[6:]
        break
tools = json.loads(raw)['result']['tools']
print(f'Verified /mcp tools/list ({len(tools)} tools):', [t['name'] for t in tools])
" <<< "$TOOLS_SSE"

echo ""
echo "========================================================================"
echo " Cloud Run MCP Server Deployed & Verified!"
echo "------------------------------------------------------------------------"
echo " MCP Server URL:               ${SERVICE_URL}/mcp"
echo " Authorization URL:            ${SERVICE_URL}/authorize"
echo " Authorization URL Parameters: &access_type=offline&prompt=consent"
echo " Token URL:                    ${SERVICE_URL}/token"
echo " Dynamic Registration URL:     ${SERVICE_URL}/register"
echo " Client ID:                    ${CLIENT_ID}"
echo " Scopes:                       openid email profile"
echo "========================================================================"
