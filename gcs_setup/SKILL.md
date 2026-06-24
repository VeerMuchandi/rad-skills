---
name: GCS Setup
description: Provisions one or more Google Cloud Storage buckets with secure uniform bucket-level access and public access prevention using Terraform.
mode: manual
---

# GCS Setup Skill

This skill allows you to easily provision one or more Google Cloud Storage (GCS) buckets on Google Cloud Platform using Terraform. It automatically enables required APIs, configures secure uniform bucket-level access, enforces public access prevention, and supports bulk creation.

## Prerequisites
- **Terraform Version**: `v1.5+` (Recommended `v1.14+`)
- **GCP Project**: Active Google Cloud Project with billing enabled.
- **Permissions**:
    - `roles/storage.admin` (to manage GCS buckets)
    - `roles/serviceusage.serviceUsageConsumer` (to enable services)

## Skill Directory Structure
```text
gcs_setup/
├── SKILL.md                 # This instructions file
├── resources/
│   └── templates/
│       ├── main.tf          # Core GCS resources
│       ├── variables.tf     # Customizable variables
│       └── outputs.tf       # Bucket names and URLs outputs
└── scripts/
    └── deploy_gcs.py        # Helper Python script to orchestrate deployment
```

## 1. How to Use this Skill (Step-by-Step)

### Step 1: Initialize the Deployment Workspace
Create a dedicated deployment directory outside your agent code package to prevent Terraform state/binaries from being packaged with the agent.

```bash
mkdir -p deploy_gcs
```

### Step 2: Copy the Templates
Copy the templates from this skill to your new `deploy_gcs` folder.
*(Note: Replace `<path_to_skill>` with the path of this skill folder, e.g. `skills/gcs_setup`)*

```bash
cp -r <path_to_skill>/resources/templates/* deploy_gcs/
```

### Step 3: Configure Deployment (`deploy_gcs/terraform.tfvars`)
Create a file named `deploy_gcs/terraform.tfvars` and set the following parameters:

```hcl
project_id    = "your-gcp-project-id"
region        = "us-central1"
bucket_names  = ["my-source-bucket", "my-archive-bucket", "my-error-bucket"]
force_destroy = true  # Set to false for production to prevent accidental data loss
```

### Step 4: Run Terraform
Navigate to the `deploy_gcs` directory, initialize, and deploy the resources:

```bash
cd deploy_gcs
terraform init
terraform apply -auto-approve
```

### Step 5: Capture Output
Upon successful completion, Terraform outputs the connection details and bucket URLs:
```hcl
bucket_names = [
  "my-source-bucket",
  "my-archive-bucket",
  "my-error-bucket"
]
bucket_urls = {
  "my-source-bucket"  = "gs://my-source-bucket"
  "my-archive-bucket" = "gs://my-archive-bucket"
  "my-error-bucket"   = "gs://my-error-bucket"
}
```

---

### Option B: Using the Orchestration Helper Script (Recommended)
You can automate the deployment and bucket creation in a single step using the helper Python script.

Run the script:
```bash
python3 <path_to_skill>/scripts/deploy_gcs.py \
  --project "your-gcp-project-id" \
  --buckets "my-source-bucket,my-archive-bucket,my-error-bucket" \
  --work-dir "deploy_gcs"
```

To destroy the buckets later:
```bash
python3 <path_to_skill>/scripts/deploy_gcs.py \
  --project "your-gcp-project-id" \
  --buckets "my-source-bucket,my-archive-bucket,my-error-bucket" \
  --work-dir "deploy_gcs" \
  --destroy
```

---

## 2. Best Practices & Security
- **Uniform Bucket-Level Access**: Enabled by default to simplify IAM permissions management.
- **Public Access Prevention**: Set to `enforced` by default to prevent bucket objects from being accidentally exposed to the public internet.
- **Force Destroy**: Set to `true` in development to allow deleting non-empty buckets. **Always set to `false` in production!**
