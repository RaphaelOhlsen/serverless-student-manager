output "function_name" {
  description = "Name of the Lambda function."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "ARN of the Lambda function."
  value       = aws_lambda_function.this.arn
}

output "invoke_arn" {
  description = "Invoke ARN of the Lambda function."
  value       = aws_lambda_function.this.invoke_arn
}

output "execution_role_name" {
  description = "Name of the Lambda execution IAM role."
  value       = aws_iam_role.this.name
}

output "execution_role_arn" {
  description = "ARN of the Lambda execution IAM role."
  value       = aws_iam_role.this.arn
}

output "log_group_name" {
  description = "Name of the Lambda CloudWatch Log Group."
  value       = aws_cloudwatch_log_group.this.name
}

output "log_group_arn" {
  description = "ARN of the Lambda CloudWatch Log Group."
  value       = aws_cloudwatch_log_group.this.arn
}

output "alias_name" {
  description = "Name of the stable Lambda alias."
  value       = aws_lambda_alias.live.name
}

output "alias_arn" {
  description = "ARN of the stable Lambda alias."
  value       = aws_lambda_alias.live.arn
}

output "alias_invoke_arn" {
  description = "Invoke ARN of the stable Lambda alias."
  value       = aws_lambda_alias.live.invoke_arn
}
