---
name: Sobi MCP Skill Generator & Sandbox Onboarding
description: Generates a Sobi sandbox companion skill (SKILL.md & .zip) with exact remote_cli mcp tool schemas, configures Sobi Agent Workload Identity IAM roles for Hodor PDP Shim outbound OAuth token injection, and mounts the skill and MCP server onto Sobi agents in Gemini Enterprise.
---

# Sobi MCP Skill Generator & Sandbox Onboarding Skill

Use this skill whenever an MCP Server (either a Custom BYO Cloud Run MCP Server or a Managed MCP Server such as Snowflake) registered in Gemini Enterprise needs to be invoked by the **Sobi** long-running AI coworker (`sobi-*`) inside its VMaaS sandbox container (`/workspace`) via `remote_cli mcp`.

> **Why This Is a Separate, Modular Skill:**
> 1. **AI Coworker Agnosticism:** MCP servers registered in Gemini Enterprise can be used by standard Gemini Enterprise chat, ADK agents, or other AI coworkers that do not use Sobi's VMaaS sandbox or `remote_cli mcp`.
> 2. **Future-Proofing for Sobi Evolution:** As Sobi evolves to natively introspect MCP tool `inputSchema` and invoke registered MCP servers without requiring explicit `remote_cli mcp` instructions in a `SKILL.md`, this skill can be retired or updated without affecting how MCP servers are built, deployed, or registered.

---

## Core Architecture & Sobi-Specific Lessons

When invoking a registered MCP connector from the Sobi VMaaS sandbox (`/workspace`), **three Sobi-specific failure modes** occur if not configured properly:

