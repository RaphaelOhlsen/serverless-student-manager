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

output "students_api_function_name" {
  description = "Name of the students-api Lambda function."
  value       = module.students_api.function_name
}

output "students_api_function_arn" {
  description = "ARN of the students-api Lambda function."
  value       = module.students_api.function_arn
}

output "students_api_execution_role_arn" {
  description = "ARN of the students-api Lambda execution role."
  value       = module.students_api.execution_role_arn
}

output "students_api_log_group_name" {
  description = "CloudWatch Log Group used by the students-api Lambda function."
  value       = module.students_api.log_group_name
}

output "students_api_alias_name" {
  description = "Stable alias of the students-api Lambda function."
  value       = module.students_api.alias_name
}

output "students_api_alias_arn" {
  description = "ARN of the stable students-api Lambda alias."
  value       = module.students_api.alias_arn
}

output "http_api_id" {
  description = "ID of the API Gateway HTTP API."
  value       = module.http_api.api_id
}

output "http_api_endpoint" {
  description = "Base endpoint of the API Gateway HTTP API."
  value       = module.http_api.api_endpoint
}

output "http_api_execution_arn" {
  description = "Execution ARN of the API Gateway HTTP API."
  value       = module.http_api.execution_arn
}

output "http_api_jwt_authorizer_id" {
  description = "ID of the HTTP API JWT authorizer."
  value       = module.http_api.jwt_authorizer_id
}

output "http_api_stage_name" {
  description = "Name of the HTTP API stage."
  value       = module.http_api.stage_name
}

output "http_api_access_log_group_name" {
  description = "CloudWatch Log Group used for HTTP API access logs."
  value       = module.http_api.access_log_group_name
}

output "idempotency_table_name" {
  description = "Name of the idempotency DynamoDB table."
  value       = module.idempotency_store.table_name
}

output "idempotency_table_arn" {
  description = "ARN of the idempotency DynamoDB table."
  value       = module.idempotency_store.table_arn
}

output "audit_table_name" {
  description = "Name of the audit events DynamoDB table."
  value       = module.audit_store.table_name
}

output "audit_table_arn" {
  description = "ARN of the audit events DynamoDB table."
  value       = module.audit_store.table_arn
}

output "audit_gsi_actor_time" {
  description = "Name of the audit actor/time GSI."
  value       = module.audit_store.gsi_actor_time
}

output "audit_gsi_correlation_time" {
  description = "Name of the audit correlation/time GSI."
  value       = module.audit_store.gsi_correlation_time
}

output "audit_gsi_period_time" {
  description = "Name of the audit period/time GSI."
  value       = module.audit_store.gsi_period_time
}

output "bootstrap_admin_role_arn" {
  description = "ARN of the GitHub Actions role used for first Administrator bootstrap."
  value       = module.bootstrap_admin_access.role_arn
}

output "bootstrap_admin_policy_arn" {
  description = "ARN of the managed IAM policy used for first Administrator bootstrap."
  value       = module.bootstrap_admin_access.policy_arn
}

output "admin_recovery_role_arn" {
  description = "ARN of the GitHub Actions role used for sole Administrator MFA recovery."
  value       = module.admin_recovery_access.role_arn
}

output "admin_recovery_policy_arn" {
  description = "ARN of the managed IAM policy used for sole Administrator MFA recovery."
  value       = module.admin_recovery_access.policy_arn
}
