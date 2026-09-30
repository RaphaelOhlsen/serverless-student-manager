mock_provider "aws" {}

variables {
  alias_name = "alias/serverless-student-manager-dev-audit-cursor-hmac"

  tags = {
    Environment = "dev"
  }
}

run "plans_audit_cursor_hmac_key" {
  command = plan

  assert {
    condition     = aws_kms_key.this.customer_master_key_spec == "HMAC_256"
    error_message = "The audit cursor KMS key must use HMAC_256."
  }

  assert {
    condition     = aws_kms_key.this.key_usage == "GENERATE_VERIFY_MAC"
    error_message = "The audit cursor KMS key must permit only MAC generation and verification."
  }

  assert {
    condition     = aws_kms_key.this.enable_key_rotation == null
    error_message = "Automatic rotation must be omitted for the HMAC key."
  }

  assert {
    condition     = aws_kms_alias.this.name == "alias/serverless-student-manager-dev-audit-cursor-hmac"
    error_message = "The audit cursor KMS alias is incorrect."
  }

  assert {
    condition     = aws_kms_key.this.tags["Component"] == "audit-cursor-signing"
    error_message = "The Component tag must identify audit cursor signing."
  }

}
