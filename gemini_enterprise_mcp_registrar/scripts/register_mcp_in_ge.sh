#!/usr/bin/env bash
# Standalone Gemini Enterprise (Discovery Engine), Agent Registry & Agent Identity MCP Registrar
set -euo pipefail

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY

ACTION="inspect" # inspect | fp64 | register-custom-mcp | register-bigquery-mcp | republish | delete
PROJECT_ID=""
LOCATION="global"
ENGINE_ID=""
COLLECTION_ID=""
DISPLAY_NAME="Custom MCP Server"
DESCRIPTION="Custom MCP Server registered in Gemini Enterprise."
MCP_URI=""
AUTH_URL=""
TOKEN_URL=""
CLIENT_ID=""
CLIENT_SECRET=""
SCOPES="openid email profile"
USE_PREPROD="true"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --action) ACTION="$2"; shift 2 ;;
    --project|--ge-project) PROJECT_ID="$2"; shift 2 ;;
    --location|--ge-location) LOCATION="$2"; shift 2 ;;
    --engine-id) ENGINE_ID="$2"; shift 2 ;;
    --collection-id) COLLECTION_ID="$2"; shift 2 ;;
    --display-name) DISPLAY_NAME="$2"; shift 2 ;;
    --description) DESCRIPTION="$2"; shift 2 ;;
    --mcp-uri|--mcp-url) MCP_URI="$2"; shift 2 ;;
    --auth-url|--auth-uri) AUTH_URL="$2"; shift 2 ;;
    --token-url|--token-uri) TOKEN_URL="$2"; shift 2 ;;
    --client-id) CLIENT_ID="$2"; shift 2 ;;
    --client-secret) CLIENT_SECRET="$2"; shift 2 ;;
    --scopes) SCOPES="$2"; shift 2 ;;
    --prod-only) USE_PREPROD="false"; shift 1 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

