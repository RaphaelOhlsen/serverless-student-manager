resource "aws_s3_bucket" "terraform_state" {
  bucket        = var.state_bucket_name
  force_destroy = false
  tags          = local.state_bucket_tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "terraform_state_bucket" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.terraform_state.arn,
      "${aws_s3_bucket.terraform_state.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  policy = data.aws_iam_policy_document.terraform_state_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.terraform_state]
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url = local.github_oidc_url

  client_id_list = [local.github_oidc_audience]
  tags           = local.oidc_provider_tags
}

data "aws_iam_policy_document" "github_actions_dev_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = [local.github_oidc_audience]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.github_dev_subject]
    }
  }
}

data "aws_iam_policy_document" "github_actions_prod_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = [local.github_oidc_audience]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.github_prod_subject]
    }
  }
}

resource "aws_iam_role" "github_actions_dev_deployment" {
  name                 = "student-manager-github-dev-deploy"
  description          = "Temporary GitHub Actions deployment role for dev."
  assume_role_policy   = data.aws_iam_policy_document.github_actions_dev_trust.json
  max_session_duration = 3600
  tags                 = local.dev_deployment_tags
}

resource "aws_iam_role" "github_actions_prod_deployment" {
  name                 = "student-manager-github-prod-deploy"
  description          = "Temporary GitHub Actions deployment role for prod."
  assume_role_policy   = data.aws_iam_policy_document.github_actions_prod_trust.json
  max_session_duration = 3600
  tags                 = local.prod_deployment_tags
}

data "aws_iam_policy_document" "terraform_state_dev" {
  statement {
    sid       = "ListDevStatePath"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.terraform_state.arn]

    condition {
      test     = "StringEquals"
      variable = "s3:prefix"
      values = [
        local.dev_state_key,
        local.dev_lockfile_key,
      ]
    }
  }

  statement {
    sid     = "ReadWriteDevState"
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:PutObject"]
    resources = [
      "${aws_s3_bucket.terraform_state.arn}/${local.dev_state_key}",
    ]
  }

  statement {
    sid     = "ManageDevLockfile"
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "${aws_s3_bucket.terraform_state.arn}/${local.dev_lockfile_key}",
    ]
  }
}

data "aws_iam_policy_document" "terraform_state_prod" {
  statement {
    sid       = "ListProdStatePath"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.terraform_state.arn]

    condition {
      test     = "StringEquals"
      variable = "s3:prefix"
      values = [
        local.prod_state_key,
        local.prod_lockfile_key,
      ]
    }
  }

  statement {
    sid     = "ReadWriteProdState"
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:PutObject"]
    resources = [
      "${aws_s3_bucket.terraform_state.arn}/${local.prod_state_key}",
    ]
  }

  statement {
    sid     = "ManageProdLockfile"
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "${aws_s3_bucket.terraform_state.arn}/${local.prod_lockfile_key}",
    ]
  }
}

resource "aws_iam_policy" "terraform_state_dev" {
  name        = "student-manager-terraform-state-dev"
  description = "Least-privilege access to the dev Terraform state and lockfile."
  policy      = data.aws_iam_policy_document.terraform_state_dev.json
  tags        = local.dev_deployment_tags
}

resource "aws_iam_policy" "terraform_state_prod" {
  name        = "student-manager-terraform-state-prod"
  description = "Least-privilege access to the prod Terraform state and lockfile."
  policy      = data.aws_iam_policy_document.terraform_state_prod.json
  tags        = local.prod_deployment_tags
}

resource "aws_iam_role_policy_attachment" "terraform_state_dev" {
  role       = aws_iam_role.github_actions_dev_deployment.name
  policy_arn = aws_iam_policy.terraform_state_dev.arn
}

data "aws_partition" "current" {}

data "aws_caller_identity" "current" {}

resource "aws_iam_role_policy" "lambda_application_release_dev" {
  name = "student-manager-dev-lambda-application-release"
  role = aws_iam_role.github_actions_dev_deployment.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ReleaseDevLambdaApplicationCode"
      Effect = "Allow"
      Action = [
        "lambda:GetAlias",
        "lambda:GetFunctionConfiguration",
        "lambda:PublishVersion",
        "lambda:UpdateAlias",
        "lambda:UpdateFunctionCode",
      ]
      Resource = [
        "arn:${data.aws_partition.current.partition}:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:serverless-student-manager-dev-students-api",
        "arn:${data.aws_partition.current.partition}:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:serverless-student-manager-dev-users-api",
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "terraform_state_prod" {
  role       = aws_iam_role.github_actions_prod_deployment.name
  policy_arn = aws_iam_policy.terraform_state_prod.arn
}
