output "public_status_items_table_name" {
  description = "Name of the public_status_items table."
  value       = aws_dynamodb_table.public_status_items.name
}

output "public_status_items_table_arn" {
  description = "ARN of the public_status_items table."
  value       = aws_dynamodb_table.public_status_items.arn
}

output "report_metadata_table_name" {
  description = "Name of the report_metadata table."
  value       = aws_dynamodb_table.report_metadata.name
}

output "report_metadata_table_arn" {
  description = "ARN of the report_metadata table."
  value       = aws_dynamodb_table.report_metadata.arn
}

output "report_metadata_gsi_period_name" {
  description = "Name of the report_metadata GSI keyed on period (yyyymm)."
  value       = "gsi_period"
}

output "page_view_logs_table_name" {
  description = "Name of the page_view_logs table (TTL enabled)."
  value       = aws_dynamodb_table.page_view_logs.name
}

output "page_view_logs_table_arn" {
  description = "ARN of the page_view_logs table (TTL enabled)."
  value       = aws_dynamodb_table.page_view_logs.arn
}

output "maintenance_windows_table_name" {
  description = "Name of the maintenance_windows table (TTL enabled)."
  value       = aws_dynamodb_table.maintenance_windows.name
}

output "maintenance_windows_table_arn" {
  description = "ARN of the maintenance_windows table (TTL enabled)."
  value       = aws_dynamodb_table.maintenance_windows.arn
}

# All four tables intentionally leave DynamoDB Streams disabled, so there is no
# stream ARN to publish. Exposed as an explicit constant so consumers (and the
# snapshot test) can assert the absence of a Product_B -> Product_A push channel.
output "streams_enabled" {
  description = "Always false: no table enables DynamoDB Streams (no push channel toward Product_A)."
  value       = false
}

output "ttl_attribute_name" {
  description = "Attribute name used as the TTL timestamp on the TTL-enabled tables."
  value       = var.ttl_attribute_name
}
