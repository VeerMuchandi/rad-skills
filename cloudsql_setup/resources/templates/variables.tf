variable "project_id" {
  description = "The GCP Project ID"
  type        = string
}

variable "region" {
  description = "The GCP Region"
  type        = string
  default     = "us-central1"
}

variable "instance_name_prefix" {
  description = "Prefix for the database instance name"
  type        = string
  default     = "adk-db"
}

variable "database_flavor" {
  description = "The database flavor: 'postgres' or 'mysql'"
  type        = string
  default     = "postgres"
}

variable "database_version" {
  description = "The database version (e.g. POSTGRES_15 or MYSQL_8_0)"
  type        = string
  default     = "POSTGRES_15"
}

variable "tier" {
  description = "The database tier/size"
  type        = string
  default     = "db-f1-micro"
}

variable "database_name" {
  description = "The name of the database"
  type        = string
  default     = "adk_database"
}

variable "db_username" {
  description = "The database user"
  type        = string
  default     = "adk_user"
}

variable "secret_prefix" {
  description = "Prefix for the Secret Manager secrets"
  type        = string
  default     = "adk_"
}

variable "deletion_protection" {
  description = "Whether to protect the database instance from deletion"
  type        = bool
  default     = false
}
