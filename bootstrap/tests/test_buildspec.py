"""buildspec の静的検証（AssumeRole 分離設計 / plan バイナリ参照）。

各 buildspec が Terraform 実行前に terraform-exec-role を assume している
（sts assume-role + TERRAFORM_EXEC_ROLE_ARN）ことを検証する。
terraform 実行・AWS 認証は不要。ファイル内容を文字列で検査する。
"""

from __future__ import annotations

from pathlib import Path

BUILDSPEC_DIR = Path(__file__).resolve().parent.parent / "buildspec"


def _read(name: str) -> str:
    path = BUILDSPEC_DIR / name
    assert path.exists(), f"buildspec が見つからない: {path}"
    return path.read_text(encoding="utf-8")


def test_dispatcher_assumes_terraform_exec_role():
    """ディスパッチャ buildspec.yml が assume-role と TERRAFORM_EXEC_ROLE_ARN を使うこと。"""
    content = _read("buildspec.yml")
    assert "sts assume-role" in content or "sts assume-role" in content.replace("\\\n", " "), (
        "buildspec.yml に aws sts assume-role がない"
    )
    assert "TERRAFORM_EXEC_ROLE_ARN" in content, (
        "buildspec.yml で TERRAFORM_EXEC_ROLE_ARN を使用していない"
    )


def test_apply_buildspec_assumes_terraform_exec_role():
    """buildspec-apply.yml が assume-role と TERRAFORM_EXEC_ROLE_ARN を使うこと。"""
    content = _read("buildspec-apply.yml")
    assert "sts assume-role" in content, "buildspec-apply.yml に aws sts assume-role がない"
    assert "TERRAFORM_EXEC_ROLE_ARN" in content, (
        "buildspec-apply.yml で TERRAFORM_EXEC_ROLE_ARN を使用していない"
    )


def test_apply_buildspec_references_plan_secondary_source():
    """buildspec-apply.yml が plan_output のセカンダリソース経由で tfplan.binary を参照すること。"""
    content = _read("buildspec-apply.yml")
    assert "CODEBUILD_SRC_DIR_" in content, (
        "buildspec-apply.yml がセカンダリソースディレクトリ（CODEBUILD_SRC_DIR_<name>）を参照していない"
    )
    assert "tfplan.binary" in content, "buildspec-apply.yml が tfplan.binary を参照していない"


def test_validate_and_plan_buildspecs_assume_role():
    """validate/plan の個別 buildspec も assume-role してから terraform を実行すること。"""
    for name in ["buildspec-validate.yml", "buildspec-plan.yml"]:
        content = _read(name)
        assert "sts assume-role" in content, f"{name} に aws sts assume-role がない"
        assert "TERRAFORM_EXEC_ROLE_ARN" in content, (
            f"{name} で TERRAFORM_EXEC_ROLE_ARN を使用していない"
        )


def test_fmt_buildspec_does_not_assume_role():
    """fmt はローカル処理のため assume-role していないこと（統一しない旨）。"""
    content = _read("buildspec-fmt.yml")
    assert "sts assume-role" not in content, (
        "buildspec-fmt.yml は AWS 認証不要のため assume-role すべきでない"
    )


def test_all_buildspecs_install_the_pinned_checksum_verified_terraform():
    for name in ["buildspec.yml", "buildspec-fmt.yml", "buildspec-validate.yml", "buildspec-plan.yml", "buildspec-apply.yml"]:
        content = _read(name)
        assert ".terraform-version" in content
        assert ".terraform-version.checksums" in content
        assert "linux_amd64" in content
        assert "sha256sum -c -" in content
        assert "terraform version -json" in content


def test_plan_buildspec_uploads_versioned_lambda_package_and_records_contract():
    for name in ["buildspec.yml", "buildspec-plan.yml"]:
        content = _read(name)
        assert "apps/portal-lambda/build.sh" in content
        assert "lambda/${COMMIT_SHA}/portal-api.zip" in content
        assert "s3api put-object" in content
        assert "--server-side-encryption aws:kms" in content
        assert "TF_VAR_lambda_package_s3_object_version" in content
        assert "TF_VAR_lambda_source_code_hash" in content
        assert "lambda-package-metadata.json" in content
        assert ".terraform.lock.hcl" in content
        assert "aws ssm get-parameter" in content


def test_plan_buildspec_reads_two_phase_deployment_inputs_from_ssm():
    """Plan consumes the immutable image tag and the reviewed 0/1 ECS gate."""
    for name in ["buildspec.yml", "buildspec-plan.yml"]:
        content = _read(name)
        assert "SSM_APPLICATION_IMAGE_TAG" in content
        assert "SSM_ECS_DESIRED_COUNT" in content
        assert "SSM_ALB_INGRESS_CIDRS" in content
        assert "TF_VAR_network_allowed_alb_ingress_cidrs" in content
        assert "TF_VAR_application_image_tag" in content
        assert "TF_VAR_ecs_desired_count" in content
        assert "TF_VAR_cognito_callback_urls" in content
        assert "TF_VAR_cognito_logout_urls" in content
        assert "TF_VAR_cognito_keep_localhost_urls" in content
        assert "TF_VAR_monitoring_enable_sns_subscription" in content
        assert "TF_VAR_monitoring_notification_endpoint" in content
        assert "TF_VAR_monitoring_notification_protocol" in content
        assert '== "0" || "$TF_VAR_ecs_desired_count" == "1"' in content


def test_apply_requires_approved_plan_lock_and_s3_object_identity():
    for name in ["buildspec.yml", "buildspec-apply.yml"]:
        content = _read(name)
        assert "test -n \"$PLAN_SRC_DIR\"" in content
        assert "cmp -s \"$PLAN_LOCK\"" in content
        assert "-lockfile=readonly" in content
        assert "s3api head-object" in content
        assert "--version-id \"$PACKAGE_VERSION\"" in content
        assert "HEAD_OBJECT_JSON=" in content
        assert "jq -r '.Metadata[\"source-code-hash\"] // empty'" in content
        assert "Lambda package metadata source-code-hash was not found" in content
        assert "Lambda package source-code-hash mismatch" in content
        assert "Lambda package integrity check: OK" in content
        assert "Metadata.source-code-hash" not in content
        assert 'PLAN_FILE="$TF_WORKDIR/tfplan.binary"' not in content
