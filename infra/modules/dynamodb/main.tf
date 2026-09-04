locals {
  public_status_items_name = "${var.name_prefix}-public-status-items"
  report_metadata_name     = "${var.name_prefix}-report-metadata"
  page_view_logs_name      = "${var.name_prefix}-page-view-logs"
  maintenance_windows_name = "${var.name_prefix}-maintenance-windows"
}

# Portal_DB is the Product_B (public portal) datastore. All four tables use
# PAY_PER_REQUEST on-demand billing (Requirement 24.5): dev traffic is small and
# hard to predict, so on-demand avoids paying for idle provisioned capacity.
#
# SEPARATION NOTE: these tables belong to Product_B only. This module creates no
# dependency on and no write path into Product_A (Aurora/RDS/EKS/ECS/SQS). The
# A->B one-way link is implemented later by Cronjob_Summary (Task 16.2), not
# here. None of these tables enable Streams, so there is no push channel back
# toward Product_A.

# public_status_items: current incident/status list and detail served to Viewers
# (Requirement 10.1, 10.2, 14.2). PK: status_id.
resource "aws_dynamodb_table" "public_status_items" {
  name         = local.public_status_items_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "status_id"

  attribute {
    name = "status_id"
    type = "S"
  }

  tags = merge(var.common_tags, {
    Name      = local.public_status_items_name
    Component = "dynamodb"
    Role      = "public-status-items"
  })
}

# report_metadata: monthly report metadata list/detail (Requirement 11.1, 11.2,
# 14.1). PK: report_id. GSI gsi_period is keyed on period (yyyymm) so reports can
# be listed/filtered by month efficiently (Requirement 11.1).
resource "aws_dynamodb_table" "report_metadata" {
  name         = local.report_metadata_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "report_id"

  attribute {
    name = "report_id"
    type = "S"
  }

  attribute {
    name = "period"
    type = "S"
  }

  global_secondary_index {
    name            = "gsi_period"
    hash_key        = "period"
    projection_type = "ALL"
  }

  tags = merge(var.common_tags, {
    Name      = local.report_metadata_name
    Component = "dynamodb"
    Role      = "report-metadata"
  })
}

# page_view_logs: append-only view records (Requirement 10.3). PK: view_id. TTL
# is enabled so records self-delete after their retention window, keeping
# storage cost down.
resource "aws_dynamodb_table" "page_view_logs" {
  name         = local.page_view_logs_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "view_id"

  attribute {
    name = "view_id"
    type = "S"
  }

  ttl {
    attribute_name = var.ttl_attribute_name
    enabled        = true
  }

  tags = merge(var.common_tags, {
    Name      = local.page_view_logs_name
    Component = "dynamodb"
    Role      = "page-view-logs"
  })
}

# maintenance_windows: maintenance information (Requirement 10, ancillary). PK:
# window_id. TTL enabled so expired windows self-delete.
resource "aws_dynamodb_table" "maintenance_windows" {
  name         = local.maintenance_windows_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "window_id"

  attribute {
    name = "window_id"
    type = "S"
  }

  ttl {
    attribute_name = var.ttl_attribute_name
    enabled        = true
  }

  tags = merge(var.common_tags, {
    Name      = local.maintenance_windows_name
    Component = "dynamodb"
    Role      = "maintenance-windows"
  })
}
