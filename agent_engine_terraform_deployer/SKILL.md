---
name: Agent Engine Terraform Deployer
description: Deploys ADK agents to Vertex AI Agent Engine using the standard Terraform pattern.
mode: manual
---

# Agent Engine Terraform Deployer Skill

This skill helps you deploy your Agent Development Kit (ADK) agent to Vertex AI Agent Engine using a robust, self-contained Terraform pattern. It implements the "Golden Project Structure" and automated packaging logic recommended by the ADK team.

## Official References
- **Module Source:** [github.com/GoogleCloudPlatform/cloud-foundation-fabric/modules/agent-engine](https://github.com/GoogleCloudPlatform/cloud-foundation-fabric/tree/master/modules/agent-engine)
- **Documentation:** [Agent Engine Module README](https://github.com/GoogleCloudPlatform/cloud-foundation-fabric/blob/master/modules/agent-engine/README.md)

## Capabilities
- **Intelligent Preparation**: Intelligently scans and updates `.ae_ignore`, `requirements.txt`, and `.env` for deployment readiness.
- **Initialize Deployment**: Sets up a `deploy/` directory with the golden `main.tf` template.
- **Support for Multiple Sources**:
    - **Local Source**: Deploys from your local machine (ideal for dev).
    - **GitHub Source**: Deploys directly from a GitHub repository (ideal for CI/CD).
- **Auto-Packaging**: Automatically packages your agent code, excluding bulky files.
- **Non-Intrusive Wrapping**: Dynamically generates an `app.py` wrapper during deployment.

## Prerequisites
- **Terraform Version**:
    - **Minimum**: `v1.12.2`
    - **Recommended**: `v1.14.4`
    - [Download Terraform](https://releases.hashicorp.com/terraform/) if needed.
- **GCP Project**: Access to a Google Cloud Project with billing enabled.
- **Permissions**:
    - `roles/aiplatform.user`
    - `roles/storage.objectViewer`
    - `roles/serviceusage.serviceUsageConsumer`
    - `roles/cloudtrace.agent`

## 1. Golden Project Structure
Always separate your deployment logic from your agent code. This prevents Terraform from accidentally zipping up its own bulky provider binaries.

```text
my_project/
├── .ae_ignore              # Patterns to exclude (caching, env files, etc.)
├── my_agent_package/       # YOUR AGENT FOLDER (must have __init__.py)
│   ├── agent.py            # Root agent logic
│   ├── requirements.txt    # Dependencies
│   └── ...
└── deploy/                 # DEDICATED DEPLOYMENT FOLDER
    └── main.tf             # Self-contained Terraform logic
```

## 2. Configuration Reference

### Environment Variables (.env)
Ensure your agent's `.env` includes the following for proper observability:
```bash
# Enables agent traces and logs (excludes prompts/responses)
GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true

# Enables logging of input prompts and output responses
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

### Dependencies (requirements.txt)
Your agent's `requirements.txt` **MUST** include:
```text
google-cloud-aiplatform[agent_engines,adk]
```

## 3. Workflow

### Step 0: Intelligent Agent Preparation (Automated)
Instead of manually creating files, run the provided helper script. It will intelligently scan your agent directory and generate/update `.ae_ignore`, `requirements.txt`, and `.env` with the correct configurations.

```bash
# Run the preparation script pointing to your agent directory (replace /path/to/your/agent)
python3 scripts/prepare_agent.py /path/to/your/agent
```

This script will:
1.  **Exclude Junk**: Add robust exclusions to `.ae_ignore` (git, venve, terraform, `*.zip`, `*.pkl`, etc.).
2.  **Ensure Dependencies**: Add `google-cloud-aiplatform[agent_engines,adk]` to `requirements.txt` if missing.
3.  **Enable Telemetry**: Inject observability env vars into `.env` if not present.

### Option A: Local Deployment (Development)
Use this when you have the code on your machine.

1.  **Initialize**:
    ```bash
    mkdir -p deploy
    # Copy templates/main_local.tf to deploy/main.tf
    ```
2.  **Configure** (`deploy/terraform.tfvars`):
    ```hcl
    project_id        = "your-project-id"
    region            = "us-central1"
    agent_engine_name = "epp-telecom-concierge"
    agent_folder_name = "epp_telecom_concierge"
    ```
3.  **Deploy**:
    ```bash
    cd deploy && terraform init && terraform apply
    ```

### Option B: GitHub Deployment (CI/CD)
Use this to deploy code from a remote repository.

1.  **Initialize**:
    ```bash
    mkdir -p deploy
    # Copy templates/main_github.tf to deploy/main.tf
    ```
2.  **Configure** (`deploy/terraform.tfvars`):
    ```hcl
    project_id         = "your-project-id"
    region             = "us-central1"
    agent_engine_name  = "epp-telecom-concierge"
    github_repo        = "username/repo"
    github_branch      = "main"
    agent_package_name = "epp_telecom_concierge"
    ```
3.  **Deploy**:
    ```bash
    cd deploy && terraform init && terraform apply
    ```

## 4. Critical Learnings & Troubleshooting

### A. The "ResourceExhausted" (256MB) Limit
**The Issue**: Terraform's `inline_source` (base64) has a strict limit. Including `.terraform` or `.adk` folders in your zip will trigger this.
**The Solution**: Use the `EXCLUDES` logic implemented in the templates and `.ae_ignore` to keep the archive under 100KB. The intelligent preparation script handles most of this for you.

### B. "ModuleNotFoundError" on Agent Engine
**The Issue**: Agent Engine extracts your archive into `/code/` and adds it to `PYTHONPATH`. If you don't preserve your package folder in the tarball (e.g., if you tar the *contents* of the folder instead of the folder itself), absolute imports like `from my_package.agent import ...` will fail.
**The Solution**: The templates in this skill always tar from the **parent** of your package directory (`tar -C .. my_package/`).

### C. "Non-Intrusive" Wrapping
**The Issue**: You don't want `AdkApp(agent=root_agent)` in your dev code because it creates dependencies on Vertex SDK during local testing.
**The Solution**: The Terraform template generates a transient `app.py` wrapper that imports your agent *only* during the deployment phase. This keeps your business logic "pure."

### D. Provider Inconsistency Error
**The Issue**: `filebase64()` fails if the file doesn't exist during the `plan` phase.
**The Solution**: We use `data "external"` instead of `null_resource`. Data sources run **before** resource evaluation, ensuring the archive is ready before Terraform checks its size/hash.

### E. IAM Propagation Wait (Error Code 3)
**The Issue**: Agent Engine creation fails (Error Code 3) if the service account roles haven't finished propagating.
**The Solution**: The CFF module includes a `time_sleep`. If you encounter "Error code 3" on the first run, simply retry `terraform apply` after a few minutes.

## 5. A2A Authorization Resource (Gemini Enterprise)

When deploying A2A agents that require OAuth (like A2UI), you must create an `AGENT_AUTHORIZATION` resource in Gemini Enterprise.

### 5.1 Prerequisite: Create Web OAuth Client

Before creating the authorization resource, the user must create a Web OAuth Client in the Google Cloud Console for the project.

1.  Navigate to **APIs & Services > Credentials** in the Cloud Console.
2.  Click **Create Credentials > OAuth client ID**.
3.  Select Application type: **Web application**.
4.  Add the following **Authorized redirect URIs**:
    *   `https://vertexaisearch.cloud.google.com/oauth-redirect`
    *   `https://vertexaisearch.cloud.google.com/static/oauth/oauth.html`
5.  Save the Client ID and Client Secret.

### 5.2 Construct authorizationUri

Construct the `authorizationUri` using the Client ID and the encoded redirect URI:

```text
https://accounts.google.com/o/oauth2/v2/auth?client_id=<YOUR_CLIENT_ID>&redirect_uri=https%3A%2F%2Fvertexaisearch.cloud.google.com%2Fstatic%2Foauth%2Foauth.html&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcloud-platform&include_granted_scopes=true&response_type=code&access_type=offline&prompt=consent
```

### 5.3 Create Authorization Resource via cURL

Use `curl` with the **Global Endpoint** and include the `X-Goog-User-Project` header.

```bash
curl -X POST \
   -H "Authorization: Bearer \$(gcloud auth application-default print-access-token)" \
   -H "Content-Type: application/json" \
   -H "X-Goog-User-Project: <PROJECT_ID>" \
   "https://global-discoveryengine.googleapis.com/v1alpha/projects/<PROJECT_ID>/locations/global/authorizations?authorizationId=<AUTH_ID>" \
   -d '{
      "name": "projects/<PROJECT_ID>/locations/global/authorizations/<AUTH_ID>",
      "serverSideOauth2": {
         "clientId": "<CLIENT_ID>",
         "clientSecret": "<CLIENT_SECRET>",
         "authorizationUri": "<AUTH_URI>",
         "tokenUri": "<TOKEN_URI>"
      }
   }'
```

Replace `<PROJECT_ID>`, `<AUTH_ID>`, `<CLIENT_ID>`, `<CLIENT_SECRET>`, `<AUTH_URI>`, and `<TOKEN_URI>`.

## 6. A2UI Agent Deployments (Hard Redirection)

> [!CAUTION]
> **Terraform deployments are NOT supported for A2UI agents in this repository.** 
> A2UI agents require a complex Custom Executor setup (to intercept streams and yield binary `DataPart` objects) which relies on Python Pickle-based deployments. Terraform uses Source-based (`tar.gz`) deployments and cannot support this natively.

**If you need to deploy an A2UI agent, you MUST use the Python SDK Deployer.**
Please refer to the `Agent Engine Python Deployer` skill for instructions on Pickle-based deployments.
