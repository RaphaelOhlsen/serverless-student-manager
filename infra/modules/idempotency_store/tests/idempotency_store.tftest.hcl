mock_provider "aws" {}

variables {
  table_name                     = "serverless-student-manager-dev-idempotency"
  point_in_time_recovery_enabled = false
  deletion_protection_enabled    = false
  data_classification            = "confidential"

  tags = {
    Environment = "dev"
  }
}

run "plans_idempotency_table" {
  command = plan

  assert {
    condition     = aws_dynamodb_table.this.name == "serverless-student-manager-dev-idempotency"
    error_message = "The DynamoDB table name is incorrect."
  }

  assert {
    condition     = aws_dynamodb_table.this.billing_mode == "PAY_PER_REQUEST"
    error_message = "The DynamoDB table must use PAY_PER_REQUEST billing mode."
  }

  assert {
    condition     = aws_dynamodb_table.this.hash_key == "id"
    error_message = "The DynamoDB partition key must be id."
  }

  assert {
    condition     = aws_dynamodb_table.this.ttl[0].enabled == true
    error_message = "TTL must be enabled."
  }

  assert {
    condition     = aws_dynamodb_table.this.ttl[0].attribute_name == "expiration"
    error_message = "TTL must use the expiration attribute."
  }

  assert {
    condition     = aws_dynamodb_table.this.tags["Component"] == "idempotency"
    error_message = "The Component tag must be idempotency."
  }

  assert {
    condition     = aws_dynamodb_table.this.tags["DataClassification"] == "confidential"
    error_message = "The DataClassification tag is incorrect."
  }

  assert {
    condition     = output.table_name == "serverless-student-manager-dev-idempotency"
    error_message = "The table_name output is incorrect."
  }
}
