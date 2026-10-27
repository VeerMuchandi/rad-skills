---
name: Gemini Enterprise MCP Registrar
description: Standalone guide and automation for inspecting, registering, republishing, verifying, and deleting BYO Custom MCP (`custom_mcp`) and 1P Managed MCP (`bigquery_mcp`) servers across Gemini Enterprise (Discovery Engine), Agent Registry, and Agent Identity.
---

# Gemini Enterprise MCP Registrar Skill

Use this skill whenever a developer or administrator wants to **register an existing MCP Server** (hosted on Cloud Run, 3P SaaS like Snowflake/GitHub, Apigee, or 1P Managed BigQuery MCP) in **Gemini Enterprise (Discovery Engine)**, publish it to **Agent Registry (`agentregistry.googleapis.com`)**, bind its OAuth 2.0 credentials in **Agent Identity (`agentidentity.googleapis.com`)**, link its DataStore to a Gemini Enterprise Engine, or cleanly tear down an old MCP connector.

*(Note: If you need to build and deploy a new MCP Server on Google Cloud Run first, use the [**Cloud Run MCP Server Creator**](../cloud_run_mcp_server_creator/SKILL.md) skill. If you need to generate a Sobi VMaaS sandbox companion skill (`SKILL.md` & `.zip`) and configure Sobi Agent Workload Identity IAM for `remote_cli mcp`, use the [**Sobi MCP Skill Generator**](../sobi_mcp_skill_generator/SKILL.md) skill.)*

---

## Core Architecture & Critical Pitfalls to Avoid

### 1. Atomic `setUpDataConnectorV2` Creation vs. `PATCH` (`Couldn't connect Custom MCP Server`)
* **Pitfall:** If a `custom_mcp` connector is initially created via `setUpDataConnectorV2` with `connectorModes: ["FEDERATED"]` or `isActionConfigured: false` and patched afterward via `UpdateDataConnector` (`PATCH`), Discovery Engine stores the OAuth secret only in the *tenant* project rather than the *producer* project. As a result, `GetWidgetConfig` and `BuildAuthorizationUrl` fail to build `authorizationUri` (`"connectorAuthState": {}`), and clicking **Connect** in the Gemini Enterprise end-user UI fails immediately with `"Couldn't connect Custom MCP Server"`.
* **Fix:**
  1. **Always** create the connector in a **single atomic `setUpDataConnectorV2` call** with `"connectorModes": ["FEDERATED", "ACTIONS"]`, `"isActionConfigured": true`, and `"createBapConnection": true`.
  2. When registering via `preprod-discoveryengine.googleapis.com`, Discovery Engine automatically publishes the `McpServer` resource into **Agent Registry (`agentregistry.googleapis.com`)**.
  3. If you also want dynamic MCP tools populated on the Discovery Engine `dataConnector` itself, call `PATCH .../dataConnector?updateMask=dynamic_tools,bap_config` *(never include `action_config` in `updateMask`, and only pass `name`, `displayName`, `description`, `enabled` inside `dynamicTools`—never `inputSchema`)*.

### 2. Collection Fingerprint (`FP64`) Naming Convention (`ge-auth-$FP64` & `ge-bind-$FP64`)
* Gemini Enterprise and Agent Registry map each collection (`<COLLECTION_ID>`) to its Agent Identity `AuthProvider` and Agent Registry `AuthBinding` using the **64-bit `fingerprint2011` hash (`FP64`)** of `<COLLECTION_ID>`:
  * **Agent Identity `AuthProvider` ID:** `ge-auth-<FP64>`
  * **Agent Registry `AuthBinding` ID:** `ge-bind-<FP64>`
* **Critical Resource Path Rule in `AuthBinding`:**
  * `source.identifier` and `target.identifier` MUST use **`$PROJECT_NUMBER`**:
    * `"source": {"identifier": "projects/$PROJECT_NUMBER/locations/global/workloads/*"}`
    * `"target": {"identifier": "projects/$PROJECT_NUMBER/locations/global/mcpServers/$MCP_SERVER_ID"}`
  * `authProviderBinding.authProvider` MUST use **`$PROJECT_ID`** (the alphanumeric project ID, e.g., `projects/my-project-id/locations/global/authProviders/ge-auth-$FP64`).

