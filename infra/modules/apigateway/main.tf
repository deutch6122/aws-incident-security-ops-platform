locals {
  api_name = "${var.name_prefix}-portal-api"
}

# Portal_API front door for Product_B (Requirement 9.3, 12.4). An HTTP API
# (apigatewayv2) is used instead of a REST API: it is cheaper and lower-latency,
# which fits the small dev workload, and it has first-class Cognito JWT
# authorizer support.
#
# SEPARATION NOTE: this module belongs to Product_B only. It integrates solely
# with the Portal_API Lambda (via lambda_invoke_arn) and never connects to
# Product_A (Backend API / ECS / ALB / Aurora). CloudFront reaches this API as
# a custom origin using the api_domain_name output.
resource "aws_apigatewayv2_api" "this" {
  name          = local.api_name
  protocol_type = "HTTP"

  tags = merge(var.common_tags, {
    Name      = local.api_name
    Component = "apigateway"
    Role      = "portal-api"
  })
}

# Cognito JWT authorizer. Tokens are validated against the User Pool issuer and
# the App Client audience list, both supplied by the cognito module (Task 14.1).
resource "aws_apigatewayv2_authorizer" "cognito_jwt" {
  api_id           = aws_apigatewayv2_api.this.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${var.name_prefix}-cognito-jwt"

  jwt_configuration {
    issuer   = var.jwt_issuer_url
    audience = var.jwt_audiences
  }
}

# AWS_PROXY integration to the Portal_API Lambda. The Lambda function itself is
# implemented in Task 15; this module only wires the invoke ARN it receives.
resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.lambda_invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# /api/* route protected by the Cognito JWT authorizer. Every request under
# /api/ must carry a valid token (Requirement 9.3).
resource "aws_apigatewayv2_route" "api_proxy" {
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "ANY /api/{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.lambda.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_jwt.id
}

# API Gateway が Portal_API Lambda を呼び出す最小権限。source_arn を当該 API の
# execution ARN に限定し、他 API からの invoke を許容しない。source_arn の
# wildcard は execution ARN 配下のメソッド/パス2階層（/*/*）のみに留め、過度な
# 広域 wildcard を避ける。ANY /api/{proxy+} の呼び出し経路をカバーする。
resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowPortalApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}

resource "aws_apigatewayv2_stage" "this" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = var.stage_name
  auto_deploy = true

  tags = merge(var.common_tags, {
    Name      = "${local.api_name}-${var.stage_name}"
    Component = "apigateway"
    Role      = "portal-api-stage"
  })
}
