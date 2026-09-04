-- Feature: aws-incident-security-ops-platform
-- Migration: 0001_init_schema (rollback / down)
-- Target: Aurora PostgreSQL Serverless v2 (Product_A)
--
-- Reverses 0001_init_schema.sql. Drops in FK-safe order (children first, or CASCADE).
-- SCHEMA DDL ONLY. No credentials / roles / secrets.
--
-- WARNING: This DROPs tables and DESTROYS all contained data. Review carefully
-- before running against any environment. Intended for dev reset workflows only.

BEGIN;

DROP TRIGGER IF EXISTS trg_findings_set_updated_at  ON findings;
DROP TRIGGER IF EXISTS trg_incidents_set_updated_at ON incidents;
DROP FUNCTION IF EXISTS set_updated_at();

DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS monthly_summaries;
DROP TABLE IF EXISTS finding_triage;
DROP TABLE IF EXISTS findings;
DROP TABLE IF EXISTS incident_comments;
DROP TABLE IF EXISTS alarm_events;
DROP TABLE IF EXISTS incidents;

COMMIT;
