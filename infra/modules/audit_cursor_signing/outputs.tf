output "key_arn" {
  description = "ARN of the KMS HMAC key used to authenticate audit cursors."
  value       = aws_kms_key.this.arn
}

output "alias_name" {
  description = "Alias of the KMS HMAC key used to authenticate audit cursors."
  value       = aws_kms_alias.this.name
}
