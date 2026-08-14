data "aws_iam_policy_document" "assume_role" {
  statement {
    sid     = "AllowLambdaServiceToAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name = "${var.function_name}-execution"

  assume_role_policy = data.aws_iam_policy_document.assume_role.json

  tags = merge(
    var.tags,
    {
      Component          = var.component
      DataClassification = var.data_classification
    }
  )
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_in_days

  tags = merge(
    var.tags,
    {
      Component          = var.component
      DataClassification = var.data_classification
    }
  )
}

data "aws_iam_policy_document" "logging" {
  statement {
    sid    = "WriteLambdaLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = [
      "${aws_cloudwatch_log_group.this.arn}:*",
    ]
  }
}

resource "aws_iam_role_policy" "logging" {
  name   = "${var.function_name}-logging"
  role   = aws_iam_role.this.name
  policy = data.aws_iam_policy_document.logging.json
}

resource "aws_iam_role_policy" "additional" {
  count = var.additional_iam_policy_json == null ? 0 : 1

  name   = "${var.function_name}-service"
  role   = aws_iam_role.this.name
  policy = var.additional_iam_policy_json
}

resource "aws_lambda_function" "this" {
  function_name = var.function_name
  description   = var.description

  role = aws_iam_role.this.arn

  package_type = "Zip"

  runtime       = var.runtime
  handler       = var.handler
  architectures = var.architectures

  memory_size = var.memory_size
  timeout     = var.timeout

  # The local package is used only to bootstrap the Lambda function.
  # Subsequent application releases are deployed by GitHub Actions.
  filename = var.bootstrap_package_filename

  publish = false

  environment {
    variables = var.environment_variables
  }

  tags = merge(
    var.tags,
    {
      Component          = var.component
      DataClassification = var.data_classification
    }
  )

  lifecycle {
    # Terraform uses the package only to bootstrap the function.
    # GitHub Actions owns subsequent application code deployments.
    ignore_changes = [
      filename,
    ]
  }

  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role_policy.logging,
    aws_iam_role_policy.additional,
  ]
}

resource "aws_lambda_alias" "live" {
  name        = var.alias_name
  description = "Stable alias used by application integrations."

  function_name    = aws_lambda_function.this.function_name
  function_version = "$LATEST"

  lifecycle {
    # GitHub Actions owns promotion and rollback of published versions.
    ignore_changes = [
      function_version,
    ]
  }
}
