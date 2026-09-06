"""Static alb-module configuration tests (Task 7); no Terraform or AWS access."""

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


def test_certificate_arn_is_required() -> None:
    block = _variable_block("certificate_arn")
    # No default assignment => required input (the word "default" may appear in prose).
    assert not re.search(r"^\s*default\s*=", block, re.MULTILINE), "certificate_arn must not have a default (required input)"
    assert "arn:aws" in block and ":acm:" in block, "certificate_arn must validate an ACM ARN"


def test_https_443_listener_is_unconditional_and_forwards() -> None:
    listener = _resource_block(MAIN, "aws_lb_listener", "https")
    assert "port              = 443" in listener
    assert 'protocol          = "HTTPS"' in listener
    assert "ssl_policy" in listener
    assert "certificate_arn   = var.certificate_arn" in listener
    assert "target_group_arn = aws_lb_target_group.this.arn" in listener
    # No certificate-based count condition remains.
    assert "count" not in listener, "HTTPS listener must be created unconditionally"


def test_http_80_listener_redirects_to_https_301_without_forward() -> None:
    listener = _resource_block(MAIN, "aws_lb_listener", "http")
    assert "port              = 80" in listener
    assert 'protocol          = "HTTP"' in listener
    assert 'type = "redirect"' in listener
    assert 'protocol    = "HTTPS"' in listener
    assert 'port        = "443"' in listener
    assert 'status_code = "HTTP_301"' in listener
    # HTTP listener must NOT forward to the target group.
    assert "target_group_arn" not in listener, "HTTP listener must not forward to the target group"
    assert 'type             = "forward"' not in listener


def test_ingress_80_and_443_both_limited_by_allowed_cidrs() -> None:
    validation = _variable_block("allowed_ingress_cidrs")
    assert 'cidr != "0.0.0.0/0"' in validation
    http_ingress = _resource_block(MAIN, "aws_vpc_security_group_ingress_rule", "http")
    assert "var.allowed_ingress_cidrs" in http_ingress
    assert "from_port         = 80" in http_ingress
    https_ingress = _resource_block(MAIN, "aws_vpc_security_group_ingress_rule", "https")
    assert "var.allowed_ingress_cidrs" in https_ingress
    assert "from_port         = 443" in https_ingress


def test_alb_security_group_removes_implicit_allow_all() -> None:
    sg = _resource_block(MAIN, "aws_security_group", "alb")
    assert "ingress     = []" in sg
    assert "egress      = []" in sg


def test_external_security_group_interface_exists() -> None:
    # create_security_group toggle + external alb_security_group_id input.
    assert 'variable "create_security_group"' in VARIABLES
    assert 'variable "alb_security_group_id"' in VARIABLES
    local_sel = re.search(r"security_group_id = var.create_security_group \? (.*)", MAIN)
    assert local_sel, "SG selection local must choose between created and supplied SG"
    assert "var.alb_security_group_id" in MAIN


def test_egress_targets_ecs_sg_and_forbids_public_internet() -> None:
    egress = _resource_block(MAIN, "aws_vpc_security_group_egress_rule", "to_ecs")
    assert "referenced_security_group_id = var.ecs_security_group_id" in egress
    assert "from_port                    = var.app_port" in egress
    assert '"0.0.0.0/0"' not in egress
    assert 'cidr_ipv4         = "0.0.0.0/0"' not in MAIN


def test_access_logs_enabled_and_bucket_not_created_in_module() -> None:
    alb = _resource_block(MAIN, "aws_lb", "this")
    assert "access_logs {" in alb
    assert "enabled = true" in alb
    assert "bucket  = var.access_logs_bucket" in alb
    assert "length(trimspace(var.access_logs_bucket)) > 0" in _variable_block("access_logs_bucket")
    # The module must NOT create the access-log bucket or its policy (Task 27 owns them).
    assert 'resource "aws_s3_bucket"' not in MAIN
    assert 'resource "aws_s3_bucket_policy"' not in MAIN
    assert "owns the ALB access-log bucket" in README or "access-log bucket" in README


def test_target_group_is_ip_type_http_app_port() -> None:
    tg = _resource_block(MAIN, "aws_lb_target_group", "this")
    assert 'target_type = "ip"' in tg
    assert 'protocol    = "HTTP"' in tg
    assert "port        = var.app_port" in tg
    assert "health_check {" in tg
    assert "path                = var.health_check_path" in tg
    assert "contains([8000, 8080], var.app_port)" in VARIABLES


def test_name_prefix_and_common_tags_are_used() -> None:
    assert "var.name_prefix" in MAIN
    assert "merge(var.common_tags" in MAIN


def test_https_listener_output_is_not_nullable() -> None:
    assert 'output "https_listener_arn"' in OUTPUTS
    block = re.search(r'output "https_listener_arn" \{(.*?)\n\}', OUTPUTS, re.DOTALL).group(1)
    # Must reference the unconditional listener directly, with no try()/[0]/null fallback.
    assert "aws_lb_listener.https.arn" in block
    assert "try(" not in block
    assert "null" not in block
    # The old nullable 'listener_arn' output must be gone.
    assert 'output "listener_arn"' not in OUTPUTS


def test_outputs_expose_ids_and_no_secret() -> None:
    for output in ("alb_arn", "alb_dns_name", "alb_zone_id", "target_group_arn",
                   "https_listener_arn", "http_listener_arn", "security_group_id"):
        assert f'output "{output}"' in OUTPUTS
    lowered = (MAIN + VARIABLES + OUTPUTS + README).lower()
    for forbidden in ("password=", "postgresql://", "authorization: bearer "):
        assert forbidden not in lowered
    assert not re.search(r"\b\d{12}\b", lowered), "no literal 12-digit account id may appear"
