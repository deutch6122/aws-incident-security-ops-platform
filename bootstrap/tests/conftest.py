"""pytest 共通フィクスチャ / ヘルパ（Bootstrap 構成テスト）。

AWS 認証・terraform 実行を一切必要としない静的検証のための共通処理。
bootstrap/ 配下の .tf ファイルを読み込み、文字列/正規表現で内容を検査する。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# bootstrap/ ディレクトリ（このファイルの 1 つ上）。
BOOTSTRAP_DIR = Path(__file__).resolve().parent.parent


def read_tf(filename: str) -> str:
    """bootstrap/ 配下の単一 .tf ファイル内容を返す。"""
    path = BOOTSTRAP_DIR / filename
    assert path.exists(), f"expected file not found: {path}"
    return path.read_text(encoding="utf-8")


def read_all_tf() -> str:
    """bootstrap/ 配下の全 .tf ファイルを連結した文字列を返す。"""
    chunks = []
    for path in sorted(BOOTSTRAP_DIR.glob("*.tf")):
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def strip_comments(hcl: str) -> str:
    """HCL から行コメント（# / //）とブロックコメント（/* */）を除去する。

    コメント内の記述（例: 説明文中の "AdministratorAccess"）を
    実コードと誤検出しないために使用する。
    """
    # ブロックコメント /* ... */ を除去
    hcl = re.sub(r"/\*.*?\*/", "", hcl, flags=re.DOTALL)
    # 行コメント（# または //）を除去。文字列内の # は簡易対応で許容。
    lines = []
    for line in hcl.splitlines():
        # 先頭からのコメント除去（簡易: 引用符を跨がない前提の静的検査）
        line = re.sub(r"#.*$", "", line)
        line = re.sub(r"//.*$", "", line)
        lines.append(line)
    return "\n".join(lines)


@pytest.fixture(scope="session")
def all_tf() -> str:
    return read_all_tf()


@pytest.fixture(scope="session")
def all_tf_no_comments() -> str:
    return strip_comments(read_all_tf())
