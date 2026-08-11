locals {
  project_name = "serverless-student-manager"

  bootstrap_state_key = "bootstrap/terraform.tfstate"
  dev_state_key       = "environments/dev/terraform.tfstate"
  prod_state_key      = "environments/prod/terraform.tfstate"

  dev_lockfile_key  = "${local.dev_state_key}.tflock"
  prod_lockfile_key = "${local.prod_state_key}.tflock"

  github_oidc_url      = "https://token.actions.githubusercontent.com"
  github_oidc_audience = "sts.amazonaws.com"
  github_dev_subject   = "repo:${var.github_repository}:ref:refs/heads/main"
  github_prod_subject  = "repo:${var.github_repository}:environment:prod"

  common_tags = {
    Project   = local.project_name
    ManagedBy = "Terraform"
  }

  state_bucket_tags = {
    Environment        = "shared"
    Workload           = "infrastructure-management"
    Component          = "terraform-state"
    DataClassification = "restricted"
  }

  oidc_provider_tags = {
    Environment        = "shared"
    Workload           = "deployment-automation"
    Component          = "cicd"
    DataClassification = "internal"
  }

  dev_deployment_tags = {
    Environment        = "dev"
    Workload           = "deployment-automation"
    Component          = "cicd"
    DataClassification = "internal"
  }

  prod_deployment_tags = {
    Environment        = "prod"
    Workload           = "deployment-automation"
    Component          = "cicd"
    DataClassification = "internal"
  }
}
