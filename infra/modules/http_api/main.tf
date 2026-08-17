resource "aws_apigatewayv2_api" "this" {
  name          = var.api_name
  protocol_type = "HTTP"

  dynamic "cors_configuration" {
    for_each = length(var.cors_allow_origins) > 0 ? [1] : []

    content {
      allow_credentials = var.cors_allow_credentials
      allow_headers     = var.cors_allow_headers
      allow_methods     = var.cors_allow_methods
      allow_origins     = var.cors_allow_origins
      expose_headers    = var.cors_expose_headers
      max_age           = var.cors_max_age
    }
  }

  tags = merge(
    var.tags,
    {
      Component          = var.component
      DataClassification = var.data_classification
    }
  )
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id = aws_apigatewayv2_api.this.id

  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${var.api_name}-jwt"

  jwt_configuration {
    audience = var.jwt_audience
    issuer   = var.jwt_issuer
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  for_each = var.integrations

  api_id = aws_apigatewayv2_api.this.id

  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  integration_uri    = each.value.invoke_arn

  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "this" {
  for_each = var.routes

  api_id = aws_apigatewayv2_api.this.id

  route_key = each.value.route_key
  target    = "integrations/${aws_apigatewayv2_integration.lambda[each.value.integration_key].id}"

  authorization_type = each.value.authorization_type

  authorizer_id = (
    each.value.authorization_type == "JWT"
    ? aws_apigatewayv2_authorizer.jwt.id
    : null
  )
}

resource "aws_cloudwatch_log_group" "access" {
  count = var.access_logging_enabled ? 1 : 0

  name              = "/aws/apigateway/${var.api_name}"
  retention_in_days = var.access_log_retention_in_days

  tags = merge(
    var.tags,
    {
      Component          = var.component
      DataClassification = var.data_classification
    }
  )
}

resource "aws_apigatewayv2_stage" "default" {
  api_id = aws_apigatewayv2_api.this.id

  name        = "$default"
  auto_deploy = true

  dynamic "access_log_settings" {
    for_each = var.access_logging_enabled ? [1] : []

    content {
      destination_arn = aws_cloudwatch_log_group.access[0].arn

      format = jsonencode({
        requestId               = "$context.requestId"
        routeKey                = "$context.routeKey"
        status                  = "$context.status"
        responseLength          = "$context.responseLength"
        integrationErrorMessage = "$context.integrationErrorMessage"
      })
    }
  }

  tags = merge(
    var.tags,
    {
      Component          = var.component
      DataClassification = var.data_classification
    }
  )
}

resource "aws_lambda_permission" "api_gateway" {
  for_each = var.integrations

  statement_id = "AllowExecutionFromApiGateway"

  action        = "lambda:InvokeFunction"
  function_name = each.value.function_name
  qualifier     = each.value.alias_name

  principal  = "apigateway.amazonaws.com"
  source_arn = "${aws_apigatewayv2_api.this.execution_arn}/*/*/*"
}