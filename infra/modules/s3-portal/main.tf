# Bucket naming: real values are never embedded. The name is derived from the
# name_prefix, the fixed purpose "portal-storage", the current account id (from a
# data source), and the region. The suffix "<account-id>-<region>" is always
# appended in full to keep names globally unique; only the STEM is deterministically
# truncated so the whole name stays within the 63-character S3 limit.
data "aws_caller_identity" "current" {}

locals {
  bucket_suffix   = "${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  bucket_stem_src = "${var.name_prefix}-portal-storage"
  # Max stem length = 63 - 1 (the hyphen joining stem and suffix) - length(suffix).
  bucket_stem_max = 63 - 1 - length(local.bucket_suffix)
  # Truncate the stem (never the suffix) and strip any trailing hyphen created by
  # the cut so the join does not produce a double hyphen or a leading/trailing dash.
  bucket_stem = trimsuffix(substr(local.bucket_stem_src, 0, max(local.bucket_stem_max, 0)), "-")
  bucket_name = "${local.bucket_stem}-${local.bucket_suffix}"
}

# Portal_Storage: static site + monthly report files for Product_B. Objects are
# served only through CloudFront using OAC; the bucket is never public.
#
# OWNERSHIP BOUNDARY: this module owns the S3 bucket foundation ONLY. The
# CloudFront distribution is created in Task 22, and the OAC bucket policy is
# owned by the dev root in Task 27 (so that s3-portal and cloudfront do not form
# a circular dependency). This module therefore creates NO aws_s3_bucket_policy
# and takes NO cloudfront_distribution_arn input.
#
# SEPARATION NOTE: this bucket belongs to Product_B. It has no dependency on and
# no write path into Product_A. Product_A's Cronjob_Summary places report files
# under reports/* via the A->B one-way link (Task 16.2); that write path is not
# defined here.
resource "aws_s3_bucket" "portal" {
  bucket        = local.bucket_name
  force_destroy = var.force_destroy

  tags = merge(var.common_tags, {
    Name      = local.bucket_name
    Component = "s3-portal"
    Role      = "portal-storage"
  })
}

# Enforce bucket-owner ownership so object ACLs are disabled entirely; access is
# governed only by the bucket policy (owned by the dev root, Task 27), never by
# object/bucket ACLs.
resource "aws_s3_bucket_ownership_controls" "portal" {
  bucket = aws_s3_bucket.portal.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Public access block: all four settings true. The bucket is never public; the
# only read path is CloudFront via OAC (Requirement 12.2, 12.3).
resource "aws_s3_bucket_public_access_block" "portal" {
  bucket = aws_s3_bucket.portal.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Server-side encryption at rest (SSE-S3). No customer key material or secret is
# referenced.
resource "aws_s3_bucket_server_side_encryption_configuration" "portal" {
  bucket = aws_s3_bucket.portal.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "portal" {
  bucket = aws_s3_bucket.portal.id

  versioning_configuration {
    status = "Enabled"
  }
}
