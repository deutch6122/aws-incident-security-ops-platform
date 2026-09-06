# module: lambda (Portal_API)

Product_B（公開ポータル）の Portal_API Lambda を定義する。関数シェル、IAM 実行ロール
（`lambda-portal-role`）、CloudWatch Logs グループを構成する（Requirement 9.3, 14.3,
18.3）。Lambda コード本体は Task 15 で実装する。

- 対応要件: Req 9.3, 14.3, 18.3
- 実装: Task 14.3

## リソース

| リソース | 論理名 | 補足 |
| --- | --- | --- |
| `aws_lambda_function` | `<name_prefix>-portal-api` | Python, memory 256〜512MB, timeout 既定 10s |
| `aws_iam_role` | `<name_prefix>-lambda-portal-role` | Lambda 実行ロール |
| `aws_iam_role_policy`（logs） | `<name_prefix>-lambda-portal-logs` | CloudWatch Logs 出力 |
| `aws_iam_role_policy`（dynamodb） | `<name_prefix>-lambda-portal-dynamodb` | DynamoDB 読取＋page_view_logs 書込 |
| `aws_cloudwatch_log_group` | `/aws/lambda/<name_prefix>-portal-api` | 保持 14 or 30 日 |

命名は `ops-platform-dev-<resource>` 準拠。`common_tags` を関数・ロール・ログ
グループへ付与する。

## 設計判断

- **runtime** は変数（既定 `python3.12`、validation で python3.10〜3.13）。
- **memory_size** は 256〜512MB を validation で強制（既定 256）。**timeout** 既定 10
  秒（範囲 1〜30、変数）。
- **package** は versioning 有効な artifact bucket の immutable object のみを使用する。
  `lambda_package_s3_bucket` / `lambda_package_s3_key` /
  `lambda_package_s3_object_version` / `lambda_source_code_hash` を必須入力とし、ローカル
  filename 方式は使用しない。key は `lambda/<commit-sha>/portal-api.zip` 形式とする。
- **IAM 権限は Product_B 内限定**（最小権限、Requirement 17）:
  - DynamoDB **読取**（GetItem/BatchGetItem/Query/Scan）: `public_status_items` /
    `report_metadata` / `maintenance_windows`（各テーブル＋`/index/*`）。ARN は変数で
    受ける。
  - DynamoDB **書込**（PutItem）: 別ステートメントで `page_view_logs` **のみ**
    （Requirement 10.3, 14.3）。
  - **CloudWatch Logs**（CreateLogGroup/CreateLogStream/PutLogEvents）: 本関数の
    ロググループにスコープ（AWSLambdaBasicExecutionRole 相当を明示ポリシーで付与、
    Requirement 18.3）。
- **log_retention_days** は 14 or 30（logging モジュールの保持方針に一致）。

## Product_A / Product_B 分離

`lambda-portal-role` の権限は Product_B の Portal_DB（DynamoDB）に限定される。
Aurora/RDS/ECS/EKS/Product_A SQS/Backend API への参照・書込権限を一切付与しない。
`page_view_logs` のみが書込可能で、A→B 連携は一方向を維持する（Requirement 14.3）。
実 Secret 値/DB URL/Bearer token/AWS credentials は含めず、ARN/変数のみを扱う。

## 変数

- `name_prefix`（必須）/ `common_tags`（必須）
- `runtime`（既定 `python3.12`）/ `handler`（既定 `app.handler.lambda_handler`）
- `lambda_package_s3_bucket` / `lambda_package_s3_key` /
  `lambda_package_s3_object_version` / `lambda_source_code_hash`（すべて必須）
- `memory_size`（既定 256、範囲 256〜512）/ `timeout`（既定 10、範囲 1〜30）
- `log_retention_days`（既定 14、14 or 30）
- `public_status_items_table_arn` / `report_metadata_table_arn` /
  `maintenance_windows_table_arn`（読取）/ `page_view_logs_table_arn`（書込）

## 出力

- `lambda_function_name` / `lambda_function_arn` / `lambda_invoke_arn`
- `lambda_role_arn` / `log_group_name`

## packageとdev root配線

`apps/portal-lambda/build.sh` は固定順序・mtime・permission で依存ライブラリと
`app/` を `dist/portal-api.zip` にまとめる。実 S3 upload はパイプライン側で行う。

dev rootはversioned S3 packageのbucket/key/object version/source hash、DynamoDB table ARN、Portal bucketを配線済みです。Lambda invoke ARN/function名はAPI Gatewayへ渡します。ローカルfilename方式は使用しません。

## テスト

`tests/test_lambda_snapshot.py` は Terraform/AWS を実行しない静的テスト。memory 256〜
512 の validation・timeout=10・`lambda-portal-role` の DynamoDB 権限が Product_B
テーブル限定・`page_view_logs` のみ書込・CloudWatch Logs 権限・Product_A 非参照・
機微リテラル非混入を検証する。