### 1. Sobi Sandbox Outbound Credential Injection (`401 Unauthorized` on `calling "initialize"`)
* **How `remote_cli mcp` Injects OAuth Bearer Tokens:**
  1. Inside the Sobi VMaaS sandbox container, `/usr/local/bin/remote_cli mcp` intentionally sends **no `Authorization` header**.
  2. Outbound requests to `--endpoint 'https://<mcp-endpoint>'` traverse **Agent Gateway $\rightarrow$ Gatekeeper $\rightarrow$ Hodor PDP Shim**:
     * **Agent Gateway (`AgentGatewayRegistryLookupFilter`)** calls `apphubendpoint.googleapis.com/v1alpha/projects/<PROJECT_NUMBER>/locations/global:lookupAgentRegistry` for the Sobi Agent's `aiapp-<agentfe_id>` and MCP endpoint URI, resolving `authProviderInfo.authProvider` (`projects/<PROJECT_NUMBER>/locations/global/authProviders/ge-auth-<id>`).
     * **Gatekeeper** attaches `X-Google-IAP-Token-Delegation` containing `auth_provider_name`, `id_jag`, and `euc` (the Sobi Agent's Workload Identity).
     * **Hodor PDP Shim (`OutgoingCredentialModule::AttachCred`)** executes the M2 credential flow:
       1. Calls `AuthProviderService.GetAuthProvider(auth_provider_name)` on `agentidentity.googleapis.com` **authenticated with `euc_` (the Sobi Agent's Workload Identity)**.
       2. Extracts `connector_reference_auth_provider.connector` (`projects/<PROJECT_NUMBER>/locations/global/collections/<COLLECTION_ID>/dataConnector`).
       3. Calls `DataConnectorService.AcquireAccessToken` (`discoveryengine.googleapis.com`) using the end-user's identity to fetch the OAuth 2.0 `accessToken` and injects `Authorization: Bearer <access_token>` into the outbound request.
* **Pitfall (`401 Unauthorized` on `remote_cli mcp`):**
  * `AuthProviderService.GetAuthProvider` requires the **`agentidentity.authProviders.get`** IAM permission, which is granted by **`roles/agentidentity.viewer`** (and is **NOT** included in `roles/agentidentity.user`!).
  * If the Sobi Agent's Workload Identity (`principalSet://agents.global.org-<ORG_ID>.system.id.goog/...`) only has `roles/agentidentity.user` and lacks **`roles/agentidentity.viewer`**, `GetAuthProvider` fails with `PERMISSION_DENIED`. Hodor PDP Shim fails open (`CommonResponse::CONTINUE` with no `Authorization` header), and the MCP Server rejects the unauthenticated request with `401 Unauthorized` (`calling "initialize": Unauthorized`).
* **Fix:**
  * Grant **`roles/agentidentity.viewer`**, **`roles/agentidentity.user`**, and **`roles/agentregistry.viewer`** on the Gemini Enterprise project to the Sobi Agent Workload Identity principal sets:
    ```bash
    for PRINCIPAL in \
      "principalSet://agents.global.org-${ORG_ID}.system.id.goog/attribute.platform/aiplatform" \
      "principalSet://agents.global.org-${ORG_ID}.system.id.goog/attribute.platformContainer/aiplatform/projects/${PROJECT_NUMBER}"; do
      for ROLE in "roles/agentidentity.viewer" "roles/agentidentity.user" "roles/agentregistry.viewer"; do
        gcloud projects add-iam-policy-binding "${GE_PROJECT_ID}" \
          --member="${PRINCIPAL}" \
          --role="${ROLE}" \
          --condition=None
      done
    done
    ```

### 2. Positional `remote_cli mcp` Syntax & Stripped `inputSchema`
* **Pitfall A (Stripped `inputSchema`):** Discovery Engine's `DataConnector.DynamicTool` proto only stores `name`, `displayName`, and `description`—it does **not** store `inputSchema` (parameter names and types). Without a companion skill, the Sobi agent has to spend extra turns running `remote_cli mcp <connector> list-tools` and `remote_cli mcp <connector> describe <tool>` or risks guessing wrong parameter names.
* **Pitfall B (Invalid `-s` / `-t` Flags):** `/usr/local/bin/remote_cli mcp` uses **positional `<connector> <tool>` arguments**, NOT `-s` or `-t` flags. If a skill is not mounted, the agent may hallucinate `remote_cli mcp -s ... -t ...`, which fails immediately with `flag provided but not defined: -s`.
* **Pitfall C (Hardcoded Project Numbers Across Environments):** Never reuse a `SKILL.md` or `.zip` from another project without updating the `PROJECT_NUMBER` and `COLLECTION_ID` in `projects/<GE_PROJECT_NUMBER>/locations/global/collections/<COLLECTION_ID>/dataConnector`.
* **The Exact `remote_cli mcp` Invocation Format:**
  ```bash
  remote_cli mcp \
    projects/<GE_PROJECT_NUMBER>/locations/global/collections/<COLLECTION_ID>/dataConnector \
    <tool_name> \
    --json '{"<exact_param_name>": "<value>"}' \
    --endpoint 'https://<mcp-endpoint-url>'
  ```

### 3. Skill Sharing (`ALL_USERS`) & Mounting on Sobi Agents (`skillAgents` + `mcpServers`)
* **Pitfall A (`RESTRICTED` Scope):** Uploading a skill `.zip` in the UI defaults `sharingConfig.scope` to `"RESTRICTED"`, preventing other users (or unmounted sessions) from accessing it.
* **Pitfall B (Unmounted `skillAgents` & Unreconciled `mcpServers`):**
  * Existing `sobi-*` agents must have `projects/<GE_PROJECT_NUMBER>/locations/global/skills/private-skill-<SKILL_AGENT_ID>` in `longRunningAgentDefinition.skillAgents` so the skill is mounted in `/workspace`.
  * If a user's `sobi-*` agent (`aiapp-<agentfe_id>`) was created *before* the MCP connector was registered, its `longRunningAgentDefinition.mcpServers` list must include the connector's Agent Registry URN (`projects/<GE_PROJECT_NUMBER>/locations/global/mcpServers/agentregistry-...`) via `PATCH ...?updateMask=longRunningAgentDefinition.skill_agents,longRunningAgentDefinition.mcp_servers` so `ResolveConnectorsForUpdate` binds the MCP server and its `authProvider` (`ge-auth-*`) to `aiapp-<agentfe_id>`.

---

## Step-by-Step Workflow

### Step 1: Collect Inputs
1. **`GE_PROJECT_ID`**: Gemini Enterprise Google Cloud Project ID.
2. **`ENGINE_ID`**: Gemini Enterprise Engine ID (e.g., `global-gemini-enterprise`).
3. **`COLLECTION_ID`**: The registered MCP connector's collection ID (e.g., `google-patents-mcp`).
4. **`MCP_ENDPOINT_URL`**: Full MCP endpoint URL (e.g., `https://<service-url>/mcp`).
5. **`CLIENT_ID`** & **`CLIENT_SECRET`** *(or `--access-token` / `--custom-skill-md`)*: To introspect `tools/list` from the MCP server (or provide a custom `SKILL.md` file path).

### Step 2: Run the Automated Sobi Skill & Onboarding Script
Use [`scripts/setup_sobi_mcp_skill.sh`](./scripts/setup_sobi_mcp_skill.sh) to automatically:
1. Grant `roles/agentidentity.viewer`, `roles/agentidentity.user`, and `roles/agentregistry.viewer` to the Sobi Agent Workload Identity principal sets on `GE_PROJECT_ID`.
2. Introspect `tools/list` from `MCP_ENDPOINT_URL` (or read `--custom-skill-md`) and generate `<collection_id>_skill/SKILL.md` and `<collection_id>_skill.zip` with the target project's `PROJECT_NUMBER`.
3. Create or update the Skill Agent on `.../assistants/default_assistant/agents` with `sharingConfig.scope = "ALL_USERS"`.
4. Mount `private-skill-<ID>` (`skillAgents`) and reconcile `agentregistry-...` (`mcpServers`) onto existing `sobi-*` agents in the engine.

```bash
bash .agents/skills/sobi_mcp_skill_generator/scripts/setup_sobi_mcp_skill.sh \
  --ge-project "<GEMINI_ENTERPRISE_PROJECT_ID>" \
  --engine-id "<ENGINE_ID>" \
  --collection-id "<COLLECTION_ID>" \
  --mcp-url "https://<service-url>/mcp" \
  --display-name "<DISPLAY_NAME>" \
  --description "<DESCRIPTION>" \
  --client-id "<GOOGLE_OAUTH_CLIENT_ID>" \
  --client-secret "<GOOGLE_OAUTH_CLIENT_SECRET>"
```
*(Or pass `--custom-skill-md <path/to/SKILL.md>` if you have a hand-crafted `SKILL.md` with domain-specific examples or SQL schemas like Snowflake.)*

---

## Quick Troubleshooting Matrix (Sobi Sandbox)

| Symptom / Error Signature | Root Cause | Exact Fix |
| :--- | :--- | :--- |
| **`401 Unauthorized` (`calling "initialize": Unauthorized`)** when Sobi sandbox runs `remote_cli mcp` | Hodor PDP Shim calls `AuthProviderService.GetAuthProvider` on `agentidentity.googleapis.com` using the Sobi Agent's Workload Identity (`euc_`), which requires `agentidentity.authProviders.get` (**`roles/agentidentity.viewer`**, NOT in `roles/agentidentity.user`). Without it, Hodor fails open without injecting `Authorization: Bearer <token>`. | Grant `roles/agentidentity.viewer`, `roles/agentidentity.user`, and `roles/agentregistry.viewer` on the Gemini Enterprise project to `principalSet://agents.global.org-<ORG_ID>.system.id.goog/attribute.platform/aiplatform` and `.../attribute.platformContainer/aiplatform/projects/<PROJECT_NUMBER>`. |
| **`lookupAgentRegistry` returns `{}`** for a user's `aiapp-<agentfe_id>` | The user's `sobi-*` agent was created before the MCP connector was registered, or `longRunningAgentDefinition.mcpServers` does not include the new `agentregistry-...` URN. | Patch the `sobi-*` agent with `?updateMask=longRunningAgentDefinition.skill_agents,longRunningAgentDefinition.mcp_servers` including the connector's `mcpServers/agentregistry-...` URN. |
| **Sobi sandbox guesses `-s` / `-t` flags (`flag provided but not defined: -s`) or wrong tool parameter names** | The companion skill (`private-skill-*`) is either `RESTRICTED`, not mounted in `sobi-*` `skillAgents`, or references another project's `PROJECT_NUMBER`. | Run `setup_sobi_mcp_skill.sh` to generate the project-specific `SKILL.md`, set `sharingConfig.scope: "ALL_USERS"`, and mount `private-skill-<ID>` onto the `sobi-*` agent, then start a new Sobi chat session. |
