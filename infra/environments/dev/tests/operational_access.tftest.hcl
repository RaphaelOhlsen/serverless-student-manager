mock_provider "aws" {}

variables {
  aws_region     = "us-east-1"
  aws_account_id = "123456789012"

  students_api_bootstrap_package_filename = "bootstrap.zip"

  github_repository    = "example/serverless-student-manager"
  github_owner_id      = "12345678"
  github_repository_id = "87654321"
}

override_module {
  target = module.student_store
  outputs = {
    table_name      = "serverless-student-manager-dev-students"
    table_arn       = "arn:aws:dynamodb:us-east-1:123456789012:table/serverless-student-manager-dev-students"
    gsi_status_name = "gsi-status-name"
    gsi_all_name    = "gsi-all-name"
  }
}

override_module {
  target = module.user_store
  outputs = {
    table_name = "serverless-student-manager-dev-users"
    table_arn  = "arn:aws:dynamodb:us-east-1:123456789012:table/serverless-student-manager-dev-users"
  }
}

override_module {
  target = module.identity
  outputs = {
    user_pool_id        = "us-east-1_example"
    user_pool_arn       = "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_example"
    user_pool_client_id = "example-client"
    issuer              = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example"
  }
}

override_module {
  target = module.students_api
  outputs = {
    function_name      = "serverless-student-manager-dev-students-api"
    function_arn       = "arn:aws:lambda:us-east-1:123456789012:function:serverless-student-manager-dev-students-api"
    execution_role_arn = "arn:aws:iam::123456789012:role/serverless-student-manager-dev-students-api-execution"
    log_group_name     = "/aws/lambda/serverless-student-manager-dev-students-api"
    alias_name         = "live"
    alias_arn          = "arn:aws:lambda:us-east-1:123456789012:function:serverless-student-manager-dev-students-api:live"
    alias_invoke_arn   = "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/example/invocations"
  }
}

override_module {
  target = module.http_api
  outputs = {
    api_id                = "example-api"
    api_endpoint          = "https://example.execute-api.us-east-1.amazonaws.com"
    execution_arn         = "arn:aws:execute-api:us-east-1:123456789012:example-api"
    jwt_authorizer_id     = "authorizer"
    stage_name            = "$default"
    access_log_group_name = "/aws/apigateway/serverless-student-manager-dev-http-api"
  }
}

override_module {
  target = module.idempotency_store
  outputs = {
    table_name = "serverless-student-manager-dev-idempotency"
    table_arn  = "arn:aws:dynamodb:us-east-1:123456789012:table/serverless-student-manager-dev-idempotency"
  }
}

override_module {
  target = module.audit_store
  outputs = {
    table_name           = "serverless-student-manager-dev-audit-events"
    table_arn            = "arn:aws:dynamodb:us-east-1:123456789012:table/serverless-student-manager-dev-audit-events"
    gsi_actor_time       = "gsi-actor-time"
    gsi_correlation_time = "gsi-correlation-time"
    gsi_period_time      = "gsi-period-time"
  }
}

override_module {
  target = module.bootstrap_admin_access
  outputs = {
    role_name   = "student-manager-github-dev-bootstrap-admin"
    role_arn    = "arn:aws:iam::123456789012:role/student-manager-github-dev-bootstrap-admin"
    policy_name = "student-manager-dev-bootstrap-admin"
    policy_arn  = "arn:aws:iam::123456789012:policy/student-manager-dev-bootstrap-admin"
  }
}

override_module {
  target = module.admin_recovery_access
  outputs = {
    role_name   = "student-manager-github-dev-admin-recovery"
    role_arn    = "arn:aws:iam::123456789012:role/student-manager-github-dev-admin-recovery"
    policy_name = "student-manager-dev-admin-recovery"
    policy_arn  = "arn:aws:iam::123456789012:policy/student-manager-dev-admin-recovery"
  }
}