compute_fp64() {
  local val="$1"
  python3 - "$val" << 'EOF'
import struct, sys

MASK64 = 0xFFFFFFFFFFFFFFFF
K0 = 0xa5b85c5e198ed849
K1 = 0x8d58ac26afe12e47
K2 = 0xc47b6e9e3a970ed3
MUL = 0xc6a4a7935bd1e995

def u64(b, offset=0):
    return struct.unpack_from("<Q", b, offset)[0]

def rotate(v, shift):
    v &= MASK64
    return ((v >> shift) | (v << (64 - shift))) & MASK64

def shift_mix(v):
    v &= MASK64
    return (v ^ (v >> 47)) & MASK64

def hash128_to_64(hi, lo):
    hi &= MASK64
    lo &= MASK64
    a = ((lo ^ hi) * MUL) & MASK64
    a ^= (a >> 47)
    b = ((hi ^ a) * MUL) & MASK64
    b ^= (b >> 47)
    b = (b * MUL) & MASK64
    return b

def murmur_hash64_with_seed(s: bytes, seed: int) -> int:
    h = (seed ^ ((len(s) * MUL) & MASK64)) & MASK64
    idx = 0
    while len(s) - idx >= 8:
        data = (shift_mix((u64(s, idx) * MUL) & MASK64) * MUL) & MASK64
        h = ((h ^ data) * MUL) & MASK64
        idx += 8
    rem = s[idx:]
    if rem:
        data = 0
        for i, b in enumerate(rem):
            data |= (b << (8 * i))
        h = ((h ^ data) * MUL) & MASK64
    h = (shift_mix(h) * MUL) & MASK64
    h = shift_mix(h)
    return h

def weak32(s: bytes, off: int, a: int, b: int):
    w = u64(s, off)
    x = u64(s, off + 8)
    y = u64(s, off + 16)
    z = u64(s, off + 24)
    a = (a + w) & MASK64
    b = rotate((b + a + z) & MASK64, 51)
    c = a
    a = (a + x + y) & MASK64
    b = (b + rotate(a, 23)) & MASK64
    return (a + z) & MASK64, (b + c) & MASK64

def hash33(s: bytes) -> int:
    n = len(s)
    z = u64(s, 24)
    a = (u64(s, 0) + ((n + u64(s, n - 16)) * K0)) & MASK64
    b = rotate((a + z) & MASK64, 52)
    c = rotate(a, 37)
    a = (a + u64(s, 8)) & MASK64
    c = (c + rotate(a, 7)) & MASK64
    a = (a + u64(s, 16)) & MASK64
    vf = (a + z) & MASK64
    vs = (b + rotate(a, 31) + c) & MASK64
    a = (u64(s, 16) + u64(s, n - 32)) & MASK64
    z = u64(s, n - 8)
    b = rotate((a + z) & MASK64, 52)
    c = rotate(a, 37)
    a = (a + u64(s, n - 24)) & MASK64
    c = (c + rotate(a, 7)) & MASK64
    a = (a + u64(s, n - 16)) & MASK64
    wf = (a + z) & MASK64
    ws = (b + rotate(a, 31) + c) & MASK64
    r = shift_mix(((vf + ws) * K2 + (wf + vs) * K0) & MASK64)
    return (shift_mix((r * K0 + vs) & MASK64) * K2) & MASK64

def hash65(s: bytes) -> int:
    n = len(s)
    x = u64(s, 0)
    y = u64(s, n - 16) ^ K1
    z = u64(s, n - 56) ^ K0
    v1, v2 = weak32(s, n - 64, n, y)
    w1, w2 = weak32(s, n - 32, (n * K1) & MASK64, K0)
    z = (z + shift_mix(v2) * K1) & MASK64
    x = (rotate((z + x) & MASK64, 39) * K1) & MASK64
    y = (rotate(y, 33) * K1) & MASK64
    s = s[:-1]
    off = 0
    while len(s) - off >= 64:
        x = (rotate((x + y + v1 + u64(s, off + 16)) & MASK64, 37) * K1) & MASK64
        y = (rotate((y + v2 + u64(s, off + 48)) & MASK64, 42) * K1) & MASK64
        x ^= w2
        y ^= v1
        z = rotate(z ^ w1, 33)
        v1, v2 = weak32(s, off, (v2 * K1) & MASK64, (x + w1) & MASK64)
        w1, w2 = weak32(s, off + 32, (z + w2) & MASK64, y)
        z, x = x, z
        off += 64
    return hash128_to_64((hash128_to_64(v1, w1) + shift_mix(y) * K1 + z) & MASK64,
                         (hash128_to_64(v2, w2) + x) & MASK64)

def fingerprint2011(val: str) -> int:
    s = val.encode("utf-8")
    if len(s) <= 32:
        res = murmur_hash64_with_seed(s, K0 ^ K1 ^ K2)
    elif len(s) <= 64:
        res = hash33(s)
    else:
        res = hash65(s)
    u = u64(s, 0) if len(s) >= 8 else K0
    v = u64(s, len(s) - 8) if len(s) >= 9 else K0
    res = hash128_to_64((res + v) & MASK64, u)
    if res < 2:
        res = (res - 2) & MASK64
    return res

print(fingerprint2011(sys.argv[1]))
EOF
}

if [[ "$ACTION" == "fp64" ]]; then
  if [[ -z "$COLLECTION_ID" ]]; then
    echo "Usage: $0 --action fp64 --collection-id <COLLECTION_ID>" >&2
    exit 1
  fi
  compute_fp64 "$COLLECTION_ID"
  exit 0
fi

if [[ -z "$PROJECT_ID" ]]; then
  echo "Error: --project <PROJECT_ID> is required." >&2
  exit 1
fi

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
TOKEN=$(gcloud auth application-default print-access-token 2>/dev/null || gcloud auth print-access-token)

if [[ "$USE_PREPROD" == "true" ]]; then
  DE_HOST="https://preprod-discoveryengine.googleapis.com"
else
  DE_HOST="https://discoveryengine.googleapis.com"
fi

