output "lambda_log_group_name" {
  description = "Portal Lambda CloudWatch Logs group name, or null when disabled."
  value       = try(aws_cloudwatch_log_group.lambda[0].name, null)
}

output "lambda_log_group_arn" {
  description = "Portal Lambda CloudWatch Logs group ARN, or null when disabled."
  value       = try(aws_cloudwatch_log_group.lambda[0].arn, null)
}

output "vpc_flowlogs_log_group_name" {
  description = "VPC Flow Logs CloudWatch Logs group name, or null when disabled."
  value       = try(aws_cloudwatch_log_group.vpc_flowlogs[0].name, null)
}

output "vpc_flowlogs_log_group_arn" {
  description = "VPC Flow Logs CloudWatch Logs group ARN, or null when disabled."
  value       = try(aws_cloudwatch_log_group.vpc_flowlogs[0].arn, null)
}
