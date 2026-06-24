output "bucket_names" {
  description = "List of created GCS bucket names"
  value       = [for b in google_storage_bucket.buckets : b.name]
}

output "bucket_urls" {
  description = "Map of bucket names to their gs:// URLs"
  value       = { for name, b in google_storage_bucket.buckets : name => b.url }
}
