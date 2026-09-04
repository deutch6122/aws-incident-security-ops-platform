output "user_pool_id" {
  description = "ID of the Cognito User Pool."
  value       = aws_cognito_user_pool.this.id
}

output "user_pool_arn" {
  description = "ARN of the Cognito User Pool (usable as an API Gateway JWT authorizer audience source)."
  value       = aws_cognito_user_pool.this.arn
}

output "user_pool_endpoint" {
  description = "Endpoint (host) of the Cognito User Pool."
  value       = aws_cognito_user_pool.this.endpoint
}

output "app_client_id" {
  description = "ID of the public App Client used by the Portal frontend (no client secret)."
  value       = aws_cognito_user_pool_client.portal.id
}

# OIDC issuer URL built locally from the region and the runtime user pool id.
# The concrete pool id is resolved by Terraform at apply time; no real id is
# committed here. The API Gateway JWT authorizer (Task 14.2) uses this as its
# issuer.
output "issuer_url" {
  description = "OIDC issuer URL for the User Pool, used by the API Gateway JWT authorizer."
  value       = "https://cognito-idp.${local.region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
}
