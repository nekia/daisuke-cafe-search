variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
  default     = "daisuke-cafe-search"
}

variable "region" {
  description = "Google Cloud region for backend resources."
  type        = string
  default     = "asia-northeast1"
}

variable "environment" {
  description = "Environment suffix (e.g. prod, dev)."
  type        = string
  default     = "prod"
}

variable "backend_service_name" {
  description = "Cloud Run service name."
  type        = string
  default     = "daisuke-cafe-backend"
}

variable "artifact_registry_repository_id" {
  description = "Artifact Registry repository ID for Docker images."
  type        = string
  default     = "backend-images"
}

variable "container_image" {
  description = "Container image URL to deploy to Cloud Run."
  type        = string
}

variable "container_port" {
  description = "Port exposed by the backend container."
  type        = number
  default     = 3001
}

variable "runtime_service_account_email" {
  description = "Cloud Run runtime service account email. If null, uses the default Compute Engine service account."
  type        = string
  default     = null
}

variable "create_runtime_service_account" {
  description = "Whether to create and use a dedicated runtime service account."
  type        = bool
  default     = false
}

variable "allow_unauthenticated" {
  description = "Whether to allow unauthenticated invocations to Cloud Run."
  type        = bool
  default     = true
}

variable "mongodb_connection_string" {
  description = "MongoDB connection string used by the backend (plain env mode only)."
  type        = string
  default     = null
  sensitive   = true
}

variable "google_client_id" {
  description = "Google OAuth client ID used by backend token verification (plain env mode only)."
  type        = string
  default     = null
}

variable "use_secret_manager_env" {
  description = "Use Secret Manager references for Cloud Run env vars to match existing production behavior."
  type        = bool
  default     = true
}

variable "mongodb_connection_string_secret_name" {
  description = "Secret Manager secret name for MongoDB connection string."
  type        = string
  default     = "MONGODB_CONNECTION_STRING"
}

variable "mongodb_connection_string_secret_version" {
  description = "Secret Manager version for MongoDB connection string secret."
  type        = string
  default     = "latest"
}

variable "google_client_id_secret_name" {
  description = "Secret Manager secret name for Google OAuth client ID."
  type        = string
  default     = "REACT_APP_GOOGLE_CLIENT_ID"
}

variable "google_client_id_secret_version" {
  description = "Secret Manager version for Google OAuth client ID secret."
  type        = string
  default     = "latest"
}

variable "cpu" {
  description = "CPU limit for Cloud Run container."
  type        = string
  default     = "1000m"
}

variable "memory" {
  description = "Memory limit for Cloud Run container."
  type        = string
  default     = "512Mi"
}
