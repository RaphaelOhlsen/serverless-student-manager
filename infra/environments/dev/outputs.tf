output "project_name" {
  description = "Project name."
  value       = local.project_name
}

output "environment" {
  description = "Terraform environment."
  value       = local.environment
}

output "aws_region" {
  description = "AWS region used by the environment."
  value       = var.aws_region
}
