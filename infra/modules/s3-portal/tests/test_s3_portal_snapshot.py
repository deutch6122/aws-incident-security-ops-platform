"""Static s3-portal-module configuration tests (Task 21); no Terraform or AWS access."""

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


def test_bucket_exists_with_common_tags() -> None:
    assert 'resource "aws_s3_bucket" "portal"' in MAIN
    block = _resource_block("aws_s3_bucket", "portal")
    assert "bucket        = local.bucket_name" in block
    assert "merge(var.common_tags" in block


def test_bucket_name_uses_account_id_and_region_suffix() -> None:
    # suffix = "<account-id>-<region>" from the caller-identity data source and
    # the region variable; account id is never a literal.
    assert 'data "aws_caller_identity" "current"' in MAIN
    assert "data.aws_caller_identity.current.account_id" in MAIN
    assert "var.aws_region" in MAIN
    bucket_suffix = re.search(r"bucket_suffix\s*=\s*(.+)", MAIN).group(1)
    assert "account_id" in bucket_suffix and "var.aws_region" in bucket_suffix
    # Final name appends the full suffix after the stem.
    assert re.search(r'bucket_name\s*=\s*"\$\{local\.bucket_stem\}-\$\{local\.bucket_suffix\}"', MAIN)


def test_stem_is_truncated_not_suffix() -> None:
    # Max stem length is derived from 63 minus the joining hyphen minus the suffix
    # length, then the STEM is cut with substr; the suffix is never truncated.
    assert "63 - 1 - length(local.bucket_suffix)" in MAIN
    stem_line = re.search(r"bucket_stem\s*=\s*(.+)", MAIN).group(1)
    assert "substr(local.bucket_stem_src" in stem_line
    assert "local.bucket_stem_max" in stem_line
    assert 'trimsuffix(' in stem_line and '"-"' in stem_line
    # The suffix expression must not be passed through substr/truncation.
    assert "substr(local.bucket_suffix" not in MAIN


def test_bucket_name_expression_stays_within_63_chars() -> None:
    # Structural guarantee: stem_max = 63 - 1 - len(suffix); final name is
    # stem(<=stem_max) + "-" + suffix, whose length is <= 63 for any suffix
    # length up to 61 (the max function guards against a negative stem length).
    assert "max(local.bucket_stem_max, 0)" in MAIN


def test_no_bucket_policy_resource_in_module() -> None:
    # Task 21 owns bucket foundation only; the OAC bucket policy is owned by the
    # dev root in Task 27. There must be no policy resource or policy document.
    assert 'resource "aws_s3_bucket_policy"' not in MAIN
    assert 'aws_iam_policy_document' not in MAIN


def test_no_cloudfront_distribution_arn_variable() -> None:
    # No variable declaration and no code-level reference (comments stripped, so
    # the ownership-boundary note may still mention the retired input by name).
    assert 'variable "cloudfront_distribution_arn"' not in VARIABLES
    assert "cloudfront_distribution_arn" not in MAIN_CODE
    assert "cloudfront_distribution_arn" not in OUTPUTS


def test_aws_region_rejects_empty() -> None:
    block = re.search(r'variable "aws_region" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert block, "aws_region variable missing"
    assert "trimspace(var.aws_region)" in block.group(1)
    assert "> 0" in block.group(1)


def test_public_access_block_all_four_true() -> None:
    block = _resource_block("aws_s3_bucket_public_access_block", "portal")
    assert re.search(r"block_public_acls\s+=\s+true", block)
    assert re.search(r"block_public_policy\s+=\s+true", block)
    assert re.search(r"ignore_public_acls\s+=\s+true", block)
    assert re.search(r"restrict_public_buckets\s+=\s+true", block)
    assert "false" not in block


def test_object_ownership_disables_acls() -> None:
    block = _resource_block("aws_s3_bucket_ownership_controls", "portal")
    assert 'object_ownership = "BucketOwnerEnforced"' in block


def test_sse_s3_and_versioning_enabled() -> None:
    sse = _resource_block("aws_s3_bucket_server_side_encryption_configuration", "portal")
    assert 'sse_algorithm = "AES256"' in sse
    ver = _resource_block("aws_s3_bucket_versioning", "portal")
    assert "status = \"Enabled\"" in ver


def test_no_public_acl_grant() -> None:
    assert "public-read" not in MAIN
    assert 'acl = "public-read"' not in MAIN


def test_reports_prefix_declared_and_documented() -> None:
    assert 'variable "reports_prefix"' in VARIABLES
    assert 'default     = "reports/"' in VARIABLES
    assert "reports/" in README


def test_force_destroy_variable_present() -> None:
    assert 'variable "force_destroy"' in VARIABLES


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
    # No 12-digit account id literal anywhere.
    assert not re.search(r"\b\d{12}\b", haystack), "no literal 12-digit account id may appear"