override_data {
  target = data.aws_iam_policy_document.resume_first_admin_invitation
  values = {
    json = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "ReadAndResendFirstAdminInvitation"
          Effect   = "Allow"
          Action   = ["cognito-idp:AdminCreateUser", "cognito-idp:AdminGetUser"]
          Resource = "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_example"
        },
        {
          Sid      = "ReadFirstAdminState"
          Effect   = "Allow"
          Action   = "dynamodb:GetItem"
          Resource = "arn:aws:dynamodb:us-east-1:123456789012:table/serverless-student-manager-dev-users"
        },
        {
          Sid      = "ManageInvitationResumeIdempotency"
          Effect   = "Allow"
          Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
          Resource = "arn:aws:dynamodb:us-east-1:123456789012:table/serverless-student-manager-dev-idempotency"
        },
      ]
    })
  }
}

override_data {
  target = data.aws_iam_policy_document.verify_first_admin_email
  values = {
    json = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "VerifyFirstAdminEmailInCognito"
          Effect   = "Allow"
          Action   = ["cognito-idp:AdminGetUser", "cognito-idp:AdminUpdateUserAttributes"]
          Resource = "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_example"
        },
        {
          Sid      = "ReadFirstAdminIdentityState"
          Effect   = "Allow"
          Action   = "dynamodb:GetItem"
          Resource = "arn:aws:dynamodb:us-east-1:123456789012:table/serverless-student-manager-dev-users"
        },
        {
          Sid      = "ManageEmailVerificationIdempotency"
          Effect   = "Allow"
          Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
          Resource = "arn:aws:dynamodb:us-east-1:123456789012:table/serverless-student-manager-dev-idempotency"
        },
        {
          Sid      = "AppendEmailVerificationAudit"
          Effect   = "Allow"
          Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
          Resource = "arn:aws:dynamodb:us-east-1:123456789012:table/serverless-student-manager-dev-audit-events"
        },
      ]
    })
  }
}

override_data {
  target          = module.resume_first_admin_invitation_operational_access.data.aws_iam_policy_document.trust
  override_during = plan
  values = {
    json = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Sid    = "GitHubActionsOidc"
        Effect = "Allow"
        Action = "sts:AssumeRoleWithWebIdentity"
        Principal = {
          Federated = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
        }
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
            "token.actions.githubusercontent.com:sub" = "repo:example@12345678/serverless-student-manager@87654321:environment:dev-resume-first-admin-invitation"
          }
        }
      }]
    })
  }
}

override_resource {
  target          = module.resume_first_admin_invitation_operational_access.aws_iam_role.this
  override_during = plan
  values = {
    arn = "arn:aws:iam::123456789012:role/student-manager-github-dev-resume-first-admin-invitation"
  }
}

override_resource {
  target          = module.resume_first_admin_invitation_operational_access.aws_iam_policy.this
  override_during = plan
  values = {
    arn = "arn:aws:iam::123456789012:policy/student-manager-dev-resume-first-admin-invitation"
  }
}

override_data {
  target          = module.verify_first_admin_email_operational_access.data.aws_iam_policy_document.trust
  override_during = plan
  values = {
    json = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Sid    = "GitHubActionsOidc"
        Effect = "Allow"
        Action = "sts:AssumeRoleWithWebIdentity"
        Principal = {
          Federated = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
        }
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
            "token.actions.githubusercontent.com:sub" = "repo:example@12345678/serverless-student-manager@87654321:environment:dev-verify-first-admin-email"
          }
        }
      }]
    })
  }
}

override_resource {
  target          = module.verify_first_admin_email_operational_access.aws_iam_role.this
  override_during = plan
  values = {
    arn = "arn:aws:iam::123456789012:role/student-manager-github-dev-verify-first-admin-email"
  }
}

override_resource {
  target          = module.verify_first_admin_email_operational_access.aws_iam_policy.this
  override_during = plan
  values = {
    arn = "arn:aws:iam::123456789012:policy/student-manager-dev-verify-first-admin-email"
  }
}

