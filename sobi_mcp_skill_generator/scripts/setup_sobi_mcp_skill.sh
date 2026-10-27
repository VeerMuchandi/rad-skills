#!/usr/bin/env bash
# Sobi MCP Skill Generator & Sandbox Onboarding Script
# 1. Grants Sobi Agent Workload Identity IAM roles (roles/agentidentity.viewer, etc.) for Hodor PDP Shim outbound OAuth token injection
# 2. Generates project-specific <collection_id>_skill/SKILL.md & .zip from live MCP tools/list (or --custom-skill-md)
# 3. Creates/updates the Skill Agent in Gemini Enterprise with sharingConfig.scope="ALL_USERS"
# 4. Mounts the skill (skillAgents) and reconciles the MCP server (mcpServers) on Sobi agents (sobi-*)
set -euo pipefail

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY

GE_PROJECT_ID=""
GE_LOCATION="global"
ENGINE_ID=""
COLLECTION_ID=""
MCP_URL=""
DISPLAY_NAME="Custom MCP Server"
DESCRIPTION="Custom MCP Server registered in Gemini Enterprise."
CLIENT_ID=""
CLIENT_SECRET=""
ACCESS_TOKEN=""
CUSTOM_SKILL_MD=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ge-project) GE_PROJECT_ID="$2"; shift 2 ;;
    --ge-location) GE_LOCATION="$2"; shift 2 ;;
    --engine-id) ENGINE_ID="$2"; shift 2 ;;
    --collection-id) COLLECTION_ID="$2"; shift 2 ;;
    --mcp-url) MCP_URL="$2"; shift 2 ;;
    --display-name) DISPLAY_NAME="$2"; shift 2 ;;
    --description) DESCRIPTION="$2"; shift 2 ;;
    --client-id) CLIENT_ID="$2"; shift 2 ;;
    --client-secret) CLIENT_SECRET="$2"; shift 2 ;;
    --access-token) ACCESS_TOKEN="$2"; shift 2 ;;
    --custom-skill-md) CUSTOM_SKILL_MD="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$GE_PROJECT_ID" || -z "$ENGINE_ID" || -z "$COLLECTION_ID" || -z "$MCP_URL" ]]; then
  echo "Usage: $0 --ge-project <GE_PROJECT_ID> --engine-id <ENGINE_ID> --collection-id <COLLECTION_ID> --mcp-url <MCP_ENDPOINT_URL> [options]"
  exit 1
fi

GE_PROJECT_NUM=$(gcloud projects describe "$GE_PROJECT_ID" --format="value(projectNumber)")
ADC_TOKEN=$(gcloud auth application-default print-access-token 2>/dev/null || gcloud auth print-access-token)

echo "=== [1/4] Granting Sobi Agent Workload Identity IAM Roles on ${GE_PROJECT_ID} (${GE_PROJECT_NUM}) ==="
gcloud services enable agentregistry.googleapis.com apphub.googleapis.com apphubendpoint.googleapis.com --project "$GE_PROJECT_ID" >/dev/null 2>&1 || true
GE_ORG_ID=$(gcloud projects get-ancestors "$GE_PROJECT_ID" --format="json" | python3 -c "import sys, json; ancestors=json.load(sys.stdin); orgs=[a['id'] for a in ancestors if a.get('type')=='organization']; print(orgs[0] if orgs else '')")
if [[ -n "$GE_ORG_ID" ]]; then
  for PRINCIPAL in \
    "principalSet://agents.global.org-${GE_ORG_ID}.system.id.goog/attribute.platform/aiplatform" \
    "principalSet://agents.global.org-${GE_ORG_ID}.system.id.goog/attribute.platformContainer/aiplatform/projects/${GE_PROJECT_NUM}"; do
    for ROLE in \
      "roles/agentidentity.viewer" \
      "roles/agentidentity.user" \
      "roles/agentregistry.viewer"; do
      gcloud projects add-iam-policy-binding "$GE_PROJECT_ID" \
        --member="$PRINCIPAL" \
        --role="$ROLE" \
        --condition=None >/dev/null
    done
  done
  echo "Granted roles/agentidentity.viewer, roles/agentidentity.user, and roles/agentregistry.viewer for org ${GE_ORG_ID}."
