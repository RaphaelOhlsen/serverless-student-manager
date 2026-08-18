data "aws_iam_policy_document" "trust" {
  statement {
    sid     = "GitHubActionsOidc"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [var.oidc_subject]
    }
  }
}

resource "aws_iam_role" "this" {
  name                 = var.role_name
  description          = var.role_description
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  max_session_duration = var.max_session_duration

  tags = merge(
    var.tags,
    {
      Component          = "operational-access"
      DataClassification = var.data_classification
    }
  )
}

resource "aws_iam_policy" "this" {
  name        = var.policy_name
  description = var.policy_description
  policy      = var.policy_json

  tags = merge(
    var.tags,
    {
      Component          = "operational-access"
      DataClassification = var.data_classification
    }
  )
}

resource "aws_iam_role_policy_attachment" "this" {
  role       = aws_iam_role.this.name
  policy_arn = aws_iam_policy.this.arn
}
