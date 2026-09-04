"""Static Task 14.2 apigateway-module configuration tests; no Terraform or AWS access."""

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
        rf'resource "{resource_type}" "{resource_name}" \{{(.*?)(?=\nresource |\Z)',
        MAIN,
        re.DOTALL,
    )
    assert match, f"resource {resource_type}.{resource_name} was not found"
    return match.group(1)


def test_versions_pin_terraform_and_aws_provider() -> None:
    assert 'required_version = ">= 1.10"' in VERSIONS
    assert 'version = "~> 5.0"' in VERSIONS


def test_http_api_exists() -> None:
    block = _resource_block("aws_apigatewayv2_api", "this")
    assert 'protocol_type = "HTTP"' in block


def test_api_proxy_route_exists() -> None:
    # /api/* route (Requirement 9.3).
    block = _resource_block("aws_apigatewayv2_route", "api_proxy")
    assert "/api/" in block
    assert re.search(r'route_key\s*=\s*"ANY /api/\{proxy\+\}"', block)


def test_cognito_jwt_authorizer_configured() -> None:
    block = _resource_block("aws_apigatewayv2_authorizer", "cognito_jwt")
    assert 'authorizer_type  = "JWT"' in block or 'authorizer_type = "JWT"' in block
    assert "jwt_configuration {" in block
    assert "issuer   = var.jwt_issuer_url" in block or "issuer = var.jwt_issuer_url" in block
    assert "audience = var.jwt_audiences" in block


def test_route_applies_jwt_authorizer() -> None:
    block = _resource_block("aws_apigatewayv2_route", "api_proxy")
    assert 'authorization_type = "JWT"' in block
    assert "authorizer_id      = aws_apigatewayv2_authorizer.cognito_jwt.id" in block or \
        "authorizer_id = aws_apigatewayv2_authorizer.cognito_jwt.id" in block


def test_lambda_integration_is_aws_proxy() -> None:
    block = _resource_block("aws_apigatewayv2_integration", "lambda")
    assert 'integration_type       = "AWS_PROXY"' in block or 'integration_type = "AWS_PROXY"' in block
    assert "integration_uri" in block
    assert "var.lambda_invoke_arn" in block


def test_naming_uses_prefix_and_common_tags_applied() -> None:
    assert "var.name_prefix" in MAIN
    assert MAIN.count("merge(var.common_tags") == 2  # api + stage


def test_does_not_reference_product_a_resources() -> None:
    # API Gateway must integrate only with the Portal_API Lambda, never with
    # Product_A (Backend API / ECS / ALB / Aurora).
    lowered = MAIN_CODE.lower()
    for forbidden in (
        "aws_rds",
        "aurora",
        "aws_eks",
        "aws_ecs",
        "aws_lb",
        "aws_alb",
        "backend-api",
        "backend_api",
        "rds_cluster",
    ):
        assert forbidden not in lowered, f"Product_A reference {forbidden!r} must not appear"


def test_outputs_publish_id_endpoint_execution_domain_authorizer() -> None:
    for name in (
        "api_id",
        "api_endpoint",
        "api_execution_arn",
        "api_domain_name",
        "authorizer_id",
    ):
        assert f'output "{name}"' in OUTPUTS, f"output {name} missing"


def test_api_domain_name_derived_not_hardcoded() -> None:
    match = re.search(r'output "api_domain_name" \{(.*?)\n\}', OUTPUTS, re.DOTALL)
    assert match, "api_domain_name output missing"
    body = match.group(1)
    assert "replace(" in body and "api_endpoint" in body


def test_lambda_permission_exists_with_minimal_privilege() -> None:
    # API Gateway must be granted least-privilege permission to invoke the
    # Portal_API Lambda.
    block = _resource_block("aws_lambda_permission", "apigw_invoke")
    assert 'principal     = "apigateway.amazonaws.com"' in block or \
        'principal = "apigateway.amazonaws.com"' in block
    assert 'action        = "lambda:InvokeFunction"' in block or \
        'action = "lambda:InvokeFunction"' in block
    assert "var.lambda_function_name" in block


def test_lambda_permission_source_arn_scoped_to_this_api() -> None:
    # source_arn must be scoped to this API's execution ARN, not an overly broad
    # wildcard. Only the execution ARN reference plus a two-level "/*/*" is
    # permitted.
    block = _resource_block("aws_lambda_permission", "apigw_invoke")
    match = re.search(r'source_arn\s*=\s*"([^"]*)"', block)
    assert match, "aws_lambda_permission must set source_arn"
    source_arn = match.group(1)
    assert "aws_apigatewayv2_api.this.execution_arn" in source_arn, \
        "source_arn must reference this API's execution ARN"
    assert source_arn.count("*") <= 2, "source_arn wildcard must stay minimal (at most /*/*)"
    assert source_arn.endswith("/*/*"), "source_arn should limit to two path/method levels"


def test_lambda_function_name_variable_declared() -> None:
    assert 'variable "lambda_function_name"' in VARIABLES
    assert "length(trimspace(var.lambda_function_name)) > 0" in VARIABLES


def test_no_sensitive_or_real_literals_present() -> None:
    haystack = "\n".join([MAIN, VARIABLES, OUTPUTS, README]).lower()
    for needle in (
        "password=",
        "postgresql://",
        "aws_secret_access_key",
        "authorization: bearer",
        "arn:aws:execute-api:ap-northeast-1:",
        "execute-api.ap-northeast-1.amazonaws.com",
    ):
        assert needle not in haystack, f"sensitive/real literal {needle!r} must not appear"
