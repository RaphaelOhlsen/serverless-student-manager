mock_provider "aws" {}

variables {
  aws_region        = "us-east-1"
  state_bucket_name = "serverless-student-manager-test-state"
  github_repository = "example/serverless-student-manager"
}

run "reject_ipv4_bucket_name" {
  command = plan

  variables {
    state_bucket_name = "192.168.0.1"
  }

  expect_failures = [var.state_bucket_name]
}

run "reject_reserved_bucket_prefix" {
  command = plan

  variables {
    state_bucket_name = "xn--reserved-state-bucket"
  }

  expect_failures = [var.state_bucket_name]
}

run "reject_reserved_bucket_suffix" {
  command = plan

  variables {
    state_bucket_name = "reserved-state-bucket--table-s3"
  }

  expect_failures = [var.state_bucket_name]
}

run "secure_bootstrap_configuration" {
  command = plan

  assert {
    condition     = aws_s3_bucket.terraform_state.force_destroy == false
    error_message = "The state bucket must not allow force destruction."
  }

  assert {
    condition     = strcontains(file("${path.module}/main.tf"), "prevent_destroy = true")
    error_message = "The state bucket must be protected by prevent_destroy."
  }

  assert {
    condition     = aws_s3_bucket_versioning.terraform_state.versioning_configuration[0].status == "Enabled"
    error_message = "The state bucket must have versioning enabled."
  }

  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.terraform_state.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    error_message = "The state bucket must explicitly use SSE-S3 AES256."
  }

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.terraform_state.block_public_acls,
      aws_s3_bucket_public_access_block.terraform_state.block_public_policy,
      aws_s3_bucket_public_access_block.terraform_state.ignore_public_acls,
      aws_s3_bucket_public_access_block.terraform_state.restrict_public_buckets,
    ])
    error_message = "All S3 Block Public Access controls must be enabled."
  }

  assert {
    condition     = aws_s3_bucket_ownership_controls.terraform_state.rule[0].object_ownership == "BucketOwnerEnforced"
    error_message = "The state bucket must enforce bucket ownership and disable ACLs."
  }

  assert {
    condition = alltrue([
      aws_s3_bucket.terraform_state.tags.Environment == "shared",
      aws_s3_bucket.terraform_state.tags.Workload == "infrastructure-management",
      aws_s3_bucket.terraform_state.tags.Component == "terraform-state",
      aws_s3_bucket.terraform_state.tags.DataClassification == "restricted",
    ])
    error_message = "The state bucket must have the approved security tags."
  }

  assert {
    condition     = strcontains(file("${path.module}/main.tf"), "DenyInsecureTransport") && strcontains(file("${path.module}/main.tf"), "aws:SecureTransport") && strcontains(file("${path.module}/main.tf"), "values   = [\"false\"]")
    error_message = "The bucket policy must deny insecure transport."
  }

  assert {
    condition     = strcontains(file("${path.module}/locals.tf"), "repo:$${var.github_repository}:ref:refs/heads/main") && strcontains(file("${path.module}/locals.tf"), "sts.amazonaws.com") && !strcontains(file("${path.module}/main.tf"), "StringLike")
    error_message = "The dev trust must use exact aud and main-branch sub claims."
  }

  assert {
    condition     = strcontains(file("${path.module}/locals.tf"), "repo:$${var.github_repository}:environment:prod") && strcontains(file("${path.module}/locals.tf"), "sts.amazonaws.com") && !strcontains(file("${path.module}/main.tf"), "StringLike")
    error_message = "The prod trust must use exact aud and prod-environment sub claims."
  }

  assert {
    condition     = aws_iam_role.github_actions_dev_deployment.max_session_duration == 3600 && aws_iam_role.github_actions_prod_deployment.max_session_duration == 3600
    error_message = "Deployment role sessions must be limited to one hour."
  }

  assert {
    condition     = local.dev_state_key == "environments/dev/terraform.tfstate" && local.dev_lockfile_key == "environments/dev/terraform.tfstate.tflock"
    error_message = "The dev policy must be isolated from prod and bootstrap states."
  }

  assert {
    condition     = local.prod_state_key == "environments/prod/terraform.tfstate" && local.prod_lockfile_key == "environments/prod/terraform.tfstate.tflock"
    error_message = "The prod policy must be isolated from dev and bootstrap states."
  }

  assert {
    condition     = length(regexall("actions = \\[\"s3:GetObject\", \"s3:PutObject\"\\]", file("${path.module}/main.tf"))) == 2
    error_message = "Each state object must grant only GetObject and PutObject."
  }

  assert {
    condition     = length(regexall("actions = \\[\"s3:GetObject\", \"s3:PutObject\", \"s3:DeleteObject\"\\]", file("${path.module}/main.tf"))) == 2
    error_message = "Each lockfile must grant GetObject, PutObject and DeleteObject."
  }

  assert {
    condition     = !strcontains(join("", [for filename in fileset(path.module, "*.tf") : file("${path.module}/${filename}")]), "aws_dynamodb_table")
    error_message = "The bootstrap must not create a DynamoDB locking table."
  }

  assert {
    condition     = output.bootstrap_state_key == "bootstrap/terraform.tfstate" && output.dev_state_key == "environments/dev/terraform.tfstate" && output.prod_state_key == "environments/prod/terraform.tfstate"
    error_message = "The state key outputs must match the approved state layout."
  }

  assert {
    condition     = length(regexall("(?m)^output ", file("${path.module}/outputs.tf"))) == 10
    error_message = "The bootstrap must expose all ten approved outputs."
  }
}
