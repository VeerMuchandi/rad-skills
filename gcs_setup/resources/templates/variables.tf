variable "project_id" {
  description = "The GCP Project ID"
  type        = string
}

variable "region" {
  description = "The GCP Region for the buckets"
  type        = string
  default     = "us-central1"
}

variable "bucket_names" {
  description = "List of GCS bucket names to create"
  type        = list(string)
}

variable "storage_class" {
  description = "The storage class for the buckets"
  type        = string
  default     = "STANDARD"
}

variable "force_destroy" {
  description = "Allow deleting buckets containing objects during terraform destroy"
  type        = bool
  default     = true
}
