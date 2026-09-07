data "aws_partition" "current" {}
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  web_acl_name   = "${var.name_prefix}-cloudfront-web-acl"
  log_group_name = "aws-waf-logs-${var.name_prefix}-cloudfront"
  kms_enabled    = var.waf_logging_enabled && var.waf_kms_enabled
}

data "aws_iam_policy_document" "waf_logs_kms" {
  count = local.kms_enabled ? 1 : 0

  statement {
    sid    = "EnableAccountKeyAdministration"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions   = ["kms:*"]
    resources = ["*"]
  }

  statement {
    sid    = "AllowCloudWatchLogsUse"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["logs.us-east-1.amazonaws.com"]
    }

    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
      "kms:CreateGrant",
    ]
    resources = ["*"]

    condition {
      test     = "ArnEquals"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:${data.aws_partition.current.partition}:logs:us-east-1:${data.aws_caller_identity.current.account_id}:log-group:${local.log_group_name}"]
    }

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["logs.us-east-1.amazonaws.com"]
    }
  }
}

resource "aws_kms_key" "waf_logs" {
  count = local.kms_enabled ? 1 : 0

  description             = "KMS key for ${local.log_group_name}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.waf_logs_kms[0].json

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-waf-logs"
    Component = "waf"
    Role      = "log-encryption"
  })
}

resource "aws_kms_alias" "waf_logs" {
  count = local.kms_enabled ? 1 : 0

  name          = "alias/${var.name_prefix}-waf-logs"
  target_key_id = aws_kms_key.waf_logs[0].key_id
}

resource "aws_cloudwatch_log_group" "waf" {
  count = var.waf_logging_enabled ? 1 : 0

  name              = local.log_group_name
  retention_in_days = var.waf_log_retention_days
  kms_key_id        = local.kms_enabled ? aws_kms_key.waf_logs[0].arn : null

  tags = merge(var.common_tags, {
    Name      = local.log_group_name
    Component = "waf"
    Role      = "access-logs"
  })
}

data "aws_iam_policy_document" "waf_log_delivery" {
  count = var.waf_logging_enabled ? 1 : 0

  statement {
    sid    = "AWSLogDeliveryWrite"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["delivery.logs.amazonaws.com"]
    }

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.waf[0].arn}:log-stream:*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${data.aws_partition.current.partition}:logs:us-east-1:${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}

resource "aws_cloudwatch_log_resource_policy" "waf" {
  count = var.waf_logging_enabled ? 1 : 0

  policy_name     = "${var.name_prefix}-waf-log-delivery"
  policy_document = data.aws_iam_policy_document.waf_log_delivery[0].json
}

resource "aws_wafv2_web_acl" "cloudfront" {
  name        = local.web_acl_name
  description = "CloudFront Web ACL for ${var.name_prefix}"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 10

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-common-rule-set"
      sampled_requests_enabled   = true
    }
  }

  dynamic "rule" {
    for_each = { for group in var.waf_additional_managed_rule_groups : "${group.vendor_name}/${group.name}" => group }

    content {
      name     = replace("${rule.value.vendor_name}-${rule.value.name}", "/[^0-9A-Za-z_-]/", "-")
      priority = rule.value.priority

      override_action {
        none {}
      }

      statement {
        managed_rule_group_statement {
          name        = rule.value.name
          vendor_name = rule.value.vendor_name
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = replace("${var.name_prefix}-${rule.value.vendor_name}-${rule.value.name}", "/[^0-9A-Za-z_-]/", "-")
        sampled_requests_enabled   = true
      }
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name_prefix}-cloudfront-web-acl"
    sampled_requests_enabled   = true
  }

  lifecycle {
    precondition {
      condition     = data.aws_region.current.name == "us-east-1"
      error_message = "CloudFront-scope WAF resources must use an AWS provider configured for us-east-1."
    }
  }

  tags = merge(var.common_tags, {
    Name      = local.web_acl_name
    Component = "waf"
    Role      = "cloudfront-protection"
  })
}

resource "aws_wafv2_web_acl_logging_configuration" "cloudfront" {
  count = var.waf_logging_enabled ? 1 : 0

  log_destination_configs = [aws_cloudwatch_log_group.waf[0].arn]
  resource_arn            = aws_wafv2_web_acl.cloudfront.arn

  redacted_fields {
    single_header {
      name = "authorization"
    }
  }

  redacted_fields {
    single_header {
      name = "cookie"
    }
  }

  depends_on = [aws_cloudwatch_log_resource_policy.waf]
}
