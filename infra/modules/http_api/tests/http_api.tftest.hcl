mock_provider "aws" {
  mock_resource "aws_apigatewayv2_api" {
    defaults = {
      id            = "abc123def4"
      execution_arn = "arn:aws:execute-api:us-east-1:123456789012:abc123def4"
    }
  }

  mock_resource "aws_apigatewayv2_authorizer" {
    defaults = {
      id = "authorizer123"
    }
  }

  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/apigateway/serverless-student-manager-dev-http-api"
    }
  }
}

variables {
  api_name = "serverless-student-manager-dev-http-api"

  jwt_issuer = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example"

  jwt_audience = [
    "example-client-id",
  ]

  integrations = {
    students = {
      invoke_arn    = "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:123456789012:function:students-api:live/invocations"
      function_name = "students-api"
      alias_name    = "live"
    }
    users = {
      invoke_arn    = "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:123456789012:function:users-api:live/invocations"
      function_name = "users-api"
      alias_name    = "live"
    }
  }

  routes = {
    health = {
      route_key          = "GET /health"
      integration_key    = "students"
      authorization_type = "NONE"
    }

    get_student = {
      route_key          = "GET /students/{studentId}"
      integration_key    = "students"
      authorization_type = "JWT"
    }

    list_students = {
      route_key          = "GET /students"
      integration_key    = "students"
      authorization_type = "JWT"
    }
    create_student = {
      route_key          = "POST /students"
      integration_key    = "students"
      authorization_type = "JWT"
    }
    activate_current_user = {
      route_key          = "POST /users/me/activation"
      integration_key    = "users"
      authorization_type = "JWT"
    }
    get_current_user = {
      route_key          = "GET /users/me"
      integration_key    = "users"
      authorization_type = "JWT"
    }
  }

  cors_allow_origins = [
    "http://localhost:5173",
  ]

  cors_allow_methods = [
    "GET",
    "POST",
    "PUT",
    "DELETE",
    "OPTIONS",
  ]

  cors_allow_headers = [
    "Authorization",
    "Content-Type",
    "Idempotency-Key",
  ]

  cors_allow_credentials = false
  cors_max_age           = 300

  access_logging_enabled       = true
  access_log_retention_in_days = 14

  component           = "http-api"
  data_classification = "confidential"

  tags = {
    Project     = "serverless-student-manager"
    Environment = "dev"
    ManagedBy   = "Terraform"
    Workload    = "student-management"
  }
}

