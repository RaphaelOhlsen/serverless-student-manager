resource "aws_kms_key" "this" {
  description = var.description

  customer_master_key_spec = "HMAC_256"
  key_usage                = "GENERATE_VERIFY_MAC"

  deletion_window_in_days = var.deletion_window_in_days

  tags = merge(
    var.tags,
    {
      Component          = "audit-cursor-signing"
      DataClassification = var.data_classification
    }
  )
}

resource "aws_kms_alias" "this" {
  name          = var.alias_name
  target_key_id = aws_kms_key.this.key_id
}
