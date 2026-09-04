"""Static Task 13.2/13.4 s3-portal-module configuration tests; no Terraform or AWS access."""

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


def test_bucket_exists_with_naming_and_common_tags() -> None:
    assert 'resource "aws_s3_bucket" "portal"' in MAIN
    block = _resource_block("aws_s3_bucket", "portal")
    assert "${var.name_prefix}-portal-storage" in MAIN
    assert "merge(var.common_tags" in block


def test_public_access_block_all_four_true() -> None:
    block = _resource_block("aws_s3_bucket_public_access_block", "portal")
    assert re.search(r"block_public_acls\s+=\s+true", block)
    assert re.search(r"block_public_policy\s+=\s+true", block)
    assert re.search(r"ignore_public_acls\s+=\s+true", block)
    assert re.search(r"restrict_public_buckets\s+=\s+true", block)
    # No setting may be false.
    assert "false" not in block


def test_object_ownership_disables_acls() -> None:
    block = _resource_block("aws_s3_bucket_ownership_controls", "portal")
    assert 'object_ownership = "BucketOwnerEnforced"' in block


def test_oac_only_bucket_policy_principal_and_source_arn_condition() -> None:
    # The policy allows only the CloudFront service principal, restricted by the
    # distribution's SourceArn. There must be no public wildcard principal.
    policy = re.search(
        r'data "aws_iam_policy_document" "portal" \{(.*?)\n\}\n', MAIN, re.DOTALL
    )
    assert policy, "portal bucket policy document missing"
    body = policy.group(1)
    assert 'effect  = "Allow"' in body
    assert 'actions = ["s3:GetObject"]' in body
    assert 'identifiers = ["cloudfront.amazonaws.com"]' in body
    assert 'variable = "AWS:SourceArn"' in body
    assert "var.cloudfront_distribution_arn" in body
    # No public principal.
    assert '"*"' not in body
    # The bucket policy resource references the document and depends on the PAB.
    assert 'resource "aws_s3_bucket_policy" "portal"' in MAIN
    assert "aws_s3_bucket_public_access_block.portal" in _resource_block(
        "aws_s3_bucket_policy", "portal"
    )


def test_no_public_acl_grant() -> None:
    # There must be no ACL granting public-read (defence in depth beyond PAB).
    assert "public-read" not in MAIN
    assert 'acl = "public-read"' not in MAIN


def test_reports_prefix_declared_and_documented() -> None:
    assert 'variable "reports_prefix"' in VARIABLES
    assert 'default     = "reports/"' in VARIABLES
    assert "reports/" in README


def test_does_not_reference_product_a_resources() -> None:
    lowered = MAIN_CODE.lower()
    for forbidden in ("aws_rds", "aurora", "aws_eks", "aws_ecs", "aws_sqs", "rds_cluster", "eks_cluster"):
        assert forbidden not in lowered, f"Product_A reference {forbidden!r} must not appear"


def test_outputs_publish_bucket_identity_and_prefix() -> None:
    for name in ("bucket_name", "bucket_arn", "bucket_regional_domain_name", "reports_prefix"):
        assert f'output "{name}"' in OUTPUTS, f"output {name} missing"


def test_no_sensitive_or_real_literals_present() -> None:
    haystack = "\n".join([MAIN, VARIABLES, OUTPUTS, README]).lower()
    for needle in (
        "password=",
        "postgresql://",
        "aws_secret_access_key",
        "authorization:",
        "bearer ",
        "arn:aws:cloudfront::",
    ):
        assert needle not in haystack, f"sensitive/real literal {needle!r} must not appear"
