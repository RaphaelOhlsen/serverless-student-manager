mock_provider "aws" {}

variables {
  table_name                     = "serverless-student-manager-dev-students"
  point_in_time_recovery_enabled = false
  deletion_protection_enabled    = false

  tags = {
    Environment = "dev"
  }
}

run "plans_students_table" {
  command = plan

  assert {
    condition     = aws_dynamodb_table.this.name == "serverless-student-manager-dev-students"
    error_message = "The DynamoDB table name is incorrect."
  }

  assert {
    condition     = aws_dynamodb_table.this.billing_mode == "PAY_PER_REQUEST"
    error_message = "The DynamoDB table must use PAY_PER_REQUEST billing mode."
  }

  assert {
    condition     = aws_dynamodb_table.this.hash_key == "PK"
    error_message = "The DynamoDB partition key must be PK."
  }

  assert {
    condition     = aws_dynamodb_table.this.range_key == "SK"
    error_message = "The DynamoDB sort key must be SK."
  }

  assert {
    condition     = aws_dynamodb_table.this.tags["Component"] == "students"
    error_message = "The Component tag must be students."
  }

  assert {
    condition     = aws_dynamodb_table.this.tags["DataClassification"] == "confidential"
    error_message = "The DataClassification tag must be confidential."
  }

  assert {
    condition = contains(
      [for index in aws_dynamodb_table.this.global_secondary_index : index.name],
      "gsi-status-name"
    )
    error_message = "The gsi-status-name index must exist."
  }

  assert {
    condition = contains(
      [for index in aws_dynamodb_table.this.global_secondary_index : index.name],
      "gsi-all-name"
    )
    error_message = "The gsi-all-name index must exist."
  }

  assert {
    condition     = output.gsi_status_name == "gsi-status-name"
    error_message = "The status/name GSI output is incorrect."
  }

  assert {
    condition     = output.gsi_all_name == "gsi-all-name"
    error_message = "The all/name GSI output is incorrect."
  }
}
