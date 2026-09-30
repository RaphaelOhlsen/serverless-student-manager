mock_provider "aws" {}

override_data {
  target = data.aws_iam_policy_document.assume_role

  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

override_data {
  target = data.aws_iam_policy_document.logging

  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

variables {
  function_name = "serverless-student-manager-dev-audit-api"
  description   = "Audit Query API Lambda function."

  runtime       = "python3.13"
  handler       = "audit_api.app.lambda_handler"
  architectures = ["x86_64"]

  memory_size = 512
  timeout     = 10

  bootstrap_package_filename = "/tmp/audit-api-bootstrap.zip"

  log_retention_in_days = 14

  component           = "audit-api"
  data_classification = "confidential"

  environment_variables = {
    AUDIT_CURSOR_KMS_KEY_ARN     = "arn:aws:kms:us-east-1:123456789012:key/00000000-0000-4000-8000-000000000001"
    AUDIT_TABLE_NAME             = "serverless-student-manager-dev-audit-events"
    ENVIRONMENT                  = "dev"
    POWERTOOLS_LOG_LEVEL         = "DEBUG"
    POWERTOOLS_METRICS_NAMESPACE = "ServerlessStudentManager"
    POWERTOOLS_SERVICE_NAME      = "audit-api"
    USERS_TABLE_NAME             = "serverless-student-manager-dev-users"
  }

  additional_iam_policy_json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"

  tags = {
    Project     = "serverless-student-manager"
    Environment = "dev"
    ManagedBy   = "Terraform"
    Workload    = "student-management"
  }
}

run "plans_audit_api_lambda" {
  command = plan

  assert {
    condition     = aws_lambda_function.this.function_name == "serverless-student-manager-dev-audit-api"
    error_message = "The audit-api Lambda function name is incorrect."
  }

  assert {
    condition = (
      one(aws_lambda_function.this.environment).variables["AUDIT_CURSOR_KMS_KEY_ARN"]
      == "arn:aws:kms:us-east-1:123456789012:key/00000000-0000-4000-8000-000000000001"
    )
    error_message = "The audit-api AUDIT_CURSOR_KMS_KEY_ARN is incorrect."
  }

  assert {
    condition     = aws_lambda_function.this.runtime == "python3.13"
    error_message = "The audit-api Lambda runtime must be python3.13."
  }

  assert {
    condition     = aws_lambda_function.this.handler == "audit_api.app.lambda_handler"
    error_message = "The audit-api Lambda handler is incorrect."
  }

  assert {
    condition     = aws_lambda_function.this.filename == "/tmp/audit-api-bootstrap.zip"
    error_message = "The audit-api bootstrap package filename is incorrect."
  }

  assert {
    condition = (
      one(aws_lambda_function.this.environment).variables["USERS_TABLE_NAME"]
      == "serverless-student-manager-dev-users"
    )
    error_message = "The audit-api USERS_TABLE_NAME is incorrect."
  }

  assert {
    condition = (
      one(aws_lambda_function.this.environment).variables["AUDIT_TABLE_NAME"]
      == "serverless-student-manager-dev-audit-events"
    )
    error_message = "The audit-api AUDIT_TABLE_NAME is incorrect."
  }

  assert {
    condition     = aws_lambda_alias.live.name == "live"
    error_message = "The audit-api stable alias must be named live."
  }

  assert {
    condition     = length(aws_iam_role_policy.additional) == 1
    error_message = "The audit-api read-only service IAM policy must be attached."
  }

  assert {
    condition     = aws_lambda_function.this.tags["Component"] == "audit-api"
    error_message = "The audit-api Component tag is incorrect."
  }
}
