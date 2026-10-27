---
name: Cloud Run MCP Server Creator
description: End-to-end guide, templates, and automation for building, securing (OAuth 2.0), and deploying a production Model Context Protocol (MCP) Server on Google Cloud Run.
---

# Cloud Run MCP Server Creator Skill

Use this skill whenever a developer wants to **build a new Model Context Protocol (MCP) Server in Python**, **secure it with OAuth 2.0**, and **deploy it to Google Cloud Run**.

*(Note: To register a deployed Cloud Run MCP Server—or any existing MCP server—into Gemini Enterprise, Agent Registry, and Agent Identity, use the companion [**Gemini Enterprise MCP Registrar**](../gemini_enterprise_mcp_registrar/SKILL.md) skill. To generate a Sobi sandbox companion skill for `remote_cli mcp`, use the [**Sobi MCP Skill Generator**](../sobi_mcp_skill_generator/SKILL.md) skill.)*

---

## Core Architecture & Hard-Won Lessons (Why Things Break & How We Solve Them)

When building and deploying an MCP Server on Cloud Run for enterprise AI platforms (such as Gemini Enterprise, Vertex AI Agent Engine, or custom MCP clients), **four critical failure modes** occur if you use naive defaults. You **MUST** follow these patterns in every Cloud Run MCP server you generate:

### 1. Dual-Layer Security: Public Cloud Run Ingress + Application-Layer OAuth 2.0
* **Pitfall:** Deploying Cloud Run with `--no-allow-unauthenticated` blocks enterprise MCP clients (such as Gemini Enterprise / Discovery Engine / BAP / Hodor PDP Shim) and browser OAuth 2.0 redirects, because MCP platforms send **application-level OAuth 2.0 Bearer tokens**, not GCP IAM OIDC identity tokens.
* **Requirement:**
  1. Deploy Cloud Run with `--allow-unauthenticated` (`allUsers` granted `roles/run.invoker`).
  2. If the GCP Organization enforces Domain Restricted Sharing (`constraints/iam.allowedPolicyMemberDomains`), relax it on the project first:
     ```bash
     gcloud resource-manager org-policies disable-enforce constraints/iam.allowedPolicyMemberDomains --project=<PROJECT_ID>
     ```
  3. Enforce strict OAuth 2.0 Bearer token verification **inside the FastMCP server** (`TokenVerifier` + `AuthSettings`), leaving `/`, `/health`, `/healthz`, `/authorize`, and `/token` publicly reachable for health checks and the 3-legged OAuth handshake.

### 2. FastMCP Cloud Run Scaling & DNS Rebinding Protection
* **Pitfall A (DNS Rebinding 421/400 errors):** The `mcp` Python SDK enables DNS rebinding protection by default, which rejects Cloud Run `Host: <service>-<hash>-uc.a.run.app` headers.
  * **Fix:** Always configure `TransportSecuritySettings(enable_dns_rebinding_protection=False, allowed_hosts=["*"], allowed_origins=["*"])`.
* **Pitfall B (Multi-instance Session Loss):** Cloud Run scales across multiple instances, causing stateful StreamableHTTP sessions to fail with unknown session IDs.
  * **Fix:** Initialize `FastMCP(..., stateless_http=True)` and deploy Cloud Run with `--session-affinity`.
* **Pitfall C (Transport Compatibility):** Modern MCP clients use **StreamableHTTP (`/mcp`)**, while some legacy/inspector tools use **SSE (`/sse`)**.
  * **Fix:** Build a unified Starlette ASGI app (`get_asgi_app()`) starting from `mcp.streamable_http_app()` and merging routes from `mcp.sse_app()`.
* **Pitfall D (Unnecessary Confirmation Prompts):** Without read-only annotations, MCP clients may prompt users for confirmation before calling search/lookup tools.
  * **Fix:** Attach `ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)` to all read-only tools.

### 3. Google Auth Platform Branding (`Error 403: org_internal`)
* **Pitfall:** Setting Google Auth Platform **Audience / User Type** to **Internal** blocks admins or users from other organizations/domains with `"Access blocked: <App> can only be used within its organization"`.
* **Fix:** Set the OAuth Branding Audience to **External**, create a **Web application** OAuth Client ID & Secret, and add the MCP client's redirect URI (e.g., `https://vertexaisearch.cloud.google.com/oauth-redirect`) to **Authorized redirect URIs**.

