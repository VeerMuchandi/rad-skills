output "job_id" {
  description = "The fully qualified resource name of the created Cloud Scheduler job"
  value       = google_cloud_scheduler_job.job.id
}

output "job_state" {
  description = "The state of the created Cloud Scheduler job"
  value       = google_cloud_scheduler_job.job.state
}
