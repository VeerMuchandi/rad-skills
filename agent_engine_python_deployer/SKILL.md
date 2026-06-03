---
name: Agent Engine Python Deployer
description: Deploys ADK agents to Vertex AI Agent Engine using the Python SDK and registers them with Gemini Enterprise.
---

# Agent Engine Python Deployer Skill

This skill documents the Python SDK method for deploying ADK agents to Vertex AI Agent Engine (`client.agent_engines.create`) and registering them with Gemini Enterprise using the `DiscoveryEngine` HTTP API. This is an alternative to the Terraform-based deployment workflow.

## 1. Prerequisites

-   **Python 3.10+**: Active environment with dependencies.
-   **Google Cloud Project**: With billing enabled.
-   **Dependencies**:
    ```text
    google-cloud-aiplatform[agent_engines,adk]
    a2a-sdk >= 0.3.4
    cloudpickle >= 3.1.2
    pydantic
    python-dotenv
    ```

## 2. Configuration (`.env`)

Ensure your environment variables are configured correctly:

```bash
# GCP Project Config
PROJECT_ID="your-project-id"
LOCATION="us-central1"
STORAGE_BUCKET="gs://your-staging-bucket"

# Gemini Enterprise Config
GEMINI_ENTERPRISE_APP_ID="your-app-id"

# Authorization Config (obtained from Discovery Engine authorizations API if needed)
AGENT_AUTHORIZATION="projects/PROJECT_NUMBER/locations/global/authorizations/AUTH_ID"

# Logging & Telemetry flags
GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

## 3. Core Workflow

The workflow involves using the Python SDK to deploy and then post-processing the endpoint for Gemini Enterprise.

### 2.B Create Authorization Resource (If Required)

When deploying A2A agents (including A2UI and non-A2UI A2A agents on Agent Engine), you must create an `AGENT_AUTHORIZATION` resource in Gemini Enterprise.

#### 2.B.1 Prerequisite: Create Web OAuth Client

Before creating the authorization resource, you must create a Web OAuth Client in the Google Cloud Console for the project.

1.  Navigate to **APIs & Services > Credentials** in the Cloud Console.
2.  Click **Create Credentials > OAuth client ID**.
3.  Select Application type: **Web application**.
4.  Add the following **Authorized redirect URIs**:
    *   `https://vertexaisearch.cloud.google.com/oauth-redirect`
    *   `https://vertexaisearch.cloud.google.com/static/oauth/oauth.html`
5.  Save the Client ID and Client Secret.

#### 2.B.2 Construct authorizationUri

Construct the `authorizationUri` using the Client ID and the encoded redirect URI:

```text
https://accounts.google.com/o/oauth2/v2/auth?client_id=<YOUR_CLIENT_ID>&redirect_uri=https%3A%2F%2Fvertexaisearch.cloud.google.com%2Fstatic%2Foauth%2Foauth.html&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcloud-platform&include_granted_scopes=true&response_type=code&access_type=offline&prompt=consent
```

#### 2.B.3 Create Authorization Resource via cURL

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

### 3.A Initialize Vertex AI
```python
import os
import vertexai
from dotenv import load_dotenv

load_dotenv()

vertexai.init(
    project=os.environ["PROJECT_ID"],
    location=os.environ["LOCATION"],
    staging_bucket=os.environ["STORAGE_BUCKET"],
)
```

### B. Define `AgentSkill` and Create Card
```python
from a2a.types import AgentSkill
from vertexai.preview.reasoning_engines.templates.a2a import create_agent_card

agent_skill = AgentSkill(
    id="contact_lookup",
    name="Contact Lookup Agent",
    description="A helpful assistant agent that can find contact card.",
    tags=["Contact-Lookup"],
    examples=["Find John Doe"],
)

agent_card = create_agent_card(
    agent_name="Test Contact Card Agent",
    description="A helpful assistant agent that can find contact card.",
    skills=[agent_skill],
)
```

