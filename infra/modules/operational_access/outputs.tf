output "role_name" {
  description = "Name of the operational IAM role."
  value       = aws_iam_role.this.name
}

output "role_arn" {
  description = "ARN of the operational IAM role."
  value       = aws_iam_role.this.arn
}

output "policy_name" {
  description = "Name of the managed IAM policy attached to the operational role."
  value       = aws_iam_policy.this.name
}

output "policy_arn" {
  description = "ARN of the managed IAM policy attached to the operational role."
  value       = aws_iam_policy.this.arn
}
