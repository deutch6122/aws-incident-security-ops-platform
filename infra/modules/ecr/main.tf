resource "aws_ecr_repository" "this" {
  for_each = var.repository_components

  name                 = "${var.name_prefix}-${each.value}"
  image_tag_mutability = var.image_tag_mutability

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
    # Future extension: add a validated customer-managed KMS key variable when
    # tenancy or compliance requires key-level access controls.
  }

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-${each.value}"
    Component = each.value
  })
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after ${var.untagged_image_expiration_days} days."
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.untagged_image_expiration_days
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Retain only the most recent ${var.tagged_image_retention_count} release-tagged images."
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = var.retained_tag_prefixes
          countType     = "imageCountMoreThan"
          countNumber   = var.tagged_image_retention_count
        }
        action = { type = "expire" }
      },
    ]
  })
}
