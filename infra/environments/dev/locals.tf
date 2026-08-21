locals {
  project_name = "serverless-student-manager"
  environment  = "dev"


  github_repository_parts = split("/", var.github_repository)

  github_owner           = local.github_repository_parts[0]
  github_repository_name = local.github_repository_parts[1]

  github_immutable_repository = "${local.github_owner}@${var.github_owner_id}/${local.github_repository_name}@${var.github_repository_id}"

  github_oidc_provider_arn = "arn:aws:iam::${var.aws_account_id}:oidc-provider/token.actions.githubusercontent.com"

  github_bootstrap_admin_subject               = "repo:${local.github_immutable_repository}:environment:dev-bootstrap-admin"
  github_admin_recovery_subject                = "repo:${local.github_immutable_repository}:environment:dev-admin-recovery"
  github_resume_first_admin_invitation_subject = "repo:${local.github_immutable_repository}:environment:dev-resume-first-admin-invitation"

  common_tags = {
    Project     = local.project_name
    Environment = local.environment
    ManagedBy   = "Terraform"
    Workload    = "student-management"
  }

  operational_tags = {
    Project     = local.project_name
    Environment = local.environment
    ManagedBy   = "Terraform"
    Workload    = "deployment-automation"
  }
}
