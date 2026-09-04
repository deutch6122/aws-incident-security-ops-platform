"""Finding reference APIs (Task 8.7, Req 4.1-4.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.errors import NotFoundError
from app.repository_ports import RepositoryProvider
from app.routers.deps import get_repository_provider
from app.schemas import FindingDetailOut, FindingOut, FindingTriageOut
from app.security import require_bearer_auth

router = APIRouter(
    prefix="/findings",
    tags=["findings"],
    dependencies=[Depends(require_bearer_auth)],
)


@router.get("", response_model=list[FindingOut])
def list_findings(
    provider: RepositoryProvider = Depends(get_repository_provider),
) -> list[FindingOut]:
    """Return all findings (Req 4.1)."""

    with provider.bundle() as repos:
        findings = repos.findings.list()
        return [FindingOut.model_validate(item) for item in findings]


@router.get("/{finding_id}", response_model=FindingDetailOut)
def get_finding(
    finding_id: int,
    provider: RepositoryProvider = Depends(get_repository_provider),
) -> FindingDetailOut:
    """Return a finding with its triage entries; 404 when unknown (Req 4.2/4.3)."""

    with provider.bundle() as repos:
        finding = repos.findings.get(finding_id)
        if finding is None:
            raise NotFoundError("finding", finding_id)
        triage = repos.triage.list_for_finding(finding_id)
        detail = FindingDetailOut.model_validate(finding)
        detail.triage = [FindingTriageOut.model_validate(entry) for entry in triage]
        return detail
