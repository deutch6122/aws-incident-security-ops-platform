locals {
  topic_name             = "${var.name_prefix}-alarms"
  product_a_dashboard    = "${var.name_prefix}-product-a"
  product_b_dashboard    = "${var.name_prefix}-product-b"
  alarm_actions          = [aws_sns_topic.alarms.arn]
  ok_actions             = [aws_sns_topic.alarms.arn]
  evaluation_periods     = var.alarm_evaluation_periods
  period_seconds         = var.alarm_period_seconds
}

# --------------------------------------------------------------------------- #
# SNS topic. Every alarm's alarm_actions (and ok_actions) point here so a single
# topic fans out notifications. Subscriptions (email/chatbot) are added out of
# band; no real endpoint / secret is embedded (Requirement 18.1).
# --------------------------------------------------------------------------- #
resource "aws_sns_topic" "alarms" {
  name = local.topic_name

  tags = merge(var.common_tags, {
    Name      = local.topic_name
    Component = "monitoring"
    Role      = "alarm-notifications"
  })
}

# --------------------------------------------------------------------------- #
# Product_A alarms                                                             #
# --------------------------------------------------------------------------- #

# SQS DLQ depth > 0: a message reached the dead-letter queue and needs triage
# (Requirement 6.4 / DLQ 運用方針). Uses "notBreaching" so absent data is healthy.
resource "aws_cloudwatch_metric_alarm" "sqs_dlq_messages_visible" {
  alarm_name          = "${var.name_prefix}-sqs-dlq-messages-visible"
  alarm_description   = "SQS DLQ has one or more visible messages; investigate poison events."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = local.evaluation_periods
  period              = local.period_seconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = var.dlq_queue_name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.ok_actions

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-sqs-dlq-messages-visible"
    Component = "monitoring"
    Product   = "A"
  })
}

resource "aws_cloudwatch_metric_alarm" "ecs_cpu_high" {
  alarm_name          = "${var.name_prefix}-ecs-cpu-high"
  alarm_description   = "ECS service CPUUtilization is high."
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.ecs_cpu_high_threshold_percent
  evaluation_periods  = local.evaluation_periods
  period              = local.period_seconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.ok_actions

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-ecs-cpu-high"
    Component = "monitoring"
    Product   = "A"
  })
}

resource "aws_cloudwatch_metric_alarm" "ecs_memory_high" {
  alarm_name          = "${var.name_prefix}-ecs-memory-high"
  alarm_description   = "ECS service MemoryUtilization is high."
  namespace           = "AWS/ECS"
  metric_name         = "MemoryUtilization"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.ecs_memory_high_threshold_percent
  evaluation_periods  = local.evaluation_periods
  period              = local.period_seconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.ok_actions

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-ecs-memory-high"
    Component = "monitoring"
    Product   = "A"
  })
}

# RunningTaskCount below the desired minimum means the Backend_API is degraded.
resource "aws_cloudwatch_metric_alarm" "ecs_running_tasks_low" {
  alarm_name          = "${var.name_prefix}-ecs-running-tasks-low"
  alarm_description   = "ECS service RunningTaskCount dropped below the desired minimum."
  namespace           = "ECS/ContainerInsights"
  metric_name         = "RunningTaskCount"
  statistic           = "Minimum"
  comparison_operator = "LessThanThreshold"
  threshold           = var.ecs_min_running_tasks
  evaluation_periods  = local.evaluation_periods
  period              = local.period_seconds
  treat_missing_data  = "breaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.ok_actions

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-ecs-running-tasks-low"
    Component = "monitoring"
    Product   = "A"
  })
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx_high" {
  alarm_name          = "${var.name_prefix}-alb-5xx-high"
  alarm_description   = "ALB is returning HTTP 5XX responses above threshold."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_ELB_5XX_Count"
  statistic           = "Sum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alb_5xx_threshold_count
  evaluation_periods  = local.evaluation_periods
  period              = local.period_seconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.ok_actions

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-alb-5xx-high"
    Component = "monitoring"
    Product   = "A"
  })
}

resource "aws_cloudwatch_metric_alarm" "alb_latency_high" {
  alarm_name          = "${var.name_prefix}-alb-latency-high"
  alarm_description   = "ALB TargetResponseTime (latency) is high."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "TargetResponseTime"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alb_latency_threshold_seconds
  evaluation_periods  = local.evaluation_periods
  period              = local.period_seconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.ok_actions

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-alb-latency-high"
    Component = "monitoring"
    Product   = "A"
  })
}

resource "aws_cloudwatch_metric_alarm" "aurora_acu_high" {
  alarm_name          = "${var.name_prefix}-aurora-acu-high"
  alarm_description   = "Aurora ServerlessDatabaseCapacity (ACU) is at or near the max ACU."
  namespace           = "AWS/RDS"
  metric_name         = "ServerlessDatabaseCapacity"
  statistic           = "Average"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = var.aurora_acu_threshold
  evaluation_periods  = local.evaluation_periods
  period              = local.period_seconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBClusterIdentifier = var.aurora_db_cluster_identifier
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.ok_actions

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-aurora-acu-high"
    Component = "monitoring"
    Product   = "A"
  })
}

