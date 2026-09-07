"""Task 23 WAF module contract tests; no Terraform or AWS access."""

from pathlib import Path


MODULE = Path(__file__).resolve().parents[1]
MAIN = (MODULE / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE / "variables.tf").read_text(encoding="utf-8")
OUTPUTS = (MODULE / "outputs.tf").read_text(encoding="utf-8")


def test_cloudfront_acl_has_baseline_managed_rules_and_visibility() -> None:
    assert 'resource "aws_wafv2_web_acl" "cloudfront"' in MAIN
    assert 'scope       = "CLOUDFRONT"' in MAIN
    assert MAIN.count("AWSManagedRulesCommonRuleSet") >= 2
    assert "waf_additional_managed_rule_groups" in MAIN
    assert "cloudwatch_metrics_enabled = true" in MAIN
    assert "sampled_requests_enabled   = true" in MAIN
    assert 'data.aws_region.current.name == "us-east-1"' in MAIN


def test_logging_defaults_on_and_redacts_credentials() -> None:
    assert 'variable "waf_logging_enabled"' in VARIABLES
    assert 'variable "waf_kms_enabled"' in VARIABLES
    assert VARIABLES.count("default     = true") >= 2
    assert 'log_group_name = "aws-waf-logs-' in MAIN
    assert MAIN.count("redacted_fields {") == 2
    assert 'name = "authorization"' in MAIN
    assert 'name = "cookie"' in MAIN


def test_log_delivery_and_kms_policies_are_scoped() -> None:
    assert 'resource "aws_cloudwatch_log_resource_policy" "waf"' in MAIN
    assert 'identifiers = ["delivery.logs.amazonaws.com"]' in MAIN
    assert 'variable = "aws:SourceAccount"' in MAIN
    assert 'variable = "aws:SourceArn"' in MAIN
    assert 'identifiers = ["logs.us-east-1.amazonaws.com"]' in MAIN
    assert "AllowTerraformExecToAssociateLogGroup" in MAIN
    assert 'role/${var.name_prefix}-terraform-exec-role' in MAIN
    assert '"kms:Describe*"' in MAIN
    assert 'variable = "kms:EncryptionContext:aws:logs:arn"' in MAIN
    assert 'test     = "ArnLike"' in MAIN
    assert 'variable = "kms:ViaService"' in MAIN


def test_child_module_uses_only_standard_aws_provider() -> None:
    combined = "\n".join((MAIN, VARIABLES, OUTPUTS))
    assert "aws.us_east_1" not in combined
    assert "provider =" not in MAIN


def test_web_acl_arn_is_exported() -> None:
    assert 'output "web_acl_arn"' in OUTPUTS
