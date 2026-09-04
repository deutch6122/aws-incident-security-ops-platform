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
    for group in ("alb", "ecs", "eks", "db"):
        block = _resource_block("aws_security_group", group)
        assert "egress      = []" in block
    assert 'resource "aws_vpc_security_group_egress_rule" "ecs_https_external"' in MAIN
    assert 'resource "aws_vpc_security_group_egress_rule" "eks_https_external"' in MAIN


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
