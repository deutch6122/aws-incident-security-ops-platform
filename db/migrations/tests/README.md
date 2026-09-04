# Product_A DB migration tests

Feature: `aws-incident-security-ops-platform`.

Two independent test layers verify the migration DDL in `db/migrations/`:

| File | Task | Needs Docker? | Needs extra deps? | What it checks |
| --- | --- | --- | --- | --- |
| `test_schema_sql.py` | 6.2 | No | No (pytest only) | Static (text/regex) checks of the DDL: 7 tables, required UNIQUE / FK `ON DELETE CASCADE` constraints, audit columns, and that no credentials/roles appear. |
| `test_schema_apply_smoke.py` | 6.3 | Yes (local) | Yes (`requirements-smoke.txt`) | Applies the migration to a **local** throwaway PostgreSQL container and verifies the 7 tables and key constraints against the live catalog. Optionally verifies the down migration drops all tables. |

The smoke test **skips itself** (it never fails) when Docker or the smoke deps
are missing, so it is safe to run in either environment.

## Static tests (no Docker, no AWS, no extra deps)

The static suite runs anywhere with just `pytest`:

```sh
python3 -m pytest db/migrations/tests/test_schema_sql.py -q
```

## Schema-apply smoke test (Task 6.3, local PostgreSQL container)

The smoke test applies `0001_init_schema.sql` to a **local** PostgreSQL
container started by `testcontainers`, then queries `information_schema` /
`pg_constraint` to confirm:

- all 7 tables exist (`incidents`, `incident_comments`, `findings`,
  `finding_triage`, `alarm_events`, `monthly_summaries`, `audit_logs`) — Req 8.1;
- `external_id` on `incidents` / `findings` / `alarm_events` is UNIQUE + NOT NULL;
- `monthly_summaries.period` is UNIQUE + NOT NULL;
- `incident_comments` / `finding_triage` FKs are `ON DELETE CASCADE`;
- (optional) the down migration drops all 7 tables.

### Prerequisites

1. **Start a Docker daemon** (e.g. open Docker Desktop, or start the Docker
   engine). Without it the smoke test skips with `Docker daemon unavailable`.
2. **Install the smoke-test dependencies** (pinned):

   ```sh
   python3 -m pip install -r db/migrations/tests/requirements-smoke.txt
   ```

### Run

```sh
# With Docker running + deps installed: the smoke test executes.
# With Docker stopped OR deps missing: the smoke test skips (does not fail).
python3 -m pytest db/migrations/tests -q
```

## Notes on scope and safety

- **No AWS is used by any test.** The smoke test only drives a *local* Docker
  PostgreSQL container. There is no AWS CLI, no AWS credentials, no Secrets
  Manager, and no connection to Aurora or any real database.
- **No secrets are committed.** The smoke test uses testcontainers' local-only
  default credentials (`test` / `test`) that never leave the local Docker
  network. Real DB credentials for the platform are generated and stored by RDS
  in AWS Secrets Manager and consumed at runtime via the secret ARN (see
  `db/migrations/README.md`).
- The PostgreSQL image is pinned to `postgres:16-alpine` to stay consistent
  with the Aurora PostgreSQL 16-series engine.