### 3. End-User UI Labeling, Deleted Collection Cooldown & Cross-Org Browser Sessions
* **End-User Connector Card Name:** In the Gemini Enterprise end-user **Connectors** page (`:fetchConnectorWidgets`), every `custom_mcp` connector displays the catalog title **"Custom MCP Server"** rather than the admin collection `displayName`. Inform the user that the **"Custom MCP Server"** card corresponds to their registered MCP server.
* **Deleted Collection ID Cooldown:** Deleting a collection (`DELETE .../collections/<id>`) triggers asynchronous DataStore deletion (`<id>_mcp_data` or `<id>_table`) that can take hours. When recreating a deleted connector immediately, choose a new `collectionId` (e.g., `<name>-v2`).
* **Cross-Org Cloud Console "Verify Auth":** When testing "Verify Auth" in the Cloud Console UI for an MCP server hosted in a different GCP organization, use an incognito/isolated browser window signed **only** into the target Gemini Enterprise admin account so `vertexaisearch.cloud.google.com/oauth-redirect` does not pick up a conflicting corporate session cookie.

---

## Complete Command Reference & Workflow

You can either run the automated script [`scripts/register_mcp_in_ge.sh`](./scripts/register_mcp_in_ge.sh) (which includes a built-in pure-Python `fingerprint2011` calculator and automates all steps below) or run the exact `curl` commands directly.

### 0. Environment Variables
```bash
export PROJECT_ID="<PROJECT_ID>"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
export ENGINE_ID="<ENGINE_ID>"
# Use application-default token if print-access-token returns 401 ACCESS_TOKEN_TYPE_UNSUPPORTED
export TOKEN="$(gcloud auth application-default print-access-token 2>/dev/null || gcloud auth print-access-token)"
```

---

### 1. Inspect Existing Connectors, MCP Servers, AuthProviders & Bindings

```bash
# 1.1 List Agent Registry MCP servers
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  "https://agentregistry.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/mcpServers" | python3 -m json.tool

# 1.2 List Agent Registry AuthBindings
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  "https://agentregistry.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/bindings" | python3 -m json.tool

# 1.3 List Agent Identity AuthProviders
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  "https://agentidentity.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/authProviders" | python3 -m json.tool

# 1.4 List Engine linked dataStoreIds
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  "https://preprod-discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/collections/default_collection/engines/$ENGINE_ID" | python3 -m json.tool

# 1.5 Inspect a specific collection's dataConnector
export COLLECTION_ID="<COLLECTION_ID>"
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  "https://preprod-discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/collections/$COLLECTION_ID/dataConnector" | python3 -m json.tool
```
*(Or via script: `bash .agents/skills/gemini_enterprise_mcp_registrar/scripts/register_mcp_in_ge.sh --action inspect --project "$PROJECT_ID" --engine-id "$ENGINE_ID"`)*

---

### 2. Compute Collection Fingerprint (`FP64`)

Compute the `fingerprint2011` (`FP64`) of `<COLLECTION_ID>` (used in `ge-auth-$FP64` and `ge-bind-$FP64`):

```bash
export COLLECTION_ID="<COLLECTION_ID>"
export FP64="$(bash .agents/skills/gemini_enterprise_mcp_registrar/scripts/register_mcp_in_ge.sh --action fp64 --collection-id "$COLLECTION_ID")"
echo "FP64=$FP64"
```

---

### 3. Delete Old Connector (Clean Full Teardown)

When removing an old or misconfigured connector, clean up all four resources (Engine `dataStoreIds`, Discovery Engine `collection`, Agent Registry `binding`, and Agent Identity `authProvider`):

```bash
export OLD_COLLECTION="<OLD_COLLECTION_ID>"
export OLD_FP64="$(bash .agents/skills/gemini_enterprise_mcp_registrar/scripts/register_mcp_in_ge.sh --action fp64 --collection-id "$OLD_COLLECTION")"

# 3.1 Unlink old data store IDs from Engine (keep only active dataStoreIds)
curl -s -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  -H "Content-Type: application/json" \
  "https://preprod-discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/collections/default_collection/engines/$ENGINE_ID?updateMask=dataStoreIds" \
  -d '{
    "dataStoreIds": [
      "<ACTIVE_DATASTORE_ID_1>",
      "<ACTIVE_DATASTORE_ID_2>"
    ]
  }'

# 3.2 Delete collection (deletes DataConnector, DataStores, and Agent Registry McpServer)
curl -s -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  "https://preprod-discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/collections/$OLD_COLLECTION"

# 3.3 Delete Agent Registry AuthBinding
curl -s -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  "https://agentregistry.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/bindings/ge-bind-$OLD_FP64"

# 3.4 Delete Agent Identity AuthProvider
curl -s -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  "https://agentidentity.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/authProviders/ge-auth-$OLD_FP64"
```
*(Or via script: `bash .agents/skills/gemini_enterprise_mcp_registrar/scripts/register_mcp_in_ge.sh --action delete --project "$PROJECT_ID" --engine-id "$ENGINE_ID" --collection-id "$OLD_COLLECTION"`)*

