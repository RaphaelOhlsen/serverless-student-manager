output "table_name" {
  description = "Name of the students DynamoDB table."
  value       = aws_dynamodb_table.this.name
}

output "table_arn" {
  description = "ARN of the students DynamoDB table."
  value       = aws_dynamodb_table.this.arn
}

output "gsi_status_name" {
  description = "Name of the status/name global secondary index."
  value       = "gsi-status-name"
}

output "gsi_all_name" {
  description = "Name of the all-students/name global secondary index."
  value       = "gsi-all-name"
}
