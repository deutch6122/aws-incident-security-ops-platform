# Task 4 wires only modules implemented in this task. Later platform modules
# remain intentionally absent until their respective implementation tasks.
module "network" {
  source = "../../modules/network"

  name_prefix                     = local.name_prefix
  common_tags                     = local.common_tags
  vpc_cidr                        = var.network_vpc_cidr
  availability_zones              = var.network_availability_zones
  public_subnet_cidrs             = var.network_public_subnet_cidrs
  private_app_subnet_cidrs        = var.network_private_app_subnet_cidrs
  isolated_db_subnet_cidrs        = var.network_isolated_db_subnet_cidrs
  enable_nat_gateway              = var.network_enable_nat_gateway
  allowed_alb_ingress_cidrs       = var.network_allowed_alb_ingress_cidrs
  app_port                        = var.network_app_port
  external_https_egress_cidrs     = var.network_external_https_egress_cidrs
  enable_vpc_endpoints            = var.network_enable_vpc_endpoints
  interface_vpc_endpoint_services = var.network_interface_vpc_endpoint_services
}

module "ecr" {
  source = "../../modules/ecr"

  name_prefix                    = local.name_prefix
  common_tags                    = local.common_tags
  image_tag_mutability           = var.ecr_image_tag_mutability
  untagged_image_expiration_days = var.ecr_untagged_image_expiration_days
  tagged_image_retention_count   = var.ecr_tagged_image_retention_count
  retained_tag_prefixes          = var.ecr_retained_tag_prefixes
}

# Task 6.1 consumes the network module's isolated DB subnet and DB security
# group outputs. These references establish the network-to-Aurora dependency;
# never replace them with public or private application subnets.
module "aurora" {
  source = "../../modules/aurora"

  name_prefix                      = local.name_prefix
  common_tags                      = local.common_tags
  database_subnet_ids              = values(module.network.isolated_db_subnet_ids)
  db_security_group_id             = module.network.security_group_ids.db
  database_name                    = var.aurora_database_name
  engine_version                   = var.aurora_engine_version
  master_username                  = var.aurora_master_username
  master_user_secret_kms_key_id    = var.aurora_master_user_secret_kms_key_id
  min_capacity                     = var.aurora_min_capacity
  max_capacity                     = var.aurora_max_capacity
  backup_retention_period          = var.aurora_backup_retention_period
  enabled_cloudwatch_logs_exports  = var.aurora_enabled_cloudwatch_logs_exports
  performance_insights_enabled     = var.aurora_performance_insights_enabled
  deletion_protection              = var.aurora_deletion_protection
  skip_final_snapshot              = var.aurora_skip_final_snapshot
  final_snapshot_identifier        = var.aurora_final_snapshot_identifier
}

# CodePipeline, CodeBuild, artifact storage, and execution IAM roles are owned
# only by bootstrap/. The canonical dev pipeline contract is documented in
# pipeline-contract.md; this root owns backend inputs and module wiring only.