---

### 4. Create / Register New Connector (via `preprod-discoveryengine` or `discoveryengine`)

#### 4A. 1P BigQuery MCP (`bigquery_mcp` v2.0)
```bash
export NEW_COLLECTION="<NEW_COLLECTION_ID>"

curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  -H "Content-Type: application/json" \
  "https://preprod-discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global:setUpDataConnectorV2?collectionId=$NEW_COLLECTION&collectionDisplayName=BigQuery" \
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
  }"
```

#### 4B. BYO Custom MCP (`custom_mcp`)
Works for any Cloud Run MCP server or 3P MCP server (e.g., Snowflake, GitHub, ServiceNow):
```bash
export NEW_COLLECTION="<NEW_COLLECTION_ID>"
export MCP_URI="https://<service-url>/mcp"
export CLIENT_ID="<OAUTH_CLIENT_ID>"
export CLIENT_SECRET="<OAUTH_CLIENT_SECRET>"
export AUTH_URL="https://<service-url>/authorize"
export TOKEN_URL="https://<service-url>/token"
export SCOPES="openid email profile"

curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  -H "Content-Type: application/json" \
  "https://preprod-discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global:setUpDataConnectorV2?collectionId=$NEW_COLLECTION&collectionDisplayName=Custom%20MCP" \
  -d "{
    \"dataSource\": \"custom_mcp\",
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
    \"connectorModes\": [\"FEDERATED\", \"ACTIONS\"],
    \"actionConfig\": {
      \"actionParams\": {
        \"instance_uri\": \"$MCP_URI\",
        \"auth_uri\": \"$AUTH_URL\",
        \"auth_uri_params\": \"&access_type=offline&prompt=consent\",
        \"token_uri\": \"$TOKEN_URL\",
        \"client_id\": \"$CLIENT_ID\",
        \"client_secret\": \"$CLIENT_SECRET\",
        \"scopes\": \"$SCOPES\",
        \"auth_type\": \"OAUTH\",
        \"auth_key\": \"OAuth\",
        \"mcp_server_source\": \"BYO_MCP\"
      },
      \"isActionConfigured\": true,
      \"createBapConnection\": true
    },
    \"bapConfig\": {
      \"supportedConnectorModes\": [\"ACTIONS\"]
    }
  }"
```
*(Note: If the MCP server uses the Cloud Run MCP Server Creator's built-in `/authorize` & `/token` endpoints, `scripts/register_mcp_in_ge.sh` also automatically mints an initial `refresh_token` and populates `dynamicTools` + `bapConfig.enabledActions` via `PATCH ?updateMask=dynamic_tools,bap_config`.)*

#### 4C. Republish Existing Connector to Agent Registry
If a connector was previously created via `discoveryengine.googleapis.com` (prod) or is missing from `agentregistry.googleapis.com/v1alpha/.../mcpServers`, republish it by sending a lightweight `PATCH` through `preprod-discoveryengine.googleapis.com`:
```bash
export COLLECTION_ID="<COLLECTION_ID>"

curl -s -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  -H "Content-Type: application/json" \
  "https://preprod-discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/collections/$COLLECTION_ID/dataConnector?updateMask=refreshInterval" \
  -d '{
    "refreshInterval": "86400s"
  }'
```

---

### 5. Create Agent Identity `AuthProvider` (`ge-auth-$FP64`) & Agent Registry `AuthBinding` (`ge-bind-$FP64`)

After the `McpServer` appears in `agentregistry.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/mcpServers`, create the `AuthProvider` and `AuthBinding`:

```bash
export FP64="$(bash .agents/skills/gemini_enterprise_mcp_registrar/scripts/register_mcp_in_ge.sh --action fp64 --collection-id "$NEW_COLLECTION")"
export MCP_SERVER_ID="<AGENT_REGISTRY_MCP_SERVER_ID>" # e.g., from step 1.1 (mcpServers list)

# 5.1 Create AuthProvider in Agent Identity
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  -H "Content-Type: application/json" \
  "https://agentidentity.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/authProviders?authProviderId=ge-auth-$FP64" \
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
  }"

# 5.2 Create AuthBinding in Agent Registry
# IMPORTANT: source & target use $PROJECT_NUMBER; authProvider uses $PROJECT_ID!
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  -H "Content-Type: application/json" \
  "https://agentregistry.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/bindings?bindingId=ge-bind-$FP64" \
  -d "{
    \"displayName\": \"ge-bind-$FP64\",
    \"source\": {
      \"identifier\": \"projects/$PROJECT_NUMBER/locations/global/workloads/*\"
    },
    \"target\": {
      \"identifier\": \"projects/$PROJECT_NUMBER/locations/global/mcpServers/$MCP_SERVER_ID\"
    },
    \"authProviderBinding\": {
      \"authProvider\": \"projects/$PROJECT_ID/locations/global/authProviders/ge-auth-$FP64\"
    }
  }"
```

---

### 6. Link New DataStore to Engine & Verify

```bash
# 6.1 Link DataStore (<NEW_COLLECTION_ID>_mcp_data for custom_mcp, or <NEW_COLLECTION_ID>_table for bigquery_mcp) to Engine
curl -s -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  -H "Content-Type: application/json" \
  "https://preprod-discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/collections/default_collection/engines/$ENGINE_ID?updateMask=dataStoreIds" \
  -d '{
    "dataStoreIds": [
      "<ACTIVE_DATASTORE_ID_1>",
      "<NEW_COLLECTION_ID>_<ENTITY_NAME>"
    ]
  }'

# 6.2 Verify FetchConnectorWidgets
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: $PROJECT_NUMBER" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global:fetchConnectorWidgets" | python3 -m json.tool
```

---

## Automated One-Command Registration (`scripts/register_mcp_in_ge.sh`)

Use [`scripts/register_mcp_in_ge.sh`](./scripts/register_mcp_in_ge.sh) to run any of the workflows above in a single command:

### Register a BYO Custom MCP Server (Discovery Engine + Agent Registry + Agent Identity + Engine Link)
```bash
bash .agents/skills/gemini_enterprise_mcp_registrar/scripts/register_mcp_in_ge.sh \
  --action register-custom-mcp \
  --project "<GEMINI_ENTERPRISE_PROJECT_ID>" \
  --engine-id "<ENGINE_ID>" \
  --collection-id "<COLLECTION_ID>" \
  --display-name "<DISPLAY_NAME>" \
  --description "<DESCRIPTION>" \
  --mcp-uri "https://<service-url>/mcp" \
  --auth-url "https://<service-url>/authorize" \
  --token-url "https://<service-url>/token" \
  --client-id "<OAUTH_CLIENT_ID>" \
  --client-secret "<OAUTH_CLIENT_SECRET>" \
  --scopes "openid email profile"
```

### Register a 1P BigQuery MCP Server (`bigquery_mcp` v2.0)
```bash
bash .agents/skills/gemini_enterprise_mcp_registrar/scripts/register_mcp_in_ge.sh \
  --action register-bigquery-mcp \
  --project "<GEMINI_ENTERPRISE_PROJECT_ID>" \
  --engine-id "<ENGINE_ID>" \
  --collection-id "<COLLECTION_ID>" \
  --display-name "BigQuery"
```

### Republish an Existing Connector to Agent Registry & Bind Auth
```bash
bash .agents/skills/gemini_enterprise_mcp_registrar/scripts/register_mcp_in_ge.sh \
  --action republish \
  --project "<GEMINI_ENTERPRISE_PROJECT_ID>" \
  --collection-id "<COLLECTION_ID>" \
  --auth-url "https://<service-url>/authorize" \
  --token-url "https://<service-url>/token" \
  --client-id "<OAUTH_CLIENT_ID>" \
  --client-secret "<OAUTH_CLIENT_SECRET>" \
  --scopes "openid email profile"
```

### Delete an Existing Connector (Full Cleanup)
```bash
bash .agents/skills/gemini_enterprise_mcp_registrar/scripts/register_mcp_in_ge.sh \
  --action delete \
  --project "<GEMINI_ENTERPRISE_PROJECT_ID>" \
  --engine-id "<ENGINE_ID>" \
  --collection-id "<OLD_COLLECTION_ID>"
```
