---
name: A2UI Remote Tester
description: Specialized role for testing A2UI agents deployed on Vertex AI Agent Engine using a local proxy server.
mode: manual
---

# A2UI Remote Tester Skill

You are the **A2UI Remote Tester**. Your primary responsibility is to verify that A2UI agents deployed on Vertex AI Agent Engine (Google Agent Runtime) function correctly, handle sessions properly, and respond to protocol requests using an interactive mock client.

This skill provides patterns and templates for setting up a remote testing harness, which involves running a local proxy server that forwards A2A requests to the deployed agent endpoint, while serving the interactive mock client locally.

## Core Responsibilities
1. **Proxy Server Setup**: Create a local server (e.g., using FastAPI) that forwards requests to the remote Agent Engine instance.
2. **A2A Protocol Bridge**: Handle JSON-RPC 2.0 requests from the client and translate them to the format expected by the Agent Engine API.
3. **UI Rendering Verification**: Use the mock client to verify component rendering and interaction flow with the live remote agent.

## Implementation Guide

### Step 1: Create a Remote Tester Sub-folder
Create a folder named `remote_tester` directly under the agent's root directory. Copy the `index.html` file from your `local_tester` folder into this new folder, and update the heading in it to `<h1>A2UI Remote Tester</h1>` and the title to `<title>A2UI Remote Tester</title>` to distinguish it from the local tester.

### Step 2: Implement the Proxy Server
Create a Python script (e.g., `proxy_server.py`) inside the `remote_tester` folder.

Here is the complete template for `proxy_server.py`:

```python
import os
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import logging
import requests
import time
from google.auth import default
from google.auth.transport.requests import Request as AuthRequest

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Configure these for your deployed agent
PROJECT_ID = "your-project-id"
LOCATION = "us-central1"
ENGINE_ID = "your-engine-id"

def get_bearer_token():
    credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(AuthRequest())
    return credentials.token

@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    token = get_bearer_token()
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}/a2a/v1/card"
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers)
    return res.json()

@app.get("/")
async def get_index():
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"))

@app.post("/jsonrpc")
async def handle_jsonrpc(request: Request):
    body = await request.json()
    logger.info(f"Received JSON-RPC request: {body}")
    
    if body.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": body.get("id")}
        
    method = body.get("method")
    params = body.get("params", {})
    request_id = body.get("id")
    
    if method == "message/send":
        message = params.get("message", {})
        
        token = get_bearer_token()
        url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}/a2a/v1/message:send"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # Translate client payload to standard A2A Message format
        a2a_parts = []
        if "text" in message and message["text"]:
            a2a_parts.append({"text": message["text"]})
        if "parts" in message:
            for part in message["parts"]:
                a2a_part = {}
                if "data" in part:
                    a2a_part["data"] = {"data": part["data"]}
                if "metadata" in part:
                    a2a_part["metadata"] = part["metadata"]
                if "text" in part:
                    a2a_part["text"] = part["text"]
                a2a_parts.append(a2a_part)
        
        a2a_message = {
            "role": "ROLE_USER",
            "content": a2a_parts
        }
        
        payload = {"message": a2a_message}
        
        logger.info(f"Forwarding to remote agent: {url}")
        res = requests.post(url, headers=headers, json=payload)
        
        if res.status_code != 200:
            return {"jsonrpc": "2.0", "error": {"code": res.status_code, "message": res.text}, "id": request_id}
            
        remote_response = res.json()
        task_id = remote_response.get("task", {}).get("id")
        
        if task_id:
            logger.info(f"Polling Task {task_id}...")
            task_url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}/a2a/v1/tasks/{task_id}"
            
            for _ in range(90):
                time.sleep(2)
                task_res = requests.get(task_url, headers=headers)
                if task_res.status_code == 404:
                    logger.warning("Task status returned 404 (not found). Syncing replica, retrying...")
                    continue
                if task_res.status_code == 200:
                    task_data = task_res.json()
                    state = task_data.get("status", {}).get("state")
                    
                    if state == "TASK_STATE_SUCCEEDED" or state == "TASK_STATE_COMPLETED":
                        artifacts = task_data.get("artifacts", [])
                        # Load schema
                        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_to_client_with_standard_catalog.json")
                        schema = None
                        if os.path.exists(schema_path):
                            try:
                                with open(schema_path, "r") as f:
                                    schema = json.load(f)
                            except Exception as e:
                                logger.error(f"Failed to load schema from {schema_path}: {e}")

                        parts = []
                        if artifacts:
                            parts = artifacts[0].get("parts", [])
                            # Clean nested data fields in A2UI parts if needed
                            for part in parts:
                                if "data" in part and part.get("metadata", {}).get("mimeType") == "application/json+a2ui":
                                    data_field = part["data"]
                                    if isinstance(data_field, dict) and "data" in data_field:
                                        part["data"] = data_field["data"]
                                    
                                    # Validate data_field against schema
                                    if schema:
                                        try:
                                            import jsonschema
                                            jsonschema.validate(instance=part["data"], schema=schema)
                                            logger.info("A2UI payload part successfully validated against schema.")
                                        except jsonschema.ValidationError as e:
                                            logger.critical(f"A2UI STRICT SCHEMA VALIDATION FAILED: {e.message}")
                                            logger.critical(f"Invalid Message: {json.dumps(part['data'], indent=2)}")
                                            raise ValueError(f"A2UI Schema Validation Error: {e.message}") from e
                            
                        return {
                            "jsonrpc": "2.0",
                            "result": {
                                "message": {
                                    "parts": parts
                                }
                            },
                            "id": request_id
                        }
                    elif state == "TASK_STATE_FAILED":
                        return {"jsonrpc": "2.0", "error": {"code": 500, "message": "Task failed on remote agent"}, "id": request_id}
                
            return {"jsonrpc": "2.0", "error": {"code": 504, "message": "Task timeout on remote agent"}, "id": request_id}
        else:
            return {"jsonrpc": "2.0", "error": {"code": 500, "message": "No task ID returned from remote agent"}, "id": request_id}
        
    return {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": request_id}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Step 3: Run the Proxy Server
```bash
cd remote_tester
python3 proxy_server.py
```

### Step 4: Test in Browser
Open the local URL (e.g., `http://localhost:8000`) in your browser.

