FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /service

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --requirement requirements.txt

COPY --chown=app:app workers ./workers

USER 10001:10001

# The worker to run is selected at deploy time via the container command, for
# example (see k8s/ manifests):
#   python -m workers.entrypoints.alarm_event_processor
#   python -m workers.entrypoints.security_finding_worker
#   python -m workers.entrypoints.monthly_summary_cronjob
CMD ["python", "-m", "workers.entrypoints.alarm_event_processor"]
