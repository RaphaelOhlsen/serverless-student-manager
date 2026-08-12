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

output "users_table_name" {
  description = "Name of the users DynamoDB table."
  value       = module.user_store.table_name
}

output "users_table_arn" {
  description = "ARN of the users DynamoDB table."
  value       = module.user_store.table_arn
}

output "cognito_user_pool_id" {
  description = "ID of the Cognito User Pool."
  value       = module.identity.user_pool_id
}

output "cognito_user_pool_arn" {
  description = "ARN of the Cognito User Pool."
  value       = module.identity.user_pool_arn
}

output "cognito_user_pool_client_id" {
  description = "ID of the Cognito application client."
  value       = module.identity.user_pool_client_id
}

output "cognito_issuer" {
  description = "OIDC issuer URL of the Cognito User Pool."
  value       = module.identity.issuer
}
