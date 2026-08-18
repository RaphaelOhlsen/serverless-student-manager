output "table_name" {
  description = "Name of the audit events DynamoDB table."
  value       = aws_dynamodb_table.this.name
}

output "table_arn" {
  description = "ARN of the audit events DynamoDB table."
  value       = aws_dynamodb_table.this.arn
}

output "gsi_actor_time" {
  description = "Name of the actor/time global secondary index."
  value       = "gsi-actor-time"
}

output "gsi_correlation_time" {
  description = "Name of the correlation/time global secondary index."
  value       = "gsi-correlation-time"
}

output "gsi_period_time" {
  description = "Name of the period/time global secondary index."
  value       = "gsi-period-time"
}
