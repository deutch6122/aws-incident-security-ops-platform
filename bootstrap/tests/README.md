# bootstrap 構成テスト（静的検証）

Bootstrap の Terraform コード（`bootstrap/*.tf`）と backend 例を、**AWS 認証や terraform 実行なし**で静的に検証する軽量テスト群です。`.tf` ファイルを文字列/正規表現で解析します。

対応要件: Req 20.4, 21.1（および最小権限 Req 17.2 の担保）

## 検証内容

| テストファイル | 検証項目 |
| --- | --- |
| `test_state.py` | state 用 S3 の public access block 4 項目が true / バージョニング・暗号化の存在 / DynamoDB lock がデフォルト無効（`enable_dynamodb_lock` default=false）かつ条件付き作成 / `use_lockfile=true` が第一候補として存在 / backend 例に `use_lockfile = true` / `required_version >= 1.10` |
| `test_cicd.py` | artifact S3 の public access block 有効・バージョニング・暗号化 / CodeBuild・CodePipeline の存在 / ステージ順序（手動承認が apply の前） |
| `test_iam_least_privilege.py` | terraform-exec-role に `AdministratorAccess` を付与していない / `Action:"*"` + `Resource:"*"` の全許可ワイルドカードがない / `NotAction` 未使用 / terraform-exec-role の信頼ポリシーが codebuild-role を Principal(AWS) にしている（サービス直 assume でない）/ `iam:PassRole` に `iam:PassedToService` condition がある / codebuild-role が terraform-exec-role を assume できる |
| `test_buildspec.py` | 各 buildspec（`buildspec.yml` / `-validate` / `-plan` / `-apply`）が Terraform 実行前に `aws sts assume-role` + `TERRAFORM_EXEC_ROLE_ARN` で assume している / `buildspec-apply.yml` が `CODEBUILD_SRC_DIR_<name>` 経由で `tfplan.binary` を参照 / `buildspec-fmt.yml` は assume しない |

`test_cicd.py` には上記に加え、Apply ステージが `source_output` と `plan_output` の両方を input に取り `PrimarySource = source_output` を設定していること、Plan の `output_artifacts` 名が整合していることの検証を含みます。

> 注: コメント中の説明文（例: 「AdministratorAccess は付与しない」）を実コードと誤検出しないよう、IAM の全許可検査はコメントを除去したうえで行っています。

## 前提（テストランナー要件）

- Python 3.9+ 
- `pytest`（`requirements.txt` 参照）

## セットアップと実行

```bash
# 依存インストール（任意で venv 推奨）
pip install -r bootstrap/tests/requirements.txt

# 実行（bootstrap/tests ディレクトリで）
cd bootstrap/tests
pytest

# または、リポジトリルートから
pytest bootstrap/tests
```

## 実行しないこと

- `terraform init` / `validate` / `plan` / `apply` は実行しません（AWS 認証情報不要）。
- AWS へのリソース作成・変更・削除は行いません。
