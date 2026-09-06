# Two independent messaging systems: "alarm" and "finding". Each system owns its
# own EventBridge rule + Standard SQS queue + dedicated DLQ + target + queue
# policy + DLQ redrive-allow policy. The two systems never reference each other's
# queues (Requirement 6.1, 6.2). A single local map drives every resource via
# for_each so the two systems share one definition without duplication.
locals {
  systems = {
    alarm = {
      role         = "alarm"
      detail_types = var.alarm_event_detail_types
    }
    finding = {
      role         = "finding"
      detail_types = var.finding_event_detail_types
    }
  }
}

# Per-system dead-letter queue. Messages that exceed sqs_max_receive_count on the
# system's main queue are moved here by that queue's redrive policy so a poison
# message cannot be redelivered forever (Requirement 6.4). SSE-SQS encrypts
# messages at rest; no customer key material or secret is referenced. DLQs are
# separated per system.
resource "aws_sqs_queue" "dlq" {
  for_each = local.systems

  name                      = "${var.name_prefix}-${each.value.role}-dlq"
  message_retention_seconds = var.dlq_message_retention_seconds
  sqs_managed_sse_enabled   = var.sqs_managed_sse

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-${each.value.role}-dlq"
    Component = "messaging"
    Role      = "${each.value.role}-dlq"
  })
}

# Per-system main Standard (not FIFO) queue. At-least-once delivery is expected;
# the worker deletes a message only after its handler succeeds. redrive_policy
# points at the SAME system's DLQ so messages exceeding sqs_max_receive_count are
# moved off the main queue (Requirement 6.4).
resource "aws_sqs_queue" "main" {
  for_each = local.systems

  name                       = "${var.name_prefix}-${each.value.role}"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = var.receive_wait_time_seconds
  sqs_managed_sse_enabled    = var.sqs_managed_sse

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = var.sqs_max_receive_count
  })

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-${each.value.role}"
    Component = "messaging"
    Role      = "${each.value.role}-queue"
  })
}

# Restrict each DLQ so that only its own system's main queue may redrive into it.
# This is the minimum-privilege complement to the main queue's redrive_policy and
# keeps the two systems' DLQs isolated.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  for_each = local.systems

  queue_url = aws_sqs_queue.dlq[each.key].id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.main[each.key].arn]
  })
}

# Per-system EventBridge rule (Requirement 6.1). The event pattern matches the
# shared event source and only this system's detail-type values, so alarm and
# finding events are routed to different queues.
resource "aws_cloudwatch_event_rule" "this" {
  for_each = local.systems

  name        = "${var.name_prefix}-${each.value.role}-rule"
  description = "Routes ${each.value.role} sample platform events to the ${var.name_prefix}-${each.value.role} SQS queue."

  event_pattern = jsonencode({
    source        = [var.event_source]
    "detail-type" = each.value.detail_types
  })

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-${each.value.role}-rule"
    Component = "messaging"
    Role      = "${each.value.role}-event-rule"
  })
}

# Deliver matched events straight to the SAME system's SQS queue (no input
# transformer; the raw event body is what the worker parses). Each rule targets
# only its own queue; there is no cross-system target.
resource "aws_cloudwatch_event_target" "this" {
  for_each = local.systems

  rule      = aws_cloudwatch_event_rule.this[each.key].name
  target_id = "${var.name_prefix}-${each.value.role}-sqs"
  arn       = aws_sqs_queue.main[each.key].arn
}

# Per-system queue policy: allow only the EventBridge service to SendMessage, and
# only for THIS system's rule (aws:SourceArn condition). This is minimum
# privilege for the EventBridge -> SQS delivery path and prevents the other
# system's rule from writing here.
data "aws_iam_policy_document" "queue_policy" {
  for_each = local.systems

  statement {
    sid     = "AllowEventBridgeSendMessage"
    effect  = "Allow"
    actions = ["sqs:SendMessage"]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    resources = [aws_sqs_queue.main[each.key].arn]

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.this[each.key].arn]
    }
  }
}

resource "aws_sqs_queue_policy" "this" {
  for_each = local.systems

  queue_url = aws_sqs_queue.main[each.key].id
  policy    = data.aws_iam_policy_document.queue_policy[each.key].json
}
