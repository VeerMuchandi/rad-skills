terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  type        = string
  description = "The GCP Project ID"
}

variable "region" {
  type        = string
  description = "The GCP Region"
  default     = "us-central1"
}

variable "marketplace_topic" {
  type        = string
  description = "The Google-managed Marketplace Pub/Sub topic (provided by Google)"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# --- Service Account for Cloud Run ---
resource "google_service_account" "dcr_runner" {
  account_id   = "dcr-runner"
  display_name = "DCR & Procurement Webhook Runner"
}

# --- Firestore Database ---
resource "google_firestore_database" "database" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
}

# --- Secret Manager Secret for Okta Token ---
resource "google_secret_manager_secret" "okta_token" {
  secret_id = "okta-api-token"

  replication {
    auto {}
  }
}

# Grant Service Account access to the Okta Token secret
resource "google_secret_manager_secret_iam_member" "okta_token_accessor" {
  secret_id = google_secret_manager_secret.okta_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.dcr_runner.email}"
}

# Grant Service Account access to Firestore
resource "google_project_iam_member" "firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.dcr_runner.email}"
}

# Grant Service Account access to Procurement API
resource "google_project_iam_member" "procurement_agent" {
  project = var.project_id
  role    = "roles/commerceplatform.procurementServiceAgent"
  member  = "serviceAccount:${google_service_account.dcr_runner.email}"
}

# --- Pub/Sub Subscription ---
# This subscription connects to the Google-managed topic and pushes to Cloud Run
resource "google_pubsub_subscription" "marketplace_sub" {
  name  = "gcp-marketplace-entitlements-sub"
  topic = var.marketplace_topic

  # Retain messages for 7 days
  message_retention_duration = "604800s"

  # Push configuration (configured after Cloud Run is deployed)
  # In a real TF flow, we might deploy Cloud Run first. For simplicity in the skill,
  # the Cloud Run URL can be passed or updated.
  push_config {
    push_endpoint = "https://placeholder-url/dcr" # Updated by the deploy script

    oidc_token {
      service_account_email = google_service_account.dcr_runner.email
    }
  }

  expiration_policy {
    ttl = "" # Never expire
  }
}

output "service_account_email" {
  value = google_service_account.dcr_runner.email
}
