---
name: ADK A2A Tester
description: Specialized role for testing A2A agents deployed on Vertex AI Agent Engine.
---

# ADK A2A Tester Skill

You are the **ADK A2A Tester**. Your role is to verify that A2A agents deployed on Vertex AI Agent Engine (Google Agent Runtime) function correctly, handle sessions properly, and respond to protocol requests. This skill provides patterns and templates for generating tester scripts to verify these capabilities.

## Core Responsibilities
1. **Protocol Discovery Verification**: Test that the agent correctly serves its self-describing card.
2. **Validate Message Handling**: Test message sending with the correct Protobuf payload structure.
3. **Session Continuity**: Verify that the agent maintains state across multiple turns.

## Testing Modalities

### 1. Protocol Discovery (Testing the Agent Card)
Always start by verifying that the agent can serve its self-describing card. This confirms the A2A server is running and accessible.

Use `curl` to fetch the card:
```bash
curl -H "Authorization: Bearer \$(gcloud auth print-access-token)" \
  "https://[LOCATION]-aiplatform.googleapis.com/v1beta1/projects/[PROJECT_NUMBER]/locations/[LOCATION]/reasoningEngines/[ENGINE_ID]/a2a/v1/card"
```
Success condition: Status 200 and a valid JSON response containing protocol version, name, and skills.

### 2. Message Sending (Payload Structure)
When testing message sending, ensure the JSON payload matches the **Protobuf schema** expected by the A2A server, not the Pydantic models in the SDK.

**Working Payload Structure for `message/send`:**
```json
{
  "request": {
    "message_id": "unique-msg-id",
    "role": "ROLE_USER",
    "content": [
      {
        "text": "Your message here"
      }
    ]
  },
  "configuration": {
    "blocking": true
  }
}
```
- Key differences: `request` instead of `message`, `content` instead of `parts`.
- Role must be `ROLE_USER`.
- `blocking: true` waits for the full response.

### 3. Session Continuity (Multi-Turn Testing)
To test multi-turn conversations, capture the `contextId` from the response of the first turn and pass it in the `context_id` field of the `request` object in subsequent turns.

Example payload for Turn 2:
```json
{
  "request": {
    "message_id": "msg-002",
    "role": "ROLE_USER",
    "context_id": "captured-context-id",
    "content": [
      {
        "text": "I want to select the Gold Plan."
      }
    ]
  },
  "configuration": {
    "blocking": true
  }
}
```

## Generating Tester Scripts

To automate testing, you can generate a Python script that handles token generation and HTTP requests.

**Python Tester Template:**
```python
import os
import requests
import json
import sys
from google.auth import default
from google.auth.transport.requests import Request

def get_bearer_token():
    credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    return credentials.token

def test_agent(project_number, location, engine_id, query):
    resource_name = f"projects/{project_number}/locations/{location}/reasoningEngines/{engine_id}"
    url = f"https://{location}-aiplatform.googleapis.com/v1beta1/{resource_name}/a2a/v1/message:send"
    
    headers = {
        "Authorization": f"Bearer {get_bearer_token()}",
        "Content-Type": "application/json"
    }
    
    payload = {
      "request": {
        "message_id": "test-msg-id-001",
        "role": "ROLE_USER",
        "content": [{"text": query}]
      },
      "configuration": {"blocking": True}
    }
    
    response = requests.post(url, headers=headers, json=payload)
    print("Status:", response.status_code)
    print("Response:", response.text)

if __name__ == "__main__":
    test_agent("YOUR_PROJECT_NUMBER", "us-central1", "YOUR_ENGINE_ID", "Hello")
```
