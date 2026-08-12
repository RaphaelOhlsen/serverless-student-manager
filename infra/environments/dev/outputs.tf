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

output "students_table_name" {
  description = "Name of the students DynamoDB table."
  value       = module.student_store.table_name
}

output "students_table_arn" {
  description = "ARN of the students DynamoDB table."
  value       = module.student_store.table_arn
}
