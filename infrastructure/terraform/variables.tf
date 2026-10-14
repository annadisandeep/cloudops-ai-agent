variable "enable_gcp" {
  description = "Provision the GCP Cloud Run stack. Keep false until reviewed and approved."
  type        = bool
  default     = false
}

variable "enable_aws" {
  description = "Provision the AWS read-only IAM stack. Keep false until reviewed and approved."
  type        = bool
  default     = false
}

variable "gcp_project_id" {
  description = "GCP project to deploy into (and/or to observe read-only)."
  type        = string
  default     = "changeme-project"
}

variable "gcp_region" {
  description = "GCP region for Cloud Run and Artifact Registry."
  type        = string
  default     = "us-central1"
}

variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "backend_image" {
  description = "Fully-qualified backend container image (pushed to Artifact Registry)."
  type        = string
  default     = "us-central1-docker.pkg.dev/changeme-project/cloudops/backend:latest"
}

variable "frontend_image" {
  description = "Fully-qualified frontend container image."
  type        = string
  default     = "us-central1-docker.pkg.dev/changeme-project/cloudops/frontend:latest"
}

variable "cors_origins" {
  description = "Comma-separated allowed CORS origins for the backend."
  type        = string
  default     = ""
}
