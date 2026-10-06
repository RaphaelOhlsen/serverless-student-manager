output "frontend_bucket_name" {
  description = "Name of the private frontend S3 bucket."
  value       = aws_s3_bucket.frontend.id
}

output "frontend_bucket_arn" {
  description = "ARN of the private frontend S3 bucket."
  value       = aws_s3_bucket.frontend.arn
}

output "frontend_cloudfront_distribution_id" {
  description = "ID of the frontend CloudFront distribution."
  value       = aws_cloudfront_distribution.frontend.id
}

output "frontend_cloudfront_distribution_arn" {
  description = "ARN of the frontend CloudFront distribution."
  value       = aws_cloudfront_distribution.frontend.arn
}

output "frontend_cloudfront_domain_name" {
  description = "Default CloudFront domain name for the frontend."
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "frontend_url" {
  description = "HTTPS URL of the frontend on the default CloudFront domain."
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}
