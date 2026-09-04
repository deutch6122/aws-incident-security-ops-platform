# module: dynamodb (Portal_DB)

Product_B（公開ポータル）のデータストア Portal_DB を定義する。4 テーブルすべてを
**PAY_PER_REQUEST**（オンデマンド課金、Requirement 24.5）で構成する。dev のトラフィック
は小さく予測困難なため、アイドル分のプロビジョンド課金を避けられるオンデマンドがコスト
効率的。

- 対応要件: Req 10.1, 11.1, 24.5（付随: Req 10.2, 10.3, 11.2, 14.1, 14.2）
- 実装: Task 13.1

## テーブル一覧

| テーブル | 論理名 | PK | 補足 | 対応要件 |
| --- | --- | --- | --- | --- |
| `public_status_items` | `<name_prefix>-public-status-items` | `status_id` (S) | 障害ステータス一覧/詳細 | Req 10.1, 10.2, 14.2 |
| `report_metadata` | `<name_prefix>-report-metadata` | `report_id` (S) | 月次レポートメタ。GSI `gsi_period`(period) | Req 11.1, 11.2, 14.1 |
| `page_view_logs` | `<name_prefix>-page-view-logs` | `view_id` (S) | 閲覧記録。**TTL 有効** | Req 10.3 |
| `maintenance_windows` | `<name_prefix>-maintenance-windows` | `window_id` (S) | メンテナンス情報。**TTL 有効** | Req 10（付随） |

命名は共通命名 helper に合わせ `ops-platform-dev-<resource>` 準拠（`name_prefix`
＋ハイフン区切りの論理名）。`common_tags` を全テーブルへ付与する。

## 設計判断

- **全テーブル PAY_PER_REQUEST**（Requirement 24.5）。
- `report_metadata` の **GSI `gsi_period`**（PK: `period`、projection ALL）: 年月
  （yyyymm）での一覧・絞り込みを効率化（Requirement 11.1）。
- `page_view_logs` / `maintenance_windows` は **TTL** でストレージコストを抑制。TTL
  属性名は `ttl_attribute_name`（既定 `expires_at`、Unix epoch 秒）で一元管理する。
- **DynamoDB Streams は全テーブルで無効**。Streams を有効にすると Product_B から
  Product_A 方向の push チャネルになり得るため、A→B 一方向方針（Requirement 14.3）に
  従い意図的に持たない。`streams_enabled` 出力は常に `false`。

## Product_A / Product_B 分離

本モジュールは Product_B 専用。Aurora/RDS/EKS/ECS/SQS への参照・依存・書込権限を
一切持たない。A→B の一方向連携（`report_metadata` 登録・`public_status_items` 反映・
`reports/*` 配置）は後続の Cronjob_Summary（Task 16.2）が実行主体となる。本モジュールは
テーブル定義のみを提供する。

## 変数

- `name_prefix`（必須、例 `ops-platform-dev`）
- `common_tags`（必須）
- `ttl_attribute_name`（既定 `expires_at`）

## 出力

- `public_status_items_table_name` / `_arn`
- `report_metadata_table_name` / `_arn` / `report_metadata_gsi_period_name`
- `page_view_logs_table_name` / `_arn`
- `maintenance_windows_table_name` / `_arn`
- `streams_enabled`（常に false）/ `ttl_attribute_name`

## dev root への配線について（後続依存）

`infra/environments/dev` への配線は、Portal_API（Task 15）や A→B 連携（Task 16.2）の
配線先確定後に行う。既存モジュールと同じ「実装したものだけ配線」方針に従い、Task 13
時点では dev ルートへは配線しない。

## テスト

`tests/test_dynamodb_snapshot.py` は Terraform/AWS を実行しない静的テスト。4 テーブル
存在・全 PAY_PER_REQUEST・`report_metadata` の GSI `gsi_period`・TTL 有効
（page_view_logs / maintenance_windows）・命名/タグ・Product_A 非参照・機微リテラル
非混入を検証する。
