---
name: Cloud Run MCP Server Creator
description: End-to-end guide, templates, and automation for building, refactoring (from local stdio), securing (Multi-Tenant OAuth 2.0, Secret Manager, Direct VPC Egress / PSC), and deploying a production Model Context Protocol (MCP) Server on Google Cloud Run.
---

# Cloud Run MCP Server Creator Skill

Use this skill whenever a developer or partner wants to:
1. **Build a new Model Context Protocol (MCP) Server in Python**, secure it with **OAuth 2.0**, and deploy it to **Google Cloud Run**.
2. **Refactor an existing local `stdio` MCP Server** (`npx` / `uvx` with static `ENV` API keys) into a **Stateless `StreamableHTTP` (`/mcp`) + `SSE` (`/sse`) Cloud Run service** with **Multi-Tenant 3-Legged OAuth 2.0** per-user token passthrough.
3. **Deploy a Regulated / Data-Gravity MCP Server** on Cloud Run connecting privately to customer VPC backends via **Direct VPC Egress** or **Private Service Connect (PSC)** and **Google Cloud Secret Manager**.

*(Companion Skills: For designing coarse-grained business workflow tools over fine-grained REST/GraphQL/gRPC APIs, use [**API-to-MCP Wrapper**](../api_to_mcp_wrapper/SKILL.md). For adding interactive visual `ui://` workflows, use [**MCP Apps Developer**](../mcp_apps_developer/SKILL.md). To register the deployed MCP server into Gemini Enterprise, Agent Registry, and Agent Identity, use [**Gemini Enterprise MCP Registrar**](../gemini_enterprise_mcp_registrar/SKILL.md). To generate a Sobi sandbox companion skill for `remote_cli mcp`, use [**Sobi MCP Skill Generator**](../sobi_mcp_skill_generator/SKILL.md).)*

---

## Core Architecture & Hard-Won Lessons (Why Things Break & How We Solve Them)

When building and deploying an MCP Server on Cloud Run for enterprise AI platforms (such as Gemini Enterprise, Vertex AI Agent Engine, Claude, or custom MCP clients), **six critical failure modes** occur if you use naive defaults. You **MUST** follow these patterns in every Cloud Run MCP server you generate:

### 1. Dual-Layer Security: Public Cloud Run Ingress + Application-Layer OAuth 2.0
* **Pitfall:** Deploying Cloud Run with `--no-allow-unauthenticated` blocks enterprise MCP clients (such as Gemini Enterprise / Discovery Engine / BAP / Hodor PDP Shim) and browser OAuth 2.0 redirects, because MCP platforms send **application-level OAuth 2.0 Bearer tokens**, not GCP IAM OIDC identity tokens.
* **Requirement:**
  1. Deploy Cloud Run with `--allow-unauthenticated` (`allUsers` granted `roles/run.invoker`).
  2. If the GCP Organization enforces Domain Restricted Sharing (`constraints/iam.allowedPolicyMemberDomains`), relax it on the project first:
     ```bash
     gcloud resource-manager org-policies disable-enforce constraints/iam.allowedPolicyMemberDomains --project=<PROJECT_ID>
     ```
  3. Enforce strict OAuth 2.0 Bearer token verification **inside the FastMCP server** (`TokenVerifier` + `AuthSettings`), leaving `/`, `/health`, `/healthz`, `/authorize`, `/token`, `/register`, and `/.well-known/oauth-*` publicly reachable for health checks and the 3-legged OAuth handshake.

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

