"""Lazy SQLAlchemy engine/session construction with injectable secret access.

Construction performs no AWS or database I/O. The engine is built on first use
from the Secrets Manager credential referenced by ARN.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from workers.config import WorkerSettings
from workers.db.secrets import (
    Boto3SecretReader,
    SecretReader,
    build_database_url,
    load_database_secret,
)


class WorkerDatabase:
    """Owns lazy DB resources; construction performs no AWS or database I/O."""

    def __init__(self, settings: WorkerSettings, secret_reader: SecretReader | None = None) -> None:
        self._settings = settings
        self._secret_reader = secret_reader
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    def get_engine(self) -> Engine:
        if self._engine is None:
            secret_arn = self._settings.require_db_secret_arn()
            reader = self._secret_reader or Boto3SecretReader(self._settings.aws_region)
            secret = load_database_secret(reader, secret_arn)
            self._engine = create_engine(build_database_url(secret), pool_pre_ping=True)
        return self._engine

    def get_session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.get_engine(), expire_on_commit=False, class_=Session
            )
        return self._session_factory

    @contextmanager
    def session(self) -> Iterator[Session]:
        db_session = self.get_session_factory()()
        try:
            yield db_session
        finally:
            db_session.close()
