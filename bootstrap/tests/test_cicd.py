"""Bootstrap CI/CD 構成の静的検証（Req 21.1）。

artifact 用 S3 の public access block 有効などを検査する。
terraform 実行・AWS 認証は不要。
"""

from __future__ import annotations

import re

from conftest import read_tf


def test_artifact_bucket_public_access_block_all_true():
    """artifact 用 S3 の public access block 4 項目が全て true であること。"""
    cicd = read_tf("cicd.tf")
    m = re.search(
        r'resource\s+"aws_s3_bucket_public_access_block"\s+"artifacts"\s*\{(.*?)\}',
        cicd,
        flags=re.DOTALL,
    )
    assert m, "artifact 用 aws_s3_bucket_public_access_block リソースが見つからない"
    block = m.group(1)
    for key in [
        "block_public_acls",
        "block_public_policy",
        "ignore_public_acls",
        "restrict_public_buckets",
    ]:
        assert re.search(rf"{key}\s*=\s*true", block), f"artifact S3 の {key} が true でない"


def test_artifact_bucket_versioning_and_encryption():
    """artifact 用 S3 にバージョニングと暗号化が設定されていること。"""
    cicd = read_tf("cicd.tf")
    assert "aws_s3_bucket_versioning" in cicd
    assert "aws_s3_bucket_server_side_encryption_configuration" in cicd
    assert 'resource "aws_kms_key" "artifacts"' in cicd
    assert 'sse_algorithm     = "aws:kms"' in cicd
    assert "kms_master_key_id = aws_kms_key.artifacts.arn" in cicd
    assert 'resource "aws_s3_bucket_lifecycle_configuration" "artifacts"' in cicd


def test_pipeline_artifact_store_uses_the_artifact_kms_key():
    cicd = read_tf("cicd.tf")
    assert "encryption_key" in cicd
    assert "id   = aws_kms_key.artifacts.arn" in cicd
    assert 'type = "KMS"' in cicd


def test_codebuild_receives_backend_artifact_and_ssm_parameter_names():
    cicd = read_tf("cicd.tf")
    for name in (
        "TF_BACKEND_BUCKET",
        "ARTIFACT_BUCKET",
        "ARTIFACT_KMS_KEY_ARN",
        "SSM_ALB_CERTIFICATE_ARN",
        "SSM_EKS_OPERATOR_PRINCIPAL_ARN",
        "SSM_MIGRATION_LAUNCHER_PRINCIPALS",
        "SSM_EKS_PUBLIC_ACCESS_CIDRS",
        "SSM_APPLICATION_IMAGE_TAG",
        "SSM_ECS_DESIRED_COUNT",
        "SSM_COGNITO_CALLBACK_URLS",
        "SSM_COGNITO_LOGOUT_URLS",
        "SSM_COGNITO_KEEP_LOCALHOST_URLS",
        "SSM_MONITORING_ENABLE_SNS_SUBSCRIPTION",
        "SSM_MONITORING_NOTIFICATION_PARAMETER_NAME",
        "SSM_MONITORING_NOTIFICATION_PROTOCOL",
    ):
        assert f'name  = "{name}"' in cicd


def test_codebuild_and_codepipeline_present():
    """CodeBuild プロジェクトと CodePipeline が定義されていること。"""
    cicd = read_tf("cicd.tf")
    assert "aws_codebuild_project" in cicd
    assert "aws_codepipeline" in cicd


def test_pipeline_stage_order_includes_approval_before_apply():
    """パイプラインのステージ順序に手動承認(Approval)が apply の前に存在すること。"""
    cicd = read_tf("cicd.tf")
    # stage 名の出現順を取得
    stage_names = re.findall(r'stage\s*\{\s*name\s*=\s*"([^"]+)"', cicd)
    assert "Approval" in stage_names, f"Approval ステージがない: {stage_names}"
    assert "Apply" in stage_names, f"Apply ステージがない: {stage_names}"
    assert stage_names.index("Approval") < stage_names.index("Apply"), (
        f"Approval が Apply より前にない: {stage_names}"
    )
    # fmt -> validate -> plan -> approval -> apply の骨格を確認
    for expected in ["Source", "Fmt", "Validate", "Plan", "Approval", "Apply"]:
        assert expected in stage_names, f"{expected} ステージがない: {stage_names}"


def _apply_action_block(cicd: str) -> str:
    """Apply ステージ内の TerraformApply アクションブロックを抽出して返す。"""
    m = re.search(
        r'action\s*\{\s*name\s*=\s*"TerraformApply"(.*?)\n    \}',
        cicd,
        flags=re.DOTALL,
    )
    assert m, "TerraformApply アクションが見つからない"
    return m.group(1)


def test_apply_stage_receives_source_and_plan_artifacts():
    """Apply ステージにコード一式（source_output）と plan_output の両方が渡ること。

    plan_output のみだと apply に必要な .tf / modules が無いため、source_output を
    input_artifacts に含め、PrimarySource を source_output に設定する必要がある。
    """
    cicd = read_tf("cicd.tf")
    block = _apply_action_block(cicd)

    m = re.search(r"input_artifacts\s*=\s*\[(.*?)\]", block, flags=re.DOTALL)
    assert m, "TerraformApply の input_artifacts が見つからない"
    inputs = re.findall(r'"([^"]+)"', m.group(1))
    assert "source_output" in inputs, (
        f"Apply の input_artifacts に source_output が含まれていない: {inputs}"
    )
    assert "plan_output" in inputs, (
        f"Apply の input_artifacts に plan_output が含まれていない: {inputs}"
    )


def test_apply_stage_sets_primary_source():
    """複数 input のとき PrimarySource が source_output に設定されていること。"""
    cicd = read_tf("cicd.tf")
    block = _apply_action_block(cicd)
    assert re.search(r'PrimarySource\s*=\s*"source_output"', block), (
        "Apply アクションで PrimarySource = \"source_output\" が設定されていない"
    )


def test_plan_output_artifact_name_matches():
    """Plan アクションの output_artifacts 名（plan_output）が Apply の入力と整合すること。"""
    cicd = read_tf("cicd.tf")
    m = re.search(
        r'action\s*\{\s*name\s*=\s*"TerraformPlan"(.*?)\n    \}',
        cicd,
        flags=re.DOTALL,
    )
    assert m, "TerraformPlan アクションが見つからない"
    outputs = re.findall(r'output_artifacts\s*=\s*\[(.*?)\]', m.group(1), flags=re.DOTALL)
    assert outputs, "TerraformPlan の output_artifacts が見つからない"
    plan_outputs = re.findall(r'"([^"]+)"', outputs[0])
    assert "plan_output" in plan_outputs, (
        f"Plan の output_artifacts に plan_output がない: {plan_outputs}"
    )