### 4. Built-in Stateless HMAC-SHA256 `/authorize`, `/token`, `/register` & `/.well-known` Endpoints (Preventing COOP Popup Failures)
Why OAuth popups (such as Cloud Console's **Verify Auth**) fail with `"Failed to obtain refresh token"` when pointing directly to `accounts.google.com` or `oauth2.googleapis.com`:
1. **COOP Severing `window.opener`:** When a web console (e.g., `console.cloud.google.com`) opens a popup that redirects to `https://vertexaisearch.cloud.google.com/oauth-redirect`, `oauth-redirect` relies on `window.opener.postMessage(...)` to pass the OAuth authorization `code` back to the opener window. Navigating the popup through `accounts.google.com` sets `Cross-Origin-Opener-Policy: same-origin`, which sets `window.opener = null` and breaks the popup callback.
2. **Malformed `Authorization URL Parameters` Concatenation:** When `&access_type=offline&prompt=consent` is entered in an *Authorization URL Parameters* field, some clients concatenate it directly onto the Authorization URL without a `?` (requesting `GET /authorize&access_type=offline&prompt=consent?...`), causing a `404 Not Found` unless the server mounts a wildcard route `/authorize{extra:path}`.
3. **Guaranteed `refresh_token` & Flexible Client Auth on `/token`:** Enterprise token vaults reject token responses that omit `refresh_token`, and may send client credentials via HTTP Basic Auth (`Authorization: Basic ...`), POST form fields, or JSON body, with or without PKCE (`code_challenge` / `code_verifier`).
* **The Solution:**
  * Mount `/authorize` (and `/authorize{extra:path}`), `/token`, `/register` (RFC 7591), `/.well-known/oauth-protected-resource` (RFC 9728), and `/.well-known/oauth-authorization-server` (RFC 8414) directly on the Cloud Run MCP Server (see [`resources/server_template.py`](./resources/server_template.py)).
  * Derive an HMAC-SHA256 signing key deterministically from `GOOGLE_OAUTH_CLIENT_ID` + `GOOGLE_OAUTH_CLIENT_SECRET` so every Cloud Run container instance can issue and verify signed authorization codes (`mcp_code.*`), access tokens (`mcp_at.*`), and refresh tokens (`mcp_rt.*`) **statelessly**.

### 5. Refactoring Local `stdio` MCP Servers $\rightarrow$ Multi-Tenant Cloud Run `StreamableHTTP`
When a partner has an existing local `stdio` MCP server (`mcp.run(transport="stdio")`) that reads a static personal API key from `os.environ["PARTNER_API_KEY"]`:
1. **Replace `stdio` Transport:** Replace `mcp.run(transport="stdio")` with `get_asgi_app()` in [`resources/server_template.py`](./resources/server_template.py) and [`resources/main.py`](./resources/main.py).
2. **Upgrade Static API Keys to Multi-Tenant 3-Legged OAuth Passthrough:**
   * `resources/server_template.py` automatically captures the caller's verified OAuth Bearer token and claims into per-request `ContextVar`s during `GoogleOAuthTokenVerifier.verify_token()`.
   * Inside any `@mcp.tool()`, call `get_current_user_token()` and `get_current_user_claims()` to pass the authenticated user's token (or exchange it) when calling downstream partner APIs, enforcing per-user RBAC and tenant isolation instead of a single shared static key.

### 6. Data Gravity & Private Networking (Direct VPC Egress, PSC & Secret Manager)
For regulated industries (healthcare, finance, legal) where customer data cannot traverse the public internet and secrets cannot be stored in plain-text environment variables:
1. **Direct VPC Egress to Private Service Connect (PSC) / Internal Subnets:**
   * Pass `--network <VPC_NETWORK> --subnet <VPC_SUBNET> --vpc-egress private-ranges-only` (or `all-traffic`) to [`scripts/deploy_cloud_run_mcp.sh`](./scripts/deploy_cloud_run_mcp.sh).
   * Cloud Run routes outbound calls to internal RFC 1918 IPs, peered VPCs, AlloyDB/Cloud SQL private IPs, or PSC producer endpoints directly through the customer's VPC while keeping the MCP `/mcp` endpoint accessible to Gemini Enterprise.
2. **Secret Manager Integration & Least-Privilege Service Account:**
   * Pass `--use-secret-manager` (and optional `--set-secrets <ENV=SECRET:VERSION>` + `--service-account <CUSTOM_SA_EMAIL>`) to [`scripts/deploy_cloud_run_mcp.sh`](./scripts/deploy_cloud_run_mcp.sh) so `GOOGLE_OAUTH_CLIENT_SECRET` and downstream credentials are encrypted in Secret Manager and mounted at runtime.

---

## Step-by-Step Workflow

When triggered, follow these steps in order:

### Step 1: Collect Inputs from the User
Ask the user for any missing parameters (never guess `GOOGLE_CLOUD_PROJECT`):
1. **`PROJECT_ID`**: Target Google Cloud Project ID where Cloud Run will be deployed.
2. **`REGION`**: Cloud Run region (default: `us-central1`).
3. **`SERVICE_NAME`**: Cloud Run service name (e.g., `my-custom-mcp-server`).
4. **`GOOGLE_OAUTH_CLIENT_ID`** & **`GOOGLE_OAUTH_CLIENT_SECRET`**: OAuth 2.0 Web Application Client credentials.
5. ***(Optional — For Private Networking / Regulated Workloads)***:
   * `VPC_NETWORK` & `VPC_SUBNET` (for Direct VPC Egress / PSC)
   * `SERVICE_ACCOUNT` (custom least-privilege runtime SA)
   * `USE_SECRET_MANAGER` (`--use-secret-manager` to store and mount secrets from Secret Manager)

### Step 2: Scaffold the MCP Server from Templates
Copy the reference files from this skill's `resources/` folder into the target MCP server directory:
* [`resources/server_template.py`](./resources/server_template.py) $\rightarrow$ `server.py` (Customize `FastMCP(name=..., instructions=...)` and add `@mcp.tool()` functions).
* [`resources/main.py`](./resources/main.py) $\rightarrow$ `main.py`
* [`resources/Dockerfile`](./resources/Dockerfile) $\rightarrow$ `Dockerfile`
* [`resources/requirements.txt`](./resources/requirements.txt) $\rightarrow$ `requirements.txt` (Add any domain-specific packages such as `google-cloud-bigquery`, `google-cloud-firestore`, `httpx`, etc.).

### Step 3: Local Smoke Test
Before deploying to Cloud Run, verify the server starts cleanly and responds to `/health`, `/authorize`, `/token`, `/register`, and `/mcp` (`tools/list`).

### Step 4: Deploy to Cloud Run
Run the automated deployment script [`scripts/deploy_cloud_run_mcp.sh`](./scripts/deploy_cloud_run_mcp.sh):

**Standard Deployment:**
```bash
bash .agents/skills/cloud_run_mcp_server_creator/scripts/deploy_cloud_run_mcp.sh \
  --project "<PROJECT_ID>" \
  --region "<REGION>" \
  --service-name "<SERVICE_NAME>" \
  --source-dir "<MCP_SERVER_DIR>" \
  --client-id "<GOOGLE_OAUTH_CLIENT_ID>" \
  --client-secret "<GOOGLE_OAUTH_CLIENT_SECRET>"
```

**Regulated / Private Networking Deployment (Direct VPC Egress + PSC + Secret Manager):**
```bash
bash .agents/skills/cloud_run_mcp_server_creator/scripts/deploy_cloud_run_mcp.sh \
  --project "<PROJECT_ID>" \
  --region "<REGION>" \
  --service-name "<SERVICE_NAME>" \
  --source-dir "<MCP_SERVER_DIR>" \
  --client-id "<GOOGLE_OAUTH_CLIENT_ID>" \
  --client-secret "<GOOGLE_OAUTH_CLIENT_SECRET>" \
  --use-secret-manager \
  --network "<VPC_NETWORK>" \
  --subnet "<VPC_SUBNET>" \
  --vpc-egress "private-ranges-only" \
  --service-account "<CUSTOM_SA_EMAIL>" \
  --extra-env-vars "DOWNSTREAM_API_BASE_URL=https://<PSC_OR_INTERNAL_HOST>"
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
| **Dynamic Registration URL (RFC 7591)** | `https://<service-url>/register` |
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
| **Connection timeout to private IP / PSC endpoint** | Cloud Run service was deployed without Direct VPC Egress or the subnet lacks a route to the PSC endpoint. | Re-deploy using `--network <VPC_NETWORK> --subnet <VPC_SUBNET> --vpc-egress private-ranges-only` and verify firewall rules allow ingress from the Cloud Run subnet CIDR. |