## Best Practices
*   **Keep it Separate**: Do not import local tester code in your core agent files.
*   **Mocking**: If the agent relies on Gemini Enterprise specific features (like user identity or specific datastores), mock them in the local server or executor bridge.

## 🚨 Lessons Learned & Troubleshooting

### 1. Unified Origin for Remote Environments
*   **The Problem**: Serving the mock client (port 8080) and the API (port 8000) on different ports causes CORS preflight (OPTIONS) requests. In remote SSH environments using proxies (like Google's ÜberProxy), these preflight requests may be redirected to SSO login pages, which browsers block, causing fetch failures.
*   **The Solution**: **Serve the mock client directly from the FastAPI server** at the root `/` endpoint. This puts both on the same origin (e.g., `http://vmps.c.googlers.com:8000/`) and avoids CORS issues entirely.

### 2. Reliable Automation of Dropdowns (MultipleChoice)
*   **The Problem**: Simulating key presses on `<select>` elements in the mock client may not reliably trigger the `onchange` event, resulting in empty values being sent in the action context.
*   **The Solution**: Use `execute_browser_javascript` to set the value of the dropdown directly and manually dispatch a change event:
```javascript
const select = document.getElementById('your_component_id_select');
select.value = 'desired_value';
select.dispatchEvent(new Event('change'));
```

### 3. Stateless Task Polling Resilience
*   **The Problem**: In scaled serverless fleets, task requests may route to container replicas that are still syncing or have not yet registered the task ID, leading to transient `404 Not Found` responses from the `/tasks/{task_id}` endpoint.
*   **The Solution**: Treat a `404` status code from the task endpoint as a transient working state and continue the polling retry loop. Do not crash or abort the loop on a single non-200 check unless a terminal state (`TASK_STATE_FAILED`) is explicitly returned or the retry limit (e.g., 90 checks/180s) is exhausted.

