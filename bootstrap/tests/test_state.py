"""Bootstrap state 構成の静的検証（Req 20.3, 20.4, 21.1）。

terraform 実行・AWS 認証は不要。.tf ファイルの内容を文字列/正規表現で検査する。
"""

from __future__ import annotations

import re

from conftest import read_tf


def test_state_bucket_versioning_enabled():
    """remote state 用 S3 にバージョニング設定が存在し Enabled であること。"""
    state = read_tf("state.tf")
    assert "aws_s3_bucket_versioning" in state
    # tfstate バケット向けの versioning ブロックで status = "Enabled"
    assert re.search(r'status\s*=\s*"Enabled"', state), "state バケットの versioning が Enabled でない"


def test_state_bucket_encryption_present():
    """remote state 用 S3 に SSE（サーバーサイド暗号化）設定が存在すること。"""
    state = read_tf("state.tf")
    assert "aws_s3_bucket_server_side_encryption_configuration" in state
    assert "apply_server_side_encryption_by_default" in state
    assert re.search(r'sse_algorithm\s*=\s*"(AES256|aws:kms)"', state), "SSE アルゴリズム指定がない"


def test_state_bucket_public_access_block_all_true():
    """state 用 S3 の public access block 4 項目が全て true であること（Req 20.4）。"""
    state = read_tf("state.tf")
    # tfstate 用 public access block ブロックを抽出
    m = re.search(
        r'resource\s+"aws_s3_bucket_public_access_block"\s+"tfstate"\s*\{(.*?)\}',
        state,
        flags=re.DOTALL,
    )
    assert m, "state 用 aws_s3_bucket_public_access_block リソースが見つからない"
    block = m.group(1)
    for key in [
        "block_public_acls",
        "block_public_policy",
        "ignore_public_acls",
        "restrict_public_buckets",
    ]:
        assert re.search(rf"{key}\s*=\s*true", block), f"{key} が true でない"


def test_dynamodb_lock_disabled_by_default():
    """DynamoDB lock table がデフォルト無効（enable_dynamodb_lock default=false）であること。"""
    variables = read_tf("variables.tf")
    m = re.search(
        r'variable\s+"enable_dynamodb_lock"\s*\{(.*?)\n\}',
        variables,
        flags=re.DOTALL,
    )
    assert m, "variable enable_dynamodb_lock が見つからない"
    body = m.group(1)
    assert re.search(r"default\s*=\s*false", body), "enable_dynamodb_lock の default が false でない"


def test_dynamodb_lock_conditional_creation():
    """DynamoDB lock table が条件付き作成（count で enable_dynamodb_lock に依存）であること。"""
    state = read_tf("state.tf")
    m = re.search(
        r'resource\s+"aws_dynamodb_table"\s+"tfstate_lock"\s*\{(.*?)\n\}',
        state,
        flags=re.DOTALL,
    )
    assert m, "aws_dynamodb_table.tfstate_lock リソースが見つからない"
    body = m.group(1)
    assert re.search(r"count\s*=\s*var\.enable_dynamodb_lock", body), (
        "DynamoDB lock table が var.enable_dynamodb_lock による条件付き作成になっていない"
    )


def test_use_lockfile_documented_as_primary():
    """use_lockfile=true が第一候補としてコード/コメントに存在すること。"""
    versions = read_tf("versions.tf")
    # versions.tf のコメントに use_lockfile = true が第一候補として記載されている
    assert "use_lockfile" in versions, "versions.tf に use_lockfile の記載がない"
    assert "第一候補" in versions, "use_lockfile を第一候補とする旨の記載がない"


def test_backend_example_uses_use_lockfile():
    """infra/environments/dev の backend 例に use_lockfile = true が記載されていること。"""
    # bootstrap/tests から見たリポジトリルート配下の backend.tf.example
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    backend = repo_root / "infra" / "environments" / "dev" / "backend.tf.example"
    assert backend.exists(), f"backend 例が見つからない: {backend}"
    content = backend.read_text(encoding="utf-8")
    assert re.search(r"use_lockfile\s*=\s*true", content), "backend 例に use_lockfile = true がない"


def test_required_version_ge_1_10():
    """required_version が >= 1.10 を含むこと。"""
    versions = read_tf("versions.tf")
    assert re.search(r'required_version\s*=\s*">=\s*1\.10"', versions), (
        "required_version が >= 1.10 でない"
    )