else
  echo "WARNING: Could not determine Organization ID for ${GE_PROJECT_ID}."
fi

echo "=== [2/4] Generating Sobi Sandbox Skill (SKILL.md & .zip) ==="
SKILL_DIR="./${COLLECTION_ID//-/_}_skill"
mkdir -p "$SKILL_DIR"

if [[ -n "$CUSTOM_SKILL_MD" ]]; then
  if [[ "$(realpath "$CUSTOM_SKILL_MD")" != "$(realpath "${SKILL_DIR}/SKILL.md" 2>/dev/null || true)" ]]; then
    cp "$CUSTOM_SKILL_MD" "${SKILL_DIR}/SKILL.md"
  fi
  SKILL_BODY=$(python3 -c "
import sys
content = open(sys.argv[1]).read()
if content.startswith('---'):
    parts = content.split('---', 2)
    if len(parts) == 3:
        content = parts[2].lstrip()
print(content)
" "${SKILL_DIR}/SKILL.md")
else
  BASE_URL="${MCP_URL%/mcp}"
  if [[ -z "$ACCESS_TOKEN" && -n "$CLIENT_ID" && -n "$CLIENT_SECRET" ]]; then
    REDIRECT_LOC=$(curl -s -I "${BASE_URL}/authorize?client_id=${CLIENT_ID}&redirect_uri=https://vertexaisearch.cloud.google.com/oauth-redirect&response_type=code&scope=openid%20email%20profile" | grep -i "^location:" | awk '{print $2}' | tr -d '\r')
    AUTH_CODE=$(python3 -c "import urllib.parse, sys; print(urllib.parse.parse_qs(urllib.parse.urlparse(sys.argv[1]).query)['code'][0])" "$REDIRECT_LOC")
    TOKEN_JSON=$(curl -s -X POST "${BASE_URL}/token" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "grant_type=authorization_code&code=${AUTH_CODE}&client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}&redirect_uri=https://vertexaisearch.cloud.google.com/oauth-redirect")
    ACCESS_TOKEN=$(echo "$TOKEN_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
  fi

  TOOLS_SSE=$(curl -s -X POST "$MCP_URL" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}')

  SKILL_BODY=$(python3 -c "
import sys, json
raw = sys.stdin.read()
for line in raw.splitlines():
    if line.startswith('data: '):
        raw = line[6:]
        break
tools = json.loads(raw)['result']['tools']
connector_path = 'projects/${GE_PROJECT_NUM}/locations/${GE_LOCATION}/collections/${COLLECTION_ID}/dataConnector'
endpoint_url = '${MCP_URL}'
lines = [
    '# ${DISPLAY_NAME} Skill',
    '',
    'Use this skill whenever the user asks to interact with **${DISPLAY_NAME}** (${DESCRIPTION}).',
    '',
    '## Connection & Tool Invocation (\`remote_cli mcp\`)',
    '',
    'Inside the Sobi VMaaS container (\`/workspace\`), invoke this MCP server using \`remote_cli mcp\` with **positional** \`<connector> <tool>\` arguments (do NOT use \`-s\` or \`-t\` flags):',
    f'1. **Connector Resource Name:** \`{connector_path}\`',
    '2. **Tool Name & JSON Payload:** \`<tool_name> --json \'<json_arguments>\'\`',
    f'3. **Explicit \`--endpoint\` Flag:** \`--endpoint \'{endpoint_url}\'\`',
    '',
    'Do NOT waste turns running \`list-tools\` or \`describe\` — call the tools directly using the exact parameter schemas below.',
    '',
    '---',
    '',
    '## Available Tools & Exact Parameter Schemas',
    ''
]
for idx, t in enumerate(tools, 1):
    tname = t['name']
    tdesc = t.get('description', '').strip().splitlines()[0] if t.get('description') else ''
    schema = t.get('inputSchema', {})
    props = schema.get('properties', {})
    req = set(schema.get('required', []))
    lines.append(f'### {idx}. \`{tname}\`')
    if tdesc:
        lines.append(f'{tdesc}')
    example_args = {}
    if props:
        lines.append('- **Parameters:**')
        for pname, pinfo in props.items():
            ptype = pinfo.get('type', 'any')
            pdesc = pinfo.get('description', '')
            req_label = 'required' if pname in req else 'optional'
            lines.append(f'  - \`{pname}\` *({ptype}, {req_label})*: {pdesc}')
            if pname in req or len(example_args) == 0:
                example_args[pname] = f'<{pname}>' if ptype == 'string' else (10 if ptype == 'integer' else True)
    lines.append('```bash')
    lines.append('remote_cli mcp \\\\')
    lines.append(f'  {connector_path} \\\\')
    lines.append(f'  {tname} \\\\')
    lines.append(f'  --json \'{json.dumps(example_args)}\' \\\\')
    lines.append(f'  --endpoint \'{endpoint_url}\'')
    lines.append('```')
    lines.append('')
print('\n'.join(lines))
" <<< "$TOOLS_SSE")

  cat <<EOF > "${SKILL_DIR}/SKILL.md"
---
name: ${COLLECTION_ID}
description: ${DESCRIPTION}
---

${SKILL_BODY}
EOF
fi

(cd "$SKILL_DIR" && zip -q -r "../${COLLECTION_ID//-/_}_skill.zip" SKILL.md)
echo "Generated ${SKILL_DIR}/SKILL.md and ${COLLECTION_ID//-/_}_skill.zip"

echo "=== [3/4] Registering & Sharing Skill Agent (ALL_USERS) in ${GE_PROJECT_ID} / ${ENGINE_ID} ==="
AGENTS_BASE="https://discoveryengine.googleapis.com/v1alpha/projects/${GE_PROJECT_NUM}/locations/${GE_LOCATION}/collections/default_collection/engines/${ENGINE_ID}/assistants/default_assistant/agents"
EXISTING_AGENTS_JSON=$(curl -s -H "Authorization: Bearer $ADC_TOKEN" -H "X-Goog-User-Project: ${GE_PROJECT_NUM}" "${AGENTS_BASE}?pageSize=100")

EXISTING_SKILL_AGENT_NAME=$(python3 -c "
import sys, json
data = json.load(sys.stdin)
for a in data.get('agents', []):
    if 'skillAgentDefinition' in a and a.get('displayName') in ('${COLLECTION_ID}', '${COLLECTION_ID//_/-}'):
        print(a['name'])
        break
" <<< "$EXISTING_AGENTS_JSON")

SKILL_PAYLOAD=$(python3 -c "
import sys, json
body = sys.stdin.read()
print(json.dumps({
    'displayName': '${COLLECTION_ID}',
    'description': '${DESCRIPTION}',
    'sharingConfig': {'scope': 'ALL_USERS'},
    'skillAgentDefinition': {'instruction': body}
}))
" <<< "$SKILL_BODY")

if [[ -n "$EXISTING_SKILL_AGENT_NAME" ]]; then
  SKILL_RESP=$(curl -s -X PATCH "https://discoveryengine.googleapis.com/v1alpha/${EXISTING_SKILL_AGENT_NAME}?updateMask=displayName,description,sharingConfig,skillAgentDefinition.instruction" \
    -H "Authorization: Bearer $ADC_TOKEN" \
    -H "X-Goog-User-Project: ${GE_PROJECT_NUM}" \
    -H "Content-Type: application/json" \
    -d "$SKILL_PAYLOAD")
else
  SKILL_RESP=$(curl -s -X POST "$AGENTS_BASE" \
    -H "Authorization: Bearer $ADC_TOKEN" \
    -H "X-Goog-User-Project: ${GE_PROJECT_NUM}" \
    -H "Content-Type: application/json" \
    -d "$SKILL_PAYLOAD")
fi

SKILL_REGISTRY_PATH=$(python3 -c "
import sys, json
d = json.load(sys.stdin)
reg = d.get('skillAgentDefinition', {}).get('agentRegistrySkill', '')
if not reg and 'name' in d:
    aid = d['name'].split('/')[-1]
    reg = f'projects/${GE_PROJECT_NUM}/locations/${GE_LOCATION}/skills/private-skill-{aid}'
print(reg)
" <<< "$SKILL_RESP")
echo "Skill Agent active (ALL_USERS): ${SKILL_REGISTRY_PATH}"

echo "=== [4/4] Mounting Skill & Reconciling MCP Server on Sobi Agent(s) ==="
MCP_SERVERS_JSON=$(curl -s -H "Authorization: Bearer $ADC_TOKEN" -H "X-Goog-User-Project: ${GE_PROJECT_NUM}" \
  "https://agentregistry.googleapis.com/v1alpha/projects/${GE_PROJECT_NUM}/locations/${GE_LOCATION}/mcpServers?pageSize=100")

MCP_SERVER_URN=$(python3 -c "
import sys, json
d = json.load(sys.stdin)
for s in d.get('mcpServers', []):
    for iface in s.get('interfaces', []):
        if iface.get('url') == '${MCP_URL}':
            print(s['name'])
            sys.exit(0)
" <<< "$MCP_SERVERS_JSON")

AR_AGENTS_JSON=$(curl -s -H "Authorization: Bearer $ADC_TOKEN" -H "X-Goog-User-Project: ${GE_PROJECT_NUM}" \
  "https://agentregistry.googleapis.com/v1alpha/projects/${GE_PROJECT_NUM}/locations/${GE_LOCATION}/agents?pageSize=100")

SOBI_AGENT_NAMES=$(python3 -c "
import sys, json
de_data = json.loads(sys.argv[1])
ar_data = json.loads(sys.argv[2])
base = 'projects/${GE_PROJECT_NUM}/locations/${GE_LOCATION}/collections/default_collection/engines/${ENGINE_ID}/assistants/default_assistant/agents'
names = set()
for a in de_data.get('agents', []):
    if 'longRunningAgentDefinition' in a:
        names.add(a['name'])
for a in ar_data.get('agents', []):
    aid = a.get('agentId', '')
    if ':sobi-' in aid:
        sobi_id = aid.split(':')[-1]
        names.add(f'{base}/{sobi_id}')
for n in sorted(names):
    print(n)
" "$EXISTING_AGENTS_JSON" "$AR_AGENTS_JSON")

for SOBI_NAME in $SOBI_AGENT_NAMES; do
  SOBI_OBJ=$(curl -s -H "Authorization: Bearer $ADC_TOKEN" -H "X-Goog-User-Project: ${GE_PROJECT_NUM}" \
    "https://discoveryengine.googleapis.com/v1alpha/${SOBI_NAME}")
  SOBI_PATCH=$(python3 -c "
import sys, json
a = json.load(sys.stdin)
if 'longRunningAgentDefinition' not in a:
    sys.exit(0)
lra = a.get('longRunningAgentDefinition', {})
skills = list(lra.get('skillAgents', []))
if '${SKILL_REGISTRY_PATH}' and '${SKILL_REGISTRY_PATH}' not in skills:
    skills.append('${SKILL_REGISTRY_PATH}')
mcps = list(lra.get('mcpServers', []))
if '${MCP_SERVER_URN}' and '${MCP_SERVER_URN}' not in mcps:
    mcps.append('${MCP_SERVER_URN}')
print(json.dumps({
    'displayName': a.get('displayName', 'Gemini'),
    'description': a.get('description', 'Gemini'),
    'longRunningAgentDefinition': {
        'skillAgents': skills,
        'mcpServers': mcps
    }
}))
" <<< "$SOBI_OBJ")
  if [[ -n "$SOBI_PATCH" ]]; then
    curl -s -X PATCH "https://discoveryengine.googleapis.com/v1alpha/${SOBI_NAME}?updateMask=longRunningAgentDefinition.skill_agents,longRunningAgentDefinition.mcp_servers" \
      -H "Authorization: Bearer $ADC_TOKEN" \
      -H "X-Goog-User-Project: ${GE_PROJECT_NUM}" \
      -H "Content-Type: application/json" \
      -d "$SOBI_PATCH" >/dev/null
    echo "Mounted ${SKILL_REGISTRY_PATH} & reconciled ${MCP_SERVER_URN} onto ${SOBI_NAME}"
  fi
done
