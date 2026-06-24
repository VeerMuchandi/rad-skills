output "connection_name" {
  value       = google_sql_database_instance.default.connection_name
  description = "The Cloud SQL connection name"
}

output "secret_ids" {
  value = {
    db_connection_name = google_secret_manager_secret.db_connection_name.secret_id
    db_user            = google_secret_manager_secret.db_user.secret_id
    db_password        = google_secret_manager_secret.db_password.secret_id
    db_name            = google_secret_manager_secret.db_name.secret_id
  }
  description = "The Secret Manager secret IDs containing connection credentials"
}