run "plans_resume_first_admin_invitation_access" {
  command = plan

  assert {
    condition     = module.resume_first_admin_invitation_operational_access.role_name == "student-manager-github-dev-resume-first-admin-invitation"
    error_message = "The resume operational role name is incorrect."
  }

  assert {
    condition     = module.resume_first_admin_invitation_operational_access.policy_name == "student-manager-dev-resume-first-admin-invitation"
    error_message = "The resume managed policy name is incorrect."
  }

  assert {
    condition     = local.github_resume_first_admin_invitation_subject == "repo:example@12345678/serverless-student-manager@87654321:environment:dev-resume-first-admin-invitation"
    error_message = "The resume OIDC subject must use the exact dedicated GitHub Environment."
  }

  assert {
    condition     = !strcontains(local.github_resume_first_admin_invitation_subject, "*")
    error_message = "The resume OIDC subject must not contain wildcards."
  }

  assert {
    condition     = length(data.aws_iam_policy_document.resume_first_admin_invitation.statement) == 3
    error_message = "The resume policy must contain exactly three semantic statements."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.resume_first_admin_invitation.statement : statement.actions
      if statement.sid == "ReadAndResendFirstAdminInvitation"
      ])) == toset([
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminGetUser",
    ])
    error_message = "The Cognito statement must contain only AdminGetUser and AdminCreateUser."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.resume_first_admin_invitation.statement : statement.resources
      if statement.sid == "ReadAndResendFirstAdminInvitation"
    ])) == toset([module.identity.user_pool_arn])
    error_message = "The Cognito statement must target only the dev user pool."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.resume_first_admin_invitation.statement : statement.actions
      if statement.sid == "ReadFirstAdminState"
    ])) == toset(["dynamodb:GetItem"])
    error_message = "The users statement must contain only GetItem."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.resume_first_admin_invitation.statement : statement.resources
      if statement.sid == "ReadFirstAdminState"
    ])) == toset([module.user_store.table_arn])
    error_message = "The users statement must target only the users table."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.resume_first_admin_invitation.statement : statement.actions
      if statement.sid == "ManageInvitationResumeIdempotency"
      ])) == toset([
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ])
    error_message = "The idempotency statement must contain only GetItem, PutItem and UpdateItem."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.resume_first_admin_invitation.statement : statement.resources
      if statement.sid == "ManageInvitationResumeIdempotency"
    ])) == toset([module.idempotency_store.table_arn])
    error_message = "The idempotency statement must target only the idempotency table."
  }

  assert {
    condition = alltrue(flatten([
      for statement in data.aws_iam_policy_document.resume_first_admin_invitation.statement : [
        for action in statement.actions : !strcontains(action, "*")
      ]
    ]))
    error_message = "The resume policy must not contain wildcard actions."
  }

  assert {
    condition = alltrue(flatten([
      for statement in data.aws_iam_policy_document.resume_first_admin_invitation.statement : [
        for resource in statement.resources : resource != "*"
      ]
    ]))
    error_message = "The resume policy must not contain wildcard resources."
  }

  assert {
    condition = length(setintersection(
      toset(flatten([
        for statement in data.aws_iam_policy_document.resume_first_admin_invitation.statement : statement.actions
      ])),
      toset([
        "cognito-idp:AdminDeleteUser",
        "cognito-idp:AdminDisableUser",
        "cognito-idp:AdminUserGlobalSignOut",
        "dynamodb:DeleteItem",
        "dynamodb:TransactWriteItems",
        "dynamodb:Query",
        "dynamodb:Scan",
      ])
    )) == 0
    error_message = "The resume policy contains a forbidden action."
  }

  assert {
    condition = length(setintersection(
      toset(flatten([
        for statement in data.aws_iam_policy_document.resume_first_admin_invitation.statement : statement.resources
      ])),
      toset([
        module.audit_store.table_arn,
        module.student_store.table_arn,
      ])
    )) == 0
    error_message = "The resume policy must not grant audit or students table access."
  }

  assert {
    condition = (
      local.operational_tags["Environment"] == "dev" &&
      local.operational_tags["Workload"] == "deployment-automation"
    )
    error_message = "The resume role must receive the approved operational tags."
  }

  assert {
    condition     = output.resume_first_admin_invitation_role_arn == "arn:aws:iam::123456789012:role/student-manager-github-dev-resume-first-admin-invitation"
    error_message = "The resume role ARN output is incorrect."
  }

  assert {
    condition     = output.resume_first_admin_invitation_policy_arn == "arn:aws:iam::123456789012:policy/student-manager-dev-resume-first-admin-invitation"
    error_message = "The resume policy ARN output is incorrect."
  }
}

