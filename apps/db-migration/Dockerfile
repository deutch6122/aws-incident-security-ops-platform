FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    MIGRATIONS_DIR=/opt/migrations

WORKDIR /opt/migration

RUN groupadd --system --gid 10001 migration \
    && useradd --system --uid 10001 --gid migration --home-dir /nonexistent --shell /usr/sbin/nologin migration

COPY apps/db-migration/requirements.txt ./requirements.txt
RUN python -m pip install --requirement requirements.txt

COPY --chown=migration:migration apps/db-migration/run_migration.py ./run_migration.py
COPY --chown=migration:migration db/migrations /opt/migrations

USER 10001:10001
ENTRYPOINT ["python", "/opt/migration/run_migration.py"]
