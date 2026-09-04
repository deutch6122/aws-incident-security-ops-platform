# データベース設計

design.md の「Data Models」を要約し、設計理由を記載する（Req 26.2, 26.3）。

## Aurora PostgreSQL（Product_A / 7 テーブル）

Aurora Serverless v2 (PostgreSQL)、Writer 1 台・Reader なし・最小 ACU=0.5 / 最大 ACU=2（Req 24.3）。isolated-db subnet に配置し、許可アプリからのみ接続可能とする（Req 15.4）。

| テーブル | 役割 | 主な制約 |
| --- | --- | --- |
| `incidents` | インシデント本体 | `external_id UNIQUE`（冪等取込） |
| `incident_comments` | 対応履歴 | `incident_id` FK / `ON DELETE CASCADE` |
| `findings` | セキュリティ Finding | `external_id UNIQUE`（冪等登録） |
| `finding_triage` | Finding 判定情報 | `finding_id` FK / `ON DELETE CASCADE` |
| `alarm_events` | アラームイベント取込 | `external_id UNIQUE`（冪等取込） |
| `monthly_summaries` | 月次集計 | `period UNIQUE`（同一年月は upsert） |
| `audit_logs` | 監査ログ | 状態変更を before/after で必ず記録 |

### DDL 概要

```sql
CREATE TABLE incidents (
    id BIGSERIAL PRIMARY KEY,
    external_id TEXT UNIQUE,
    title TEXT NOT NULL, severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open', description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE incident_comments (
    id BIGSERIAL PRIMARY KEY,
    incident_id BIGINT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    author TEXT NOT NULL, body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE findings (
    id BIGSERIAL PRIMARY KEY, external_id TEXT UNIQUE,
    title TEXT NOT NULL, severity TEXT NOT NULL, resource_type TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE finding_triage (
    id BIGSERIAL PRIMARY KEY,
    finding_id BIGINT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    triage_status TEXT NOT NULL, assessed_severity TEXT NOT NULL, note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE alarm_events (
    id BIGSERIAL PRIMARY KEY, external_id TEXT UNIQUE,
    source TEXT NOT NULL, event_type TEXT NOT NULL, payload JSONB,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE monthly_summaries (
    id BIGSERIAL PRIMARY KEY, period TEXT UNIQUE NOT NULL,
    incident_count INTEGER NOT NULL, finding_count INTEGER NOT NULL,
    alarm_count INTEGER NOT NULL, detail JSONB,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL, entity_id BIGINT NOT NULL, action TEXT NOT NULL,
    before_value JSONB, after_value JSONB, actor TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 設計理由

- **`external_id UNIQUE`**: EventBridge→SQS の再配送に対する冪等取込を保証する（Req 6.2, 6.3。Property 7・8）。
- **`monthly_summaries.period UNIQUE`**: 同一年月の再集計を upsert で 1 行に保つ（Req 7.2。Property 9）。
- **`audit_logs`**: インシデント / Finding の状態変更を必ず 1 件記録し、変更前後値を残す（Req 3.6, 8.3。Property 6）。
- **`ON DELETE CASCADE`**: 親（incident / finding）削除時に従属レコードを整合して削除する。

## DynamoDB（Product_B / 4 テーブル、全 PAY_PER_REQUEST）

| テーブル | PK / GSI | 補足 | 対応要件 |
| --- | --- | --- | --- |
| `public_status_items` | PK: `status_id` | 障害ステータス一覧 / 詳細 | Req 10.1, 10.2, 14.2 |
| `report_metadata` | PK: `report_id`、GSI `gsi_period`(period) | 月次レポートメタ | Req 11.1, 11.2, 14.1 |
| `page_view_logs` | PK: `view_id`、TTL 有効 | 閲覧記録（自動削除） | Req 10.3 |
| `maintenance_windows` | PK: `window_id`、TTL 有効 | メンテナンス情報 | Req 10 付随 |

### 設計理由

- **全テーブル PAY_PER_REQUEST**: トラフィックが小さく予測困難な dev 環境ではオンデマンド課金がコスト効率的（Req 24.5）。安定負荷時はプロビジョンド切替が代替案。
- **`report_metadata` GSI `gsi_period`**: 年月での一覧・絞り込みを効率化する（Req 11.1）。
- **`page_view_logs` / `maintenance_windows` の TTL**: 一定期間後に自動削除しストレージコストを抑制する。`public_status_items` 本体は閲覧記録時に変更しない（Property 10）。
