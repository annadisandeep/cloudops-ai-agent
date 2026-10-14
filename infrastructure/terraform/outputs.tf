output "backend_url" {
  description = "Cloud Run backend URL (null when GCP stack disabled)."
  value       = var.enable_gcp ? google_cloud_run_v2_service.backend[0].uri : null
}

output "frontend_url" {
  description = "Cloud Run frontend URL (null when GCP stack disabled)."
  value       = var.enable_gcp ? google_cloud_run_v2_service.frontend[0].uri : null
}

output "aws_readonly_role_arn" {
  description = "ARN of the read-only agent role (null when AWS stack disabled)."
  value       = var.enable_aws ? aws_iam_role.agent_readonly[0].arn : null
}
