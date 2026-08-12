output "table_name" {
  description = "Name of the users DynamoDB table."
  value       = aws_dynamodb_table.this.name
}

output "table_arn" {
  description = "ARN of the users DynamoDB table."
  value       = aws_dynamodb_table.this.arn
}

output "gsi_all_users_name" {
  description = "Name of the all-users/name global secondary index."
  value       = "gsi-all-users-name"
}
