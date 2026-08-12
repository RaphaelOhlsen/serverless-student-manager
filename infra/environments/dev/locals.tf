locals {
  project_name = "serverless-student-manager"
  environment  = "dev"

  common_tags = {
    Project     = local.project_name
    Environment = local.environment
    ManagedBy   = "Terraform"
    Workload    = "student-management"
  }
}
