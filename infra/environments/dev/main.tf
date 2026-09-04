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

  statement {
    sid    = "ReadUserAuthorization"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
    ]

    resources = [
      module.user_store.table_arn,
    ]
  }

  statement {
    sid    = "QueryStudentListIndexes"
    effect = "Allow"

    actions = [
      "dynamodb:Query",
    ]

    resources = [
      "${module.student_store.table_arn}/index/${module.student_store.gsi_status_name}",
      "${module.student_store.table_arn}/index/${module.student_store.gsi_all_name}",
    ]
  }

  statement {
    sid    = "TransactStudentCreation"
    effect = "Allow"

    actions = [
      "dynamodb:TransactWriteItems",
    ]

    resources = [
      module.student_store.table_arn,
    ]
  }

  statement {
    sid    = "PutStudentCreationInTransaction"
    effect = "Allow"

    actions = [
      "dynamodb:PutItem",
    ]

    resources = [
      module.student_store.table_arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "dynamodb:EnclosingOperation"
      values   = ["TransactWriteItems"]
    }
  }

  statement {
    sid    = "TransactStudentCreationAudit"
    effect = "Allow"

    actions = [
      "dynamodb:TransactWriteItems",
    ]

    resources = [
      module.audit_store.table_arn,
    ]
  }

  statement {
    sid    = "PutStudentCreationAuditInTransaction"
    effect = "Allow"

    actions = [
      "dynamodb:PutItem",
    ]

    resources = [
      module.audit_store.table_arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "dynamodb:EnclosingOperation"
      values   = ["TransactWriteItems"]
    }
  }

  statement {
    sid    = "ReadStudentCreationAuditReconciliation"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
    ]

    resources = [
      module.audit_store.table_arn,
    ]
  }

  statement {
    sid    = "ManageStudentCreationIdempotency"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
    ]

    resources = [
      module.idempotency_store.table_arn,
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
    AUDIT_RETENTION_DAYS         = "90"
    AUDIT_TABLE_NAME             = module.audit_store.table_name
    ENVIRONMENT                  = local.environment
    IDEMPOTENCY_TABLE_NAME       = module.idempotency_store.table_name
    POWERTOOLS_SERVICE_NAME      = "students-api"
    POWERTOOLS_METRICS_NAMESPACE = "ServerlessStudentManager"
    POWERTOOLS_LOG_LEVEL         = "DEBUG"
    STUDENTS_TABLE_NAME          = module.student_store.table_name
    USERS_TABLE_NAME             = module.user_store.table_name
  }

  additional_iam_policy_json = data.aws_iam_policy_document.students_api.json
}

data "aws_iam_policy_document" "users_api" {
  statement {
    sid    = "ReadActivationIdentity"
    effect = "Allow"

    actions = [
      "cognito-idp:AdminGetUser",
      "cognito-idp:AdminGetUserAuthFactors",
    ]

    resources = [
      module.identity.user_pool_arn,
    ]
  }

  statement {
    sid    = "ReadAndTransactActivationState"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:TransactWriteItems",
    ]

    resources = [
      module.user_store.table_arn,
    ]
  }

  statement {
    sid    = "UpdateActivationStateInTransaction"
    effect = "Allow"

    actions = [
      "dynamodb:UpdateItem",
    ]

    resources = [
      module.user_store.table_arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "dynamodb:EnclosingOperation"
      values   = ["TransactWriteItems"]
    }
  }

  statement {
    sid    = "AppendActivationAudit"
    effect = "Allow"

    actions = [
      "dynamodb:TransactWriteItems",
    ]

    resources = [
      module.audit_store.table_arn,
    ]
  }

  statement {
    sid    = "AppendActivationAuditInTransaction"
    effect = "Allow"

    actions = [
      "dynamodb:PutItem",
    ]

    resources = [
      module.audit_store.table_arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "dynamodb:EnclosingOperation"
      values   = ["TransactWriteItems"]
    }
  }

  statement {
    sid    = "ManageActivationIdempotency"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ]

    resources = [
      module.idempotency_store.table_arn,
    ]
  }
}

module "users_api" {
  source = "../../modules/lambda_service"

  function_name = "serverless-student-manager-dev-users-api"
  description   = "Users API Lambda function."

  runtime       = "python3.13"
  handler       = "users_api.app.lambda_handler"
  architectures = ["x86_64"]

  memory_size = 512
  timeout     = 10

  bootstrap_package_filename = var.users_api_bootstrap_package_filename

  log_retention_in_days = 14

