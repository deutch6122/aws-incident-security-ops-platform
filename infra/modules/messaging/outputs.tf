# --- Alarm system outputs -------------------------------------------------

output "alarm_queue_name" {
  description = "Name of the alarm-system Standard queue."
  value       = aws_sqs_queue.main["alarm"].name
}

output "alarm_queue_url" {
  description = "URL of the alarm-system Standard queue. Supplied to the alarm worker as its SQS queue URL."
  value       = aws_sqs_queue.main["alarm"].url
}

output "alarm_queue_arn" {
  description = "ARN of the alarm-system Standard queue. Passed to the eks module so the alarm worker role may receive and delete on this queue only."
  value       = aws_sqs_queue.main["alarm"].arn
}

output "alarm_dlq_name" {
  description = "Name of the alarm-system dead-letter queue."
  value       = aws_sqs_queue.dlq["alarm"].name
}

output "alarm_dlq_url" {
  description = "URL of the alarm-system dead-letter queue."
  value       = aws_sqs_queue.dlq["alarm"].url
}

output "alarm_dlq_arn" {
  description = "ARN of the alarm-system dead-letter queue (used by monitoring to alarm on DLQ depth > 0)."
  value       = aws_sqs_queue.dlq["alarm"].arn
}

output "alarm_event_rule_arn" {
  description = "ARN of the EventBridge rule that delivers alarm events to the alarm queue."
  value       = aws_cloudwatch_event_rule.this["alarm"].arn
}

# --- Finding system outputs -----------------------------------------------

output "finding_queue_name" {
  description = "Name of the finding-system Standard queue."
  value       = aws_sqs_queue.main["finding"].name
}

output "finding_queue_url" {
  description = "URL of the finding-system Standard queue. Supplied to the finding worker as its SQS queue URL."
  value       = aws_sqs_queue.main["finding"].url
}

output "finding_queue_arn" {
  description = "ARN of the finding-system Standard queue. Passed to the eks module so the finding worker role may receive and delete on this queue only."
  value       = aws_sqs_queue.main["finding"].arn
}

output "finding_dlq_name" {
  description = "Name of the finding-system dead-letter queue."
  value       = aws_sqs_queue.dlq["finding"].name
}

output "finding_dlq_url" {
  description = "URL of the finding-system dead-letter queue."
  value       = aws_sqs_queue.dlq["finding"].url
}

output "finding_dlq_arn" {
  description = "ARN of the finding-system dead-letter queue (used by monitoring to alarm on DLQ depth > 0)."
  value       = aws_sqs_queue.dlq["finding"].arn
}

output "finding_event_rule_arn" {
  description = "ARN of the EventBridge rule that delivers finding events to the finding queue."
  value       = aws_cloudwatch_event_rule.this["finding"].arn
}

output "securityhub_critical_event_rule_arn" {
  description = "ARN of the native Security Hub CRITICAL finding EventBridge rule."
  value       = aws_cloudwatch_event_rule.securityhub_critical.arn
}
