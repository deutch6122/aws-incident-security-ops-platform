output "web_acl_arn" {
  description = "ARN of the CloudFront-scope WAF Web ACL."
  value       = aws_wafv2_web_acl.cloudfront.arn
}

output "web_acl_id" {
  description = "ID of the CloudFront-scope WAF Web ACL."
  value       = aws_wafv2_web_acl.cloudfront.id
}

output "waf_log_group_name" {
  description = "WAF log group name, or null when logging is disabled."
  value       = var.waf_logging_enabled ? aws_cloudwatch_log_group.waf[0].name : null
}

output "waf_logs_kms_key_arn" {
  description = "KMS key ARN for WAF logs, or null when customer-managed encryption is disabled."
  value       = local.kms_enabled ? aws_kms_key.waf_logs[0].arn : null
}
