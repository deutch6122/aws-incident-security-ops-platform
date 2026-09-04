"""Static Task 4 ECR-module configuration tests; no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
MAIN = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE_DIR / "variables.tf").read_text(encoding="utf-8")
README = (MODULE_DIR / "README.md").read_text(encoding="utf-8")


def test_all_required_component_repositories_are_declared() -> None:
    for component in (
        "backend-api",
        "alarm-event-processor",
        "security-finding-worker",
        "monthly-summary-cronjob",
    ):
        assert f'"{component}"' in VARIABLES
    assert 'resource "aws_ecr_repository" "this"' in MAIN
    assert 'for_each = var.repository_components' in MAIN
    assert 'name                 = "${var.name_prefix}-${each.value}"' in MAIN


def test_repositories_scan_on_push_and_are_immutable_by_default() -> None:
    repository = re.search(
        r'resource "aws_ecr_repository" "this" \{(.*?)\n\}', MAIN, re.DOTALL
    )
    assert repository
    block = repository.group(1)
    assert "scan_on_push = true" in block
    assert 'encryption_type = "AES256"' in block
    mutability = re.search(r'variable "image_tag_mutability" \{(.*?)\n\}', VARIABLES, re.DOTALL)
    assert mutability and 'default     = "IMMUTABLE"' in mutability.group(1)


def test_lifecycle_policy_controls_untagged_and_tagged_images() -> None:
    assert 'resource "aws_ecr_lifecycle_policy" "this"' in MAIN
    assert 'tagStatus   = "untagged"' in MAIN
    assert 'countType   = "sinceImagePushed"' in MAIN
    assert 'countUnit   = "days"' in MAIN
    assert 'tagStatus     = "tagged"' in MAIN
    assert 'countType     = "imageCountMoreThan"' in MAIN
    assert "var.untagged_image_expiration_days" in MAIN
    assert "var.tagged_image_retention_count" in MAIN


def test_names_tags_and_cost_guidance_are_present() -> None:
    assert 'length("${var.name_prefix}-${component}") <= 256' in VARIABLES
    assert "merge(var.common_tags" in MAIN
    assert "cost control" in README
