output "bucket_name" {
  description = "Name of the Portal_Storage S3 bucket."
  value       = aws_s3_bucket.portal.id
}

output "bucket_arn" {
  description = "ARN of the Portal_Storage S3 bucket."
  value       = aws_s3_bucket.portal.arn
}

output "bucket_regional_domain_name" {
  description = "Regional domain name of the bucket, used as the CloudFront S3 origin domain."
  value       = aws_s3_bucket.portal.bucket_regional_domain_name
}

output "reports_prefix" {
  description = "S3 key prefix for monthly report files placed by the A->B link."
  value       = var.reports_prefix
}