resource "aws_cloudwatch_metric_alarm" "aurora_connections_high" {
  alarm_name          = "${var.name_prefix}-aurora-connections-high"
  alarm_description   = "Aurora DatabaseConnections is high."
  namespace           = "AWS/RDS"
  metric_name         = "DatabaseConnections"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.aurora_connections_threshold
  evaluation_periods  = local.evaluation_periods
  period              = local.period_seconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBClusterIdentifier = var.aurora_db_cluster_identifier
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.ok_actions

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-aurora-connections-high"
    Component = "monitoring"
    Product   = "A"
  })
}

# --------------------------------------------------------------------------- #
# Product_B alarms (Lambda / Portal_API)                                       #
# --------------------------------------------------------------------------- #
resource "aws_cloudwatch_metric_alarm" "lambda_errors_high" {
  alarm_name          = "${var.name_prefix}-lambda-errors-high"
  alarm_description   = "Portal_API Lambda Errors above threshold."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = var.lambda_errors_threshold_count
  evaluation_periods  = local.evaluation_periods
  period              = local.period_seconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.ok_actions

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-lambda-errors-high"
    Component = "monitoring"
    Product   = "B"
  })
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles_high" {
  alarm_name          = "${var.name_prefix}-lambda-throttles-high"
  alarm_description   = "Portal_API Lambda Throttles above threshold."
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  statistic           = "Sum"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = var.lambda_throttles_threshold_count
  evaluation_periods  = local.evaluation_periods
  period              = local.period_seconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.ok_actions

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-lambda-throttles-high"
    Component = "monitoring"
    Product   = "B"
  })
}

resource "aws_cloudwatch_metric_alarm" "lambda_duration_high" {
  alarm_name          = "${var.name_prefix}-lambda-duration-high"
  alarm_description   = "Portal_API Lambda Duration approaching the 10s timeout."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.lambda_duration_threshold_ms
  evaluation_periods  = local.evaluation_periods
  period              = local.period_seconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.ok_actions

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-lambda-duration-high"
    Component = "monitoring"
    Product   = "B"
  })
}

# --------------------------------------------------------------------------- #
# Dashboards: two, separated by product responsibility (Requirement 18.1).     #
#   Product_A: ECS / ALB / Aurora / SQS(+DLQ) — internal ops plane.            #
#   Product_B: CloudFront / Lambda / DynamoDB / API Gateway — delivery plane.  #
# --------------------------------------------------------------------------- #
resource "aws_cloudwatch_dashboard" "product_a" {
  dashboard_name = local.product_a_dashboard

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6,
        properties = {
          title  = "ECS CPU / Memory"
          region = var.aws_region
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_service_name],
            ["AWS/ECS", "MemoryUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_service_name],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6,
        properties = {
          title  = "ALB 5XX / Latency"
          region = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", var.alb_arn_suffix],
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", var.alb_arn_suffix],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6,
        properties = {
          title  = "Aurora ACU / Connections"
          region = var.aws_region
          metrics = [
            ["AWS/RDS", "ServerlessDatabaseCapacity", "DBClusterIdentifier", var.aurora_db_cluster_identifier],
            ["AWS/RDS", "DatabaseConnections", "DBClusterIdentifier", var.aurora_db_cluster_identifier],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 12, height = 6,
        properties = {
          title  = "SQS DLQ depth"
          region = var.aws_region
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.dlq_queue_name],
          ]
        }
      },
    ]
  })
}

resource "aws_cloudwatch_dashboard" "product_b" {
  dashboard_name = local.product_b_dashboard

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6,
        properties = {
          title  = "Portal_API Lambda Errors / Throttles / Duration"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", var.lambda_function_name],
            ["AWS/Lambda", "Throttles", "FunctionName", var.lambda_function_name],
            ["AWS/Lambda", "Duration", "FunctionName", var.lambda_function_name],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6,
        properties = {
          # CloudFront metrics live in us-east-1; the widget declares that region.
          title  = "CloudFront Requests / 5xxErrorRate"
          region = "us-east-1"
          metrics = [
            ["AWS/CloudFront", "Requests"],
            ["AWS/CloudFront", "5xxErrorRate"],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6,
        properties = {
          title  = "API Gateway 5xx / Latency"
          region = var.aws_region
          metrics = [
            ["AWS/ApiGateway", "5xx"],
            ["AWS/ApiGateway", "Latency"],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 12, height = 6,
        properties = {
          title  = "DynamoDB ConsumedRead/Write & Throttles"
          region = var.aws_region
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits"],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits"],
            ["AWS/DynamoDB", "ThrottledRequests"],
          ]
        }
      },
    ]
  })
}
