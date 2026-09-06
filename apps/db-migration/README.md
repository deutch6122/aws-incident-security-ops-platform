# Database migration runner

Dedicated one-off runner for Product_A Aurora PostgreSQL migrations. Build it only with the repository root as the Docker context:

```bash
docker build --platform linux/amd64 -f apps/db-migration/Dockerfile -t <migration-image> .
```

The runner reads `BACKEND_DB_SECRET_ARN` and fetches the secret at runtime through the migration task role. If the RDS-managed secret omits `dbname`, `BACKEND_DB_NAME` is required. It applies sorted forward files from `/opt/migrations` and never applies `*.down.sql`.

The image is separate from Backend_API. Do not copy migration SQL into the Backend runtime image. Actual image build, push, ECS run-task, and Aurora access are Category C operations and are not performed by the local test suite.
