# logging module ownership boundary (single owner per log group):
#   - ECS Backend log group  -> ecs module
#   - EKS worker log group   -> eks module
#   - Portal Lambda log group -> lambda module (aws_cloudwatch_log_group.portal)
#   - VPC Flow Logs log group -> THIS module
# This module deliberately creates NO Lambda / ECS / EKS log group; doing so
# would double-create groups owned elsewhere. It owns only the VPC Flow Logs
# destination group, the flow-log delivery IAM role, and the aws_flow_log.

data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  vpc_flowlogs_log_group_name = coalesce(var.vpc_flowlogs_log_group_name, "/vpc/${var.name_prefix}-flowlogs")
}

# VPC Flow Logs destination log group (owned solely by this module).
resource "aws_cloudwatch_log_group" "vpc_flowlogs" {
  name              = local.vpc_flowlogs_log_group_name
  retention_in_days = var.retention_in_days

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-vpc-flowlogs"
    Component = "logging"
    Role      = "vpc-flowlogs"
  })
}

# Trust policy: assumable only by the VPC Flow Logs service, and only for flow
# logs owned by this account and Region (confused-deputy protection).
data "aws_iam_policy_document" "flowlogs_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values = [
        "arn:${data.aws_partition.current.partition}:ec2:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:vpc-flow-log/*"
      ]
    }
  }
}

resource "aws_iam_role" "flowlogs" {
  name               = "${var.name_prefix}-vpc-flowlogs-role"
  assume_role_policy = data.aws_iam_policy_document.flowlogs_trust.json

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-vpc-flowlogs-role"
    Component = "logging"
    Role      = "vpc-flowlogs"
  })
}

# CloudWatch Logs write permission scoped to the dedicated flow-log group ARN
# (and its log streams). partition / region / account are NOT hard-coded: the
# ARN is taken from the log group resource, and the wildcard-exception actions
# are region-scoped via aws:RequestedRegion.
data "aws_iam_policy_document" "flowlogs" {
  # AWS documents CreateLogGroup as part of the delivery-role permissions. The
  # group is created by Terraform, but retain the action for service validation
  # and scope it to this exact group rather than Resource = "*".
  statement {
    sid       = "FlowLogsCreateGroup"
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup"]
    resources = [aws_cloudwatch_log_group.vpc_flowlogs.arn]
  }

  statement {
    sid    = "FlowLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.vpc_flowlogs.arn}:log-stream:*"]
  }

  # DescribeLogStreams supports log-group resource scoping.
  statement {
    sid       = "FlowLogsDescribeStreams"
    effect    = "Allow"
    actions   = ["logs:DescribeLogStreams"]
    resources = [aws_cloudwatch_log_group.vpc_flowlogs.arn]
  }

  # DescribeLogGroups has no resource-level scope, so constrain its required
  # wildcard with the requested Region.
  statement {
    sid       = "FlowLogsDescribeGroups"
    effect    = "Allow"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [data.aws_region.current.name]
    }
  }
}

resource "aws_iam_role_policy" "flowlogs" {
  name   = "${var.name_prefix}-vpc-flowlogs-policy"
  role   = aws_iam_role.flowlogs.id
  policy = data.aws_iam_policy_document.flowlogs.json
}

# Capture ALL traffic for the supplied VPC into the dedicated CloudWatch Logs
# group via the dedicated delivery role. Dependencies on the group and role are
# expressed by reference.
resource "aws_flow_log" "this" {
  vpc_id                   = var.vpc_id
  traffic_type             = "ALL"
  log_destination_type     = "cloud-watch-logs"
  log_destination          = aws_cloudwatch_log_group.vpc_flowlogs.arn
  iam_role_arn             = aws_iam_role.flowlogs.arn
  max_aggregation_interval = 600

  # iam_role_arn alone depends only on the role body. Ensure its inline policy
  # is attached before EC2 validates and starts the CloudWatch delivery.
  depends_on = [aws_iam_role_policy.flowlogs]

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-vpc-flowlog"
    Component = "logging"
    Role      = "vpc-flowlog"
  })
}
