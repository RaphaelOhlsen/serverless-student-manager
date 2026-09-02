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
  function_name = "serverless-student-manager-dev-students-api"
  description   = "Students API Lambda function."

  runtime       = "python3.13"
  handler       = "students_api.app.lambda_handler"
  architectures = ["x86_64"]

  memory_size = 512
  timeout     = 10

  bootstrap_package_filename = "/tmp/students-api-bootstrap.zip"

  log_retention_in_days = 14

  component           = "students-api"
  data_classification = "confidential"

  environment_variables = {
    POWERTOOLS_SERVICE_NAME      = "students-api"
    POWERTOOLS_METRICS_NAMESPACE = "ServerlessStudentManager"
    POWERTOOLS_LOG_LEVEL         = "DEBUG"
    STUDENTS_TABLE_NAME          = "serverless-student-manager-dev-students"
    USERS_TABLE_NAME             = "serverless-student-manager-dev-users"
  }

  tags = {
    Project     = "serverless-student-manager"
    Environment = "dev"
    ManagedBy   = "Terraform"
    Workload    = "student-management"
  }
}

run "plans_lambda_service" {
  command = plan

  assert {
    condition     = aws_lambda_function.this.function_name == "serverless-student-manager-dev-students-api"
    error_message = "The Lambda function name is incorrect."
  }

  assert {
    condition     = aws_lambda_function.this.runtime == "python3.13"
    error_message = "The Lambda runtime must be python3.13."
  }

  assert {
    condition     = aws_lambda_function.this.handler == "students_api.app.lambda_handler"
    error_message = "The Lambda handler is incorrect."
  }

  assert {
    condition     = aws_lambda_function.this.architectures[0] == "x86_64"
    error_message = "The Lambda architecture must be x86_64."
  }

  assert {
    condition     = aws_lambda_function.this.memory_size == 512
    error_message = "The Lambda memory size must be 512 MB."
  }

  assert {
    condition     = aws_lambda_function.this.timeout == 10
    error_message = "The Lambda timeout must be 10 seconds."
  }

  assert {
    condition     = aws_lambda_function.this.publish == false
    error_message = "Terraform must not publish application Lambda versions."
  }

  assert {
    condition     = aws_lambda_function.this.package_type == "Zip"
    error_message = "The Lambda package type must be Zip."
  }

  assert {
    condition     = aws_lambda_function.this.filename == "/tmp/students-api-bootstrap.zip"
    error_message = "The Lambda bootstrap package filename is incorrect."
  }

  assert {
    condition = (
      one(aws_lambda_function.this.environment).variables["POWERTOOLS_SERVICE_NAME"]
      == "students-api"
    )
    error_message = "POWERTOOLS_SERVICE_NAME is incorrect."
  }

  assert {
    condition = (
      one(aws_lambda_function.this.environment).variables["POWERTOOLS_METRICS_NAMESPACE"]
      == "ServerlessStudentManager"
    )
    error_message = "POWERTOOLS_METRICS_NAMESPACE is incorrect."
  }

  assert {
    condition = (
      one(aws_lambda_function.this.environment).variables["STUDENTS_TABLE_NAME"]
      == "serverless-student-manager-dev-students"
    )
    error_message = "STUDENTS_TABLE_NAME is incorrect."
  }


  assert {
    condition = (
      one(aws_lambda_function.this.environment).variables["USERS_TABLE_NAME"]
      == "serverless-student-manager-dev-users"
    )
    error_message = "USERS_TABLE_NAME is incorrect."
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.name == "/aws/lambda/serverless-student-manager-dev-students-api"
    error_message = "The Lambda CloudWatch Log Group name is incorrect."
  }

  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 14
    error_message = "The CloudWatch Logs retention period must be 14 days."
  }

  assert {
    condition     = aws_iam_role.this.name == "serverless-student-manager-dev-students-api-execution"
    error_message = "The Lambda execution role name is incorrect."
  }

  assert {
    condition     = aws_lambda_alias.live.name == "live"
    error_message = "The stable Lambda alias must be named live."
  }

  assert {
    condition     = aws_lambda_alias.live.function_version == "$LATEST"
    error_message = "The bootstrap Lambda alias must initially target $LATEST."
  }

  assert {
    condition     = aws_lambda_function.this.tags["Component"] == "students-api"
    error_message = "The Component tag must be students-api."
  }

  assert {
    condition     = aws_lambda_function.this.tags["DataClassification"] == "confidential"
    error_message = "The DataClassification tag must be confidential."
  }

  assert {
    condition     = length(aws_iam_role_policy.additional) == 0
    error_message = "No additional IAM policy must be created when none is provided."
  }
}
