terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable Cloud Scheduler API if not already enabled
resource "google_project_service" "scheduler" {
  project            = var.project_id
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}

# Create the Cloud Scheduler Job with OIDC token auth
resource "google_cloud_scheduler_job" "job" {
  name             = var.job_name
  project          = var.project_id
  region           = var.region
  schedule         = var.schedule
  time_zone        = var.time_zone
  attempt_deadline = "320s" # Reasoning Engines can take a few minutes if running cold start/large GCS operations

  http_target {
    uri         = var.target_uri
    http_method = var.http_method
    body        = var.body != "" ? base64encode(var.body) : null
    
    headers = {
      "Content-Type" = "application/json"
    }

    dynamic "oauth_token" {
      for_each = var.auth_type == "OAUTH" ? [1] : []
      content {
        service_account_email = var.service_account_email
        scope                 = var.oauth_scope
      }
    }

    dynamic "oidc_token" {
      for_each = var.auth_type == "OIDC" ? [1] : []
      content {
        service_account_email = var.service_account_email
        audience              = var.audience != null ? var.audience : var.target_uri
      }
    }
  }

  depends_on = [google_project_service.scheduler]
}