### C. Instantiate A2aAgent with Custom Executor
Override the default executor to intercept the stream and parse A2UI payloads, or simply yield standard A2A messages for non-A2UI agents.
```python
from vertexai.preview.reasoning_engines import A2aAgent
import agent_executor # Your custom executor file

a2a_agent = A2aAgent(
    agent_card=agent_card,
    agent_executor_builder=agent_executor.AdkAgentToA2AExecutor,
)
```

### D. Deploy New Instance with Extra Packages
Use `extra_packages` to bundle non-module dependencies (like external scripts or templates).
```python
from google.genai import types

client = vertexai.Client(
    project=os.environ["PROJECT_ID"],
    location=os.environ["LOCATION"],
    http_options=types.HttpOptions(api_version="v1beta1"),
)

config = {
    # ... your config ...
}

remote_agent = client.agent_engines.create(agent=a2a_agent, config=config)
```

### E. Update Custom Container Packaging inplace (In-place Rebuilt)

If you need to update the source code mounted on an existing engine instance without altering its persistent platform address ID:

> [!IMPORTANT]
> **Use the Canonical Client Suite**: Do NOT use the legacy `ReasoningEngine(name=...).update()` utility. It drops Custom A2A loop wrappers. Always use `client.agent_engines.update()` to preserve the framework context.

```python
import os
import vertexai
from vertexai.preview.reasoning_engines import A2aAgent
from google.genai import types

# Load your A2A wrapper
a2a_agent = A2aAgent(...) 

client = vertexai.Client(project=PROJ_ID, location=LOC)

# Construct the full resource name
existing_engine_name = f"projects/{PROJ_ID}/locations/{LOC}/reasoningEngines/{existing_id}"

# Symmetric config (Use env_vars for flags!)
config = {
    "agent_framework": "google-adk",
    "requirements": ["google-cloud-aiplatform", "a2a-sdk", "cloudpickle", "pydantic"],
    "env_vars": {
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true",
    },
    "extra_packages": ["agent_executor.py", "a2ui_examples.py", "a2ui_schema.py"]
}

remote_agent = client.agent_engines.update(
    name=existing_engine_name,
    agent=a2a_agent,
    config=config
)
print(f"✓ Agent updated inplace: {remote_agent.name}")
```

### F. Register with Gemini Enterprise
Use the `DiscoveryEngine` API to link the Agent Engine endpoint to your Gemini Enterprise App.
```python
import requests
from google.auth import default
from google.auth.transport.requests import Request

def get_bearer_token():
    credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    return credentials.token

# ... deployment snippet above ...
remote_engine_resource = remote_agent.api_resource.name # e.g. projects/.../locations/.../reasoningEngines/...

# Fetch Agent Card JSON from endpoint for registration
a2a_endpoint = f"https://{os.environ['LOCATION']}-aiplatform.googleapis.com/v1beta1/{remote_engine_resource}/a2a/v1/card"
headers = {"Authorization": f"Bearer {get_bearer_token()}"}
response = requests.get(a2a_endpoint, headers=headers)
a2ui_agent_card = response.json()

# Register via Discovery Engine
api_endpoint = (
    f"https://discoveryengine.googleapis.com/v1alpha/projects/{os.environ['PROJECT_ID']}/"
    f"locations/global/collections/default_collection/engines/{os.environ['GEMINI_ENTERPRISE_APP_ID']}/"
    "assistants/default_assistant/agents"
)

payload = {
    "name": "my_agent_name",
    "displayName": "My A2UI Agent",
    "description": "Assist with tasks.",
    "a2aAgentDefinition": {"jsonAgentCard": json.dumps(a2ui_agent_card)},
    # CRITICAL for A2A agents on Agent Engine: Must include authorizationConfig!
    "authorizationConfig": {
        "agentAuthorization": os.environ.get("AGENT_AUTHORIZATION")
    }
}

response = requests.post(api_endpoint, headers=headers, json=payload)
```

## 4. Troubleshooting

