"""Static Task 9.3 alb-module configuration tests; no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
MAIN = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE_DIR / "variables.tf").read_text(encoding="utf-8")
OUTPUTS = (MODULE_DIR / "outputs.tf").read_text(encoding="utf-8")
README = (MODULE_DIR / "README.md").read_text(encoding="utf-8")


def _resource_block(source: str, resource_type: str, resource_name: str) -> str:
    match = re.search(
        rf'resource "{resource_type}" "{resource_name}" \{{(.*?)(?=\nresource |\Z)',
        source,
        re.DOTALL,
    )
    assert match, f"{resource_type}.{resource_name} was not found"
    return match.group(1)


def _variable_block(name: str) -> str:
    match = re.search(rf'variable "{name}" \{{(.*?)\n\}}', VARIABLES, re.DOTALL)
    assert match, f'variable "{name}" was not found'
    return match.group(1)


def test_https_443_listener_forwards_to_target_group() -> None:
    listener = _resource_block(MAIN, "aws_lb_listener", "https")
    assert "port              = 443" in listener
    assert 'protocol          = "HTTPS"' in listener
    assert "ssl_policy" in listener
    assert "certificate_arn" in listener
    assert "target_group_arn = aws_lb_target_group.this.arn" in listener
    # Listener only exists once a certificate is supplied.
    assert "count = var.certificate_arn == null ? 0 : 1" in listener


def test_http_80_listener_forwards_to_target_group() -> None:
    listener = _resource_block(MAIN, "aws_lb_listener", "http")
    assert "port              = 80" in listener
    assert 'protocol          = "HTTP"' in listener
    assert "target_group_arn = aws_lb_target_group.this.arn" in listener
    # HTTP listener is always created for dev/MVP fallback.
    assert "count = 1" in listener


def test_ingress_80_and_443_both_limited_by_allowed_cidrs() -> None:
    validation = _variable_block("allowed_ingress_cidrs")
    assert 'cidr != "0.0.0.0/0"' in validation

    # HTTP (80) ingress
    http_ingress = _resource_block(MAIN, "aws_vpc_security_group_ingress_rule", "http")
    assert "for_each" in http_ingress
    assert "var.allowed_ingress_cidrs" in http_ingress
    assert "from_port         = 80" in http_ingress
    assert "to_port           = 80" in http_ingress
    assert "cidr_ipv4         = each.value" in http_ingress

    # HTTPS (443) ingress
    https_ingress = _resource_block(MAIN, "aws_vpc_security_group_ingress_rule", "https")
    assert "for_each" in https_ingress
    assert "var.allowed_ingress_cidrs" in https_ingress
    assert "from_port         = 443" in https_ingress
    assert "to_port           = 443" in https_ingress
    assert "cidr_ipv4         = each.value" in https_ingress


def test_alb_security_group_removes_implicit_allow_all() -> None:
    sg = _resource_block(MAIN, "aws_security_group", "alb")
    assert "ingress     = []" in sg
    assert "egress      = []" in sg


def test_egress_targets_ecs_sg_and_forbids_public_internet() -> None:
    egress = _resource_block(MAIN, "aws_vpc_security_group_egress_rule", "to_ecs")
    # ALB egress must reference the ECS task SG, never a CIDR.
    assert "referenced_security_group_id = var.ecs_security_group_id" in egress
    assert "from_port                    = var.app_port" in egress
    assert "to_port                      = var.app_port" in egress
    assert 'ip_protocol                  = "tcp"' in egress
    # ALB egress must never open 0.0.0.0/0.
    assert 'cidr_ipv4         = "0.0.0.0/0"' not in MAIN
    assert '"0.0.0.0/0"' not in egress
    # Created only when this module owns the SG and an ECS SG is supplied.
    assert (
        "count = var.create_security_group && var.ecs_security_group_id != null ? 1 : 0"
        in egress
    )


def test_ecs_security_group_id_variable_validation() -> None:
    validation = _variable_block("ecs_security_group_id")
    assert "default     = null" in validation
    assert "var.ecs_security_group_id == null" in validation
    assert "sg-[0-9a-f]+" in validation


def test_access_logs_enabled_with_required_bucket() -> None:
    alb = _resource_block(MAIN, "aws_lb", "this")
    assert "access_logs {" in alb
    assert "enabled = true" in alb
    assert "bucket  = var.access_logs_bucket" in alb
    bucket_validation = _variable_block("access_logs_bucket")
    assert "length(trimspace(var.access_logs_bucket)) > 0" in bucket_validation


def test_target_group_is_ip_type_with_health_check_path() -> None:
    tg = _resource_block(MAIN, "aws_lb_target_group", "this")
    assert 'target_type = "ip"' in tg
    assert 'protocol    = "HTTP"' in tg
    assert "health_check {" in tg
    assert "path                = var.health_check_path" in tg
    assert 'default     = "/health"' in _variable_block("health_check_path")


def test_app_port_restricted_to_supported_values() -> None:
    assert "contains([8000, 8080], var.app_port)" in VARIABLES


def test_name_prefix_and_common_tags_are_used() -> None:
    assert "var.name_prefix" in MAIN
    assert "merge(var.common_tags" in MAIN


def test_outputs_expose_ids_and_no_secret() -> None:
    for output in ("alb_arn", "alb_dns_name", "target_group_arn", "listener_arn", "security_group_id"):
        assert f'output "{output}"' in OUTPUTS
    lowered = (MAIN + VARIABLES + OUTPUTS + README).lower()
    for forbidden in ("password=", "postgresql://", "bearer ", "authorization:"):
        assert forbidden not in lowered
