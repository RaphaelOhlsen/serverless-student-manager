mock_provider "aws" {}

override_data {
  target = data.aws_iam_policy_document.trust

  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"GitHubActionsOidc\",\"Effect\":\"Allow\",\"Action\":\"sts:AssumeRoleWithWebIdentity\",\"Principal\":{\"Federated\":\"arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com\"},\"Condition\":{\"StringEquals\":{\"token.actions.githubusercontent.com:aud\":\"sts.amazonaws.com\",\"token.actions.githubusercontent.com:sub\":\"repo:example@12345678/serverless-student-manager@87654321:environment:dev-bootstrap-admin\"}}}]}"
  }
}

variables {
  role_name        = "student-manager-github-dev-bootstrap-admin"
  role_description = "Temporary GitHub Actions operational role for first Administrator bootstrap."

  oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
  oidc_subject      = "repo:example@12345678/serverless-student-manager@87654321:environment:dev-bootstrap-admin"

  policy_name        = "student-manager-dev-bootstrap-admin"
  policy_description = "Least-privilege permissions for first Administrator bootstrap."

  policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem"]
        Resource = ["arn:aws:dynamodb:us-east-1:123456789012:table/example"]
      }
    ]
  })

  data_classification = "restricted"

  tags = {
    Environment = "dev"
    Workload    = "deployment-automation"
  }
}

run "plans_operational_access" {
  command = plan

  assert {
    condition     = aws_iam_role.this.name == "student-manager-github-dev-bootstrap-admin"
    error_message = "The operational IAM role name is incorrect."
  }

  assert {
    condition     = aws_iam_role.this.max_session_duration == 3600
    error_message = "The operational IAM role must default to a one-hour maximum session."
  }

  assert {
    condition     = strcontains(aws_iam_role.this.assume_role_policy, "sts:AssumeRoleWithWebIdentity")
    error_message = "The trust policy must allow AssumeRoleWithWebIdentity."
  }

  assert {
    condition     = strcontains(aws_iam_role.this.assume_role_policy, "sts.amazonaws.com")
    error_message = "The trust policy must require the GitHub OIDC audience sts.amazonaws.com."
  }

  assert {
    condition     = strcontains(aws_iam_role.this.assume_role_policy, "repo:example@12345678/serverless-student-manager@87654321:environment:dev-bootstrap-admin")
    error_message = "The trust policy must restrict access to the exact OIDC subject."
  }

  assert {
    condition     = aws_iam_role.this.tags["Component"] == "operational-access"
    error_message = "The Component tag must be operational-access."
  }

  assert {
    condition     = aws_iam_role.this.tags["DataClassification"] == "restricted"
    error_message = "The DataClassification tag must be restricted."
  }

  assert {
    condition     = aws_iam_policy.this.name == "student-manager-dev-bootstrap-admin"
    error_message = "The managed IAM policy name is incorrect."
  }

  assert {
    condition     = aws_iam_role_policy_attachment.this.role == aws_iam_role.this.name
    error_message = "The managed policy must be attached to the operational role."
  }

  assert {
    condition     = output.role_name == "student-manager-github-dev-bootstrap-admin"
    error_message = "The role_name output is incorrect."
  }

  assert {
    condition     = output.policy_name == "student-manager-dev-bootstrap-admin"
    error_message = "The policy_name output is incorrect."
  }
}
