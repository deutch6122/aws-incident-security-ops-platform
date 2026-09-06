locals {
  # Canonical prefix required by Requirement 19.1 and Property 11.
  name_prefix = "${var.project}-${var.env}"

  # Merge optional tags first so required identity tags cannot be overridden.
  common_tags = merge(
    var.additional_tags,
    {
      Project     = var.project
      Environment = var.env
      Platform    = "aws-incident-security-ops-platform"
      ManagedBy   = "terraform"
    },
  )

  # Reusable names for resources whose suffixes are supplied by this root.
  # Future modules should receive local.name_prefix and local.common_tags, or a
  # specific entry from this map, rather than rebuilding the convention.
  resource_names = {
    for logical_name, suffix in var.resource_name_suffixes :
    logical_name => "${local.name_prefix}-${suffix}"
  }

  application_images = {
    backend   = "${module.ecr.repository_urls["backend-api"]}:${var.application_image_tag}"
    migration = "${module.ecr.repository_urls["db-migration"]}:${var.application_image_tag}"
  }

  alb_access_logs_suffix   = "${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  alb_access_logs_stem_src = "${local.name_prefix}-alb-logs"
  alb_access_logs_stem_max = 63 - 1 - length(local.alb_access_logs_suffix)
  alb_access_logs_stem     = trimsuffix(substr(local.alb_access_logs_stem_src, 0, max(local.alb_access_logs_stem_max, 0)), "-")
  alb_access_logs_bucket   = "${local.alb_access_logs_stem}-${local.alb_access_logs_suffix}"

  alb_arn_suffix = try(split("loadbalancer/", module.alb.alb_arn)[1], "")
}
