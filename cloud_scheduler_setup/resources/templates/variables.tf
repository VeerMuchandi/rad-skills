variable "project_id" {
  description = "The GCP Project ID"
  type        = string
}

variable "region" {
  description = "The GCP Region for the Cloud Scheduler job"
  type        = string
  default     = "us-central1"
}

variable "job_name" {
  description = "The name of the Cloud Scheduler job"
  type        = string
}

variable "schedule" {
  description = "The cron schedule for the job (e.g. '0 9 * * *')"
  type        = string
}

variable "time_zone" {
  description = "The timezone for the schedule"
  type        = string
  default     = "America/New_York"
}

variable "target_uri" {
  description = "The target HTTP URI to invoke"
  type        = string
}

variable "http_method" {
  description = "The HTTP method to use (GET, POST, etc.)"
  type        = string
  default     = "POST"
}

variable "body" {
  description = "The string body to send with the HTTP request (e.g. JSON string)"
  type        = string
  default     = ""
}

variable "service_account_email" {
  description = "The service account email to use for token authentication"
  type        = string
}

variable "audience" {
  description = "The audience to use for OIDC token. If null, defaults to target_uri. Only used when auth_type is OIDC."
  type        = string
  default     = null
}

variable "auth_type" {
  description = "The authentication type to use (OAUTH, OIDC, or NONE)"
  type        = string
  default     = "OAUTH"
}

variable "oauth_scope" {
  description = "The OAuth scope to request. Only used when auth_type is OAUTH."
  type        = string
  default     = "https://www.googleapis.com/auth/cloud-platform"
}
