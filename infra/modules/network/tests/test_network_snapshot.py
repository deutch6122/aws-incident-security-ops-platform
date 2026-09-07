"""Static Task 4 network-module configuration tests; no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
MAIN = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE_DIR / "variables.tf").read_text(encoding="utf-8")
README = (MODULE_DIR / "README.md").read_text(encoding="utf-8")


def _resource_block(resource_type: str, resource_name: str) -> str:
    match = re.search(
        rf'resource "{resource_type}" "{resource_name}" \{{(.*?)(?=\nresource |\Z)',
        MAIN,
        re.DOTALL,
    )
    assert match, f"{resource_type}.{resource_name} was not found"
    return match.group(1)


def test_vpc_two_az_and_three_subnet_tiers_are_declared() -> None:
    assert 'default     = "10.0.0.0/16"' in VARIABLES
    assert 'default     = ["ap-northeast-1a", "ap-northeast-1c"]' in VARIABLES
    for tier in ("public", "private_app", "isolated_db"):
        assert f'resource "aws_subnet" "{tier}"' in MAIN
    for cidr in ("10.0.0.0/24", "10.0.1.0/24", "10.0.10.0/24", "10.0.11.0/24", "10.0.20.0/24", "10.0.21.0/24"):
        assert cidr in VARIABLES


def test_isolated_db_route_table_has_no_nat_or_internet_route() -> None:
    isolated_route_table = _resource_block("aws_route_table", "isolated_db")
    assert "gateway_id" not in isolated_route_table
    assert "nat_gateway_id" not in isolated_route_table
    assert 'resource "aws_route" "private_app_nat"' in MAIN
    assert 'count = var.enable_nat_gateway ? 1 : 0' in _resource_block("aws_route", "private_app_nat")


def test_nat_is_single_az_and_can_be_disabled_without_a_route() -> None:
    nat = _resource_block("aws_nat_gateway", "this")
    assert 'count = var.enable_nat_gateway ? 1 : 0' in nat
    assert 'subnet_id     = aws_subnet.public[var.availability_zones[0]].id' in nat
    assert 'resource "aws_eip" "nat"' in MAIN
    assert "single-AZ NAT Gateway" in README


def test_security_groups_have_minimum_ingress_and_explicit_egress() -> None:
    assert 'default     = ["203.0.113.0/24"]' in VARIABLES
    alb_cidrs_validation = re.search(
        r'variable "allowed_alb_ingress_cidrs" \{(.*?)\n\}', VARIABLES, re.DOTALL
    )
    assert alb_cidrs_validation and 'cidr != "0.0.0.0/0"' in alb_cidrs_validation.group(1)
    assert 'resource "aws_vpc_security_group_ingress_rule" "alb_https"' in MAIN
    assert 'from_port         = 443' in _resource_block("aws_vpc_security_group_ingress_rule", "alb_https")
    assert 'resource "aws_vpc_security_group_ingress_rule" "ecs_from_alb"' in MAIN
    for rule_name in ("db_from_ecs", "db_from_eks"):
        rule = _resource_block("aws_vpc_security_group_ingress_rule", rule_name)
        assert "from_port                    = 5432" in rule
        assert "referenced_security_group_id" in rule
    assert 'resource "aws_vpc_security_group_egress_rule" "ecs_to_db"' in MAIN
    assert 'resource "aws_vpc_security_group_egress_rule" "eks_to_db"' in MAIN
    for group in ("alb", "ecs", "eks", "db", "migration", "vpc_endpoint"):
        block = _resource_block("aws_security_group", group)
        assert "egress      = []" in block
        assert "ingress     = []" in block
        assert "ignore_changes = [ingress, egress]" in block
    assert 'resource "aws_vpc_security_group_egress_rule" "ecs_https_external"' in MAIN
    assert 'resource "aws_vpc_security_group_egress_rule" "eks_https_external"' in MAIN


def test_migration_security_group_has_no_ingress() -> None:
    # Task 6: migration SG is owned solely by the network module and has no inbound.
    migration = _resource_block("aws_security_group", "migration")
    assert "egress      = []" in migration
    assert "ingress     = []" in migration
    assert 'Role = "migration"' in migration
    # No ingress rule targets the migration SG: inspect each ingress-rule block
    # individually and assert none sets security_group_id to the migration SG.
    for block in re.findall(
        r'resource "aws_vpc_security_group_ingress_rule" "[^"]+" \{(.*?)\n\}',
        MAIN,
        re.DOTALL,
    ):
        first_line = next(
            (ln for ln in block.splitlines() if ln.strip().startswith("security_group_id")),
            "",
        )
        assert "aws_security_group.migration.id" not in first_line, (
            "migration SG must not be the target (security_group_id) of any ingress rule"
        )
    # No 0.0.0.0/0 ingress anywhere targets the migration SG (no CIDR ingress at all).
    assert "0.0.0.0/0" not in migration


def test_migration_to_db_is_postgres_only() -> None:
    mig_to_db = _resource_block("aws_vpc_security_group_egress_rule", "migration_to_db")
    assert "referenced_security_group_id = aws_security_group.db.id" in mig_to_db
    assert "from_port                    = 5432" in mig_to_db
    assert "to_port                      = 5432" in mig_to_db
    db_from_mig = _resource_block("aws_vpc_security_group_ingress_rule", "db_from_migration")
    assert "referenced_security_group_id = aws_security_group.migration.id" in db_from_mig
    assert "from_port                    = 5432" in db_from_mig
    assert "to_port                      = 5432" in db_from_mig


def test_migration_https_egress_nat_path_exists() -> None:
    # NAT path: migration HTTPS egress to external CIDRs using the shared variable.
    mig_https = _resource_block("aws_vpc_security_group_egress_rule", "migration_https_external")
    assert "for_each = toset(var.external_https_egress_cidrs)" in mig_https
    assert "security_group_id = aws_security_group.migration.id" in mig_https
    assert "from_port         = 443" in mig_https
    assert "to_port           = 443" in mig_https


def test_migration_vpc_endpoint_path_exists() -> None:
    # Endpoint path: migration -> endpoint SG egress and endpoint SG <- migration ingress,
    # both gated by enable_vpc_endpoints like the existing ECS/EKS endpoint rules.
    mig_to_vpce = _resource_block("aws_vpc_security_group_egress_rule", "migration_to_vpc_endpoint")
    assert "count = var.enable_vpc_endpoints ? 1 : 0" in mig_to_vpce
    assert "security_group_id            = aws_security_group.migration.id" in mig_to_vpce
    assert "referenced_security_group_id = aws_security_group.vpc_endpoint[0].id" in mig_to_vpce
    assert "from_port                    = 443" in mig_to_vpce
    vpce_from_mig = _resource_block("aws_vpc_security_group_ingress_rule", "vpc_endpoint_from_migration")
    assert "count = var.enable_vpc_endpoints ? 1 : 0" in vpce_from_mig
    assert "security_group_id            = aws_security_group.vpc_endpoint[0].id" in vpce_from_mig
    assert "referenced_security_group_id = aws_security_group.migration.id" in vpce_from_mig
    assert "from_port                    = 443" in vpce_from_mig


def test_alb_to_ecs_uses_app_port_default_8080() -> None:
    # ALB egress to ECS uses the backend app port variable.
    alb_to_ecs = _resource_block("aws_vpc_security_group_egress_rule", "alb_to_ecs")
    assert "referenced_security_group_id = aws_security_group.ecs.id" in alb_to_ecs
    assert "from_port                    = var.app_port" in alb_to_ecs
    # app_port default is 8080.
    app_port_var = re.search(r'variable "app_port" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert app_port_var and "default     = 8080" in app_port_var.group(1)


def test_migration_security_group_id_is_exported() -> None:
    outputs = (MODULE_DIR / "outputs.tf").read_text(encoding="utf-8")
    assert "migration = aws_security_group.migration.id" in outputs


def test_vpc_endpoints_are_optional_and_use_the_expected_services() -> None:
    endpoint_flag = re.search(r'variable "enable_vpc_endpoints" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert endpoint_flag and "default     = false" in endpoint_flag.group(1)
    assert 'resource "aws_vpc_endpoint" "s3"' in MAIN
    assert 'resource "aws_vpc_endpoint" "interface"' in MAIN
    for service in ("ecr.api", "ecr.dkr", "secretsmanager", "logs", "sqs"):
        assert f'"{service}"' in VARIABLES


def test_name_prefix_and_common_tags_are_used() -> None:
    assert "var.name_prefix" in MAIN
    assert "merge(var.common_tags" in MAIN
