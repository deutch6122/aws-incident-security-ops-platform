output "name_prefix" {
  description = "Canonical prefix for dev resource names."
  value       = local.name_prefix
}

output "common_tags" {
  description = "Non-sensitive required and additional tags used by the AWS provider."
  value       = local.common_tags
}

output "aws_region" {
  description = "AWS Region configured for this dev root."
  value       = var.aws_region
}

output "resource_names" {
  description = "Validated resource names generated from resource_name_suffixes."
  value       = local.resource_names
}

output "network" {
  description = "Non-sensitive network identifiers for later platform modules."
  value = {
    vpc_id                 = module.network.vpc_id
    public_subnet_ids      = module.network.public_subnet_ids
    private_app_subnet_ids = module.network.private_app_subnet_ids
    isolated_db_subnet_ids = module.network.isolated_db_subnet_ids
    security_group_ids     = module.network.security_group_ids
    nat_gateway_id         = module.network.nat_gateway_id
  }
}

output "ecr_repository_urls" {
  description = "ECR repository URLs keyed by deployable component."
  value       = module.ecr.repository_urls
}

output "pipeline_contract" {
  description = "Static dev inputs that must remain aligned with bootstrap CodeBuild/backend configuration."
  value = {
    tf_workdir = var.pipeline_tf_workdir
    backend_key = var.pipeline_backend_key
  }
}

output "aurora" {
  description = "Non-secret Aurora connection metadata and the AWS-managed database secret ARN for later application wiring."
  value = {
    cluster_arn             = module.aurora.cluster_arn
    cluster_id              = module.aurora.cluster_id
    cluster_endpoint        = module.aurora.cluster_endpoint
    writer_endpoint         = module.aurora.writer_endpoint
    port                    = module.aurora.port
    database_name           = module.aurora.database_name
    app_database_secret_arn = module.aurora.app_database_secret_arn
  }
}
