output "distribution_id" {
  description = "ID of the Portal_CDN CloudFront distribution."
  value       = aws_cloudfront_distribution.this.id
}

output "distribution_arn" {
  description = "ARN of the Portal_CDN CloudFront distribution (passed to the s3-portal bucket policy SourceArn condition)."
  value       = aws_cloudfront_distribution.this.arn
}

output "distribution_domain_name" {
  description = "Domain name of the Portal_CDN CloudFront distribution."
  value       = aws_cloudfront_distribution.this.domain_name
}

output "oac_id" {
  description = "ID of the Origin Access Control used for the S3 origin."
  value       = aws_cloudfront_origin_access_control.s3.id
}

output "web_acl_arn" {
  description = "ARN of the WAF Web ACL associated with the distribution."
  value       = aws_wafv2_web_acl.this.arn
}

output "price_class" {
  description = "CloudFront price class in effect."
  value       = var.price_class
}
