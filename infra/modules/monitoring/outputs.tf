output "sns_topic_arn" {
  description = "ARN of the SNS topic wired into every alarm's alarm_actions. Subscribe endpoints out of band."
  value       = aws_sns_topic.alarms.arn
}

output "sns_topic_name" {
  description = "Name of the SNS alarm-notifications topic."
  value       = aws_sns_topic.alarms.name
}

output "alarm_names" {
  description = "All CloudWatch alarm names created by this module (Product_A and Product_B)."
  value = [
    aws_cloudwatch_metric_alarm.sqs_dlq_messages_visible.alarm_name,
    aws_cloudwatch_metric_alarm.ecs_cpu_high.alarm_name,
    aws_cloudwatch_metric_alarm.ecs_memory_high.alarm_name,
    aws_cloudwatch_metric_alarm.ecs_running_tasks_low.alarm_name,
    aws_cloudwatch_metric_alarm.alb_5xx_high.alarm_name,
    aws_cloudwatch_metric_alarm.alb_latency_high.alarm_name,
    aws_cloudwatch_metric_alarm.aurora_acu_high.alarm_name,
    aws_cloudwatch_metric_alarm.aurora_connections_high.alarm_name,
    aws_cloudwatch_metric_alarm.lambda_errors_high.alarm_name,
    aws_cloudwatch_metric_alarm.lambda_throttles_high.alarm_name,
    aws_cloudwatch_metric_alarm.lambda_duration_high.alarm_name,
  ]
}

output "dlq_alarm_name" {
  description = "Name of the SQS DLQ depth > 0 alarm."
  value       = aws_cloudwatch_metric_alarm.sqs_dlq_messages_visible.alarm_name
}

output "product_a_dashboard_name" {
  description = "Name of the Product_A dashboard (ECS/ALB/Aurora/SQS)."
  value       = aws_cloudwatch_dashboard.product_a.dashboard_name
}

output "product_b_dashboard_name" {
  description = "Name of the Product_B dashboard (CloudFront/Lambda/DynamoDB/API Gateway)."
  value       = aws_cloudwatch_dashboard.product_b.dashboard_name
}
