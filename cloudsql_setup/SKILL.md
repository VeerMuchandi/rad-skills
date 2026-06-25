---
name: Cloud SQL Setup
description: Provisions a PostgreSQL Cloud SQL instance, database, database user, and registers connection details in Secret Manager using Terraform.
mode: manual
---

# Cloud SQL Setup Skill

This skill allows you to easily provision a PostgreSQL database on Google Cloud Platform using Terraform. It automatically enables required APIs, configures a secure database instance, creates a database and a user with a secure auto-generated password, and registers all connection parameters in Secret Manager for use by ADK agents.

## Prerequisites
- **Terraform Version**: `v1.5+` (Recommended `v1.14+`)
- **GCP Project**: Active Google Cloud Project with billing enabled.
- **Permissions**:
    - `roles/sqladmin.admin` (to manage Cloud SQL)
    - `roles/secretmanager.admin` (to manage secrets)
    - `roles/serviceusage.serviceUsageConsumer` (to enable services)

## Skill Directory Structure
```text
cloudsql_setup/
├── SKILL.md                 # This instructions file
├── resources/
│   └── templates/
│       ├── main.tf          # Core Terraform resources
│       ├── variables.tf     # Customizable variables
│       └── outputs.tf       # Secret IDs and Connection Name outputs
└── scripts/
    └── deploy_db.py         # Helper Python script to orchestrate deployment
```

## 1. How to Use this Skill (Step-by-Step)

### Step 1: Initialize the Deployment Workspace
Create a dedicated deployment directory outside your agent code package to prevent Terraform state/binaries from being packaged with the agent.

```bash
mkdir -p deploy_db
```

### Step 2: Copy the Templates
Copy the templates from this skill to your new `deploy_db` folder.
*(Note: Replace `<path_to_skill>` with the path of this skill folder, e.g. `skills/cloudsql_setup` or `~/.gemini/config/skills/cloudsql_setup`)*

```bash
cp -r <path_to_skill>/resources/templates/* deploy_db/
```

### Step 3: Configure Deployment (`deploy_db/terraform.tfvars`)
Create a file named `deploy_db/terraform.tfvars` and set the following parameters:

```hcl
project_id           = "your-gcp-project-id"
region               = "us-central1"
instance_name_prefix = "my-adk-db"
database_flavor      = "postgres"      # or "mysql"
database_version     = "POSTGRES_15"   # or "MYSQL_8_0"
database_name        = "my_agent_db"
db_username          = "db_user"
secret_prefix        = "my_agent_" # secrets will be created with prefix: my_agent_
deletion_protection  = false        # Set to true for production database
```

### Step 4: Run Terraform
Navigate to the `deploy_db` directory, initialize, and deploy the resources:

```bash
cd deploy_db
terraform init
terraform apply -auto-approve
```

### Step 5: Capture Output
Upon successful completion, Terraform outputs the connection details and Secret Manager secret IDs:
```hcl
connection_name = "your-project:us-central1:my-adk-db-xxxx"
secret_ids = {
  db_connection_name = "my_agent_db_connection_name"
  db_name            = "my_agent_db_name"
  db_password        = "my_agent_db_password"
  db_user            = "my_agent_db_user"
}
```

### Option B: Using the Orchestration Helper Script (Recommended)
You can automate the deployment, secrets creation, and database schema initialization in a single step using the helper Python script.

1. **Create Schema File** (e.g. `schema.sql`):
   ```sql
   CREATE TABLE IF NOT EXISTS items (
     id SERIAL PRIMARY KEY,
     name VARCHAR(100) NOT NULL,
     description TEXT
   );
   ```

2. **Run the Script**:
   ```bash
   python3 <path_to_skill>/scripts/deploy_db.py \
     --project "your-gcp-project-id" \
     --sql-file "schema.sql"
   ```

This script will run the Terraform deployment and then connect to the Cloud SQL instance over secure IAM-auth using the Python connector to execute the statements in your SQL file.

---

## 2. Connecting ADK Agent to Cloud SQL
To use the newly created database in your ADK agent:

1. **Add Dependencies**: Include these in your agent's `requirements.txt`:
   ```text
   cloud-sql-python-connector[pg8000]
   SQLAlchemy
   google-cloud-secret-manager
   ```
2. **Access Secrets in Agent**: Refer to the `secret_ids` generated. Set environment variables on the deployed agent containing the secret IDs, and use the Cloud SQL Python Connector library to access the database.

---

## 3. Troubleshooting & Learnings

### 3.1. PostgreSQL User Deletion (`cannot be dropped because some objects depend on it`)
- **The Issue**: When running `--destroy` (or `terraform destroy`), if you populated the database (created tables, sequences, etc.) using that user, PostgreSQL will block dropping the user because of these dependent objects.
- **The Workaround**: Simply re-run the destroy command. Since the database itself was already deleted during the first run, the user's dependencies are resolved and the second run will complete cleanly.
