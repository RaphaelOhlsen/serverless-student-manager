resource "aws_dynamodb_table" "this" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "PK"
  range_key = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "GSI1PK"
    type = "S"
  }

  attribute {
    name = "GSI1SK"
    type = "S"
  }

  attribute {
    name = "GSI2PK"
    type = "S"
  }

  attribute {
    name = "GSI2SK"
    type = "S"
  }

  attribute {
    name = "GSI3PK"
    type = "S"
  }

  attribute {
    name = "GSI3SK"
    type = "S"
  }

  global_secondary_index {
    name               = "gsi-actor-time"
    projection_type    = "INCLUDE"
    non_key_attributes = ["eventId", "eventType", "resourceType", "resourceId", "actorId", "occurredAt", "result", "correlationId"]

    key_schema {
      attribute_name = "GSI1PK"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "GSI1SK"
      key_type       = "RANGE"
    }
  }

  global_secondary_index {
    name               = "gsi-correlation-time"
    projection_type    = "INCLUDE"
    non_key_attributes = ["eventId", "eventType", "resourceType", "resourceId", "actorId", "occurredAt", "result", "correlationId"]

    key_schema {
      attribute_name = "GSI2PK"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "GSI2SK"
      key_type       = "RANGE"
    }
  }

  global_secondary_index {
    name               = "gsi-period-time"
    projection_type    = "INCLUDE"
    non_key_attributes = ["eventId", "eventType", "resourceType", "resourceId", "actorId", "occurredAt", "result", "correlationId"]

    key_schema {
      attribute_name = "GSI3PK"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "GSI3SK"
      key_type       = "RANGE"
    }
  }

  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery_enabled
  }

  deletion_protection_enabled = var.deletion_protection_enabled

  tags = merge(
    var.tags,
    {
      Component          = "audit"
      DataClassification = var.data_classification
    }
  )
}
