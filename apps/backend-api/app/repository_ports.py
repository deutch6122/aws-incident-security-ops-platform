"""Repository ports (Protocols) and a session-scoped provider abstraction.

The business routers depend only on these Protocols, never on SQLAlchemy
directly, so tests can inject in-memory fakes without a real database.

Two provider implementations exist:

* ``SqlAlchemyRepositoryProvider`` opens ``Database.session()`` at request time
  (no DB I/O at import time) and binds the concrete SQLAlchemy repositories.
* ``app.repository_fakes.InMemoryRepositoryProvider`` keeps everything in memory.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IncidentPort(Protocol):
    def create(
        self,
        *,
        external_id: str,
        title: str,
        severity: str,
        status: str = ...,
        description: str | None = ...,
    ) -> Any: ...
    def get(self, incident_id: int) -> Any | None: ...
    def list(self, *, offset: int = ..., limit: int = ...) -> list[Any]: ...
    def update(self, incident_id: int, **changes: str | None) -> Any | None: ...
    def count_by_status(self) -> dict[str, int]: ...


@runtime_checkable
class IncidentCommentPort(Protocol):
    def list_for_incident(self, incident_id: int) -> list[Any]: ...


@runtime_checkable
class FindingPort(Protocol):
    def get(self, finding_id: int) -> Any | None: ...
    def list(self, *, offset: int = ..., limit: int = ...) -> list[Any]: ...
    def count_by_status(self) -> dict[str, int]: ...


@runtime_checkable
class FindingTriagePort(Protocol):
    def list_for_finding(self, finding_id: int) -> list[Any]: ...


@runtime_checkable
class MonthlySummaryPort(Protocol):
    def get_by_period(self, period: str) -> Any | None: ...


@runtime_checkable
class AuditLogPort(Protocol):
    def create(
        self,
        *,
        entity_type: str,
        entity_id: int,
        action: str,
        before_value: Mapping[str, Any] | None,
        after_value: Mapping[str, Any] | None,
        actor: str | None = ...,
    ) -> Any: ...
    def list_for_entity(self, entity_type: str, entity_id: int) -> list[Any]: ...


@dataclass(slots=True)
class RepositoryBundle:
    """Repositories sharing a single unit of work / transaction scope."""

    incidents: IncidentPort
    comments: IncidentCommentPort
    findings: FindingPort
    triage: FindingTriagePort
    summaries: MonthlySummaryPort
    audit_logs: AuditLogPort


class RepositoryProvider(Protocol):
    """Yields a :class:`RepositoryBundle` bound to a fresh unit of work."""

    def bundle(self) -> "_BundleContext": ...


class _BundleContext(Protocol):
    def __enter__(self) -> RepositoryBundle: ...
    def __exit__(self, *exc: object) -> bool | None: ...


class SqlAlchemyRepositoryProvider:
    """Default provider that binds concrete repositories to a live DB session.

    A session is only opened when :meth:`bundle` is entered (request time), so
    importing this module performs no AWS or database I/O.
    """

    def __init__(self, database: Any) -> None:
        self._database = database

    @contextmanager
    def bundle(self) -> Iterator[RepositoryBundle]:
        # Imported lazily so importing the module never requires SQLAlchemy.
        from app.repositories import (
            AuditLogRepository,
            FindingRepository,
            FindingTriageRepository,
            IncidentCommentRepository,
            IncidentRepository,
            MonthlySummaryRepository,
        )

        with self._database.session() as session:
            yield RepositoryBundle(
                incidents=IncidentRepository(session),
                comments=IncidentCommentRepository(session),
                findings=FindingRepository(session),
                triage=FindingTriageRepository(session),
                summaries=MonthlySummaryRepository(session),
                audit_logs=AuditLogRepository(session),
            )
