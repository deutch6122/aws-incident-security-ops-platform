"""Static Task 4 dev/bootstrap Infra_Pipeline contract tests; no Terraform or AWS access."""

from __future__ import annotations

import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
DEV_ROOT = TESTS_DIR.parent
REPOSITORY_ROOT = DEV_ROOT.parents[2]
BOOTSTRAP = REPOSITORY_ROOT / "bootstrap"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dev_root_wires_modules_but_owns_no_pipeline_or_build_resource() -> None:
    main = _read(DEV_ROOT / "main.tf")
    dev_terraform = "\n".join(_read(path) for path in DEV_ROOT.glob("*.tf"))

    assert 'module "network"' in main
    assert 'module "ecr"' in main
    assert 'source = "../../modules/network"' in main
    assert 'source = "../../modules/ecr"' in main
    assert 'resource "aws_codepipeline"' not in dev_terraform
    assert 'resource "aws_codebuild_project"' not in dev_terraform


def test_bootstrap_owns_the_required_pipeline_order_and_manual_approval() -> None:
    cicd = _read(BOOTSTRAP / "cicd.tf")
    stage_names = re.findall(r'stage\s*\{\s*name\s*=\s*"([^"]+)"', cicd)
    assert stage_names == ["Source", "Fmt", "Validate", "Plan", "Approval", "Apply"]
    assert 'provider = "Manual"' in cicd
    assert 'input_artifacts = ["source_output", "plan_output"]' in cicd
    assert 'PrimarySource = "source_output"' in cicd


def test_apply_plan_artifact_and_assume_role_contract_is_preserved() -> None:
    buildspec = _read(BOOTSTRAP / "buildspec" / "buildspec.yml")
    apply_buildspec = _read(BOOTSTRAP / "buildspec" / "buildspec-apply.yml")
    iam = _read(BOOTSTRAP / "iam.tf")

    for text in (buildspec, apply_buildspec):
        assert 'CODEBUILD_SRC_DIR_${PLAN_ARTIFACT_NAME' in text
        assert 'apply -input=false -auto-approve "$PLAN_FILE"' in text
    assert "sts:AssumeRole" in iam
    assert "aws_iam_role.codebuild.arn" in iam
    assert 'variable = "iam:PassedToService"' in iam


def test_dev_workdir_backend_and_documentation_match_bootstrap() -> None:
    variables = _read(DEV_ROOT / "variables.tf")
    backend = _read(DEV_ROOT / "backend.tf.example")
    contract = _read(DEV_ROOT / "pipeline-contract.md")
    tfvars = _read(DEV_ROOT / "pipeline.tfvars.example")
    buildspecs = [
        _read(BOOTSTRAP / "buildspec" / name)
        for name in ("buildspec.yml", "buildspec-fmt.yml", "buildspec-validate.yml", "buildspec-plan.yml", "buildspec-apply.yml")
    ]

    assert 'default     = "infra/environments/dev"' in variables
    assert 'default     = "environments/dev/terraform.tfstate"' in variables
    assert 'key          = "environments/dev/terraform.tfstate"' in backend
    assert 'pipeline_tf_workdir = "infra/environments/dev"' in tfvars
    assert 'pipeline_backend_key = "environments/dev/terraform.tfstate"' in tfvars
    assert "Source → Fmt → Validate → Plan → Approval → Apply" in contract
    assert "Aurora, NAT Gateway, EKS, and CloudFront" in contract
    for buildspec in buildspecs:
        assert 'TF_WORKDIR: "infra/environments/dev"' in buildspec
