mock_provider "aws" {
  mock_data "aws_cloudfront_cache_policy" {
    defaults = {
      id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    }
  }

  mock_data "aws_cloudfront_response_headers_policy" {
    defaults = {
      id = "67f7725c-6f97-4210-82d7-5512b31e9d03"
    }
  }

}

override_resource {
  target          = aws_s3_bucket.frontend
  override_during = plan
  values = {
    id                          = "serverless-student-manager-dev-frontend-123456789012"
    arn                         = "arn:aws:s3:::serverless-student-manager-dev-frontend-123456789012"
    bucket_regional_domain_name = "serverless-student-manager-dev-frontend-123456789012.s3.us-east-1.amazonaws.com"
  }
}

override_resource {
  target          = aws_cloudfront_distribution.frontend
  override_during = plan
  values = {
    id          = "E1234567890ABC"
    arn         = "arn:aws:cloudfront::123456789012:distribution/E1234567890ABC"
    domain_name = "d1234567890abc.cloudfront.net"
  }
}

override_data {
  target          = data.aws_iam_policy_document.frontend_bucket
  override_during = plan
  values = {
    json = jsonencode({
      Version   = "2012-10-17"
      Statement = []
    })
  }
}

variables {
  bucket_name       = "serverless-student-manager-dev-frontend-123456789012"
  distribution_name = "serverless-student-manager-dev-frontend"

  tags = {
    Project     = "serverless-student-manager"
    Environment = "dev"
    ManagedBy   = "Terraform"
    Workload    = "student-management"
  }
}

