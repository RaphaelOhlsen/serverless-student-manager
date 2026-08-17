output "api_id" {
  description = "ID of the API Gateway HTTP API."
  value       = aws_apigatewayv2_api.this.id
}

output "api_arn" {
  description = "ARN of the API Gateway HTTP API."
  value       = aws_apigatewayv2_api.this.arn
}

output "api_endpoint" {
  description = "Base endpoint of the API Gateway HTTP API."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "execution_arn" {
  description = "Execution ARN of the API Gateway HTTP API."
  value       = aws_apigatewayv2_api.this.execution_arn
}

output "jwt_authorizer_id" {
  description = "ID of the JWT authorizer."
  value       = aws_apigatewayv2_authorizer.jwt.id
}

output "stage_name" {
  description = "Name of the HTTP API stage."
  value       = aws_apigatewayv2_stage.default.name
}

output "access_log_group_name" {
  description = "Name of the CloudWatch Log Group used for HTTP API access logs, or null when access logging is disabled."
  value       = try(aws_cloudwatch_log_group.access[0].name, null)
}

output "access_log_group_arn" {
  description = "ARN of the CloudWatch Log Group used for HTTP API access logs, or null when access logging is disabled."
  value       = try(aws_cloudwatch_log_group.access[0].arn, null)
}