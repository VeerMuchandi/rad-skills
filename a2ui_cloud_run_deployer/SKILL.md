---
name: A2UI Cloud Run Deployer
description: Deploys an A2UI ADK agent cleanly to Google Cloud Run in namespaced A2A-compatibility mode.
---

# A2UI Cloud Run Deployer Skill

This skill automates clean container packaging, compilation (via Cloud Build), and namespaced A2A deployments of A2UI agents to Google Cloud Run.

### Protocol & Preferred Transport
* **Default Preferred Transport**: `JSONRPC` (`preferred_transport=types.TransportProtocol.jsonrpc` or `"preferredTransport": "JSONRPC"`).
* **Protocol Standard**: A2A / JSON-RPC 2.0 (`message/send`).

## Required Agent Wiring for `adk api_server` (Cloud Run)

The standard `adk api_server` command defaults to a standard text-only executor. To enable rich A2UI rendering on Cloud Run, the agent must implement the following three configurations:

### 1. Automatic Startup Patching via `sitecustomize.py` (MANDATORY)
Because `adk api_server` in Cloud Run imports `A2aAgentExecutor` before loading any agent modules, trying to monkey-patch inside `agent.py` is too late. The agent folder MUST include a `sitecustomize.py` file to automatically patch `A2aAgentExecutor.execute` during Python interpreter startup:

```python
"""sitecustomize module to automatically patch ADK's A2aAgentExecutor on startup."""
import logging
import sys

logger = logging.getLogger(__name__)

try:
    import google.adk.a2a.executor.a2a_agent_executor as a2a_executor_mod
    try:
        from . import agent_executor
    except (ImportError, ValueError):
        import agent_executor

    a2a_executor_mod.A2aAgentExecutor.execute = agent_executor.a2ui_execute
    print("[A2UI-STARTUP] Successfully patched A2aAgentExecutor.execute on startup in sitecustomize.py", file=sys.stderr)
except Exception as e:
    print(f"[A2UI-STARTUP] Failed to patch A2aAgentExecutor in sitecustomize.py: {e}", file=sys.stderr)
```

### 2. `agent_executor.py` Constructor Update
Ensure the custom executor's `__init__` gracefully accepts `*args` and `**kwargs` passed down by `adk api_server`, pulling the instantiated runner from `kwargs`:
```python
class AdkAgentToA2AExecutor(agent_execution.AgentExecutor):
    def __init__(self, *args, **kwargs):
        self._runner = kwargs.get('runner')
        if not self._runner:
            self._runner = runners.Runner(
                app_name="A2UIAgent",
                agent=root_agent,
                session_service=in_memory_session_service.InMemorySessionService(),
                auto_create_session=True,
            )
```

### 3. Container `PYTHONPATH`
When building the Docker container, ensure the directory containing the agent is explicitly added to `PYTHONPATH` so that the monkey-patch can successfully resolve `import agent_executor`:
```dockerfile
ENV PYTHONPATH="/app/agents/{agent_name}:$PYTHONPATH"
```
*(Handled automatically by `deploy_a2ui.py`)*

## Instructions

When this skill is triggered, you must execute the following steps in sequence:

### Step 1: Input Collection & Verification
Ask the user for the following deployment variables:
*   `GCP_PROJECT_ID`: The Google Cloud Project ID.
*   `GCP_REGION`: The deployment region (defaults to `us-central1` if empty).
*   `AGENT_DIR`: The path to the target agent folder in the workspace.
*   `SERVICE_NAME`: The Cloud Run service name (defaults to the agent folder name).

### Step 2: Clean Staging & Deployment Execution
Run the helper deployment script located in this skill's scripts directory:
```bash
python3 .agents/skills/a2ui_cloud_run_deployer/scripts/deploy_a2ui.py \
  --project <GCP_PROJECT_ID> \
  --region <GCP_REGION> \
  --agent_dir <AGENT_DIR> \
  --service_name <SERVICE_NAME>
```

### Step 3: Verify the Deployment
Once the deployment script outputs success:
1.  **Retrieve Agent Card**: Query the Agent Card URL via `curl` to verify availability:
    ```bash
    curl -s https://<service-url>/a2a/<agent_name>/.well-known/agent-card.json
    ```
2.  **Verify Agent Execution**: Send a basic JSON-RPC 2.0 test message to ensure the agent is responsive:
    ```bash
    curl -X POST \
      -H "Content-Type: application/json" \
      -d '{"jsonrpc": "2.0", "method": "message/send", "params": {"message": {"role": "user", "parts": [{"text": "Hello"}], "messageId": "test-msg-id", "contextId": "test-session-id"}}, "id": 1}' \
      https://<service-url>/a2a/<agent_name>
    ```

### Step 4: Display Output Endpoints
Print a clean summary displaying the final endpoints:
*   **Service URL**: `https://<service-url>`
*   **Namespaced A2A RPC URL**: `https://<service-url>/a2a/<agent_name>`
*   **Agent Card Endpoint**: `https://<service-url>/a2a/<agent_name>/.well-known/agent-card.json`