run "plans_private_frontend_hosting" {
  command = plan

  assert {
    condition     = aws_s3_bucket.frontend.force_destroy == false
    error_message = "The frontend bucket must not use force destroy."
  }

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.frontend.block_public_acls,
      aws_s3_bucket_public_access_block.frontend.block_public_policy,
      aws_s3_bucket_public_access_block.frontend.ignore_public_acls,
      aws_s3_bucket_public_access_block.frontend.restrict_public_buckets,
    ])
    error_message = "The frontend bucket must block all public access paths."
  }

  assert {
    condition     = aws_s3_bucket_ownership_controls.frontend.rule[0].object_ownership == "BucketOwnerEnforced"
    error_message = "The frontend bucket must enforce bucket ownership."
  }

  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.frontend.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    error_message = "The frontend bucket must use SSE-S3."
  }

  assert {
    condition     = aws_s3_bucket_versioning.frontend.versioning_configuration[0].status == "Enabled"
    error_message = "The frontend bucket must enable versioning."
  }

  assert {
    condition = (
      aws_cloudfront_origin_access_control.frontend.origin_access_control_origin_type == "s3" &&
      aws_cloudfront_origin_access_control.frontend.signing_behavior == "always" &&
      aws_cloudfront_origin_access_control.frontend.signing_protocol == "sigv4"
    )
    error_message = "CloudFront must use an always-signed SigV4 S3 OAC."
  }

  assert {
    condition = (
      aws_cloudfront_distribution.frontend.enabled &&
      aws_cloudfront_distribution.frontend.is_ipv6_enabled &&
      aws_cloudfront_distribution.frontend.default_root_object == "index.html" &&
      aws_cloudfront_distribution.frontend.price_class == "PriceClass_100"
    )
    error_message = "The CloudFront distribution baseline is incorrect."
  }

  assert {
    condition = (
      one(aws_cloudfront_distribution.frontend.default_cache_behavior).viewer_protocol_policy == "redirect-to-https" &&
      one(aws_cloudfront_distribution.frontend.default_cache_behavior).compress &&
      one(aws_cloudfront_distribution.frontend.default_cache_behavior).cache_policy_id == data.aws_cloudfront_cache_policy.caching_disabled.id &&
      one(aws_cloudfront_distribution.frontend.default_cache_behavior).response_headers_policy_id == data.aws_cloudfront_response_headers_policy.security_headers.id
    )
    error_message = "The default behavior must redirect to HTTPS, compress, disable caching and apply managed security headers."
  }

  assert {
    condition = (
      one(aws_cloudfront_distribution.frontend.ordered_cache_behavior).path_pattern == "/assets/*" &&
      aws_cloudfront_cache_policy.immutable_assets.min_ttl == 31536000 &&
      aws_cloudfront_cache_policy.immutable_assets.default_ttl == 31536000 &&
      aws_cloudfront_cache_policy.immutable_assets.max_ttl == 31536000
    )
    error_message = "Fingerprinted assets must use the one-year immutable-compatible cache policy."
  }

  assert {
    condition = (
      one(one(aws_cloudfront_distribution.frontend.default_cache_behavior).function_association).event_type == "viewer-request" &&
      length(one(aws_cloudfront_distribution.frontend.ordered_cache_behavior).function_association) == 0 &&
      strcontains(aws_cloudfront_function.spa_rewrite.code, "lastSegment.indexOf('.') === -1") &&
      strcontains(aws_cloudfront_function.spa_rewrite.code, "request.uri = '/index.html'")
    )
    error_message = "The SPA rewrite must apply only to extensionless paths outside the assets behavior."
  }

  assert {
    condition = (
      one(aws_cloudfront_distribution.frontend.viewer_certificate).cloudfront_default_certificate &&
      aws_cloudfront_distribution.frontend.aliases == null &&
      length(aws_cloudfront_distribution.frontend.custom_error_response) == 0
    )
    error_message = "The distribution must use the default certificate without aliases or global error fallback."
  }

  assert {
    condition = (
      length(data.aws_iam_policy_document.frontend_bucket.statement) == 2 &&
      toset(one([
        for statement in data.aws_iam_policy_document.frontend_bucket.statement : statement.actions
        if statement.sid == "AllowCloudFrontReadViaOAC"
      ])) == toset(["s3:GetObject"]) &&
      toset(one([
        for statement in data.aws_iam_policy_document.frontend_bucket.statement : one(statement.principals).identifiers
        if statement.sid == "AllowCloudFrontReadViaOAC"
      ])) == toset(["cloudfront.amazonaws.com"]) &&
      one(one([
        for statement in data.aws_iam_policy_document.frontend_bucket.statement : statement.condition
        if statement.sid == "AllowCloudFrontReadViaOAC"
      ])).variable == "AWS:SourceArn" &&
      toset(one(one([
        for statement in data.aws_iam_policy_document.frontend_bucket.statement : statement.condition
        if statement.sid == "AllowCloudFrontReadViaOAC"
      ])).values) == toset([aws_cloudfront_distribution.frontend.arn])
    )
    error_message = "The bucket policy must grant read only to CloudFront and restrict it by distribution ARN."
  }

  assert {
    condition = (
      one([
        for statement in data.aws_iam_policy_document.frontend_bucket.statement : statement.effect
        if statement.sid == "DenyInsecureTransport"
      ]) == "Deny" &&
      toset(one([
        for statement in data.aws_iam_policy_document.frontend_bucket.statement : statement.actions
        if statement.sid == "DenyInsecureTransport"
      ])) == toset(["s3:*"]) &&
      one(one([
        for statement in data.aws_iam_policy_document.frontend_bucket.statement : statement.condition
        if statement.sid == "DenyInsecureTransport"
      ])).variable == "aws:SecureTransport" &&
      toset(one(one([
        for statement in data.aws_iam_policy_document.frontend_bucket.statement : statement.condition
        if statement.sid == "DenyInsecureTransport"
      ])).values) == toset(["false"])
    )
    error_message = "The bucket policy must deny all insecure transport."
  }

  assert {
    condition = (
      output.frontend_bucket_name == "serverless-student-manager-dev-frontend-123456789012" &&
      output.frontend_bucket_arn == "arn:aws:s3:::serverless-student-manager-dev-frontend-123456789012" &&
      output.frontend_cloudfront_distribution_id == "E1234567890ABC" &&
      output.frontend_cloudfront_distribution_arn == "arn:aws:cloudfront::123456789012:distribution/E1234567890ABC" &&
      output.frontend_cloudfront_domain_name == "d1234567890abc.cloudfront.net" &&
      output.frontend_url == "https://d1234567890abc.cloudfront.net"
    )
    error_message = "The frontend hosting outputs are incomplete or incorrect."
  }
}