run "plans_verify_first_admin_email_access" {
  command = plan

  assert {
    condition     = module.verify_first_admin_email_operational_access.role_name == "student-manager-github-dev-verify-first-admin-email"
    error_message = "The email verification operational role name is incorrect."
  }

  assert {
    condition     = module.verify_first_admin_email_operational_access.policy_name == "student-manager-dev-verify-first-admin-email"
    error_message = "The email verification managed policy name is incorrect."
  }

  assert {
    condition     = local.github_oidc_provider_arn == "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    error_message = "The email verification role must reuse the GitHub Actions OIDC provider."
  }

  assert {
    condition     = local.github_verify_first_admin_email_subject == "repo:example@12345678/serverless-student-manager@87654321:environment:dev-verify-first-admin-email"
    error_message = "The email verification OIDC subject must use the exact dedicated GitHub Environment."
  }

  assert {
    condition     = !strcontains(local.github_verify_first_admin_email_subject, "*")
    error_message = "The email verification OIDC subject must not contain wildcards."
  }

  assert {
    condition     = local.github_bootstrap_admin_subject == "repo:example@12345678/serverless-student-manager@87654321:environment:dev-bootstrap-admin"
    error_message = "The bootstrap OIDC subject must remain unchanged."
  }

  assert {
    condition     = local.github_admin_recovery_subject == "repo:example@12345678/serverless-student-manager@87654321:environment:dev-admin-recovery"
    error_message = "The admin recovery OIDC subject must remain unchanged."
  }

  assert {
    condition     = length(data.aws_iam_policy_document.verify_first_admin_email.statement) == 4
    error_message = "The email verification policy must contain exactly four semantic statements."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : statement.actions
      if statement.sid == "VerifyFirstAdminEmailInCognito"
      ])) == toset([
      "cognito-idp:AdminGetUser",
      "cognito-idp:AdminUpdateUserAttributes",
    ])
    error_message = "The Cognito statement must contain only AdminGetUser and AdminUpdateUserAttributes."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : statement.resources
      if statement.sid == "VerifyFirstAdminEmailInCognito"
    ])) == toset([module.identity.user_pool_arn])
    error_message = "The Cognito statement must target only the dev user pool."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : statement.actions
      if statement.sid == "ReadFirstAdminIdentityState"
    ])) == toset(["dynamodb:GetItem"])
    error_message = "The users statement must contain only GetItem."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : statement.resources
      if statement.sid == "ReadFirstAdminIdentityState"
    ])) == toset([module.user_store.table_arn])
    error_message = "The users statement must target only the users table."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : statement.actions
      if statement.sid == "ManageEmailVerificationIdempotency"
      ])) == toset([
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ])
    error_message = "The idempotency statement must contain only GetItem, PutItem and UpdateItem."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : statement.resources
      if statement.sid == "ManageEmailVerificationIdempotency"
    ])) == toset([module.idempotency_store.table_arn])
    error_message = "The idempotency statement must target only the idempotency table."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : statement.actions
      if statement.sid == "AppendEmailVerificationAudit"
      ])) == toset([
      "dynamodb:GetItem",
      "dynamodb:PutItem",
    ])
    error_message = "The audit statement must contain only GetItem and PutItem."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : statement.resources
      if statement.sid == "AppendEmailVerificationAudit"
    ])) == toset([module.audit_store.table_arn])
    error_message = "The audit statement must target only the audit table."
  }

  assert {
    condition = alltrue(flatten([
      for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : [
        for action in statement.actions : !strcontains(action, "*")
      ]
    ]))
    error_message = "The email verification policy must not contain wildcard actions."
  }

  assert {
    condition = alltrue(flatten([
      for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : [
        for resource in statement.resources : resource != "*"
      ]
    ]))
    error_message = "The email verification policy must not contain wildcard resources."
  }

  assert {
    condition = length(setintersection(
      toset(flatten([
        for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : statement.actions
      ])),
      toset([
        "cognito-idp:*",
        "cognito-idp:AdminCreateUser",
        "cognito-idp:AdminDeleteUser",
        "cognito-idp:AdminDisableUser",
        "cognito-idp:AdminEnableUser",
        "cognito-idp:AdminSetUserPassword",
        "cognito-idp:AdminUserGlobalSignOut",
        "dynamodb:*",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:TransactWriteItems",
      ])
    )) == 0
    error_message = "The email verification policy contains a forbidden action."
  }

  assert {
    condition = length(setintersection(
      toset(one([
        for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : statement.actions
        if statement.sid == "ReadFirstAdminIdentityState"
      ])),
      toset([
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:TransactWriteItems",
      ])
    )) == 0
    error_message = "The users statement contains a forbidden write or collection action."
  }

  assert {
    condition = length(setintersection(
      toset(one([
        for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : statement.actions
        if statement.sid == "ManageEmailVerificationIdempotency"
      ])),
      toset([
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:TransactWriteItems",
      ])
    )) == 0
    error_message = "The idempotency statement contains a forbidden action."
  }

  assert {
    condition = length(setintersection(
      toset(one([
        for statement in data.aws_iam_policy_document.verify_first_admin_email.statement : statement.actions
        if statement.sid == "AppendEmailVerificationAudit"
      ])),
      toset([
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:TransactWriteItems",
      ])
    )) == 0
    error_message = "The audit statement contains a forbidden mutation or collection action."
  }

  assert {
    condition = (
      local.operational_tags["Environment"] == "dev" &&
      local.operational_tags["Workload"] == "deployment-automation"
    )
    error_message = "The email verification role must receive the approved operational tags."
  }

  assert {
    condition     = output.verify_first_admin_email_role_arn == "arn:aws:iam::123456789012:role/student-manager-github-dev-verify-first-admin-email"
    error_message = "The email verification role ARN output is incorrect."
  }

  assert {
    condition     = output.verify_first_admin_email_policy_arn == "arn:aws:iam::123456789012:policy/student-manager-dev-verify-first-admin-email"
    error_message = "The email verification policy ARN output is incorrect."
  }
}

