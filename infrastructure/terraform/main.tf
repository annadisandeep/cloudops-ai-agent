# CloudOps AI Agent — infrastructure (validation-ready; provisions NOTHING by default)
#
# Both stacks are gated behind enable_gcp / enable_aws (default: false).
# `terraform init -backend=false && terraform validate` works without any
# cloud credentials. Review docs/deployment.md before ever applying.

terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

provider "aws" {
  region = var.aws_region

  # Validation-friendly: skip credential checks when only validating/planning
  # the disabled (count=0) resources.
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}
