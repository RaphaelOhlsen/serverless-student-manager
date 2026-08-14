module "student_store" {
  source = "../../modules/student_store"

  table_name = "serverless-student-manager-dev-students"

  point_in_time_recovery_enabled = false
  deletion_protection_enabled    = false
}

module "user_store" {
  source = "../../modules/user_store"

  table_name = "serverless-student-manager-dev-users"

  point_in_time_recovery_enabled = false
  deletion_protection_enabled    = false
}

module "identity" {
  source = "../../modules/identity"

  user_pool_name        = "serverless-student-manager-dev-user-pool"
  user_pool_client_name = "serverless-student-manager-dev-web"
}

data "aws_iam_policy_document" "students_api" {
  statement {
    sid    = "ReadStudentProfiles"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
    ]

    resources = [
      module.student_store.table_arn,
    ]
  }
}

module "students_api" {
  source = "../../modules/lambda_service"

  function_name = "serverless-student-manager-dev-students-api"
  description   = "Students API Lambda function."

  runtime       = "python3.13"
  handler       = "students_api.app.lambda_handler"
  architectures = ["x86_64"]

  memory_size = 512
  timeout     = 10

  bootstrap_package_filename = var.students_api_bootstrap_package_filename

  log_retention_in_days = 14

  component           = "students-api"
  data_classification = "confidential"

  environment_variables = {
    POWERTOOLS_SERVICE_NAME      = "students-api"
    POWERTOOLS_METRICS_NAMESPACE = "ServerlessStudentManager"
    POWERTOOLS_LOG_LEVEL         = "DEBUG"
    STUDENTS_TABLE_NAME          = module.student_store.table_name
  }

  additional_iam_policy_json = data.aws_iam_policy_document.students_api.json
}
