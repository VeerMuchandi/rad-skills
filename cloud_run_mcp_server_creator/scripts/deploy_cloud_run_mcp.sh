#!/usr/bin/env bash
# Cloud Run MCP Server Deployer & OAuth 2.0 / Tool Verification Script
set -euo pipefail

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY

PROJECT_ID=""
REGION="us-central1"
SERVICE_NAME=""
SOURCE_DIR="."
CLIENT_ID=""
CLIENT_SECRET=""
ALLOWED_DOMAIN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT_ID="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --service-name) SERVICE_NAME="$2"; shift 2 ;;
    --source-dir) SOURCE_DIR="$2"; shift 2 ;;
    --client-id) CLIENT_ID="$2"; shift 2 ;;
    --client-secret) CLIENT_SECRET="$2"; shift 2 ;;
    --allowed-domain) ALLOWED_DOMAIN="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$PROJECT_ID" || -z "$SERVICE_NAME" || -z "$CLIENT_ID" || -z "$CLIENT_SECRET" ]]; then
  echo "Usage: $0 --project <PROJECT_ID> --service-name <SERVICE_NAME> --client-id <CLIENT_ID> --client-secret <CLIENT_SECRET> [--region <REGION>] [--source-dir <DIR>] [--allowed-domain <DOMAIN>]"
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
  --project "$PROJECT_ID"

echo "=== [2/4] Granting build & runtime permissions to Compute Service Account ==="
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for ROLE in \
  "roles/bigquery.jobUser" \
  "roles/bigquery.dataViewer" \
  "roles/cloudbuild.builds.builder" \
  "roles/storage.objectAdmin" \
  "roles/artifactregistry.writer" \
  "roles/logging.logWriter"; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="$ROLE" \
    --condition=None >/dev/null
done

ENV_VARS="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},MCP_TRANSPORT=streamable-http,REQUIRE_OAUTH=true,GOOGLE_OAUTH_CLIENT_ID=${CLIENT_ID},GOOGLE_OAUTH_CLIENT_SECRET=${CLIENT_SECRET},OAUTH_REQUIRED_SCOPES=openid email profile"
if [[ -n "$ALLOWED_DOMAIN" ]]; then
  ENV_VARS="${ENV_VARS},GOOGLE_ALLOWED_DOMAIN=${ALLOWED_DOMAIN}"
fi

echo "=== [3/4] Deploying $SERVICE_NAME to Cloud Run ($REGION) ==="
gcloud run deploy "$SERVICE_NAME" \
  --source "$SOURCE_DIR" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "$ENV_VARS" \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 5 \
  --session-affinity \
  --quiet

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
echo " Client ID:                    ${CLIENT_ID}"
echo " Scopes:                       openid email profile"
echo "========================================================================"