-   **Cloudpickle Version**: Ensure `cloudpickle` package versions match between your local environment and the deployment `requirements` to prevent unpickling errors.
-   **Extra Packages Paths**: `extra_packages` should be relative to the running script's directory.
-   **Model Access Lockout (404)**: If you see `404 Publisher Model ... was not found`, the region may not support the model. Create a standalone `troubleshoot_access.py` to probe valid models (e.g., `gemini-2.5-flash`, `gemini-3.1-flash`).
-   **Dependency Build Failure**: Avoid pinning `google-cloud-aiplatform` to a specific sub-version in `requirements` to let the engine resolve the closest compatible version.
-   **Forced Initialization**: To prevent "Project not found" errors, use the **numeric Project Number** and call `aiplatform.init` and `vertexai.init` inside the `__init__` and `execute()` methods of your custom executor.

## 5. Operational Lessons & Parity Discipline

To prevent persistent 400 Bad Request or connection hang loops when deploying A2UI agents:

-   ⚠️ **Avoid Custom Intercept Bloat**: Do not inject complex container-loop safety overrides or unverified monkey-patches unless parity match with working references demanded it. Favor the simple, canonical `client.agent_engines.create()` workflow.
-   ⚠️ **The URL Suffix Trap**: When patching or creating `DiscoveryEngine` Agent platform registrations, the `a2aAgentDefinition.jsonAgentCard.url` must point to the base endpoint (e.g., `.../a2a`) **WITHOUT** a trailing `/v1`. Gemini Enterprise automatically appends `/v1/message:send` to the registered URL. Double suffixes (e.g., `/v1/v1/message:send`) will trigger silent 400 routing drops.
-   ⚠️ **The `env_vars` spelling rule**: When constructing GenAI `config` envelopes, pass container environment variables under the spec-validated **`env_vars`** key. Passing `environment_variables` triggers Pydantic Extra Inputs validation drop.
-   ⚠️ **Always Enable Telemetry**: Ensure `GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY` and `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` are set to `true` in `env_vars` to enable proper logging and debugging in Vertex AI. *Note: If the sandboxed runtime environment restricts external network access to telemetry.googleapis.com, setting this to true will cause connection/SSLError crashes. In such environments, set it to false.*

## 6. Golden Unified `deploy_sdk.py` Template

Use this script to seamlessly toggle between fresh creation and inplace updates based on finding existing instances:

> [!NOTE]
> A standalone version of this template is available at `templates/golden_deploy_sdk.py` within the skill directory.

```python
import os
import vertexai
from vertexai.preview.reasoning_engines import A2aAgent
from google.genai import types
from google.auth import default
# ... other standard ADK imports ...

def main():
    project_id = "your-project-id"
    location = "us-central1"
    storage = "gs://your-staging-bucket"
    existing_engine_id = os.environ.get("EXISTING_ENGINE_ID") # Set if updating
    
    vertexai.init(project=project_id, location=location, staging_bucket=storage)
    
    client = vertexai.Client(project=project_id, location=location)
    
    # ... prepare a2a_agent wrapper ...

    config = {
        "display_name": "My Agent",
        "agent_framework": "google-adk",
        "requirements": [
            "google-adk>=1.16.0",
            "google-cloud-aiplatform[agent_engines,adk]>=1.143.0",
            "a2a-sdk>=0.3.4",
            "pydantic==2.12.5",
            "cloudpickle==3.1.2"
        ],
        "env_vars": {
            "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true",
        },
        "extra_packages": [
            "agent_executor.py",
            "tools.py",
            "agent.py",
            "a2ui_examples.py",
            "a2ui_schema.py" # Vendor all local imports
        ]
    }

    if existing_engine_id:
        engine_name = f"projects/{project_id}/locations/{location}/reasoningEngines/{existing_engine_id}"
        print(f"Applying inplace update to: {existing_engine_id}")
        remote_agent = client.agent_engines.update(name=engine_name, agent=a2a_agent, config=config)
    else:
        print("Spinning up fresh create instance...")
        remote_agent = client.agent_engines.create(agent=a2a_agent, config=config)
        
    print(f"✓ Process settlement: {remote_agent.name}")

if __name__ == "__main__":
    main()
```

## 7. Working Dependencies for A2UI Agents

