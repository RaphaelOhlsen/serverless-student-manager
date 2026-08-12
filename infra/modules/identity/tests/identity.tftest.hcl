mock_provider "aws" {}

variables {
  user_pool_name        = "serverless-student-manager-dev-user-pool"
  user_pool_client_name = "serverless-student-manager-dev-web"

  tags = {
    Environment = "dev"
  }
}

run "plans_identity" {
  command = plan

  assert {
    condition     = aws_cognito_user_pool.this.name == "serverless-student-manager-dev-user-pool"
    error_message = "The Cognito User Pool name is incorrect."
  }

  assert {
    condition     = aws_cognito_user_pool.this.user_pool_tier == "ESSENTIALS"
    error_message = "The Cognito User Pool tier must be ESSENTIALS."
  }

  assert {
    condition     = aws_cognito_user_pool.this.mfa_configuration == "ON"
    error_message = "MFA must be mandatory for the Cognito User Pool."
  }

  assert {
    condition = contains(
      aws_cognito_user_pool.this.alias_attributes,
      "email"
    )
    error_message = "Email must be configured as a Cognito login alias."
  }

  assert {
    condition     = one(aws_cognito_user_pool.this.software_token_mfa_configuration).enabled
    error_message = "Software-token TOTP MFA must be enabled."
  }

  assert {
    condition     = one(aws_cognito_user_pool.this.admin_create_user_config).allow_admin_create_user_only
    error_message = "Public user sign-up must be disabled."
  }

  assert {
    condition     = one(aws_cognito_user_pool.this.password_policy).minimum_length == 12
    error_message = "The minimum password length must be 12 characters."
  }

  assert {
    condition = contains(
      flatten([
        for setting in aws_cognito_user_pool.this.account_recovery_setting : [
          for mechanism in setting.recovery_mechanism : mechanism.name
        ]
      ]),
      "verified_email"
    )
    error_message = "Verified email must be configured as the account recovery mechanism."
  }

  assert {
    condition     = aws_cognito_user_pool_client.this.generate_secret == false
    error_message = "The frontend Cognito client must not generate a client secret."
  }

  assert {
    condition     = aws_cognito_user_pool_client.this.access_token_validity == 15
    error_message = "Access token validity must be 15 minutes."
  }

  assert {
    condition     = aws_cognito_user_pool_client.this.id_token_validity == 15
    error_message = "ID token validity must be 15 minutes."
  }

  assert {
    condition     = aws_cognito_user_pool_client.this.refresh_token_validity == 8
    error_message = "Refresh token validity must be 8 hours."
  }

  assert {
    condition = !contains(
      aws_cognito_user_pool_client.this.explicit_auth_flows,
      "ALLOW_REFRESH_TOKEN_AUTH"
    )
    error_message = "ALLOW_REFRESH_TOKEN_AUTH must not be enabled when refresh token rotation is enabled."
  }

  assert {
    condition     = one(aws_cognito_user_pool_client.this.refresh_token_rotation).feature == "ENABLED"
    error_message = "Refresh token rotation must be enabled."
  }

  assert {
    condition     = one(aws_cognito_user_pool_client.this.refresh_token_rotation).retry_grace_period_seconds == 0
    error_message = "Refresh token retry grace period must be 0 seconds."
  }

  assert {
    condition     = aws_cognito_user_pool.this.tags["Component"] == "identity"
    error_message = "The Component tag must be identity."
  }

  assert {
    condition     = aws_cognito_user_pool.this.tags["DataClassification"] == "confidential"
    error_message = "The DataClassification tag must be confidential."
  }
}
