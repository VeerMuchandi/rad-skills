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

### 3. Skill Sharing (`ALL_USERS`), Immutable Agent Registry Revisions (`private-skill-*`), Connector Reconciliation (`mcpServers`), & Per-User Authorization Grant (`AGENT_ACCESS_ALLOWED`)
* **Pitfall A (`RESTRICTED` Scope):** Uploading a skill `.zip` in the UI defaults `sharingConfig.scope` to `"RESTRICTED"`, preventing other users (or unmounted sessions) from accessing it.
* **Pitfall B (Immutable Agent Registry Revisions & Duplicate `skillAgents`):**
  * When a Skill Agent is created via `POST /v1alpha/.../assistants/default_assistant/agents`, Discovery Engine delegates it to an immutable Agent Registry skill revision (`projects/<GE_PROJECT_NUMBER>/locations/global/skills/private-skill-<ID>`) and no longer exposes `agents/<ID>` on Discovery Engine for `GET` or `PATCH` (`404 Not Found`).
  * Therefore, updating a skill's `SKILL.md` instructions creates a new `private-skill-<NEW_ID>`. When mounting `private-skill-<NEW_ID>` onto `sobi-*` (`longRunningAgentDefinition.skillAgents`), you **must prune any superseded `private-skill-<OLD_ID>` entries that share the same `displayName`** from `skillAgents`—otherwise `sobi-*` retains duplicate skills and may load the stale revision.
  * Always authenticate Discovery Engine and Agent Registry REST calls with **`gcloud auth application-default print-access-token`** (ADC), NOT `gcloud auth print-access-token` (which is bound to the gcloud CLI's CBA client ID and fails with `403 PERMISSION_DENIED` when switching accounts/projects).
* **Pitfall C (Unmounted `skillAgents` & Unreconciled `mcpServers`):**
  * Existing `sobi-*` agents must have `projects/<GE_PROJECT_NUMBER>/locations/global/skills/private-skill-<SKILL_AGENT_ID>` in `longRunningAgentDefinition.skillAgents` so the skill is mounted in `/workspace`.
  * Calling `GET /v1alpha/projects/<GE_PROJECT_NUMBER>/locations/global:fetchConnectorWidgets?agent=projects/<GE_PROJECT_NUMBER>/locations/global/agents/sobi-<SOBI_ID>` triggers `SobiAgentReconciler::ReconcileConnectors` (using P4SA credentials) to automatically attach all eligible GE-provisioned `McpServer` resources (`projects/<GE_PROJECT_NUMBER>/locations/global/mcpServers/agentregistry-...`) to `longRunningAgentDefinition.mcpServers` AND resolves/creates the per-user `Authorization` resource (`projects/<PROJECT>/locations/global/authProviders/ge-auth-<FP64>/authorizations/<AUTHZ_ID>`).
* **Pitfall D (`agentAccessState: AGENT_ACCESS_DISALLOWED` on Per-User `Authorization`):**
  * Even when `authorizationState` is `AUTHORIZATION_STATE_AUTHORIZED` and project-level IAM is configured, Agent Identity evaluates per-user agent access by checking the IAM policy on the user's `Authorization` resource (`projects/<PROJECT>/locations/global/authProviders/ge-auth-<FP64>/authorizations/<AUTHZ_ID>`).
  * If `principal://<sobi_agent_spiffe_id>` (from `agentIdentityInfo.spiffeId` on the `sobi-*` agent) does not have `roles/agentidentity.user` on that `Authorization` resource (and `AuthProvider`), `:fetchConnectorWidgets?agent=...` reports `"agentAccessState": "AGENT_ACCESS_DISALLOWED"` and `remote_cli mcp` fails with `401 Unauthorized` during initialization.
  * Granting `roles/agentidentity.user` to `principal://<sobi_agent_spiffe_id>` and `principalSet://agents.global.org-<ORG_ID>.system.id.goog/*` via `POST https://agentidentity.googleapis.com/v1alpha/<AUTHZ_NAME>:setIamPolicy` transitions `agentAccessState` to `"AGENT_ACCESS_ALLOWED"`.

### 4. Preventing Sobi Web-Browsing Fallbacks (`google:browse` / `google:search`) After Successful MCP Calls
Even when `remote_cli mcp` succeeds with `200 OK`, Sobi will fall back to browsing the web (`google:browse` or `google:search`) if any of the following happen:
1. **Terminal Stdout Preview Truncation (~150 lines):** Sobi's terminal tool truncates stdout previews after ~150 lines. If Sobi prints a 4- or 5-period JSON response directly to stdout, the 4th/5th period is cut off in the terminal preview, making Sobi think the MCP server omitted earlier periods. **Fix in `SKILL.md`:** Instruct Sobi to always redirect `remote_cli mcp` output to a file (`> /tmp/out.json`) and parse it with Python.
2. **Browsing Returned Citation URLs (`*.htm`, `*.pdf`):** If an MCP tool returns `document_url` links (such as 15–25 MB SEC iXBRL `.htm` files) and Sobi sees an ambiguous/missing subtotal, Sobi may pass `document_url` to `google:browse`, hitting page size caps. **Fix in `SKILL.md`:** Explicitly prohibit passing MCP `document_url` links to `google:browse` or `curl`; state that returned URLs are strictly for markdown citation links in the final response.

### 5. Guaranteeing Turn-1 `ui://` MCP App Auto-Display in Sobi Live Code Preview (`/workspace/deliverables/index.html`)
When an MCP tool outputs a `ui://` resource (`_meta.ui.resourceUri` or `"ui_resource_uri": "ui://..."`), five pitfalls can prevent the interactive MCP App from automatically opening and rendering properly in Sobi's right-hand Canvas / Live Code Preview pane on Turn 1:
1. **Why `/workspace/deliverables/` Is Mandatory for Auto-Open (`isTaskSandboxDeliverable` in `chat_page.ts`):**
   * In the Gemini Enterprise UI (`cloud/ai/geminienterprise/ui/app/chat_page.ts` and `utils/deliverables_path.ts`), both `autoOpenChangedArtifacts` (which calls `this.openFileInCanvas({section: 'task', path: first.path}, {auto: true})`) and `changedArtifactChips` (which renders the prominent `<app-artifact-card>` deliverable card beneath the reply) filter files using `isTaskSandboxDeliverable(path)` (`/^(?:\/)?(?:workspace\/)?deliverables\//`).
   * If Sobi writes `/workspace/index.html` at the workspace root, `isTaskSandboxDeliverable` returns `false` (`skipped = 'the change is all outside deliverables/'`), so the Canvas panel **never opens automatically**!
   * Furthermore, in `boq/bidi_task_lane.ts` (`changedArtifacts`), `before.get(artifact.id)` skips `kind: 'file'` paths that already existed in an earlier turn of the same chat session (`comparableContent(artifact)` is `undefined` for `kind: 'file'`).
   * **Fix in `SKILL.md`:** Always instruct Sobi to `mkdir -p /workspace/deliverables` and write the HTML app to **both** `/workspace/deliverables/index.html` (via its native `write_file` tool) **and** a unique descriptive path `/workspace/deliverables/<slug>.html` (e.g., `/workspace/deliverables/US8000000B2_citation_graph.html`), plus link `[index.html](/workspace/deliverables/index.html)` in the final markdown response.
2. **`remote_cli mcp` Wrapper Structure (`['tool', 'isError', 'result', '_meta']`):** `remote_cli mcp` wraps the tool response inside `{"tool": "<name>", "isError": false, "result": <structuredContent>, "_meta": {"ui": {"resourceUri": "ui://..."}}}`. The MCP server should include `"ui_resource_uri"`, `"live_preview_url"`, and `"mcp_app_html"` inside `structuredContent` (not just `TextContent`), and the `SKILL.md` Python extractor must recursively walk `obj["result"]` and `obj["_meta"]` to extract the structured data payload.
3. **Shell File Write (`Ran python3`) vs. Native File-Writing Tool (`Wrote /workspace/deliverables/index.html`):** Writing a file only inside a bash/Python `terminal` command does not emit the native file-write step chip. `SKILL.md` must instruct Sobi to call its **native file-writing tool** (`write_file` / `create_file` on `/workspace/deliverables/index.html` and `/workspace/deliverables/<slug>.html`).
4. **Sandboxed `srcdoc` Iframe Prohibition Against `"Loading..."` / `fetch()` Stubs:** Sobi's Live Code Preview panel renders the HTML inside a **sandboxed `srcdoc` iframe**. Inside `about:srcdoc`, `fetch("ui://...")`, `fetch("./mcp_app.html")`, and external `fetch(LIVE_URL)` calls **always fail**, leaving the screen stuck on `"Loading..."`. Therefore, `SKILL.md` must strictly prohibit writing any `"Loading..."` screen or `fetch()` stub, and instead require Sobi to pass a **100% self-contained interactive HTML/CSS/SVG/JS application** with inline data (`const DATA = {...};` or `const RAW_ELEMENTS = [...];`) to `write_file("/workspace/deliverables/index.html", ...)`.
5. **`emit_a2ui` (`Emit a2ui`) Hijacking the Display Surface:** Calling `emit_a2ui` at the end of a turn overrides the right-hand preview pane with an A2UI summary card/chart. `SKILL.md` must explicitly prohibit calling `emit_a2ui` whenever a `ui://` MCP App or `/workspace/deliverables/index.html` is rendered.

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
2. Introspect `tools/list` from `MCP_ENDPOINT_URL` (or read `--custom-skill-md`) and generate `<collection_id>_skill/SKILL.md` and `<collection_id>_skill.zip` with the target project's `PROJECT_NUMBER` and Sobi execution guardrails.
3. Create the Skill Agent on `.../assistants/default_assistant/agents` with `sharingConfig.scope = "ALL_USERS"`.
4. Mount the new `private-skill-<ID>` (`skillAgents`) while pruning any superseded duplicate skills with the same `displayName`, trigger `:fetchConnectorWidgets?agent=...` to reconcile `agentregistry-...` (`mcpServers`) and resolve per-user `Authorization` resources, and grant `roles/agentidentity.user` to the Sobi agent's SPIFFE principal on `AuthProvider` and `Authorization` (`AGENT_ACCESS_ALLOWED`).

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
| **`401 Unauthorized` (`calling "initialize": Unauthorized`)** when Sobi sandbox runs `remote_cli mcp` | Either (1) project-level Workload Identity IAM is missing `roles/agentidentity.viewer` / `roles/agentidentity.user`, OR (2) the per-user `Authorization` resource (`authProviders/ge-auth-<FP64>/authorizations/<AUTHZ_ID>`) does not grant `roles/agentidentity.user` to `principal://<sobi_agent_spiffe_id>` (`agentAccessState: AGENT_ACCESS_DISALLOWED`). | 1. Grant project-level Workload Identity IAM roles.<br>2. Call `GET .../locations/global:fetchConnectorWidgets?agent=projects/<PROJECT_NUMBER>/locations/global/agents/sobi-<ID>` to reconcile `mcpServers` and resolve the `Authorization`.<br>3. Call `:setIamPolicy` on `authProviders/ge-auth-<FP64>` and its `authorizations/<AUTHZ_ID>` with `roles/agentidentity.user` for `principal://<spiffeId>`, and verify `agentAccessState: AGENT_ACCESS_ALLOWED`. |
| **`lookupAgentRegistry` returns `{}`** for a user's `aiapp-<agentfe_id>` | The user's `sobi-*` agent was created before the MCP connector was registered, or `longRunningAgentDefinition.mcpServers` does not include the new `agentregistry-...` URN. | Call `GET .../locations/global:fetchConnectorWidgets?agent=projects/<PROJECT_NUMBER>/locations/global/agents/sobi-<ID>` (which runs `SobiAgentReconciler` via P4SA) or patch `longRunningAgentDefinition.mcpServers`. |
| **Sobi sandbox guesses `-s` / `-t` flags (`flag provided but not defined: -s`) or ignores updated `SKILL.md` instructions** | Either (1) the skill is `RESTRICTED` / unmounted, or (2) `PATCH` was called on Discovery Engine `agents/<ID>` (which returns `404` because skills become immutable Agent Registry `private-skill-*` revisions), or an older duplicate `private-skill-*` is still listed first in `sobi-*` `skillAgents`. | Re-run `setup_sobi_mcp_skill.sh`, which creates a new `private-skill-<NEW_ID>` via `POST /agents` using ADC credentials and automatically prunes superseded `private-skill-*` entries with the same `displayName` from `sobi-*` `skillAgents`. |
| **Sobi calls `remote_cli mcp` successfully (`200 OK`) but still falls back to `google:browse` / web search** | Either (1) Sobi printed multi-period JSON directly to stdout and the ~150-line terminal preview cut off the 4th/5th period, OR (2) a missing/aliased subtotal (e.g., `operating_income == pretax_income`) prompted Sobi to call `google:browse` on a `document_url` (`*.htm`) returned by the MCP server. | 1. Ensure `SKILL.md` includes **Rule 1** (redirect `remote_cli mcp` output to `/tmp/*.json` and parse in Python) and **Rule 2** (never pass returned `document_url` citation links to `google:browse`).<br>2. Ensure the MCP server does not truncate requested multi-period arrays (use a 32 KB serialization budget) and derives missing subtotals with explicit reconciliation notes. |
| **`remote_cli: calling "tools/call": sending "tools/call": Forbidden` (while `initialize` and `tools/list` return `200 OK` on Cloud Run)** | Gatekeeper / Agent Gateway enforces an outbound tool allowlist using `AgentRegistry` `McpServer.tools`. Even after clicking **Refresh tools** in the Cloud Console (which populates `DataConnector.dynamicTools`), `AgentRegistry` `McpServer.tools` stays at `0` until `UpdateDataConnector` (`PATCH .../dataConnector`) runs to sync `dynamicTools` into `AgentRegistry`. | 1. Click **Refresh tools** in the Gemini Enterprise Console UI (`DataConnector.dynamicTools` becomes `> 0`).<br>2. Immediately run `PATCH https://discoveryengine.googleapis.com/v1alpha/projects/<PROJECT_NUMBER>/locations/global/collections/<COLLECTION_ID>/dataConnector?updateMask=bap_config,dynamic_tools` with the current `bapConfig` and `dynamicTools`, then verify `GET https://agentregistry.googleapis.com/v1alpha/projects/<PROJECT_NUMBER>/locations/global/mcpServers/<MCP_ID>` shows `tools` count `> 0`. |
| **Interactive `ui://` MCP App or `index.html` does not open automatically on Turn 1 (until user clicks `index.html`), OR gets stuck on `"Loading interactive..."`** | (1) File was written to `/workspace/index.html` instead of `/workspace/deliverables/index.html` (`chat_page.ts` only auto-opens files matching `isTaskSandboxDeliverable` `/^\/?(workspace\/)?deliverables\//`); (2) in multi-turn sessions, overwriting the exact same path is skipped by `bidi_task_lane.ts` (`before.get(artifact.id)`); (3) `remote_cli mcp` wraps output in `['tool', 'isError', 'result', '_meta']`; (4) writing a `"Loading..."` + `fetch()` stub fails inside Sobi's sandboxed `srcdoc` iframe; (5) calling `emit_a2ui` (`Emit a2ui`) overrides the right-hand preview pane. | 1. Always `mkdir -p /workspace/deliverables` and call native `write_file` on **both** `/workspace/deliverables/index.html` and a unique `/workspace/deliverables/<slug>.html` with a **100% self-contained HTML/CSS/SVG/JS application** (`const DATA = {...};`) and **zero `fetch()` or `"Loading..."` stubs**.<br>2. Include `[index.html](/workspace/deliverables/index.html)` in the markdown reply.<br>3. Explicitly forbid calling `emit_a2ui` whenever a `ui://` MCP App is rendered. |



