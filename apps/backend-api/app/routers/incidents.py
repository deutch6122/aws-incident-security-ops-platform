"""Incident CRUD + status-update APIs (Task 8.3, Req 3.1-3.6, 8.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.errors import NotFoundError
from app.repository_ports import RepositoryProvider
from app.routers.deps import get_repository_provider
from app.schemas import (
    IncidentCommentOut,
    IncidentCreate,
    IncidentDetailOut,
    IncidentOut,
    IncidentStatusUpdate,
)
from app.security import require_bearer_auth

router = APIRouter(
    prefix="/incidents",
    tags=["incidents"],
    dependencies=[Depends(require_bearer_auth)],
)


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    provider: RepositoryProvider = Depends(get_repository_provider),
) -> list[IncidentOut]:
    """Return all registered incidents (Req 3.1)."""

    with provider.bundle() as repos:
        incidents = repos.incidents.list()
        return [IncidentOut.model_validate(item) for item in incidents]


@router.get("/{incident_id}", response_model=IncidentDetailOut)
def get_incident(
    incident_id: int,
    provider: RepositoryProvider = Depends(get_repository_provider),
) -> IncidentDetailOut:
    """Return an incident with its comments; 404 when unknown (Req 3.2/3.3)."""

    with provider.bundle() as repos:
        incident = repos.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError("incident", incident_id)
        comments = repos.comments.list_for_incident(incident_id)
        detail = IncidentDetailOut.model_validate(incident)
        detail.comments = [IncidentCommentOut.model_validate(comment) for comment in comments]
        return detail


@router.post("", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    provider: RepositoryProvider = Depends(get_repository_provider),
) -> IncidentOut:
    """Create an incident; missing required fields yield 400 (Req 3.4/3.5).

    Field validation (and the 400 + ``missing_fields`` contract) is enforced by
    the shared RequestValidationError handler before this handler runs.
    """

    with provider.bundle() as repos:
        incident = repos.incidents.create(
            external_id=payload.external_id,
            title=payload.title,
            severity=payload.severity,
            status=payload.status,
            description=payload.description,
        )
        return IncidentOut.model_validate(incident)


@router.patch("/{incident_id}/status", response_model=IncidentOut)
def update_incident_status(
    incident_id: int,
    payload: IncidentStatusUpdate,
    provider: RepositoryProvider = Depends(get_repository_provider),
) -> IncidentOut:
    """Update status and append exactly one audit-log row (Req 3.6/8.3).

    The audit record captures JSON-serialisable before/after status values and
    never includes secrets or credentials.
    """

    with provider.bundle() as repos:
        incident = repos.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError("incident", incident_id)

        before_status = incident.status
        updated = repos.incidents.update(incident_id, status=payload.status)
        # update() returns None only when the row vanished between get/update.
        if updated is None:  # pragma: no cover - defensive
            raise NotFoundError("incident", incident_id)

        repos.audit_logs.create(
            entity_type="incident",
            entity_id=incident_id,
            action="status_change",
            before_value={"status": before_status},
            after_value={"status": updated.status},
            actor=payload.actor,
        )
        return IncidentOut.model_validate(updated)
