locals {
  bucket_name = "${var.name_prefix}-portal-storage"
}

# Portal_Storage: static site + monthly report files for Product_B. Objects are
# served only through CloudFront using OAC; the bucket is never public.
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
# governed only by the bucket policy (OAC), never by object/bucket ACLs.
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

# OAC-only bucket policy: allow s3:GetObject solely to the CloudFront service
# principal, and only when the request originates from this specific
# distribution (aws:SourceArn condition). Any request that is not the OAC of the
# configured distribution - including direct public requests - is denied because
# it never matches this Allow (Requirement 12.3). No public "*" principal exists.
data "aws_iam_policy_document" "portal" {
  statement {
    sid     = "AllowCloudFrontOACRead"
    effect  = "Allow"
    actions = ["s3:GetObject"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    resources = ["${aws_s3_bucket.portal.arn}/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [var.cloudfront_distribution_arn]
    }
  }
}

resource "aws_s3_bucket_policy" "portal" {
  bucket = aws_s3_bucket.portal.id
  policy = data.aws_iam_policy_document.portal.json

  # Ensure the public access block is in place before the policy is attached.
  depends_on = [aws_s3_bucket_public_access_block.portal]
}
