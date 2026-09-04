locals {
  queue_name = "${var.name_prefix}-${var.queue_name_suffix}"
  dlq_name   = "${var.name_prefix}-${var.queue_name_suffix}-dlq"
}

# Dead-letter queue. Messages that exceed max_receive_count on the main queue
# are moved here by the SQS redrive policy so a poison message cannot be
# redelivered forever (Requirement 6.4). SSE-SQS encrypts messages at rest; no
# customer key material or secret is referenced.
resource "aws_sqs_queue" "dlq" {
  name                      = local.dlq_name
  message_retention_seconds = var.dlq_message_retention_seconds
  sqs_managed_sse_enabled   = var.sqs_managed_sse

  tags = merge(var.common_tags, {
    Name      = local.dlq_name
    Component = "messaging"
    Role      = "dlq"
  })
}

# Main Standard (not FIFO) queue. At-least-once delivery is expected; the worker
# deletes a message only after its handler succeeds. redrive_policy points at
# the DLQ so messages exceeding max_receive_count are moved off the main queue
# (Requirement 6.4).
resource "aws_sqs_queue" "main" {
  name                       = local.queue_name
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = var.receive_wait_time_seconds
  sqs_managed_sse_enabled    = var.sqs_managed_sse

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = merge(var.common_tags, {
    Name      = local.queue_name
    Component = "messaging"
    Role      = "main-queue"
  })
}

# Restrict the DLQ so that only the main queue may redrive into it. This is the
# minimum-privilege complement to the main queue's redrive_policy.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.main.arn]
  })
}

# EventBridge rule for injecting sample events (Requirement 6.1). The event
# pattern is variable-driven; the default matches the platform sample source.
resource "aws_cloudwatch_event_rule" "this" {
  name          = "${var.name_prefix}-${var.queue_name_suffix}-rule"
  description   = "Routes sample platform events to the ${local.queue_name} SQS queue."
  event_pattern = jsonencode(var.eventbridge_event_pattern)

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-${var.queue_name_suffix}-rule"
    Component = "messaging"
    Role      = "event-rule"
  })
}

# Deliver matched events straight to the main SQS queue (no input transformer;
# the raw event body is what the worker parses).
resource "aws_cloudwatch_event_target" "this" {
  rule      = aws_cloudwatch_event_rule.this.name
  target_id = "${var.name_prefix}-${var.queue_name_suffix}-sqs"
  arn       = aws_sqs_queue.main.arn
}

# Queue policy: allow only the EventBridge service to SendMessage, and only for
# this specific rule (aws:SourceArn condition). This is minimum privilege for
# the EventBridge -> SQS delivery path.
data "aws_iam_policy_document" "queue_policy" {
  statement {
    sid     = "AllowEventBridgeSendMessage"
    effect  = "Allow"
    actions = ["sqs:SendMessage"]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    resources = [aws_sqs_queue.main.arn]

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.this.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "this" {
  queue_url = aws_sqs_queue.main.id
  policy    = data.aws_iam_policy_document.queue_policy.json
}
