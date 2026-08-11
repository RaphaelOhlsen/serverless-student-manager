output "bootstrap_state_key" {
  description = "S3 object key reserved for the bootstrap state after controlled migration."
  value       = local.bootstrap_state_key
}

output "dev_state_key" {
  description = "S3 object key for the dev environment state."
  value       = local.dev_state_key
}

output "dev_state_policy_arn" {
  description = "ARN of the least-privilege dev state access policy."
  value       = aws_iam_policy.terraform_state_dev.arn
}

output "github_actions_dev_deployment_role_arn" {
  description = "ARN of the GitHub Actions deployment role for dev."
  value       = aws_iam_role.github_actions_dev_deployment.arn
}

output "github_actions_oidc_provider_arn" {
  description = "ARN of the GitHub Actions OIDC provider."
  value       = aws_iam_openid_connect_provider.github_actions.arn
}

output "github_actions_prod_deployment_role_arn" {
  description = "ARN of the GitHub Actions deployment role for prod."
  value       = aws_iam_role.github_actions_prod_deployment.arn
}

output "prod_state_key" {
  description = "S3 object key for the prod environment state."
  value       = local.prod_state_key
}

output "prod_state_policy_arn" {
  description = "ARN of the least-privilege prod state access policy."
  value       = aws_iam_policy.terraform_state_prod.arn
}

output "terraform_state_bucket_arn" {
  description = "ARN of the private S3 bucket that stores Terraform states."
  value       = aws_s3_bucket.terraform_state.arn
}

output "terraform_state_bucket_name" {
  description = "Name of the private S3 bucket that stores Terraform states."
  value       = aws_s3_bucket.terraform_state.id
}
