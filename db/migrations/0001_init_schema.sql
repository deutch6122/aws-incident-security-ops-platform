-- Feature: aws-incident-security-ops-platform
-- Migration: 0001_init_schema (forward / up)
-- Target: Aurora PostgreSQL Serverless v2 (Product_A)
-- Scope: Initial schema for the 7 Product_A tables.
--
-- IMPORTANT (security): This file contains SCHEMA DDL ONLY.
--   - No credentials, passwords, secret values, connection strings.
--   - No CREATE ROLE / CREATE USER / ALTER ... PASSWORD.
-- DB credentials are managed by RDS in AWS Secrets Manager and consumed by
-- applications via the secret ARN (aurora module output: app_database_secret_arn).
-- See db/migrations/README.md for the connection and execution policy.
--
-- Design source of truth: design.md (Data Models) and docs/db/db-design.md.
-- Requirements: 8.1 (7 tables), and design rationale for 6.2/6.3/7.2/3.6/8.3.

BEGIN;

-- =============================================================================
-- incidents: インシデント本体
--   external_id UNIQUE NOT NULL -> SQS at-least-once 配送に対する冪等取込 (Req 6.2/6.3, Property 7/8)
-- =============================================================================
CREATE TABLE IF NOT EXISTS incidents (
    id              BIGSERIAL PRIMARY KEY,
    external_id     TEXT UNIQUE NOT NULL,     -- 外部由来ID。冪等取込のため UNIQUE NOT NULL
    title           TEXT NOT NULL,
    severity        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- incident_comments: 対応履歴
--   ON DELETE CASCADE -> 親 incident 削除時に従属レコードを整合削除
-- =============================================================================
CREATE TABLE IF NOT EXISTS incident_comments (
    id              BIGSERIAL PRIMARY KEY,
    incident_id     BIGINT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    author          TEXT NOT NULL,
    body            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- findings: セキュリティ Finding
--   external_id UNIQUE NOT NULL -> 冪等登録 (Req 6.3, Property 8)
-- =============================================================================
CREATE TABLE IF NOT EXISTS findings (
    id              BIGSERIAL PRIMARY KEY,
    external_id     TEXT UNIQUE NOT NULL,     -- 冪等登録のため UNIQUE NOT NULL
    title           TEXT NOT NULL,
    severity        TEXT NOT NULL,
    resource_type   TEXT,
    status          TEXT NOT NULL DEFAULT 'new',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- finding_triage: Finding 判定情報
--   ON DELETE CASCADE -> 親 finding 削除時に従属レコードを整合削除
-- =============================================================================
CREATE TABLE IF NOT EXISTS finding_triage (
    id                  BIGSERIAL PRIMARY KEY,
    finding_id          BIGINT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    triage_status       TEXT NOT NULL,
    assessed_severity   TEXT NOT NULL,
    note                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- alarm_events: アラームイベント取込
--   external_id UNIQUE NOT NULL -> 冪等取込 (Req 6.2, Property 7)
-- =============================================================================
CREATE TABLE IF NOT EXISTS alarm_events (
    id              BIGSERIAL PRIMARY KEY,
    external_id     TEXT UNIQUE NOT NULL,     -- 冪等取込のため UNIQUE NOT NULL
    source          TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    payload         JSONB,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- monthly_summaries: 月次集計
--   period UNIQUE NOT NULL -> 同一年月は upsert で 1 行 (Req 7.2, Property 9)
-- =============================================================================
CREATE TABLE IF NOT EXISTS monthly_summaries (
    id              BIGSERIAL PRIMARY KEY,
    period          TEXT UNIQUE NOT NULL,     -- 'YYYYMM'。同一年月は upsert
    incident_count  INTEGER NOT NULL,
    finding_count   INTEGER NOT NULL,
    alarm_count     INTEGER NOT NULL,
    detail          JSONB,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- audit_logs: 監査ログ
--   before_value/after_value -> 状態変更の前後値を必ず記録 (Req 3.6/8.3, Property 6)
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    entity_type     TEXT NOT NULL,           -- 'incident' | 'finding'
    entity_id       BIGINT NOT NULL,
    action          TEXT NOT NULL,           -- 'status_change' 等
    before_value    JSONB,
    after_value     JSONB,
    actor           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- Indexes (design.md のインデックス方針に整合する範囲。過剰にしない)
-- =============================================================================
-- 一覧/絞り込みの主要検索軸: status / severity / created_at
CREATE INDEX IF NOT EXISTS idx_incidents_status      ON incidents (status);
CREATE INDEX IF NOT EXISTS idx_incidents_severity    ON incidents (severity);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at  ON incidents (created_at);

CREATE INDEX IF NOT EXISTS idx_findings_status       ON findings (status);
CREATE INDEX IF NOT EXISTS idx_findings_severity     ON findings (severity);
CREATE INDEX IF NOT EXISTS idx_findings_created_at   ON findings (created_at);

-- FK 側の結合検索を助けるインデックス
CREATE INDEX IF NOT EXISTS idx_incident_comments_incident_id ON incident_comments (incident_id);
CREATE INDEX IF NOT EXISTS idx_finding_triage_finding_id     ON finding_triage (finding_id);

-- 集計対象期間抽出を助ける (received_at)
CREATE INDEX IF NOT EXISTS idx_alarm_events_received_at ON alarm_events (received_at);

-- 監査ログのエンティティ単位検索 (entity_type, entity_id)
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs (entity_type, entity_id);

-- =============================================================================
-- updated_at 自動更新トリガ (任意。べき等: CREATE OR REPLACE / DROP IF EXISTS)
--   incidents / findings の updated_at を UPDATE 時に自動更新する。
-- =============================================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_incidents_set_updated_at ON incidents;
CREATE TRIGGER trg_incidents_set_updated_at
    BEFORE UPDATE ON incidents
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_findings_set_updated_at ON findings;
CREATE TRIGGER trg_findings_set_updated_at
    BEFORE UPDATE ON findings
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

COMMIT;
