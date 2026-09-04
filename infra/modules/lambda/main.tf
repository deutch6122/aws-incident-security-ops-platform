locals {
  function_name  = "${var.name_prefix}-portal-api"
  role_name      = "${var.name_prefix}-lambda-portal-role"
  log_group_name = "/aws/lambda/${var.name_prefix}-portal-api"

  use_s3_package = length(trimspace(var.package_s3_bucket)) > 0 && length(trimspace(var.package_s3_key)) > 0

  # Read-only DynamoDB tables for the Portal_API (Product_B only). Includes each
  # base table plus its indexes (report_metadata has GSI gsi_period).
  read_table_arns = [
    var.public_status_items_table_arn,
    var.report_metadata_table_arn,
    var.maintenance_windows_table_arn,
    "${var.public_status_items_table_arn}/index/*",
    "${var.report_metadata_table_arn}/index/*",
    "${var.maintenance_windows_table_arn}/index/*",
  ]
}

# Portal_API Lambda for Product_B (Requirement 9.3, 18.3). The function code is
# implemented in Task 15; this module defines the function shell, its IAM role,
# and its CloudWatch Logs group.
#
# SEPARATION NOTE: the role's permissions are scoped entirely inside Product_B
# (Portal_DB DynamoDB tables). It has NO access to Product_A (Aurora/RDS/ECS/
# EKS/Product_A SQS/Backend API). page_view_logs is the only table this role may
# write, which keeps the A->B link one-way (Requirement 14.3).

resource "aws_iam_role" "portal" {
  name = local.role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(var.common_tags, {
    Name      = local.role_name
    Component = "lambda"
    Role      = "portal-api-execution"
  })
}

# CloudWatch Logs write permission (equivalent to AWSLambdaBasicExecutionRole,
# stated explicitly and scoped to this function's log group) (Requirement 18.3).
resource "aws_iam_role_policy" "logs" {
  name = "${var.name_prefix}-lambda-portal-logs"
  role = aws_iam_role.portal.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "CloudWatchLogs"
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
      ]
      Resource = [
        aws_cloudwatch_log_group.portal.arn,
        "${aws_cloudwatch_log_group.portal.arn}:*",
      ]
    }]
  })
}

# DynamoDB access, split into two least-privilege statements:
#  - read-only on public_status_items / report_metadata / maintenance_windows
#  - write ONLY on page_view_logs
resource "aws_iam_role_policy" "dynamodb" {
  name = "${var.name_prefix}-lambda-portal-dynamodb"
  role = aws_iam_role.portal.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "PortalDynamoRead"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:BatchGetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = local.read_table_arns
      },
      {
        Sid    = "PortalPageViewLogsWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
        ]
        # Write scope is page_view_logs ONLY.
        Resource = [var.page_view_logs_table_arn]
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "portal" {
  name              = local.log_group_name
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-portal-api-logs"
    Component = "lambda"
    Role      = "portal-api-logs"
  })
}

resource "aws_lambda_function" "portal" {
  function_name = local.function_name
  role          = aws_iam_role.portal.arn
  runtime       = var.runtime
  handler       = var.handler
  memory_size   = var.memory_size
  timeout       = var.timeout

  # The deployment package comes from either a local zip (package_filename) or
  # S3 (package_s3_bucket/key). Task 15 supplies the real artifact; the defaults
  # are placeholders so no real path is committed.
  filename  = local.use_s3_package ? null : (length(trimspace(var.package_filename)) > 0 ? var.package_filename : null)
  s3_bucket = local.use_s3_package ? var.package_s3_bucket : null
  s3_key    = local.use_s3_package ? var.package_s3_key : null

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.portal.name
  }

  depends_on = [
    aws_iam_role_policy.logs,
    aws_iam_role_policy.dynamodb,
  ]

  tags = merge(var.common_tags, {
    Name      = local.function_name
    Component = "lambda"
    Role      = "portal-api"
  })
}
