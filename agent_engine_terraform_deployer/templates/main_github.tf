variable "agent_package_name" {
  description = "The name of the Python package to create from the GitHub repo"
  type        = string
  default     = "my_agent"
}

variable "github_repo" {
  description = "The GitHub repository (format: owner/repo)"
  type        = string
}

variable "github_branch" {
  description = "The branch to deploy"
  type        = string
  default     = "main"
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

# 1. Remote Packaging & Wrapper Creation
data "external" "agent_packer" {
  program = ["bash", "-c", <<EOT
    set -e
    eval "$(jq -r '@sh "PACKAGE_NAME=\(.agent_package_name) REPO=\(.github_repo) BRANCH=\(.github_branch)"')"
    
    ASSETS_DIR="assets"
    TEMP_DIR="temp_source"
    ARCHIVE_PATH="$ASSETS_DIR/source.tar.gz"
    
    mkdir -p "$ASSETS_DIR"
    rm -rf "$TEMP_DIR"
    mkdir -p "$TEMP_DIR/$PACKAGE_NAME"

    # Fetch source from GitHub
    curl -L "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" -o "repo.tar.gz"

    # Extract directly into the package directory
    tar -xzf repo.tar.gz -C "$TEMP_DIR/$PACKAGE_NAME" --strip-components=1

    # Create the non-intrusive wrapper
    cat <<EOF > "$TEMP_DIR/$PACKAGE_NAME/app.py"
from vertexai.agent_engines import AdkApp
from .agent import root_agent
agent = AdkApp(agent=root_agent)
EOF

    # Create the slim archive
    tar -czf "$ARCHIVE_PATH" -C "$TEMP_DIR" "$PACKAGE_NAME/"

    echo '{"status": "ready", "archive_size": "'$(du -sh $ARCHIVE_PATH | cut -f1)'"}'
  EOT
  ]

  query = {
    agent_package_name = var.agent_package_name
    github_repo         = var.github_repo
    github_branch       = var.github_branch
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
      entrypoint_module = "${var.agent_package_name}.app"
      entrypoint_object = "agent"
      requirements_path = "${var.agent_package_name}/requirements.txt"
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
