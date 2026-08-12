output "user_pool_id" {
  description = "ID of the Cognito User Pool."
  value       = aws_cognito_user_pool.this.id
}

output "user_pool_arn" {
  description = "ARN of the Cognito User Pool."
  value       = aws_cognito_user_pool.this.arn
}

output "user_pool_endpoint" {
  description = "Endpoint of the Cognito User Pool."
  value       = aws_cognito_user_pool.this.endpoint
}

output "issuer" {
  description = "OIDC issuer URL of the Cognito User Pool."
  value       = "https://${aws_cognito_user_pool.this.endpoint}"
}

output "user_pool_client_id" {
  description = "ID of the Cognito User Pool application client."
  value       = aws_cognito_user_pool_client.this.id
}
