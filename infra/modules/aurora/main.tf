locals {
  # A final snapshot is retained by default. Operators should provide a unique
  # reviewed identifier for repeated destroy/recreate workflows.
  effective_final_snapshot_identifier = coalesce(
    var.final_snapshot_identifier,
    substr("${var.name_prefix}-aurora-final", 0, 63),
  )
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-aurora-subnets"
  description = "Isolated database subnets for the Aurora PostgreSQL cluster."
  subnet_ids = var.database_subnet_ids

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-aurora-subnets"
    Component = "aurora"
    Tier      = "isolated-db"
  })
}

resource "aws_rds_cluster" "this" {
  cluster_identifier = "${var.name_prefix}-aurora"
  engine             = "aurora-postgresql"
  engine_version     = var.engine_version
  database_name      = var.database_name
  master_username    = var.master_username

  # RDS generates, stores, and returns the master credential through Secrets
  # Manager. Terraform never receives or writes a plaintext password.
  manage_master_user_password   = true
  master_user_secret_kms_key_id = var.master_user_secret_kms_key_id

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.db_security_group_id]
  storage_encrypted      = true

  backup_retention_period      = var.backup_retention_period
  enabled_cloudwatch_logs_exports = tolist(var.enabled_cloudwatch_logs_exports)
  deletion_protection           = var.deletion_protection
  skip_final_snapshot           = var.skip_final_snapshot
  final_snapshot_identifier     = var.skip_final_snapshot ? null : local.effective_final_snapshot_identifier
  copy_tags_to_snapshot         = true
  apply_immediately             = false

  serverlessv2_scaling_configuration {
    min_capacity = var.min_capacity
    max_capacity = var.max_capacity
  }

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-aurora"
    Component = "aurora"
    Role      = "database-cluster"
  })
}

# The MVP intentionally creates exactly one writer and no reader instances.
# Aurora storage remains multi-AZ by service design; this does not describe the
# database as single-AZ. An RDS PostgreSQL db.t4g.micro single-AZ deployment is
# a documented cost alternative, not a conditional implementation here.
resource "aws_rds_cluster_instance" "writer" {
  identifier         = "${var.name_prefix}-aurora-writer"
  cluster_identifier = aws_rds_cluster.this.id
  engine             = aws_rds_cluster.this.engine
  engine_version     = aws_rds_cluster.this.engine_version
  instance_class     = "db.serverless"

  publicly_accessible          = false
  auto_minor_version_upgrade   = true
  performance_insights_enabled = var.performance_insights_enabled

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-aurora-writer"
    Component = "aurora"
    Role      = "writer"
  })
}
