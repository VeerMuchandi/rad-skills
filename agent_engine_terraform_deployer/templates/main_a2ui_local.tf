variable "agent_folder_name" {
  description = "The name of the folder containing the agent code (e.g., phone_plan_shopper_a2ui)"
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

locals {
  registration_payload = jsondecode(file("../registration_payload.json"))
  agent_card_json      = local.registration_payload.a2aAgentDefinition.jsonAgentCard
}

# 1. Automated Packaging & Wrapper Creation (Runs during 'terraform plan')
data "external" "agent_packer" {
  program = ["bash", "-c", <<EOT
    set -e
    # Extract agent_folder_name from the JSON input provided by Terraform
    eval "$(jq -r '@sh "AGENT_FOLDER_NAME=\(.agent_folder_name)"')"
    
    AGENT_DIR="../$AGENT_FOLDER_NAME"
    ASSETS_DIR="assets"
    ARCHIVE_PATH="$ASSETS_DIR/source.tar.gz"
    WRAPPER_PATH="$AGENT_DIR/agent_wrapper.py"
    
    mkdir -p "$ASSETS_DIR"

    # Create the non-intrusive wrapper agent_wrapper.py
    cat <<'EOF' > "$WRAPPER_PATH"
import os
import json
import google.cloud.aiplatform as aiplatform
from vertexai.preview.reasoning_engines import A2aAgent
from a2a.types import AgentCard

# Auto-resolve correct import for the executor module
try:
    import agent_executor
except ImportError:
    from . import agent_executor

# Initialize Vertex AI to prevent project resolution failures
project_id = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
if project_id:
    aiplatform.init(project=project_id)
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id

# Load agent card from registration payload
current_dir = os.path.dirname(os.path.abspath(__file__))
payload_path = os.path.join(current_dir, "registration_payload.json")
with open(payload_path, "r") as f:
    payload = json.load(f)
    card_data = json.loads(payload["a2aAgentDefinition"]["jsonAgentCard"])
    agent_card = AgentCard(**card_data)

agent = A2aAgent(
    agent_card=agent_card,
    agent_executor_builder=agent_executor.AdkAgentToA2AExecutor,
)
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
    class_methods = [
      {
        name           = "on_message_send"
        api_mode       = "a2a_extension"
        a2a_agent_card = local.agent_card_json
        parameters = {
          type = "object"
          properties = {}
          required = ["request", "context"]
        }
      },
      {
        name           = "on_get_task"
        api_mode       = "a2a_extension"
        a2a_agent_card = local.agent_card_json
        parameters = {
          type = "object"
          properties = {}
          required = ["request", "context"]
        }
      },
      {
        name           = "on_cancel_task"
        api_mode       = "a2a_extension"
        a2a_agent_card = local.agent_card_json
        parameters = {
          type = "object"
          properties = {}
          required = ["request", "context"]
        }
      },
      {
        name           = "handle_authenticated_agent_card"
        api_mode       = "a2a_extension"
        a2a_agent_card = local.agent_card_json
        parameters = {
          type = "object"
          properties = {}
          required = ["request", "context"]
        }
      }
    ]
    environment_variables = {
      PROJECT_ID                                         = var.project_id
      LOCATION                                           = var.region
      GOOGLE_GENAI_USE_VERTEXAI                          = "1"
      GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY          = "true"
      OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = "true"
      NUM_WORKERS                                        = "1"
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
      entrypoint_module = "${var.agent_folder_name}.agent_wrapper"
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
