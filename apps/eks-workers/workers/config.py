"""Environment-backed worker settings; secret values are never defaulted.

Only non-secret configuration lives here: the AWS region, the Secrets Manager
ARN reference (not the secret value), the worker SQS queue URL, and log/loop
tuning. The DB password and full connection URL never appear as settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class WorkerConfigurationError(RuntimeError):
    """Configuration error that never embeds a secret value or connection URL."""


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    """Non-secret deployment settings shared by all workers."""

    aws_region: str = "ap-northeast-1"
    db_secret_arn: str | None = None
    sqs_queue_url: str | None = None
    max_messages: int = 10
    wait_time_seconds: int = 20
    visibility_timeout_seconds: int = 60

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> WorkerSettings:
        """Build settings from the environment without importing AWS clients."""

        env = environ if environ is not None else dict(os.environ)

        def _int(name: str, default: int) -> int:
            raw = _clean(env.get(name))
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError as exc:
                raise WorkerConfigurationError(f"{name} must be an integer") from exc

        return cls(
            aws_region=_clean(env.get("WORKER_AWS_REGION")) or "ap-northeast-1",
            db_secret_arn=_clean(env.get("WORKER_DB_SECRET_ARN")),
            sqs_queue_url=_clean(env.get("WORKER_SQS_QUEUE_URL")),
            max_messages=_int("WORKER_MAX_MESSAGES", 10),
            wait_time_seconds=_int("WORKER_WAIT_TIME_SECONDS", 20),
            visibility_timeout_seconds=_int("WORKER_VISIBILITY_TIMEOUT_SECONDS", 60),
        )

    def require_db_secret_arn(self) -> str:
        if self.db_secret_arn is None:
            raise WorkerConfigurationError("WORKER_DB_SECRET_ARN is not configured")
        return self.db_secret_arn

    def require_sqs_queue_url(self) -> str:
        if self.sqs_queue_url is None:
            raise WorkerConfigurationError("WORKER_SQS_QUEUE_URL is not configured")
        return self.sqs_queue_url
