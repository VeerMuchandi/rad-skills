---
name: ADK Gemini Enterprise Datastore Connector
description: Skill for connecting ADK agents to Gemini Enterprise connected data sources with secure user-level access control.
---

# Instructions

This skill provides guidelines and patterns for connecting ADK agents to Gemini Enterprise connected data sources. The primary focus is on secure user-level access control (ACLs) by propagating the user's OAuth token.

## Core Concepts

### 1. User Identity Propagation
When searching an enterprise datastore (e.g., Google Drive, Jira), the agent must respect the calling user's permissions. This is achieved by passing the user's OAuth token directly to the Datastore API (Discovery Engine API).

### 2. Token Retrieval
In the Gemini Enterprise runtime, the user's access token is injected into the agent's session state.
Retrieve the token from the `ToolContext` using the key defined by the environment variable `AUTH_NAME`:

```python
from google.adk.tools import ToolContext

def my_tool(query: str, tool_context: ToolContext):
    auth_name = os.getenv("AUTH_NAME")
    access_token = tool_context.state.get(auth_name)
    # Use access_token in API calls
```

### 3. Local Development Fallback
For local testing where the Gemini Enterprise runtime is not available, fall back to **Application Default Credentials (ADC)**.

```python
from google.auth import default
from google.auth import transport

if access_token:
    # Use retrieved token
else:
    # Fallback to ADC
    creds, project_id = default()
    auth_req = transport.requests.Request()
    creds.refresh(auth_req)
    access_token = creds.token
```

## Implementation Patterns

### Generic Datastore Client
Use a generic client to handle API communication. Do not hardcode specific datastore IDs or project IDs; use environment variables.

See [examples/tools_template.py](./examples/tools_template.py) for a reusable template.

### Agent Integration
Focus this skill on *integrating* the datastore tool. Use the `ADK Developer` skill for general agent building and orchestration.

See [examples/agent_usage.py](./examples/agent_usage.py) for a minimal usage example.

## Design Considerations

### Documenting Testing Differences
When designing an agent that uses this skill, the architect **MUST** include a section in the architecture document detailing the differences between local testing and testing on Gemini Enterprise. This is crucial because the authentication mechanisms differ significantly (ADC vs. Session-injected OAuth tokens), affecting how user permissions (ACLs) are enforced.

Include a table or summary similar to the following in the design:

| Feature | Local Testing | Gemini Enterprise |
| :--- | :--- | :--- |
| **Auth Method** | Application Default Credentials (ADC) | User OAuth Token (Session Injected) |
| **Identity Used** | Developer's identity | Calling End-User's identity |
| **ACL Enforcement** | Based on Developer's access | Based on End-User's access |

### Environment Variables Fallbacks
When retrieving configuration like `PROJECT_ID` and `LOCATION` in your tools, use fallbacks to support both local development and Agent Engine runtime:
```python
project_id = os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
location = os.getenv("LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION")
```
Note that `GOOGLE_CLOUD_PROJECT` is reserved in Agent Engine and cannot be set manually in the environment variables block of the deployment config.

### Prompt Engineering for Search
When instructing the agent to use the datastore search tool, ensure it handles relative or temporal queries (like 'last', 'latest', 'recent') gracefully. Keyword search engines might not understand these terms directly. Instruct the agent to:
1. Try searching with a broad query or keywords related to the topic instead of refusing to answer immediately.
2. Analyze the results to identify the most relevant or recent documents if date information is available.
3. Avoid early refusal when specific keywords are not provided.

## Deployment Considerations

### Terraform Deployment (Preferred)
For production deployments, it is recommended to use the generalized Terraform approach documented in the `Agent Engine Terraform Deployer` skill. This ensures reproducible deployments and proper management of infrastructure state.

### Gemini Enterprise Registration
Use the `Gemini Enterprise Agent Registrar` skill to perform the registration and handle OAuth setup. When constructing the registration payload, ensure that:
1.  An Authorization Resource is created for the OAuth flow to propagate the user's token.
2.  The `authorizationConfig` in the registration payload uses the numeric `PROJECT_NUMBER` instead of the `PROJECT_ID`.
3.  Verify if the data source requires additional OAuth scopes beyond `cloud-platform` (e.g., for real-time federation to third-party systems like Jira or Workspace apps like Google Drive).
