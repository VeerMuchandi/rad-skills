---
name: A2UI Cloud Run Deployer
description: Deploys an A2UI ADK agent cleanly to Google Cloud Run in namespaced A2A-compatibility mode.
---

# A2UI Cloud Run Deployer Skill

This skill automates clean container packaging, compilation (via Cloud Build), and namespaced A2A deployments of A2UI agents to Google Cloud Run.

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
