locals {
  common_labels = {
    app         = "daisuke-cafe-search"
    environment = var.environment
    managed_by  = "terraform"
  }

  default_compute_sa_email = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
  backend_runtime_sa_email = var.create_runtime_service_account ? google_service_account.backend_runtime[0].email : coalesce(
    var.runtime_service_account_email,
    local.default_compute_sa_email
  )
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_service" "run" {
  project            = var.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  project            = var.project_id
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iam" {
  project            = var.project_id
  service            = "iam.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  project            = var.project_id
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "backend" {
  location      = var.region
  repository_id = var.artifact_registry_repository_id
  description   = "Docker repository for backend images"
  format        = "DOCKER"

  labels = local.common_labels

  depends_on = [
    google_project_service.run,
    google_project_service.artifactregistry,
    google_project_service.iam,
    google_project_service.cloudbuild
  ]
}

resource "google_project_iam_member" "cloudbuild_artifact_registry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${data.google_project.current.number}@cloudbuild.gserviceaccount.com"
}

# Cloud Build GitHub triggers are created in the console (or Cloud Build v2 + repository_event_config).
# The legacy google_cloudbuild_trigger github {} block often returns API 400 without a 2nd-gen connection.

resource "google_service_account" "backend_runtime" {
  count = var.create_runtime_service_account ? 1 : 0

  account_id   = "backend-runtime-sa"
  display_name = "Backend Cloud Run runtime service account"
  project      = var.project_id
}

resource "google_cloud_run_v2_service" "backend" {
  name     = var.backend_service_name
  location = var.region
  project  = var.project_id

  template {
    service_account = local.backend_runtime_sa_email

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image = var.container_image

      ports {
        container_port = var.container_port
      }

      resources {
        cpu_idle = true

        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
      }

      dynamic "env" {
        for_each = var.use_secret_manager_env ? [1] : []
        content {
          name = "MONGODB_CONNECTION_STRING"
          value_source {
            secret_key_ref {
              secret  = var.mongodb_connection_string_secret_name
              version = var.mongodb_connection_string_secret_version
            }
          }
        }
      }

      dynamic "env" {
        for_each = var.use_secret_manager_env ? [1] : []
        content {
          name = "REACT_APP_GOOGLE_CLIENT_ID"
          value_source {
            secret_key_ref {
              secret  = var.google_client_id_secret_name
              version = var.google_client_id_secret_version
            }
          }
        }
      }

      dynamic "env" {
        for_each = var.use_secret_manager_env ? [] : [1]
        content {
          name  = "MONGODB_CONNECTION_STRING"
          value = var.mongodb_connection_string
        }
      }

      dynamic "env" {
        for_each = var.use_secret_manager_env ? [] : [1]
        content {
          name  = "REACT_APP_GOOGLE_CLIENT_ID"
          value = var.google_client_id
        }
      }
    }
  }

  depends_on = [
    google_project_service.run,
    google_project_service.artifactregistry,
    google_project_service.iam,
    google_project_service.cloudbuild
  ]

  lifecycle {
    ignore_changes = [
      client,
      template[0].containers[0].name
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count    = var.allow_unauthenticated ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
