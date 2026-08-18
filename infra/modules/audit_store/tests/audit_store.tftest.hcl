mock_provider "aws" {}

variables {
  table_name                     = "serverless-student-manager-dev-audit-events"
  point_in_time_recovery_enabled = false
  deletion_protection_enabled    = false
  data_classification            = "confidential"

  tags = {
    Environment = "dev"
  }
}

run "plans_audit_table" {
  command = plan

  assert {
    condition     = aws_dynamodb_table.this.name == "serverless-student-manager-dev-audit-events"
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
    condition     = aws_dynamodb_table.this.tags["Component"] == "audit"
    error_message = "The Component tag must be audit."
  }

  assert {
    condition     = aws_dynamodb_table.this.tags["DataClassification"] == "confidential"
    error_message = "The DataClassification tag must be confidential."
  }

  assert {
    condition = contains(
      [for index in aws_dynamodb_table.this.global_secondary_index : index.name],
      "gsi-actor-time"
    )
    error_message = "The gsi-actor-time index must exist."
  }

  assert {
    condition = contains(
      [for index in aws_dynamodb_table.this.global_secondary_index : index.name],
      "gsi-correlation-time"
    )
    error_message = "The gsi-correlation-time index must exist."
  }

  assert {
    condition = contains(
      [for index in aws_dynamodb_table.this.global_secondary_index : index.name],
      "gsi-period-time"
    )
    error_message = "The gsi-period-time index must exist."
  }

  assert {
    condition = alltrue([
      for index in aws_dynamodb_table.this.global_secondary_index :
      index.name != "gsi-actor-time" || (
        index.projection_type == "INCLUDE" &&
        contains([for key in index.key_schema : "${key.attribute_name}:${key.key_type}"], "GSI1PK:HASH") &&
        contains([for key in index.key_schema : "${key.attribute_name}:${key.key_type}"], "GSI1SK:RANGE")
      )
    ])
    error_message = "The gsi-actor-time key schema or projection is incorrect."
  }

  assert {
    condition = alltrue([
      for index in aws_dynamodb_table.this.global_secondary_index :
      index.name != "gsi-correlation-time" || (
        index.projection_type == "INCLUDE" &&
        contains([for key in index.key_schema : "${key.attribute_name}:${key.key_type}"], "GSI2PK:HASH") &&
        contains([for key in index.key_schema : "${key.attribute_name}:${key.key_type}"], "GSI2SK:RANGE")
      )
    ])
    error_message = "The gsi-correlation-time key schema or projection is incorrect."
  }

  assert {
    condition = alltrue([
      for index in aws_dynamodb_table.this.global_secondary_index :
      index.name != "gsi-period-time" || (
        index.projection_type == "INCLUDE" &&
        contains([for key in index.key_schema : "${key.attribute_name}:${key.key_type}"], "GSI3PK:HASH") &&
        contains([for key in index.key_schema : "${key.attribute_name}:${key.key_type}"], "GSI3SK:RANGE")
      )
    ])
    error_message = "The gsi-period-time key schema or projection is incorrect."
  }

  assert {
    condition = alltrue([
      for index in aws_dynamodb_table.this.global_secondary_index :
      alltrue([
        for attribute in ["eventId", "eventType", "resourceType", "resourceId", "actorId", "occurredAt", "result", "correlationId"] :
        contains(index.non_key_attributes, attribute)
      ])
    ])
    error_message = "All GSIs must project the approved audit summary attributes."
  }

  assert {
    condition     = aws_dynamodb_table.this.ttl[0].enabled == true
    error_message = "TTL must be enabled."
  }

  assert {
    condition     = aws_dynamodb_table.this.ttl[0].attribute_name == "expiresAt"
    error_message = "TTL must use the expiresAt attribute."
  }

  assert {
    condition     = output.table_name == "serverless-student-manager-dev-audit-events"
    error_message = "The table_name output is incorrect."
  }

  assert {
    condition     = output.gsi_actor_time == "gsi-actor-time"
    error_message = "The actor/time GSI output is incorrect."
  }

  assert {
    condition     = output.gsi_correlation_time == "gsi-correlation-time"
    error_message = "The correlation/time GSI output is incorrect."
  }

  assert {
    condition     = output.gsi_period_time == "gsi-period-time"
    error_message = "The period/time GSI output is incorrect."
  }
}