  component           = "users-api"
  data_classification = "confidential"

  environment_variables = {
    POWERTOOLS_SERVICE_NAME      = "users-api"
    POWERTOOLS_METRICS_NAMESPACE = "ServerlessStudentManager"
    POWERTOOLS_LOG_LEVEL         = "DEBUG"
    ENVIRONMENT                  = local.environment
    USERS_TABLE_NAME             = module.user_store.table_name
    AUDIT_TABLE_NAME             = module.audit_store.table_name
    IDEMPOTENCY_TABLE_NAME       = module.idempotency_store.table_name
    USER_POOL_ID                 = module.identity.user_pool_id
    AUDIT_RETENTION_DAYS         = "90"
  }

  additional_iam_policy_json = data.aws_iam_policy_document.users_api.json
}

module "http_api" {
  source = "../../modules/http_api"

  api_name = "${local.project_name}-${local.environment}-http-api"

  jwt_issuer = module.identity.issuer

  jwt_audience = [
    module.identity.user_pool_client_id,
  ]

  cors_allow_origins = [
    "http://localhost:5173",
  ]

  cors_allow_methods = [
    "GET",
    "POST",
  ]

  cors_allow_headers = [
    "Authorization",
    "Idempotency-Key",
  ]

  integrations = {
    students = {
      invoke_arn    = module.students_api.alias_invoke_arn
      function_name = module.students_api.function_name
      alias_name    = module.students_api.alias_name
    }
    users = {
      invoke_arn    = module.users_api.alias_invoke_arn
      function_name = module.users_api.function_name
      alias_name    = module.users_api.alias_name
    }
  }

  routes = {
    health = {
      route_key          = "GET /health"
      integration_key    = "students"
      authorization_type = "NONE"
    }

    get_student = {
      route_key          = "GET /students/{studentId}"
      integration_key    = "students"
      authorization_type = "JWT"
    }

    list_students = {
      route_key          = "GET /students"
      integration_key    = "students"
      authorization_type = "JWT"
    }

    create_student = {
      route_key          = "POST /students"
      integration_key    = "students"
      authorization_type = "JWT"
    }

    activate_current_user = {
      route_key          = "POST /users/me/activation"
      integration_key    = "users"
      authorization_type = "JWT"
    }

    get_current_user = {
      route_key          = "GET /users/me"
      integration_key    = "users"
      authorization_type = "JWT"
    }
  }

  component           = "http-api"
  data_classification = "confidential"

  tags = local.common_tags
}

module "idempotency_store" {
  source = "../../modules/idempotency_store"

  table_name = "serverless-student-manager-dev-idempotency"

  point_in_time_recovery_enabled = false
  deletion_protection_enabled    = false

  tags = local.common_tags
}

module "audit_store" {
  source = "../../modules/audit_store"

  table_name = "serverless-student-manager-dev-audit-events"

  point_in_time_recovery_enabled = false
  deletion_protection_enabled    = false

  tags = local.common_tags
}

data "aws_iam_policy_document" "bootstrap_admin" {
  statement {
    sid    = "ManageBootstrapCognitoIdentity"
    effect = "Allow"

    actions = [
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminGetUser",
      "cognito-idp:AdminDeleteUser",
      "cognito-idp:AdminDisableUser",
    ]

    resources = [
      module.identity.user_pool_arn,
    ]
  }

  statement {
    sid    = "ReadAndTransactUserProvisioning"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:TransactWriteItems",
    ]

    resources = [
      module.user_store.table_arn,
      module.audit_store.table_arn,
    ]
  }

  statement {
    sid    = "WriteUserProvisioningArtifacts"
    effect = "Allow"

    actions = [
      "dynamodb:PutItem",
    ]

    resources = [
      module.user_store.table_arn,
    ]
  }

  statement {
    sid    = "AppendAuditEvents"
    effect = "Allow"

    actions = [
      "dynamodb:PutItem",
    ]

    resources = [
      module.audit_store.table_arn,
    ]
  }

  statement {
    sid    = "ManageBootstrapIdempotency"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
    ]

    resources = [
      module.idempotency_store.table_arn,
    ]
  }
}

module "bootstrap_admin_access" {
  source = "../../modules/operational_access"

  role_name        = "student-manager-github-dev-bootstrap-admin"
  role_description = "Temporary GitHub Actions operational role for first Administrator bootstrap."

  oidc_provider_arn = local.github_oidc_provider_arn
  oidc_subject      = local.github_bootstrap_admin_subject