run "plans_http_api" {
  command = plan

  assert {
    condition     = aws_apigatewayv2_api.this.name == "serverless-student-manager-dev-http-api"
    error_message = "The HTTP API name is incorrect."
  }

  assert {
    condition = contains(
      one(aws_apigatewayv2_api.this.cors_configuration).allow_headers,
      "Idempotency-Key"
    )
    error_message = "CORS must allow the Idempotency-Key header."
  }

  assert {
    condition     = aws_apigatewayv2_api.this.protocol_type == "HTTP"
    error_message = "The API Gateway protocol type must be HTTP."
  }

  assert {
    condition = contains(
      one(aws_apigatewayv2_api.this.cors_configuration).allow_origins,
      "http://localhost:5173"
    )
    error_message = "The HTTP API CORS configuration must allow the configured frontend origin."
  }

  assert {
    condition = contains(
      one(aws_apigatewayv2_api.this.cors_configuration).allow_methods,
      "GET"
    )
    error_message = "The HTTP API CORS configuration must allow GET."
  }

  assert {
    condition = contains(
      one(aws_apigatewayv2_api.this.cors_configuration).allow_methods,
      "POST"
    )
    error_message = "The HTTP API CORS configuration must allow POST."
  }

  assert {
    condition = contains(
      one(aws_apigatewayv2_api.this.cors_configuration).allow_methods,
      "OPTIONS"
    )
    error_message = "The HTTP API CORS configuration must allow OPTIONS."
  }

  assert {
    condition = contains(
      one(aws_apigatewayv2_api.this.cors_configuration).allow_headers,
      "Authorization"
    )
    error_message = "The HTTP API CORS configuration must allow the Authorization header."
  }

  assert {
    condition = contains(
      one(aws_apigatewayv2_api.this.cors_configuration).allow_headers,
      "Content-Type"
    )
    error_message = "The HTTP API CORS configuration must allow the Content-Type header."
  }

  assert {
    condition     = one(aws_apigatewayv2_api.this.cors_configuration).allow_credentials == false
    error_message = "CORS credentials must be disabled."
  }

  assert {
    condition     = one(aws_apigatewayv2_api.this.cors_configuration).max_age == 300
    error_message = "The CORS preflight cache duration must be 300 seconds."
  }

  assert {
    condition     = aws_apigatewayv2_authorizer.jwt.authorizer_type == "JWT"
    error_message = "The API authorizer type must be JWT."
  }

  assert {
    condition = contains(
      aws_apigatewayv2_authorizer.jwt.identity_sources,
      "$request.header.Authorization"
    )
    error_message = "The JWT authorizer must read the Authorization header."
  }

  assert {
    condition = (
      one(aws_apigatewayv2_authorizer.jwt.jwt_configuration).issuer
      == "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example"
    )
    error_message = "The JWT issuer is incorrect."
  }

  assert {
    condition = contains(
      one(aws_apigatewayv2_authorizer.jwt.jwt_configuration).audience,
      "example-client-id"
    )
    error_message = "The JWT audience is incorrect."
  }

  assert {
    condition     = aws_apigatewayv2_integration.lambda["students"].integration_type == "AWS_PROXY"
    error_message = "The students integration must use AWS_PROXY."
  }

  assert {
    condition     = aws_apigatewayv2_integration.lambda["students"].integration_method == "POST"
    error_message = "Lambda proxy integrations must use POST as the integration method."
  }

  assert {
    condition = (
      aws_apigatewayv2_integration.lambda["students"].integration_uri
      == "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:123456789012:function:students-api:live/invocations"
    )
    error_message = "The students integration must invoke the live Lambda alias."
  }

  assert {
    condition     = aws_apigatewayv2_integration.lambda["students"].payload_format_version == "2.0"
    error_message = "The Lambda integration payload format must be 2.0."
  }

  assert {
    condition     = aws_apigatewayv2_integration.lambda["users"].integration_type == "AWS_PROXY"
    error_message = "The users integration must use AWS_PROXY."
  }

  assert {
    condition     = aws_apigatewayv2_route.this["health"].route_key == "GET /health"
    error_message = "The public health route is incorrect."
  }

  assert {
    condition     = aws_apigatewayv2_route.this["health"].authorization_type == "NONE"
    error_message = "The health route must be public."
  }

  assert {
    condition     = aws_apigatewayv2_route.this["get_student"].route_key == "GET /students/{studentId}"
    error_message = "The get-student route is incorrect."
  }

  assert {
    condition     = aws_apigatewayv2_route.this["get_student"].authorization_type == "JWT"
    error_message = "The get-student route must require JWT authorization."
  }

  assert {
    condition     = aws_apigatewayv2_route.this["list_students"].route_key == "GET /students"
    error_message = "The list-students route key is incorrect."
  }

  assert {
    condition     = aws_apigatewayv2_route.this["list_students"].authorization_type == "JWT"
    error_message = "The list-students route must use JWT authorization."
  }

  assert {
    condition     = aws_apigatewayv2_route.this["create_student"].route_key == "POST /students"
    error_message = "The create-student route key is incorrect."
  }

  assert {
    condition     = aws_apigatewayv2_route.this["create_student"].authorization_type == "JWT"
    error_message = "The create-student route must use JWT authorization."
  }

  assert {
    condition     = aws_apigatewayv2_route.this["activate_current_user"].route_key == "POST /users/me/activation"
    error_message = "The activation route key is incorrect."
  }

  assert {
    condition     = aws_apigatewayv2_route.this["activate_current_user"].authorization_type == "JWT"
    error_message = "The activation route must use JWT authorization."
  }

  assert {
    condition     = aws_apigatewayv2_route.this["get_current_user"].route_key == "GET /users/me"
    error_message = "The self-profile route key is incorrect."
  }

  assert {
    condition     = aws_apigatewayv2_route.this["get_current_user"].authorization_type == "JWT"
    error_message = "The self-profile route must use JWT authorization."
  }

  assert {
    condition     = aws_apigatewayv2_stage.default.name == "$default"
    error_message = "The HTTP API must use the default stage."
  }

  assert {
    condition     = aws_apigatewayv2_stage.default.auto_deploy
    error_message = "The default HTTP API stage must use auto deploy."
  }

  assert {
    condition     = length(aws_cloudwatch_log_group.access) == 1
    error_message = "An HTTP API access log group must be created when access logging is enabled."
  }

  assert {
    condition     = aws_cloudwatch_log_group.access[0].name == "/aws/apigateway/serverless-student-manager-dev-http-api"
    error_message = "The HTTP API access log group name is incorrect."
  }

  assert {
    condition     = aws_cloudwatch_log_group.access[0].retention_in_days == 14
    error_message = "HTTP API access logs must be retained for 14 days."
  }

  assert {
    condition     = length(aws_apigatewayv2_stage.default.access_log_settings) == 1
    error_message = "The default stage must have access logging configured."
  }

  assert {
    condition = strcontains(
      one(aws_apigatewayv2_stage.default.access_log_settings).format,
      "$context.requestId"
    )
    error_message = "The access log format must include the API Gateway request ID."
  }

  assert {
    condition = strcontains(
      one(aws_apigatewayv2_stage.default.access_log_settings).format,
      "$context.routeKey"
    )
    error_message = "The access log format must include the route key."
  }

  assert {
    condition = strcontains(
      one(aws_apigatewayv2_stage.default.access_log_settings).format,
      "$context.status"
    )
    error_message = "The access log format must include the HTTP status."
  }

  assert {
    condition     = aws_lambda_permission.api_gateway["students"].principal == "apigateway.amazonaws.com"
    error_message = "API Gateway must be the Lambda invocation principal."
  }

  assert {
    condition     = aws_lambda_permission.api_gateway["students"].action == "lambda:InvokeFunction"
    error_message = "API Gateway must be allowed to invoke the Lambda function."
  }

  assert {
    condition     = aws_lambda_permission.api_gateway["students"].function_name == "students-api"
    error_message = "The Lambda invocation permission must target the students-api function."
  }

  assert {
    condition     = aws_lambda_permission.api_gateway["students"].qualifier == "live"
    error_message = "API Gateway invocation permission must target the live Lambda alias."
  }

  assert {
    condition     = aws_apigatewayv2_api.this.tags["Component"] == "http-api"
    error_message = "The Component tag must be http-api."
  }

  assert {
    condition     = aws_apigatewayv2_api.this.tags["DataClassification"] == "confidential"
    error_message = "The DataClassification tag must be confidential."
  }

  assert {
    condition     = aws_cloudwatch_log_group.access[0].tags["Component"] == "http-api"
    error_message = "The access log group Component tag must be http-api."
  }

  assert {
    condition     = aws_cloudwatch_log_group.access[0].tags["DataClassification"] == "confidential"
    error_message = "The access log group DataClassification tag must be confidential."
  }
}

