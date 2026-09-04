output "api_id" {
  description = "ID of the HTTP API."
  value       = aws_apigatewayv2_api.this.id
}

output "api_endpoint" {
  description = "Default endpoint URL of the HTTP API (includes https:// scheme)."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "api_execution_arn" {
  description = "Execution ARN of the HTTP API, used to grant Lambda invoke permission (lambda:InvokeFunction source ARN)."
  value       = aws_apigatewayv2_api.this.execution_arn
}

# Host portion of the API endpoint, suitable as a CloudFront custom origin
# domain (Requirement 12.4). Derived from api_endpoint by stripping the scheme;
# no real domain is committed.
output "api_domain_name" {
  description = "Domain name (host only) of the HTTP API, used as the CloudFront API origin domain."
  value       = replace(aws_apigatewayv2_api.this.api_endpoint, "https://", "")
}

output "authorizer_id" {
  description = "ID of the Cognito JWT authorizer applied to the /api/* route."
  value       = aws_apigatewayv2_authorizer.cognito_jwt.id
}

output "stage_name" {
  description = "Name of the deployed stage."
  value       = aws_apigatewayv2_stage.this.name
}
