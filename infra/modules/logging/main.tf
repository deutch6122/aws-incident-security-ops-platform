locals {
  lambda_log_group_name       = coalesce(var.lambda_log_group_name, "/aws/lambda/${var.name_prefix}-portal")
  vpc_flowlogs_log_group_name = coalesce(var.vpc_flowlogs_log_group_name, "/vpc/${var.name_prefix}-flowlogs")
}

# Portal API Lambda log group (Task 15 consumes this). Created here only because
# no other module owns a Lambda log group. The ECS application log group and the
# EKS worker log group are intentionally NOT declared in this module: the ecs
# and eks modules already own them, so re-declaring them here would
# double-create. See README.md for the ownership table.
resource "aws_cloudwatch_log_group" "lambda" {
  count = var.enable_lambda_log_group ? 1 : 0

  name              = local.lambda_log_group_name
  retention_in_days = var.retention_in_days

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-portal-lambda-logs"
    Component = "logging"
    Role      = "lambda"
  })
}

# VPC Flow Logs destination log group. VPC Flow Logs are not owned by any other
# module, so this module owns the CloudWatch destination group.
resource "aws_cloudwatch_log_group" "vpc_flowlogs" {
  count = var.enable_vpc_flowlogs_log_group ? 1 : 0

  name              = local.vpc_flowlogs_log_group_name
  retention_in_days = var.retention_in_days

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-vpc-flowlogs"
    Component = "logging"
    Role      = "vpc-flowlogs"
  })
}

# Fargate built-in log router: EKS Fargate logging is driven by the k8s
# aws-observability ConfigMap, and the eks module owns the pod-execution-role
# logging grant plus the worker log group. This module deliberately declares no
# Fluent Bit log-router workload and no aws_cloudwatch_log_group for the /ecs or
# /eks log paths.
