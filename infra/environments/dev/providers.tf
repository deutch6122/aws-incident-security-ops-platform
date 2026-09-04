# AWS resources for this root are restricted to the dev Region.
provider "aws" {
  region = var.aws_region

  # Provider-level tags apply the platform identity consistently to taggable resources.
  default_tags {
    tags = local.common_tags
  }
}
