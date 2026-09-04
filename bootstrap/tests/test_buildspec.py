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
