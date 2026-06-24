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

# Enable Cloud Storage API if not already enabled
resource "google_project_service" "storage" {
  project            = var.project_id
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

# Create multiple GCS Buckets using for_each
resource "google_storage_bucket" "buckets" {
  for_each      = toset(var.bucket_names)
  name          = each.value
  project       = var.project_id
  location      = var.region
  storage_class = var.storage_class
  force_destroy = var.force_destroy

  uniform_bucket_level_access = true

  # Basic lifecycle rule example: can be customized if needed
  # public_access_prevention is set to inherited or enforced.
  # Let's enforce public access prevention by default for security!
  public_access_prevention = "enforced"

  depends_on = [google_project_service.storage]
}