case "$ACTION" in
  inspect)
    echo "=== [1] Agent Registry MCP Servers ($PROJECT_ID / $PROJECT_NUMBER) ==="
    curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
      "https://agentregistry.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/mcpServers" | python3 -m json.tool || true

    echo "=== [2] Agent Registry AuthBindings ==="
    curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
      "https://agentregistry.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/bindings" | python3 -m json.tool || true

    echo "=== [3] Agent Identity AuthProviders ==="
    curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
      "https://agentidentity.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/authProviders" | python3 -m json.tool || true

    if [[ -n "$ENGINE_ID" ]]; then
      echo "=== [4] Engine ($ENGINE_ID) Linked dataStoreIds ==="
      curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
        "${DE_HOST}/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/collections/default_collection/engines/$ENGINE_ID" | python3 -m json.tool || true
    fi

    if [[ -n "$COLLECTION_ID" ]]; then
      FP64=$(compute_fp64 "$COLLECTION_ID")
      echo "=== [5] Collection ($COLLECTION_ID, FP64=$FP64) DataConnector ==="
      curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
        "${DE_HOST}/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/collections/$COLLECTION_ID/dataConnector" | python3 -m json.tool || true
    fi
    ;;

  delete)
    if [[ -z "$COLLECTION_ID" ]]; then
      echo "Error: --collection-id <OLD_COLLECTION_ID> is required for --action delete" >&2
      exit 1
    fi
    OLD_FP64=$(compute_fp64 "$COLLECTION_ID")
    echo "=== Deleting Connector Collection '$COLLECTION_ID' (FP64=$OLD_FP64) ==="

    if [[ -n "$ENGINE_ID" ]]; then
      echo "[1/4] Unlinking ${COLLECTION_ID}_* dataStores from Engine $ENGINE_ID..."
      UPDATED_DS=$(curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
        "${DE_HOST}/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/collections/default_collection/engines/$ENGINE_ID" | \
        python3 -c "import sys, json; ds=[d for d in json.load(sys.stdin).get('dataStoreIds', []) if not d.startswith('${COLLECTION_ID}_')]; print(json.dumps({'dataStoreIds': ds}))")
      curl -s -X PATCH \
        -H "Authorization: Bearer $TOKEN" \
        -H "X-Goog-User-Project: $PROJECT_NUMBER" \
        -H "Content-Type: application/json" \
        "${DE_HOST}/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/collections/default_collection/engines/$ENGINE_ID?updateMask=dataStoreIds" \
        -d "$UPDATED_DS" >/dev/null
    fi

    echo "[2/4] Deleting Discovery Engine Collection $COLLECTION_ID..."
    curl -s -X DELETE \
      -H "Authorization: Bearer $TOKEN" \
      -H "X-Goog-User-Project: $PROJECT_NUMBER" \
      "${DE_HOST}/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/collections/$COLLECTION_ID" | python3 -m json.tool || true

    echo "[3/4] Deleting Agent Registry AuthBinding ge-bind-$OLD_FP64..."
    curl -s -X DELETE \
      -H "Authorization: Bearer $TOKEN" \
      -H "X-Goog-User-Project: $PROJECT_NUMBER" \
      "https://agentregistry.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/bindings/ge-bind-$OLD_FP64" | python3 -m json.tool || true

    echo "[4/4] Deleting Agent Identity AuthProvider ge-auth-$OLD_FP64..."
    curl -s -X DELETE \
      -H "Authorization: Bearer $TOKEN" \
      -H "X-Goog-User-Project: $PROJECT_NUMBER" \
      "https://agentidentity.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/authProviders/ge-auth-$OLD_FP64" | python3 -m json.tool || true
    echo "Done deleting $COLLECTION_ID."
    ;;

  register-bigquery-mcp)
    if [[ -z "$COLLECTION_ID" ]]; then
      echo "Error: --collection-id is required for --action register-bigquery-mcp" >&2
      exit 1
    fi
    ENCODED_DISPLAY_NAME=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$DISPLAY_NAME")
    echo "=== [1/2] Creating 1P BigQuery MCP Connector ($COLLECTION_ID) ==="
    curl -s -X POST \
      -H "Authorization: Bearer $TOKEN" \
      -H "X-Goog-User-Project: $PROJECT_NUMBER" \
      -H "Content-Type: application/json" \
      "${DE_HOST}/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION:setUpDataConnectorV2?collectionId=$COLLECTION_ID&collectionDisplayName=${ENCODED_DISPLAY_NAME}" \
      -d "{
        \"dataSource\": \"bigquery_mcp\",
        \"dataSourceVersion\": 2,
        \"refreshInterval\": \"86400s\",
        \"entities\": [{\"entityName\": \"table\"}],
        \"params\": {
          \"billing_project_id\": \"$PROJECT_ID\"
        },
        \"connectorModes\": [\"FEDERATED\", \"ACTIONS\"],
        \"actionConfig\": {
          \"isActionConfigured\": true,
          \"useStaticSecrets\": true,
          \"createBapConnection\": true
        }
      }" | python3 -m json.tool

    if [[ -n "$ENGINE_ID" ]]; then
      echo "=== [2/2] Linking ${COLLECTION_ID}_table to Engine $ENGINE_ID ==="
      EXISTING_DS=$(curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
        "${DE_HOST}/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/collections/default_collection/engines/$ENGINE_ID" | \
        python3 -c "import sys, json; ds=json.load(sys.stdin).get('dataStoreIds', []); ds.append('${COLLECTION_ID}_table') if '${COLLECTION_ID}_table' not in ds else None; print(json.dumps({'dataStoreIds': ds}))")
      curl -s -X PATCH \
        -H "Authorization: Bearer $TOKEN" \
        -H "X-Goog-User-Project: $PROJECT_NUMBER" \
        -H "Content-Type: application/json" \
        "${DE_HOST}/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/collections/default_collection/engines/$ENGINE_ID?updateMask=dataStoreIds" \
        -d "$EXISTING_DS" >/dev/null
      echo "Linked ${COLLECTION_ID}_table to engine $ENGINE_ID."
    fi
    ;;

  register-custom-mcp)
    if [[ -z "$COLLECTION_ID" || -z "$MCP_URI" || -z "$CLIENT_ID" || -z "$CLIENT_SECRET" ]]; then
      echo "Usage: $0 --action register-custom-mcp --project <PROJECT_ID> --collection-id <ID> --mcp-uri <URI> --client-id <ID> --client-secret <SECRET> [--auth-url <URL>] [--token-url <URL>] [--engine-id <ENGINE_ID>]" >&2
      exit 1
    fi
    # Normalize MCP_URI (ensure it ends with /mcp if user passed service root URL)
    BASE_SERVICE_URL="${MCP_URI%/mcp}"
    if [[ "$MCP_URI" != */mcp && "$MCP_URI" != */sse ]]; then
      MCP_URI="${BASE_SERVICE_URL}/mcp"
    fi
    [[ -z "$AUTH_URL" ]] && AUTH_URL="${BASE_SERVICE_URL}/authorize"
    [[ -z "$TOKEN_URL" ]] && TOKEN_URL="${BASE_SERVICE_URL}/token"

    FP64=$(compute_fp64 "$COLLECTION_ID")
    ENCODED_DISPLAY_NAME=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$DISPLAY_NAME")

    # Try to mint an initial refresh_token & access_token if the server supports stateless /authorize & /token
    REFRESH_TOKEN=""
    ACCESS_TOKEN=""
    REDIRECT_LOC=$(curl -s -I "${AUTH_URL}?client_id=${CLIENT_ID}&redirect_uri=https://vertexaisearch.cloud.google.com/oauth-redirect&response_type=code&scope=openid%20email%20profile" | grep -i "^location:" | awk '{print $2}' | tr -d '\r' || true)
    if [[ "$REDIRECT_LOC" == *"code="* ]]; then
      AUTH_CODE=$(python3 -c "import urllib.parse, sys; print(urllib.parse.parse_qs(urllib.parse.urlparse(sys.argv[1]).query)['code'][0])" "$REDIRECT_LOC")
      TOKEN_JSON=$(curl -s -X POST "$TOKEN_URL" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "grant_type=authorization_code&code=${AUTH_CODE}&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}&redirect_uri=https://vertexaisearch.cloud.google.com/oauth-redirect")
      REFRESH_TOKEN=$(echo "$TOKEN_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin).get('refresh_token', ''))" 2>/dev/null || true)
      ACCESS_TOKEN=$(echo "$TOKEN_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null || true)
    fi

    echo "=== [1/4] Creating BYO Custom MCP Connector ($COLLECTION_ID, FP64=$FP64) via $DE_HOST ==="
    curl -s -X POST \
      -H "Authorization: Bearer $TOKEN" \
      -H "X-Goog-User-Project: $PROJECT_NUMBER" \
      -H "Content-Type: application/json" \
      "${DE_HOST}/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION:setUpDataConnectorV2?collectionId=$COLLECTION_ID&collectionDisplayName=${ENCODED_DISPLAY_NAME}" \
      -d "{
        \"dataSource\": \"custom_mcp\",
        \"dataSourceVersion\": 1,
        \"connectorSourceId\": \"custom_mcp\",
        \"connectorType\": \"THIRD_PARTY_FEDERATED\",
        \"connectorModes\": [\"FEDERATED\", \"ACTIONS\"],
        \"autoRunDisabled\": true,
        \"syncMode\": \"PERIODIC\",
        \"refreshInterval\": \"86400s\",
        \"entities\": [{\"entityName\": \"mcp_data\"}],
        \"params\": {
          \"oauth_access_token\": \"\",
          \"auth_type\": \"AUTHORIZATION_TYPE_UNDEFINED\"
        },
        \"destinationConfigs\": [{
          \"key\": \"instance_uri\",
          \"destinations\": [{\"host\": \"$MCP_URI\"}]
        }],
        \"actionConfig\": {
          \"actionParams\": {
            \"instance_uri\": \"$MCP_URI\",
            \"auth_uri\": \"$AUTH_URL\",
            \"auth_uri_params\": \"&access_type=offline&prompt=consent\",
            \"token_uri\": \"$TOKEN_URL\",
            \"client_id\": \"$CLIENT_ID\",
            \"client_secret\": \"$CLIENT_SECRET\",
            \"scopes\": \"$SCOPES\",
            \"refresh_token\": \"$REFRESH_TOKEN\",
            \"pkce_support_enabled\": false,
            \"client_secret_basic_override\": false,
            \"auth_type\": \"OAUTH\",
            \"auth_key\": \"OAuth\",
            \"mcp_server_description\": \"$DESCRIPTION\",
            \"mcp_server_source\": \"BYO_MCP\"
          },
          \"createBapConnection\": true,
          \"isActionConfigured\": true
        },
        \"bapConfig\": {
          \"supportedConnectorModes\": [\"ACTIONS\"]
        }
      }" | python3 -m json.tool

    if [[ -n "$ACCESS_TOKEN" ]]; then
      echo "=== [2/4] Discovering dynamic tools from $MCP_URI and updating dataConnector ==="
      TOOLS_SSE=$(curl -s -X POST "$MCP_URI" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' || true)
      if [[ -n "$TOOLS_SSE" ]]; then
        PATCH_BODY=$(python3 -c "
import sys, json
raw = sys.stdin.read()
for line in raw.splitlines():
    if line.startswith('data: '):
        raw = line[6:]
        break
tools = json.loads(raw)['result']['tools']
print(json.dumps({
    'name': 'projects/${PROJECT_NUMBER}/locations/${LOCATION}/collections/${COLLECTION_ID}/dataConnector',
    'dataSource': 'custom_mcp',
    'bapConfig': {
        'supportedConnectorModes': ['ACTIONS'],
        'enabledActions': [t['name'] for t in tools]
    },
    'dynamicTools': [
        {
            'name': t['name'],
            'displayName': t['name'],
            'description': t.get('description', ''),
            'enabled': True
        }
        for t in tools
    ]
}))
" <<< "$TOOLS_SSE" 2>/dev/null || true)
        if [[ -n "$PATCH_BODY" ]]; then
          curl -s -X PATCH "${DE_HOST}/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/collections/$COLLECTION_ID/dataConnector?updateMask=dynamic_tools,bap_config" \
            -H "Authorization: Bearer $TOKEN" \
            -H "X-Goog-User-Project: $PROJECT_NUMBER" \
            -H "Content-Type: application/json" \
            -d "$PATCH_BODY" >/dev/null
          echo "Populated dynamicTools and bapConfig.enabledActions on $COLLECTION_ID."
        fi
      fi
    fi

    echo "=== [3/4] Configuring Agent Identity AuthProvider (ge-auth-$FP64) & Agent Registry AuthBinding (ge-bind-$FP64) ==="
    MCP_SERVER_ID=$(curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
      "https://agentregistry.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/mcpServers" | \
      python3 -c "
import sys, json
data = json.load(sys.stdin)
for s in data.get('mcpServers', []):
    if s.get('displayName') == '${COLLECTION_ID}' or '${MCP_URI}' in json.dumps(s):
        print(s['name'].split('/')[-1])
        break
" 2>/dev/null || true)

    curl -s -X POST \
      -H "Authorization: Bearer $TOKEN" \
      -H "X-Goog-User-Project: $PROJECT_NUMBER" \
      -H "Content-Type: application/json" \
      "https://agentidentity.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/authProviders?authProviderId=ge-auth-$FP64" \
      -d "{
        \"displayName\": \"ge-auth-$FP64\",
        \"oauth2CredentialsFlow\": {
          \"flowType\": \"AUTHORIZATION_CODE_FLOW\",
          \"clientId\": \"$CLIENT_ID\",
          \"clientSecret\": \"$CLIENT_SECRET\",
          \"authorizationUri\": \"$AUTH_URL\",
          \"tokenEndpointUri\": \"$TOKEN_URL\",
          \"scopes\": [\"$SCOPES\"]
        }
      }" >/dev/null || true

    if [[ -n "$MCP_SERVER_ID" ]]; then
      curl -s -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "X-Goog-User-Project: $PROJECT_NUMBER" \
        -H "Content-Type: application/json" \
        "https://agentregistry.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/bindings?bindingId=ge-bind-$FP64" \
        -d "{
          \"displayName\": \"ge-bind-$FP64\",
          \"source\": {
            \"identifier\": \"projects/$PROJECT_NUMBER/locations/$LOCATION/workloads/*\"
          },
          \"target\": {
            \"identifier\": \"projects/$PROJECT_NUMBER/locations/$LOCATION/mcpServers/$MCP_SERVER_ID\"
          },
          \"authProviderBinding\": {
            \"authProvider\": \"projects/$PROJECT_ID/locations/$LOCATION/authProviders/ge-auth-$FP64\"
          }
        }" >/dev/null || true
      echo "Bound ge-auth-$FP64 -> ge-bind-$FP64 -> mcpServers/$MCP_SERVER_ID."
    else
      echo "Note: Agent Registry mcpServer not yet visible; run --action republish if needed."
    fi

    if [[ -n "$ENGINE_ID" ]]; then
      echo "=== [4/4] Linking ${COLLECTION_ID}_mcp_data to Engine $ENGINE_ID ==="
      EXISTING_DS=$(curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
        "${DE_HOST}/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/collections/default_collection/engines/$ENGINE_ID" | \
        python3 -c "import sys, json; ds=json.load(sys.stdin).get('dataStoreIds', []); ds.append('${COLLECTION_ID}_mcp_data') if '${COLLECTION_ID}_mcp_data' not in ds else None; print(json.dumps({'dataStoreIds': ds}))")
      curl -s -X PATCH \
        -H "Authorization: Bearer $TOKEN" \
        -H "X-Goog-User-Project: $PROJECT_NUMBER" \
        -H "Content-Type: application/json" \
        "${DE_HOST}/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/collections/default_collection/engines/$ENGINE_ID?updateMask=dataStoreIds" \
        -d "$EXISTING_DS" >/dev/null
      echo "Linked ${COLLECTION_ID}_mcp_data to engine $ENGINE_ID."
    fi
    ;;

  republish)
    if [[ -z "$COLLECTION_ID" ]]; then
      echo "Error: --collection-id is required for --action republish" >&2
      exit 1
    fi
    FP64=$(compute_fp64 "$COLLECTION_ID")
    echo "=== [1/2] Republishing $COLLECTION_ID (FP64=$FP64) to Agent Registry via preprod-discoveryengine ==="
    curl -s -X PATCH \
      -H "Authorization: Bearer $TOKEN" \
      -H "X-Goog-User-Project: $PROJECT_NUMBER" \
      -H "Content-Type: application/json" \
      "https://preprod-discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/collections/$COLLECTION_ID/dataConnector?updateMask=refreshInterval" \
      -d '{"refreshInterval": "86400s"}' | python3 -m json.tool

    if [[ -n "$CLIENT_ID" && -n "$CLIENT_SECRET" && -n "$AUTH_URL" && -n "$TOKEN_URL" ]]; then
      echo "=== [2/2] Ensuring Agent Identity AuthProvider (ge-auth-$FP64) & Agent Registry AuthBinding (ge-bind-$FP64) ==="
      MCP_SERVER_ID=$(curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
        "https://agentregistry.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/mcpServers" | \
        python3 -c "
import sys, json
data = json.load(sys.stdin)
for s in data.get('mcpServers', []):
    if s.get('displayName') == '${COLLECTION_ID}':
        print(s['name'].split('/')[-1])
        break
" 2>/dev/null || true)

      curl -s -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "X-Goog-User-Project: $PROJECT_NUMBER" \
        -H "Content-Type: application/json" \
        "https://agentidentity.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/authProviders?authProviderId=ge-auth-$FP64" \
        -d "{
          \"displayName\": \"ge-auth-$FP64\",
          \"oauth2CredentialsFlow\": {
            \"flowType\": \"AUTHORIZATION_CODE_FLOW\",
            \"clientId\": \"$CLIENT_ID\",
            \"clientSecret\": \"$CLIENT_SECRET\",
            \"authorizationUri\": \"$AUTH_URL\",
            \"tokenEndpointUri\": \"$TOKEN_URL\",
            \"scopes\": [\"$SCOPES\"]
          }
        }" >/dev/null || true

      if [[ -n "$MCP_SERVER_ID" ]]; then
        curl -s -X POST \
          -H "Authorization: Bearer $TOKEN" \
          -H "X-Goog-User-Project: $PROJECT_NUMBER" \
          -H "Content-Type: application/json" \
          "https://agentregistry.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/$LOCATION/bindings?bindingId=ge-bind-$FP64" \
          -d "{
            \"displayName\": \"ge-bind-$FP64\",
            \"source\": {
              \"identifier\": \"projects/$PROJECT_NUMBER/locations/$LOCATION/workloads/*\"
            },
            \"target\": {
              \"identifier\": \"projects/$PROJECT_NUMBER/locations/$LOCATION/mcpServers/$MCP_SERVER_ID\"
            },
            \"authProviderBinding\": {
              \"authProvider\": \"projects/$PROJECT_ID/locations/$LOCATION/authProviders/ge-auth-$FP64\"
            }
          }" >/dev/null || true
        echo "Bound ge-auth-$FP64 -> ge-bind-$FP64 -> mcpServers/$MCP_SERVER_ID."
      fi
    fi
    ;;

  *)
    echo "Unknown --action: $ACTION (expected: inspect | fp64 | register-custom-mcp | register-bigquery-mcp | republish | delete)" >&2
    exit 1
    ;;
esac
