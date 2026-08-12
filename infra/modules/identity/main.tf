resource "aws_cognito_user_pool" "this" {
  name           = var.user_pool_name
  user_pool_tier = "ESSENTIALS"

  # ADR-017:
  # userId is the immutable technical Cognito Username.
  # Email is an alias used by administrative users to sign in.
  alias_attributes         = ["email"]
  auto_verified_attributes = ["email"]

  # ADR-014 / RNF-SEC-012:
  # TOTP MFA is mandatory.
  # SMS and email MFA are intentionally not configured.
  mfa_configuration = "ON"

  software_token_mfa_configuration {
    enabled = true
  }

  # Public administrative-user registration is disabled.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  # RNF-SEC-009:
  # Strong password policy for administrative users.
  password_policy {
    minimum_length    = 12
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
  }

  # ADR-014:
  # Account recovery uses verified email only.
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = merge(
    var.tags,
    {
      Component          = "identity"
      DataClassification = "confidential"
    }
  )
}

resource "aws_cognito_user_pool_client" "this" {
  name         = var.user_pool_client_name
  user_pool_id = aws_cognito_user_pool.this.id

  # React SPA is a public client and must not have a client secret.
  generate_secret = false

  # Authentication through Secure Remote Password (SRP).
  #
  # ALLOW_REFRESH_TOKEN_AUTH is intentionally omitted because
  # refresh-token rotation is enabled.
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
  ]

  # Avoid revealing whether a user exists.
  prevent_user_existence_errors = "ENABLED"

  # Allows issued tokens to be revoked.
  enable_token_revocation = true

  # ADR-014 / RNF-SEC-013:
  # Access and ID tokens: 15 minutes.
  # Refresh token: 8 hours.
  access_token_validity  = 15
  id_token_validity      = 15
  refresh_token_validity = 8

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "hours"
  }

  # Refresh-token rotation is enabled.
  #
  # Explicitly setting retry_grace_period_seconds = 0 avoids the
  # provider inconsistency observed when AWS returned 0 while
  # Terraform had planned the value as null.
  refresh_token_rotation {
    feature                    = "ENABLED"
    retry_grace_period_seconds = 0
  }
}