run "plans_bootstrap_admin_access" {
  command = plan

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.bootstrap_admin.statement : statement.actions
      if statement.sid == "ReadAndTransactUserProvisioning"
      ])) == toset([
      "dynamodb:GetItem",
      "dynamodb:TransactWriteItems",
    ])
    error_message = "The bootstrap provisioning read/transaction statement must contain exactly GetItem and TransactWriteItems."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.bootstrap_admin.statement : statement.resources
      if statement.sid == "ReadAndTransactUserProvisioning"
      ])) == toset([
      module.user_store.table_arn,
      module.audit_store.table_arn,
    ])
    error_message = "The bootstrap provisioning statement must target only the users and audit tables."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.bootstrap_admin.statement : statement.actions
      if statement.sid == "WriteUserProvisioningArtifacts"
      ])) == toset([
      "dynamodb:PutItem",
    ])
    error_message = "The bootstrap users write statement must contain exactly PutItem."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.bootstrap_admin.statement : statement.resources
      if statement.sid == "WriteUserProvisioningArtifacts"
      ])) == toset([
      module.user_store.table_arn,
    ])
    error_message = "The bootstrap users write statement must target only the users table."
  }
}

run "plans_students_list_api_access" {
  command = plan

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.students_api.statement : statement.actions
      if statement.sid == "ReadUserAuthorization"
    ])) == toset(["dynamodb:GetItem"])
    error_message = "The students API users statement must contain only GetItem."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.students_api.statement : statement.resources
      if statement.sid == "ReadUserAuthorization"
    ])) == toset([module.user_store.table_arn])
    error_message = "The students API authorization read must target only the users table."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.students_api.statement : statement.actions
      if statement.sid == "QueryStudentListIndexes"
    ])) == toset(["dynamodb:Query"])
    error_message = "The students list statement must contain only Query."
  }

  assert {
    condition = toset(one([
      for statement in data.aws_iam_policy_document.students_api.statement : statement.resources
      if statement.sid == "QueryStudentListIndexes"
      ])) == toset([
      "${module.student_store.table_arn}/index/gsi-status-name",
      "${module.student_store.table_arn}/index/gsi-all-name",
    ])
    error_message = "The students list Query permission must target only the two approved GSIs."
  }

  assert {
    condition = alltrue(flatten([
      for statement in data.aws_iam_policy_document.students_api.statement : [
        for action in statement.actions : action != "dynamodb:Scan"
      ]
    ]))
    error_message = "The students API policy must not allow DynamoDB Scan."
  }
}
