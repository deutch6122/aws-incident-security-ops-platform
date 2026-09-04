"""Task 7-only protected routes used to verify shared HTTP contracts.

These routes deliberately do not implement Task 8 business CRUD APIs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.contract_store import ContractLookup
from app.errors import NotFoundError
from app.security import require_bearer_auth

router = APIRouter(
    prefix="/_contracts",
    tags=["Task 7 contract verification"],
    dependencies=[Depends(require_bearer_auth)],
)


class RequiredFieldsContract(BaseModel):
    title: str
    severity: str


def _lookup(request: Request) -> ContractLookup:
    return request.app.state.contract_lookup


@router.get("/protected")
def protected_placeholder() -> dict[str, str]:
    return {"status": "authenticated", "scope": "task-7-placeholder"}


@router.post("/required-fields")
def required_fields_placeholder(payload: RequiredFieldsContract) -> dict[str, list[str]]:
    return {"accepted_fields": [payload.title, payload.severity]}


@router.get("/incidents/{identifier}")
def incident_lookup_contract(identifier: int, request: Request) -> dict[str, int | str]:
    if not _lookup(request).has_incident(identifier):
        raise NotFoundError("incident", identifier)
    return {"resource": "incident", "identifier": identifier}


@router.get("/findings/{identifier}")
def finding_lookup_contract(identifier: int, request: Request) -> dict[str, int | str]:
    if not _lookup(request).has_finding(identifier):
        raise NotFoundError("finding", identifier)
    return {"resource": "finding", "identifier": identifier}


@router.get("/summaries/{period}")
def summary_lookup_contract(period: str, request: Request) -> dict[str, str]:
    if not _lookup(request).has_summary(period):
        raise NotFoundError("summary", period)
    return {"resource": "summary", "identifier": period}


@router.get("/unexpected-error", include_in_schema=False)
def unexpected_error_contract() -> None:
    raise RuntimeError("task-7 error contract probe")