  policy_name        = "student-manager-dev-bootstrap-admin"
  policy_description = "Least-privilege permissions for first Administrator bootstrap."
  policy_json        = data.aws_iam_policy_document.bootstrap_admin.json

  data_classification = "restricted"

  tags = local.operational_tags
}

data "aws_iam_policy_document" "resume_first_admin_invitation" {
  statement {
    sid    = "ReadAndResendFirstAdminInvitation"
    effect = "Allow"

    actions = [
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminGetUser",
    ]

    resources = [
      module.identity.user_pool_arn,
    ]
  }

  statement {
    sid    = "ReadFirstAdminState"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
    ]

    resources = [
      module.user_store.table_arn,
    ]
  }

  statement {
    sid    = "ManageInvitationResumeIdempotency"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ]

    resources = [
      module.idempotency_store.table_arn,
    ]
  }
}

module "resume_first_admin_invitation_operational_access" {
  source = "../../modules/operational_access"

  role_name        = "student-manager-github-dev-resume-first-admin-invitation"
  role_description = "Temporary GitHub Actions operational role for first Administrator invitation resume."

  oidc_provider_arn = local.github_oidc_provider_arn
  oidc_subject      = local.github_resume_first_admin_invitation_subject

  policy_name        = "student-manager-dev-resume-first-admin-invitation"
  policy_description = "Least-privilege permissions for first Administrator invitation resume."
  policy_json        = data.aws_iam_policy_document.resume_first_admin_invitation.json

  data_classification = "restricted"

  tags = local.operational_tags
}

data "aws_iam_policy_document" "verify_first_admin_email" {
  statement {
    sid    = "VerifyFirstAdminEmailInCognito"
    effect = "Allow"

    actions = [
      "cognito-idp:AdminGetUser",
      "cognito-idp:AdminUpdateUserAttributes",
    ]

    resources = [
      module.identity.user_pool_arn,
    ]
  }

  statement {
    sid    = "ReadFirstAdminIdentityState"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
    ]

    resources = [
      module.user_store.table_arn,
    ]
  }

  statement {
    sid    = "ManageEmailVerificationIdempotency"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ]

    resources = [
      module.idempotency_store.table_arn,
    ]
  }

  statement {
    sid    = "AppendEmailVerificationAudit"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
    ]

    resources = [
      module.audit_store.table_arn,
    ]
  }
}

module "verify_first_admin_email_operational_access" {
  source = "../../modules/operational_access"

  role_name        = "student-manager-github-dev-verify-first-admin-email"
  role_description = "Temporary GitHub Actions operational role for first Administrator email verification."

  oidc_provider_arn = local.github_oidc_provider_arn
  oidc_subject      = local.github_verify_first_admin_email_subject

  policy_name        = "student-manager-dev-verify-first-admin-email"
  policy_description = "Least-privilege permissions for first Administrator email verification."
  policy_json        = data.aws_iam_policy_document.verify_first_admin_email.json

  data_classification = "restricted"

  tags = local.operational_tags
}

data "aws_iam_policy_document" "admin_recovery" {
  statement {
    sid    = "ManageRecoveryCognitoIdentity"
    effect = "Allow"

    actions = [
      "cognito-idp:AdminGetUser",
      "cognito-idp:AdminUserGlobalSignOut",
      "cognito-idp:AdminDisableUser",
      "cognito-idp:AdminDeleteUser",
      "cognito-idp:AdminCreateUser",
    ]

    resources = [
      module.identity.user_pool_arn,
    ]
  }

  statement {
    sid    = "ReadAndTransactRecoveryState"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:TransactWriteItems",
    ]

    resources = [
      module.user_store.table_arn,
      module.audit_store.table_arn,
    ]
  }

  statement {
    sid    = "ManageRecoveryIdempotency"
    effect = "Allow"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
    ]

    resources = [
      module.idempotency_store.table_arn,
    ]
  }
}

module "admin_recovery_access" {
  source = "../../modules/operational_access"

  role_name        = "student-manager-github-dev-admin-recovery"
  role_description = "Temporary GitHub Actions operational role for sole Administrator MFA recovery."

  oidc_provider_arn = local.github_oidc_provider_arn
  oidc_subject      = local.github_admin_recovery_subject

  policy_name        = "student-manager-dev-admin-recovery"
  policy_description = "Least-privilege permissions for sole Administrator MFA recovery."
  policy_json        = data.aws_iam_policy_document.admin_recovery.json

  data_classification = "restricted"

  tags = local.operational_tags
}