When deploying A2UI agents to Vertex AI Agent Engine, you may encounter `KeyError: 'serialized'` errors during unpickling in the container if there is a version mismatch for `protobuf` or `cloudpickle`.

The following specific combination of dependency versions has been verified to work successfully for A2UI agents:

```python
        "requirements": [
            "google-adk==1.28.1",
            "google-cloud-aiplatform[agent_engines,adk]==1.143.0",
            "a2a-sdk==0.3.25",
            "pydantic==2.12.5",
            "cloudpickle==3.1.2",
            "protobuf==6.33.6",
            "jsonschema==4.26.0",
            "a2ui-agent-sdk @ git+https://github.com/google/A2UI.git#subdirectory=agent_sdks/python",
        ],
```

Ensure you use these exact versions in your `deploy_ae.py` script if you encounter unpickling errors related to protobuf.

## 8. Lifecycle & Dynamic Registration

To resolve **404/400 Routing Errors**, do not rely on static IP/URL registrations.
1.  **In-Place Updates**: Use `client.agent_engines.update()` to preserve the Engine ID and platform address.
2.  **Authoritative Card Sync**: Post-deployment, always fetch the agent card from the Engine's `/a2a/v1/card` endpoint and push it to the Discovery Engine `a2aAgentDefinition`. This guarantees the registered URL matches the proxy's expectations perfectly.

## 9. Golden Boilerplate: deploy_ae.py

This template manages in-place updates and pinned dependency versions.

> [!NOTE]
> A standalone version of this template is available at `templates/golden_deploy_ae.py` within the skill directory.

```python
import os, vertexai, json, requests
from vertexai.preview.reasoning_engines import A2aAgent
from google.genai import types
from google.protobuf import json_format

# Monkey-patch json_format.MessageToJson and MessageToDict to handle Pydantic models (like AgentCard) correctly
original_message_to_json = json_format.MessageToJson
def patched_message_to_json(message, *args, **kwargs):
    if hasattr(message, "model_dump_json"):
        return message.model_dump_json()
    elif hasattr(message, "json"):
        return message.json()
    elif isinstance(message, dict):
        return json.dumps(message)
    return original_message_to_json(message, *args, **kwargs)
json_format.MessageToJson = patched_message_to_json

original_message_to_dict = json_format.MessageToDict
def patched_message_to_dict(message, *args, **kwargs):
    if hasattr(message, "model_dump"):
        return message.model_dump()
    elif hasattr(message, "dict"):
        return message.dict()
    elif isinstance(message, dict):
        return message
    return original_message_to_dict(message, *args, **kwargs)
json_format.MessageToDict = patched_message_to_dict

# STABLE VERSIONS FOR PYTHON 3.13 / A2UI
VERSIONS = [
    "google-adk==1.28.1", "a2a-sdk==0.3.25", "pydantic==2.12.5", 
    "cloudpickle==3.1.2", "protobuf==6.33.6",
    "a2ui-agent-sdk @ git+https://github.com/google/A2UI.git#subdirectory=agent_sdks/python"
]

def main():
    existing_id = os.environ.get("EXISTING_ENGINE_ID")
    vertexai.init(project=os.environ["PROJECT_ID"], location="us-central1", staging_bucket=os.environ["BUCKET"])
    client = vertexai.Client(project=os.environ["PROJECT_ID"], location="us-central1")
    
    # ... create agent card ...
    
    a2a_agent = A2aAgent(agent_card=my_card, agent_executor_builder=AdkAgentToA2AExecutor)
    config = {
        "requirements": VERSIONS, 
        "extra_packages": ["agent_executor.py", "agent.py", "tools.py"]
    }

    if existing_id:
        name = f"projects/{os.environ['PROJECT_ID']}/locations/us-central1/reasoningEngines/{existing_id}"
        remote = client.agent_engines.update(name=name, agent=a2a_agent, config=config)
    else:
        remote = client.agent_engines.create(agent=a2a_agent, config=config)
    
    print(f"Deploy complete: {remote.name}")

if __name__ == "__main__":
    main()
```

