output "queue_arn" {
  description = "ARN of the main Standard queue. Passed to the eks module as sqs_queue_arns so the worker role may receive and delete."
  value       = aws_sqs_queue.main.arn
}

output "queue_url" {
  description = "URL of the main Standard queue. Supplied to the EKS worker Deployment as WORKER_SQS_QUEUE_URL."
  value       = aws_sqs_queue.main.url
}

output "queue_name" {
  description = "Name of the main Standard queue."
  value       = aws_sqs_queue.main.name
}

output "dlq_arn" {
  description = "ARN of the dead-letter queue (used by monitoring to alarm on DLQ depth > 0)."
  value       = aws_sqs_queue.dlq.arn
}

output "dlq_url" {
  description = "URL of the dead-letter queue."
  value       = aws_sqs_queue.dlq.url
}

output "dlq_name" {
  description = "Name of the dead-letter queue."
  value       = aws_sqs_queue.dlq.name
}

output "event_rule_arn" {
  description = "ARN of the EventBridge rule that delivers sample events to the main queue."
  value       = aws_cloudwatch_event_rule.this.arn
}
