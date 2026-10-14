# GCP stack (disabled by default): Artifact Registry + Cloud Run + least-privilege
# service account. Cloud Run scales to zero — near-zero idle cost.

resource "google_artifact_registry_repository" "cloudops" {
  count         = var.enable_gcp ? 1 : 0
  location      = var.gcp_region
  repository_id = "cloudops"
  description   = "CloudOps AI Agent container images"
  format        = "DOCKER"
}

# Runtime service account for the backend — read-only observability roles only.
resource "google_service_account" "backend" {
  count        = var.enable_gcp ? 1 : 0
  account_id   = "cloudops-backend"
  display_name = "CloudOps AI Agent backend (read-only observability)"
}

locals {
  backend_readonly_roles = [
    "roles/monitoring.viewer",
    "roles/logging.viewer",
    "roles/compute.viewer",
  ]
}

resource "google_project_iam_member" "backend_readonly" {
  for_each = var.enable_gcp ? toset(local.backend_readonly_roles) : toset([])
  project  = var.gcp_project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.backend[0].email}"
}

resource "google_cloud_run_v2_service" "backend" {
  count    = var.enable_gcp ? 1 : 0
  name     = "cloudops-backend"
  location = var.gcp_region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.backend[0].email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.backend_image

      ports {
        container_port = 8000
      }

      env {
        name  = "CLOUDOPS_DEMO_MODE"
        value = "true"
      }
      env {
        name  = "CLOUDOPS_LLM_PROVIDER"
        value = "mock"
      }
      env {
        name  = "CLOUDOPS_CORS_ORIGINS"
        value = var.cors_origins
      }
      # Secrets (e.g. CLOUDOPS_GEMINI_API_KEY) must come from Secret Manager,
      # never from tfvars. See docs/deployment.md.

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      startup_probe {
        http_get {
          path = "/api/v1/health"
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 6
      }
    }
  }
}

resource "google_cloud_run_v2_service" "frontend" {
  count    = var.enable_gcp ? 1 : 0
  name     = "cloudops-frontend"
  location = var.gcp_region

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.frontend_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
      }
    }
  }
}
