# AWS resources for this root are restricted to the dev Region.
provider "aws" {
  region = var.aws_region

  # Provider-level tags apply the platform identity consistently to taggable resources.
  default_tags {
    tags = local.common_tags
  }
}

# CloudFront-scope WAF resources must be created in us-east-1. The child WAF
# module receives this alias as its ordinary `aws` provider and therefore does
# not refer to a root provider alias directly.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = local.common_tags
  }
}
