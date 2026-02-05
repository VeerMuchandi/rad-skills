variable "agent_folder_name" {
  description = "The name of the folder containing the agent code (e.g., epp_telecom_shopper)"
  type        = string
}

variable "agent_engine_name" {
  description = "The display name for the Agent Engine deployment"
  type        = string
}

variable "project_id" {
  description = "The GCP Project ID"
  type        = string
}

variable "region" {
  description = "The GCP Region"
  type        = string
  default     = "us-central1"
}

terraform {
  required_providers {
    google   = { source = "hashicorp/google" }
    external = { source = "hashicorp/external" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Automated Packaging & Wrapper Creation (Runs during 'terraform plan')
data "external" "agent_packer" {
  program = ["bash", "-c", <<EOT
    set -e
    # Extract agent_folder_name from the JSON input provided by Terraform
    eval "$(jq -r '@sh "AGENT_FOLDER_NAME=\(.agent_folder_name)"')"
    
    AGENT_DIR=".."
    ASSETS_DIR="assets"
    ARCHIVE_PATH="$ASSETS_DIR/source.tar.gz"
    WRAPPER_PATH="$AGENT_DIR/app.py"
    
    mkdir -p "$ASSETS_DIR"

    # Create the non-intrusive wrapper app.py
    cat <<EOF > "$WRAPPER_PATH"
from vertexai.agent_engines import AdkApp
from .agent import root_agent
agent = AdkApp(agent=root_agent)
EOF

    # Build the exclusion list from .ae_ignore and add mandatory excludes
    EXCLUDES=""
    # Explicitly exclude the deployment folder and other bulk
    EXCLUDES="$EXCLUDES --exclude=deploy"
    EXCLUDES="$EXCLUDES --exclude=.terraform"
    EXCLUDES="$EXCLUDES --exclude=.adk"
    EXCLUDES="$EXCLUDES --exclude=__pycache__"
    EXCLUDES="$EXCLUDES --exclude=*.zip"
    EXCLUDES="$EXCLUDES --exclude=*.pkl"
    EXCLUDES="$EXCLUDES --exclude=schema.json"
    
    if [ -f "$AGENT_DIR/.ae_ignore" ]; then
      while IFS= read -r line || [ -n "$line" ]; do
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        EXCLUDES="$EXCLUDES --exclude=$line"
      done < "$AGENT_DIR/.ae_ignore"
    fi

    # Create the slim source archive
    tar -czf "$ARCHIVE_PATH" $EXCLUDES -C "$AGENT_DIR/.." "$AGENT_FOLDER_NAME/"

    echo '{"status": "ready", "archive_size": "'$(du -sh $ARCHIVE_PATH | cut -f1)'"}'
  EOT
  ]

  query = {
    agent_folder_name = var.agent_folder_name
  }
}

# 2. Deployment to Agent Engine using Cloud Foundation Fabric module
module "agent_engine" {
  source     = "github.com/GoogleCloudPlatform/cloud-foundation-fabric//modules/agent-engine?ref=v51.0.0"
  name       = var.agent_engine_name
  project_id = var.project_id
  region     = var.region

  agent_engine_config = {
    agent_framework = "google-adk"
    environment_variables = {
      PROJECT_ID                                         = var.project_id
      LOCATION                                           = var.region
      GOOGLE_GENAI_USE_VERTEXAI                          = "1"
      GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY          = "true"
      OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = "true"
    }
  }

  service_account_config = {
    roles = [
      "roles/aiplatform.user",
      "roles/storage.objectViewer",
      "roles/viewer",
      "roles/serviceusage.serviceUsageConsumer",
      "roles/cloudtrace.agent",
    ]
  }

  deployment_files = {
    source_config = {
      source_path       = "assets/source.tar.gz"
      entrypoint_module = "${var.agent_folder_name}.app"
      entrypoint_object = "agent"
      requirements_path = "${var.agent_folder_name}/requirements.txt"
    }
  }

  depends_on = [data.external.agent_packer]
}

output "deployment_info" {
  value = {
    agent_name   = var.agent_engine_name
    archive_size = data.external.agent_packer.result.archive_size
    engine_id    = module.agent_engine.id
  }
}
