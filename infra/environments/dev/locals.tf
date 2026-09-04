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
}
