output "flow_log_id" {
  description = "ID of the VPC flow log resource."
  value       = aws_flow_log.this.id
}

output "vpc_flowlogs_log_group_name" {
  description = "VPC Flow Logs CloudWatch Logs group name (owned by this module)."
  value       = aws_cloudwatch_log_group.vpc_flowlogs.name
}

output "vpc_flowlogs_log_group_arn" {
  description = "VPC Flow Logs CloudWatch Logs group ARN (owned by this module)."
  value       = aws_cloudwatch_log_group.vpc_flowlogs.arn
}

output "vpc_flowlogs_role_arn" {
  description = "ARN of the IAM role assumed by the VPC Flow Logs service to write to the log group."
  value       = aws_iam_role.flowlogs.arn
}
