locals {
  s3_origin_id  = "${var.name_prefix}-portal-s3-origin"
  api_origin_id = "${var.name_prefix}-portal-api-origin"
}

# Origin Access Control for the S3 origin. signing_behavior=always so every
# CloudFront->S3 request is SigV4-signed; origin_type=s3. The S3 bucket policy
# (s3-portal module) grants read only to this distribution's OAC, so S3 stays
# private (Requirement 12.2, 12.3).
resource "aws_cloudfront_origin_access_control" "s3" {
  name                              = "${var.name_prefix}-portal-oac"
  description                       = "OAC for Portal_Storage S3 origin"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# PROVIDER NOTE (WAF scope=CLOUDFRONT): a WAFv2 Web ACL with scope=CLOUDFRONT
# MUST be created in us-east-1. The dev root is expected to pass a us-east-1
# provider alias to this module (e.g. providers = { aws = aws.us_east_1 }) when
# wiring Task 13.3. This module does not force an alias internally so it stays
# composable; see README for the required wiring. Managed rule group + a
# rate-based rule satisfy Requirement 13.2 and 13.3.
resource "aws_wafv2_web_acl" "this" {
  name        = "${var.name_prefix}-portal-web-acl"
  description = "WAF for Portal_CDN: AWS managed common rules + rate-based rule."
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # AWS Managed Rules: common rule set (Requirement 13.2).
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1

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
      metric_name                = "${var.name_prefix}-portal-common-rules"
      sampled_requests_enabled   = true
    }
  }

  # Rate-based rule: throttle a single source IP that exceeds the limit within a
  # 5-minute window (Requirement 13.3).
  rule {
    name     = "RateLimitPerSourceIp"
    priority = 2

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.waf_rate_limit
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name_prefix}-portal-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name_prefix}-portal-web-acl"
    sampled_requests_enabled   = true
  }

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-portal-web-acl"
    Component = "cloudfront"
    Role      = "waf"
  })
}

# Portal_CDN distribution: 2 origins.
#   (1) S3 (OAC) origin -> default_cache_behavior (static content).
#   (2) API Gateway custom origin -> /api/* ordered_cache_behavior.
# HTTPS is enforced on all viewer behaviors (Requirement 12.1). The WAF Web ACL
# is associated via web_acl_id (Requirement 13.1).
#
# SEPARATION NOTE: CloudFront never connects to Product_A directly. There is no
# Aurora/RDS/EKS/ECS origin here; the only origins are the Product_B S3 bucket
# and the Product_B API Gateway.
resource "aws_cloudfront_distribution" "this" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "${var.name_prefix} Portal_CDN"
  price_class     = var.price_class
  web_acl_id      = aws_wafv2_web_acl.this.arn

  # Origin 1: S3 via OAC.
  origin {
    domain_name              = var.s3_origin_domain_name
    origin_id                = local.s3_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.s3.id
  }

  # Origin 2: API Gateway (custom origin). Domain is variable-driven and resolved
  # in Task 14; only HTTPS to the origin.
  origin {
    domain_name = var.api_gateway_origin_domain
    origin_id   = local.api_origin_id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # Default behavior -> S3 static content, redirect to HTTPS.
  default_cache_behavior {
    target_origin_id       = local.s3_origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]

    forwarded_values {
      query_string = false

      cookies {
        forward = "none"
      }
    }
  }

  # /api/* -> API Gateway origin, HTTPS only (JWT-protected content is dynamic
  # and must not be cached by default).
  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = local.api_origin_id
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0

    forwarded_values {
      query_string = true

      headers = ["Authorization"]

      cookies {
        forward = "none"
      }
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # MVP uses the default CloudFront certificate/domain (no custom domain/ACM yet,
  # see design). This still serves viewers over HTTPS.
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-portal-cdn"
    Component = "cloudfront"
    Role      = "distribution"
  })
}
