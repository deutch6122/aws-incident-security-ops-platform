"""Static Task 6.1 Aurora configuration tests; no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_DIR.parents[2]
DEV_ROOT = REPOSITORY_ROOT / "infra" / "environments" / "dev"

MAIN = (MODULE_DIR / "main.tf").read_text(encoding="utf-8")
VARIABLES = (MODULE_DIR / "variables.tf").read_text(encoding="utf-8")
OUTPUTS = (MODULE_DIR / "outputs.tf").read_text(encoding="utf-8")
README = (MODULE_DIR / "README.md").read_text(encoding="utf-8")
DEV_MAIN = (DEV_ROOT / "main.tf").read_text(encoding="utf-8")
DEV_OUTPUTS = (DEV_ROOT / "outputs.tf").read_text(encoding="utf-8")
DEV_TFVARS = (DEV_ROOT / "terraform.tfvars.example").read_text(encoding="utf-8")


def test_serverless_v2_cluster_has_one_private_writer_and_no_reader() -> None:
    assert 'resource "aws_rds_cluster" "this"' in MAIN
    assert 'engine             = "aurora-postgresql"' in MAIN
    assert "engine_version     = var.engine_version" in MAIN
    assert "serverlessv2_scaling_configuration" in MAIN
    assert "min_capacity = var.min_capacity" in MAIN
    assert "max_capacity = var.max_capacity" in MAIN
    assert 'resource "aws_rds_cluster_instance" "writer"' in MAIN
    assert 'instance_class     = "db.serverless"' in MAIN
    assert "publicly_accessible          = false" in MAIN
    assert 'resource "aws_rds_cluster_instance" "reader"' not in MAIN
    assert "for_each" not in MAIN.split('resource "aws_rds_cluster_instance" "writer"', 1)[1]
    assert 'default     = 0.5' in VARIABLES
    assert 'default     = 2' in VARIABLES


def test_isolated_subnet_group_and_database_security_group_are_exclusive() -> None:
    assert 'resource "aws_db_subnet_group" "this"' in MAIN
    assert "subnet_ids = var.database_subnet_ids" in MAIN
    assert "db_subnet_group_name   = aws_db_subnet_group.this.name" in MAIN
    assert "vpc_security_group_ids = [var.db_security_group_id]" in MAIN
    assert "database_subnet_ids" in VARIABLES
    assert "db_security_group_id" in VARIABLES


def test_rds_manages_master_secret_without_plaintext_tfvars_or_outputs() -> None:
    assert "manage_master_user_password   = true" in MAIN
    assert "master_user_secret_kms_key_id = var.master_user_secret_kms_key_id" in MAIN
    assert not re.search(r"(?m)^\s*master_password\s*=", MAIN)
    assert "aws_secretsmanager_secret_version" not in MAIN
    assert "master_user_secret[0].secret_arn" in OUTPUTS
    assert ".secret_string" not in OUTPUTS
    assert ".password" not in OUTPUTS
    assert not re.search(r"(?mi)^\\s*(?:master_)?password\\s*=", DEV_TFVARS)
    assert "master_username" in VARIABLES
    assert "master_user_secret_kms_key_id" in VARIABLES


def test_tags_and_dev_lifecycle_observability_defaults_are_declared() -> None:
    assert "merge(var.common_tags" in MAIN
    assert "var.name_prefix" in MAIN
    assert "backup_retention_period      = var.backup_retention_period" in MAIN
    assert "enabled_cloudwatch_logs_exports" in MAIN
    assert "performance_insights_enabled = var.performance_insights_enabled" in MAIN
    assert "deletion_protection           = var.deletion_protection" in MAIN
    assert "skip_final_snapshot           = var.skip_final_snapshot" in MAIN
    assert 'default     = 1' in VARIABLES
    assert 'default     = false' in VARIABLES


def test_dev_root_wires_network_outputs_and_exposes_non_secret_database_metadata() -> None:
    assert 'module "aurora"' in DEV_MAIN
    assert 'source = "../../modules/aurora"' in DEV_MAIN
    assert re.search(r"database_subnet_ids\s+=\s+values\(module\.network\.isolated_db_subnet_ids\)", DEV_MAIN)
    assert re.search(r"db_security_group_id\s+=\s+module\.network\.security_group_ids\.db", DEV_MAIN)
    assert 'output "aurora"' in DEV_OUTPUTS
    assert "module.aurora.app_database_secret_arn" in DEV_OUTPUTS
    for value in ("aurora_engine_version", "aurora_min_capacity", "aurora_max_capacity", "aurora_master_username", "aurora_backup_retention_period"):
        assert value in (DEV_ROOT / "variables.tf").read_text(encoding="utf-8")
        assert value in DEV_TFVARS


def test_readme_states_aurora_topology_rds_alternative_and_phase_two_risks() -> None:
    assert "one Writer instance and zero Reader instances" in README
    assert "multiple Availability Zones" in README
    assert "RDS PostgreSQL single-AZ with a `db.t4g.micro`-class instance" in README
    assert "continuous dev cost" in README
    assert "Serverless v2 support" in README
    assert "before apply" in README
    assert "secret rotation" in README
    assert "skip_final_snapshot" in README
    assert "GetSecretValue" in README