run "wires_computed_references" {
  command = apply

  assert {
    condition = (
      aws_apigatewayv2_route.this["create_student"].authorizer_id
      == aws_apigatewayv2_authorizer.jwt.id
    )
    error_message = "The create-student route must use the configured JWT authorizer."
  }

  assert {
    condition = (
      aws_apigatewayv2_route.this["create_student"].target
      == "integrations/${aws_apigatewayv2_integration.lambda["students"].id}"
    )
    error_message = "The create-student route must use the students integration."
  }

  assert {
    condition = (
      aws_apigatewayv2_route.this["get_student"].authorizer_id
      == aws_apigatewayv2_authorizer.jwt.id
    )
    error_message = "The get-student route must use the configured JWT authorizer."
  }


  assert {
    condition = (
      aws_apigatewayv2_route.this["list_students"].authorizer_id
      == aws_apigatewayv2_authorizer.jwt.id
    )
    error_message = "The list-students route must use the configured JWT authorizer."
  }

  assert {
    condition = (
      aws_apigatewayv2_route.this["get_current_user"].authorizer_id
      == aws_apigatewayv2_authorizer.jwt.id
    )
    error_message = "The self-profile route must use the configured JWT authorizer."
  }

  assert {
    condition = (
      aws_apigatewayv2_route.this["get_current_user"].target
      == "integrations/${aws_apigatewayv2_integration.lambda["users"].id}"
    )
    error_message = "The self-profile route must use the users integration."
  }

  assert {
    condition = (
      aws_lambda_permission.api_gateway["students"].source_arn
      == "${aws_apigatewayv2_api.this.execution_arn}/*/*/*"
    )
    error_message = "The Lambda invocation permission must be restricted to the HTTP API execution ARN."
  }
}


run "plans_without_cors_or_access_logging" {
  command = plan

  variables {
    cors_allow_origins     = []
    access_logging_enabled = false
  }

  assert {
    condition     = length(aws_apigatewayv2_api.this.cors_configuration) == 0
    error_message = "The HTTP API must not configure CORS when no allowed origins are provided."
  }

  assert {
    condition     = length(aws_cloudwatch_log_group.access) == 0
    error_message = "No access log group must be created when access logging is disabled."
  }

  assert {
    condition     = length(aws_apigatewayv2_stage.default.access_log_settings) == 0
    error_message = "The default stage must not configure access logging when it is disabled."
  }
}
