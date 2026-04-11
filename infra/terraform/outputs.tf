output "cloud_run_service_url" {
  description = "Deployed Cloud Run URL for the backend API."
  value       = google_cloud_run_v2_service.backend.uri
}

output "artifact_registry_repository" {
  description = "Artifact Registry Docker repository endpoint."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.backend.repository_id}"
}
