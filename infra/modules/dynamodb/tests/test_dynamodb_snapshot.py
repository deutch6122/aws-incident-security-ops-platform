"""Static Task 13.1/13.4 dynamodb-module configuration tests; no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
MAIN = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE_DIR / "variables.tf").read_text(encoding="utf-8")
OUTPUTS = (MODULE_DIR / "outputs.tf").read_text(encoding="utf-8")
VERSIONS = (MODULE_DIR / "versions.tf").read_text(encoding="utf-8")
README = (MODULE_DIR / "README.md").read_text(encoding="utf-8")

TABLE_RESOURCES = (
    "public_status_items",
    "report_metadata",
    "page_view_logs",
    "maintenance_windows",
)


def _strip_comments(text: str) -> str:
    # Drop full-line and trailing "#" comments so cross-product checks inspect
    # only real HCL (resource types, attributes), not explanatory prose.
    return "\n".join(re.sub(r"#.*$", "", line) for line in text.splitlines())


MAIN_CODE = _strip_comments(MAIN)


def _resource_block(resource_type: str, resource_name: str) -> str:
    match = re.search(
        rf'resource "{resource_type}" "{resource_name}" \{{(.*?)(?=\nresource |\Z)',
        MAIN,
        re.DOTALL,
    )
    assert match, f"resource {resource_type}.{resource_name} was not found"
    return match.group(1)


def test_versions_pin_terraform_and_aws_provider() -> None:
    assert 'required_version = ">= 1.10"' in VERSIONS
    assert 'version = "~> 5.0"' in VERSIONS


def test_four_tables_exist() -> None:
    for name in TABLE_RESOURCES:
        assert f'resource "aws_dynamodb_table" "{name}"' in MAIN, f"table {name} missing"


def test_all_tables_are_pay_per_request() -> None:
    # Every table must use on-demand billing (Requirement 24.5). There must be no
    # PROVISIONED billing anywhere.
    for name in TABLE_RESOURCES:
        block = _resource_block("aws_dynamodb_table", name)
        assert 'billing_mode = "PAY_PER_REQUEST"' in block, f"{name} not PAY_PER_REQUEST"
    assert "PROVISIONED" not in MAIN
    assert MAIN.count('billing_mode = "PAY_PER_REQUEST"') == 4


def test_report_metadata_has_gsi_period_on_period_key() -> None:
    block = _resource_block("aws_dynamodb_table", "report_metadata")
    assert 'hash_key     = "report_id"' in block
    gsi = re.search(r"global_secondary_index \{(.*?)\}", block, re.DOTALL)
    assert gsi, "report_metadata GSI missing"
    gsi_body = gsi.group(1)
    assert 'name            = "gsi_period"' in gsi_body
    assert 'hash_key        = "period"' in gsi_body
    # period must be declared as an attribute for the GSI key.
    assert 'name = "period"' in block


def test_ttl_enabled_on_page_view_logs_and_maintenance_windows() -> None:
    for name in ("page_view_logs", "maintenance_windows"):
        block = _resource_block("aws_dynamodb_table", name)
        ttl = re.search(r"ttl \{(.*?)\}", block, re.DOTALL)
        assert ttl, f"{name} missing ttl block"
        assert "enabled        = true" in ttl.group(1)
        assert "attribute_name = var.ttl_attribute_name" in ttl.group(1)


def test_status_and_report_tables_have_no_ttl() -> None:
    # TTL only belongs on the log/maintenance tables; the status/report tables
    # must not silently expire records.
    for name in ("public_status_items", "report_metadata"):
        block = _resource_block("aws_dynamodb_table", name)
        assert "ttl {" not in block, f"{name} should not enable TTL"


def test_no_dynamodb_streams_enabled() -> None:
    # Streams would create a push channel toward Product_A; the A->B link must
    # stay one-way (Requirement 14.3).
    assert "stream_enabled" not in MAIN
    assert "stream_view_type" not in MAIN


def test_naming_uses_prefix_and_common_tags_applied() -> None:
    assert "var.name_prefix" in MAIN
    assert MAIN.count("merge(var.common_tags") == 4


def test_does_not_reference_product_a_resources() -> None:
    # Product_B module must not read from or write to Product_A (Aurora/RDS/EKS/
    # ECS/SQS). Guard against accidental cross-product wiring.
    lowered = MAIN_CODE.lower()
    for forbidden in ("aws_rds", "aurora", "aws_eks", "aws_ecs", "aws_sqs", "rds_cluster", "eks_cluster"):
        assert forbidden not in lowered, f"Product_A reference {forbidden!r} must not appear"


def test_outputs_publish_table_names_arns_gsi_and_streams_flag() -> None:
    for name in (
        "public_status_items_table_name",
        "public_status_items_table_arn",
        "report_metadata_table_name",
        "report_metadata_table_arn",
        "report_metadata_gsi_period_name",
        "page_view_logs_table_name",
        "page_view_logs_table_arn",
        "maintenance_windows_table_name",
        "maintenance_windows_table_arn",
        "streams_enabled",
    ):
        assert f'output "{name}"' in OUTPUTS, f"output {name} missing"


def test_no_sensitive_or_real_literals_present() -> None:
    haystack = "\n".join([MAIN, VARIABLES, OUTPUTS, README]).lower()
    for needle in (
        "password=",
        "postgresql://",
        "aws_secret_access_key",
        "authorization:",
        "bearer ",
        "arn:aws:dynamodb:ap-northeast-1:",
    ):
        assert needle not in haystack, f"sensitive/real literal {needle!r} must not appear"
