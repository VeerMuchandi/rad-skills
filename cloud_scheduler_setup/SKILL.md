---
name: Cloud Scheduler Setup
description: Provisions a scheduled Cloud Scheduler job with secure OIDC token authentication to invoke HTTP targets (such as Reasoning Engine endpoints) using Terraform.
mode: manual
---

# Cloud Scheduler Setup Skill

This skill allows you to easily provision a scheduled cron job using Cloud Scheduler on Google Cloud Platform via Terraform. It automatically enables required APIs, configures a secure HTTP target call, and hooks up secure OIDC token authentication using a specified service account to allow triggering private endpoints (like Vertex AI Reasoning Engines).

## Prerequisites
- **Terraform Version**: `v1.5+` (Recommended `v1.14+`)
- **GCP Project**: Active Google Cloud Project with billing enabled.
- **Permissions**:
    - `roles/cloudscheduler.admin` (to manage Cloud Scheduler)
    - `roles/serviceusage.serviceUsageConsumer` (to enable services)
    - The target Service Account must have `roles/iam.serviceAccountUser` assigned or be callable by the scheduler.

## Skill Directory Structure
```text
cloud_scheduler_setup/
├── SKILL.md                 # This instructions file
├── resources/
│   └── templates/
│       ├── main.tf          # Core Cloud Scheduler resources
│       ├── variables.tf     # Customizable variables
│       └── outputs.tf       # Job name and state outputs
└── scripts/
    └── deploy_scheduler.py  # Helper Python script to orchestrate deployment
```

## 1. How to Use this Skill (Step-by-Step)

### Step 1: Initialize the Deployment Workspace
Create a dedicated deployment directory outside your agent code package to prevent Terraform state/binaries from being packaged with the agent.

```bash
mkdir -p deploy_scheduler
```

### Step 2: Copy the Templates
Copy the templates from this skill to your new `deploy_scheduler` folder.
*(Note: Replace `<path_to_skill>` with the path of this skill folder, e.g. `skills/cloud_scheduler_setup`)*

```bash
cp -r <path_to_skill>/resources/templates/* deploy_scheduler/
```

### Step 3: Configure Deployment (`deploy_scheduler/terraform.tfvars`)
Create a file named `deploy_scheduler/terraform.tfvars` and set the following parameters:

```hcl
project_id            = "your-gcp-project-id"
region                = "us-central1"
job_name              = "my-daily-agent-trigger"
schedule              = "0 9 * * *" # Daily at 9:00 AM
time_zone             = "America/New_York"
target_uri            = "https://us-central1-aiplatform.googleapis.com/v1/projects/your-gcp-project-id/locations/us-central1/reasoningEngines/your-engine-id:streamQuery"
http_method           = "POST"
body                  = "{\"class_method\": \"stream_query\", \"input\": {\"message\": \"Process daily sales data\"}}"
service_account_email = "your-agent-service-account@your-gcp-project-id.iam.gserviceaccount.com"
```

### Step 4: Run Terraform
Navigate to the `deploy_scheduler` directory, initialize, and deploy the resources:

```bash
cd deploy_scheduler
terraform init
terraform apply -auto-approve
```

### Step 5: Capture Output
Upon successful completion, Terraform outputs the created job ID and state:
```hcl
job_id    = "projects/your-project/locations/us-central1/jobs/my-daily-agent-trigger"
job_state = "ENABLED"
```

---

### Option B: Using the Orchestration Helper Script (Recommended)
You can automate the deployment in a single step using the helper Python script.

Run the script:
```bash
python3 <path_to_skill>/scripts/deploy_scheduler.py \
  --project "your-gcp-project-id" \
  --job-name "my-daily-agent-trigger" \
  --schedule "0 9 * * *" \
  --target-uri "https://us-central1-aiplatform.googleapis.com/v1/projects/your-project/locations/us-central1/reasoningEngines/your-engine-id:streamQuery" \
  --service-account "your-service-account@your-project.iam.gserviceaccount.com" \
  --body "{\"class_method\": \"stream_query\", \"input\": {\"message\": \"Process daily sales data\"}}" \
  --work-dir "deploy_scheduler"
```

To destroy the job later:
```bash
python3 <path_to_skill>/scripts/deploy_scheduler.py \
  --project "your-gcp-project-id" \
  --job-name "my-daily-agent-trigger" \
  --schedule "0 9 * * *" \
  --target-uri "https://us-central1-aiplatform.googleapis.com/v1/projects/your-project/locations/us-central1/reasoningEngines/your-engine-id:streamQuery" \
  --service-account "your-service-account@your-project.iam.gserviceaccount.com" \
  --work-dir "deploy_scheduler" \
  --destroy
```

---

## 2. Best Practices & Security
- **OIDC Token Auth**: Always specify a service account with the minimal roles required to call the target endpoint (e.g. `roles/aiplatform.user` for Vertex AI Agent Engine).
- **Deadlines**: The default deadline is set to `320s` to accommodate longer-running Reasoning Engine tasks (e.g. processing large GCS datasets or running database migrations).
