"""Static Task 13.3/13.4 cloudfront-module configuration tests; no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
MAIN = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE_DIR / "variables.tf").read_text(encoding="utf-8")
OUTPUTS = (MODULE_DIR / "outputs.tf").read_text(encoding="utf-8")
VERSIONS = (MODULE_DIR / "versions.tf").read_text(encoding="utf-8")
README = (MODULE_DIR / "README.md").read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    return "\n".join(re.sub(r"#.*$", "", line) for line in text.splitlines())


MAIN_CODE = _strip_comments(MAIN)


def _resource_block(resource_type: str, resource_name: str) -> str:
    match = re.search(
        rf'resource "{resource_type}" "{resource_name}" \{{(.*?)(?=\nresource |\ndata |\Z)',
        MAIN,
        re.DOTALL,
    )
    assert match, f"resource {resource_type}.{resource_name} was not found"
    return match.group(1)


def test_versions_pin_terraform_and_aws_provider() -> None:
    assert 'required_version = ">= 1.10"' in VERSIONS
    assert 'version = "~> 5.0"' in VERSIONS


def test_distribution_uses_price_class_200() -> None:
    assert 'default     = "PriceClass_200"' in VARIABLES
    block = _resource_block("aws_cloudfront_distribution", "this")
    assert "price_class     = var.price_class" in block


def test_distribution_has_two_origins() -> None:
    block = _resource_block("aws_cloudfront_distribution", "this")
    # Exactly two origin blocks: S3 and API Gateway.
    origin_ids = re.findall(r"origin_id\s+=\s+local\.(\w+)", block)
    assert "s3_origin_id" in origin_ids
    assert "api_origin_id" in origin_ids
    assert block.count("origin {") == 2


def test_s3_origin_uses_oac() -> None:
    block = _resource_block("aws_cloudfront_distribution", "this")
    assert "origin_access_control_id = aws_cloudfront_origin_access_control.s3.id" in block
    oac = _resource_block("aws_cloudfront_origin_access_control", "s3")
    assert 'signing_behavior                  = "always"' in oac
    assert 'origin_access_control_origin_type = "s3"' in oac


def test_api_gateway_origin_is_custom_and_variable_driven() -> None:
    block = _resource_block("aws_cloudfront_distribution", "this")
    assert "domain_name = var.api_gateway_origin_domain" in block
    assert "custom_origin_config" in block
    # API origin domain is a placeholder default, not a real committed domain.
    api_var = re.search(r'variable "api_gateway_origin_domain" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert api_var and 'default     = ""' in api_var.group(1)


def test_viewer_protocol_policy_is_https() -> None:
    block = _resource_block("aws_cloudfront_distribution", "this")
    policies = re.findall(r"viewer_protocol_policy = \"([^\"]+)\"", block)
    assert policies, "no viewer_protocol_policy found"
    for policy in policies:
        assert policy in ("redirect-to-https", "https-only"), f"non-HTTPS policy {policy}"
    # default behavior -> S3, /api/* -> API Gateway.
    default_beh = re.search(r"default_cache_behavior \{(.*?)\n  \}", block, re.DOTALL)
    assert default_beh and "target_origin_id       = local.s3_origin_id" in default_beh.group(1)
    api_beh = re.search(r"ordered_cache_behavior \{(.*?)\n  \}", block, re.DOTALL)
    assert api_beh and 'path_pattern           = "/api/*"' in api_beh.group(1)
    assert "target_origin_id       = local.api_origin_id" in api_beh.group(1)


def test_waf_has_managed_rules_and_rate_based_rule() -> None:
    block = _resource_block("aws_wafv2_web_acl", "this")
    assert 'scope       = "CLOUDFRONT"' in block
    assert "managed_rule_group_statement" in block
    assert "AWSManagedRulesCommonRuleSet" in block
    assert "rate_based_statement" in block
    assert "limit              = var.waf_rate_limit" in block


def test_web_acl_associated_with_distribution() -> None:
    dist = _resource_block("aws_cloudfront_distribution", "this")
    assert "web_acl_id      = aws_wafv2_web_acl.this.arn" in dist


def test_naming_uses_prefix_and_common_tags_applied() -> None:
    assert "var.name_prefix" in MAIN
    assert "merge(var.common_tags" in MAIN


def test_does_not_connect_to_product_a() -> None:
    # No Product_A origins/resources; CloudFront only fronts Product_B.
    lowered = MAIN_CODE.lower()
    for forbidden in ("aws_rds", "aurora", "aws_eks", "aws_ecs", "aws_sqs", "rds_cluster", "eks_cluster"):
        assert forbidden not in lowered, f"Product_A reference {forbidden!r} must not appear"


def test_outputs_publish_distribution_oac_and_waf_identity() -> None:
    for name in (
        "distribution_id",
        "distribution_arn",
        "distribution_domain_name",
        "oac_id",
        "web_acl_arn",
        "price_class",
    ):
        assert f'output "{name}"' in OUTPUTS, f"output {name} missing"


def test_no_sensitive_or_real_literals_present() -> None:
    haystack = "\n".join([MAIN, VARIABLES, OUTPUTS, README]).lower()
    for needle in (
        "password=",
        "postgresql://",
        "aws_secret_access_key",
        "authorization: bearer",
        ".cloudfront.net",
        ".execute-api.ap-northeast-1.amazonaws.com",
    ):
        assert needle not in haystack, f"sensitive/real literal {needle!r} must not appear"