### 4. Built-in Stateless HMAC-SHA256 `/authorize` & `/token` Endpoints (Preventing COOP Popup Failures)
Why OAuth popups (such as Cloud Console's **Verify Auth**) fail with `"Failed to obtain refresh token"` when pointing directly to `accounts.google.com` or `oauth2.googleapis.com`:
1. **COOP Severing `window.opener`:** When a web console (e.g., `console.cloud.google.com`) opens a popup that redirects to `https://vertexaisearch.cloud.google.com/oauth-redirect`, `oauth-redirect` relies on `window.opener.postMessage(...)` to pass the OAuth authorization `code` back to the opener window. Navigating the popup through `accounts.google.com` sets `Cross-Origin-Opener-Policy: same-origin`, which sets `window.opener = null` and breaks the popup callback.
2. **Malformed `Authorization URL Parameters` Concatenation:** When `&access_type=offline&prompt=consent` is entered in an *Authorization URL Parameters* field, some clients concatenate it directly onto the Authorization URL without a `?` (requesting `GET /authorize&access_type=offline&prompt=consent?...`), causing a `404 Not Found` unless the server mounts a wildcard route `/authorize{extra:path}`.
3. **Guaranteed `refresh_token` & Flexible Client Auth on `/token`:** Enterprise token vaults reject token responses that omit `refresh_token`, and may send client credentials via HTTP Basic Auth (`Authorization: Basic ...`), POST form fields, or JSON body, with or without PKCE (`code_challenge` / `code_verifier`).
* **The Solution:**
  * Mount `/authorize` (and `/authorize{extra:path}`) and `/token` directly on the Cloud Run MCP Server (see [`resources/server_template.py`](./resources/server_template.py)).
  * Derive an HMAC-SHA256 signing key deterministically from `GOOGLE_OAUTH_CLIENT_ID` + `GOOGLE_OAUTH_CLIENT_SECRET` so every Cloud Run container instance can issue and verify signed authorization codes (`mcp_code.*`), access tokens (`mcp_at.*`), and refresh tokens (`mcp_rt.*`) **statelessly**.
  * `/authorize` validates `client_id` and `redirect_uri`, signs `mcp_code.*` (preserving `state` and optional PKCE `code_challenge`), and immediately returns `302 Found` to `redirect_uri` **without** COOP headers.
  * `/token` accepts Basic Auth, form body, or JSON body, verifies `mcp_code.*` or `mcp_rt.*` (or falls back to `https://oauth2.googleapis.com/token`), and **always** returns both `access_token` and `refresh_token`.

---

## Step-by-Step Workflow

When triggered, follow these steps in order:

### Step 1: Collect Inputs from the User
Ask the user for any missing parameters (never guess `GOOGLE_CLOUD_PROJECT`):
1. **`PROJECT_ID`**: Target Google Cloud Project ID where Cloud Run (and any backend dependencies like BigQuery) will be deployed.
2. **`REGION`**: Cloud Run region (default: `us-central1`).
3. **`SERVICE_NAME`**: Cloud Run service name (e.g., `my-custom-mcp-server`).
4. **`GOOGLE_OAUTH_CLIENT_ID`** & **`GOOGLE_OAUTH_CLIENT_SECRET`**: OAuth 2.0 Web Application Client credentials.

### Step 2: Scaffold the MCP Server from Templates
Copy the reference files from this skill's `resources/` folder into the target MCP server directory:
* [`resources/server_template.py`](./resources/server_template.py) $\rightarrow$ `server.py` (Customize `FastMCP(name=..., instructions=...)` and add `@mcp.tool()` functions).
* [`resources/main.py`](./resources/main.py) $\rightarrow$ `main.py`
* [`resources/Dockerfile`](./resources/Dockerfile) $\rightarrow$ `Dockerfile`
* [`resources/requirements.txt`](./resources/requirements.txt) $\rightarrow$ `requirements.txt` (Add any domain-specific packages such as `google-cloud-bigquery`, `google-cloud-firestore`, `httpx`, etc.).

### Step 3: Local Smoke Test
Before deploying to Cloud Run, verify the server starts cleanly and responds to `/health`, `/authorize`, `/token`, and `/mcp` (`tools/list`).

### Step 4: Deploy to Cloud Run
Run the automated deployment script [`scripts/deploy_cloud_run_mcp.sh`](./scripts/deploy_cloud_run_mcp.sh):

```bash
bash .agents/skills/cloud_run_mcp_server_creator/scripts/deploy_cloud_run_mcp.sh \
  --project "<PROJECT_ID>" \
  --region "<REGION>" \
  --service-name "<SERVICE_NAME>" \
  --source-dir "<MCP_SERVER_DIR>" \
  --client-id "<GOOGLE_OAUTH_CLIENT_ID>" \
  --client-secret "<GOOGLE_OAUTH_CLIENT_SECRET>"
```

### Step 5: Verify Cloud Run Health, OAuth Handshake & Tool Discovery
After deployment, always verify:
1. `GET https://<service-url>/` (or `/health`) returns `200 OK` with `"oauth_enabled": true`. *(Note: Do NOT use `/healthz` for external URL checks on `*.run.app`—Google Frontend reserves `/*z` paths and intercepts `/healthz` with a 404 before reaching your container).*
2. `GET https://<service-url>/authorize?...` returns `302 Found` with a signed `code=mcp_code...`.
3. `POST https://<service-url>/token` exchanges `code` for `access_token` (`mcp_at...`) and `refresh_token` (`mcp_rt...`).
4. `POST https://<service-url>/mcp` with `Authorization: Bearer <access_token>` and `{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}` returns all expected tools.

### Step 6: Output Endpoints Table & Next Steps
Always output a clean reference table with the deployed endpoints so the user can either register the MCP server in the Cloud Console UI or invoke the [**Gemini Enterprise MCP Registrar**](../gemini_enterprise_mcp_registrar/SKILL.md) skill:

| Parameter | Value |
| :--- | :--- |
| **MCP Server URL (StreamableHTTP)** | `https://<service-url>/mcp` |
| **MCP Server URL (SSE)** | `https://<service-url>/sse` |
| **Authorization URL** | `https://<service-url>/authorize` |
| **Authorization URL Parameters** | `&access_type=offline&prompt=consent` |
| **Token URL** | `https://<service-url>/token` |
| **Client ID** | `<GOOGLE_OAUTH_CLIENT_ID>` |
| **Client Secret** | `<GOOGLE_OAUTH_CLIENT_SECRET>` |
| **Scopes** | `openid email profile` |

---

## Quick Troubleshooting Matrix

| Symptom / Error Signature | Root Cause | Exact Fix |
| :--- | :--- | :--- |
| **`Error 403: org_internal`** during OAuth popup | Google Auth Platform Branding Audience is set to **Internal**. | Change Audience to **External** in Google Auth Platform > Branding, and ensure `https://vertexaisearch.cloud.google.com/oauth-redirect` is in Authorized Redirect URIs. |
| **`Failed to obtain refresh token`** on Cloud Console **Verify Auth** | Pointing Auth/Token URLs to `accounts.google.com` sets `Cross-Origin-Opener-Policy: same-origin` (severing `window.opener`), or `&access_type=offline` is concatenated without `?` (`GET /authorize&access_type=...`). | Point Auth URL to `https://<service-url>/authorize` and Token URL to `https://<service-url>/token` (built-in HMAC-SHA256 endpoints in `resources/server_template.py` with `/authorize{extra:path}` wildcard and zero COOP headers). |
| **`421 Misdirected Request` or `400 Bad Request` (`Invalid Host header`)** | FastMCP's default DNS rebinding protection rejects `*.a.run.app` Host headers. | Set `TransportSecuritySettings(enable_dns_rebinding_protection=False, allowed_hosts=["*"], allowed_origins=["*"])`. |
| **`404 Not Found` on `https://<service-url>/healthz`** | Google Frontend (`*.run.app`) reserves `/*z` paths and intercepts `/healthz` before reaching the Cloud Run container. | Use `https://<service-url>/` or `https://<service-url>/health` for external health checks. |
