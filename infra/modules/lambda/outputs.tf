output "lambda_function_name" {
  description = "Name of the Portal_API Lambda function."
  value       = aws_lambda_function.portal.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Portal_API Lambda function."
  value       = aws_lambda_function.portal.arn
}

output "lambda_invoke_arn" {
  description = "Invoke ARN of the Portal_API Lambda, used by the API Gateway AWS_PROXY integration."
  value       = aws_lambda_function.portal.invoke_arn
}

output "lambda_role_arn" {
  description = "ARN of the lambda-portal-role execution role."
  value       = aws_iam_role.portal.arn
}

output "log_group_name" {
  description = "Name of the CloudWatch Logs group for the Portal_API Lambda."
  value       = aws_cloudwatch_log_group.portal.name
}
