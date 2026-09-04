"""Dashboard summary API (Task 8.1, Req 2.1/2.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.repository_ports import RepositoryProvider
from app.routers.deps import get_repository_provider
from app.schemas import DashboardSummaryOut
from app.security import require_bearer_auth

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_bearer_auth)],
)


@router.get("/summary", response_model=DashboardSummaryOut)
def dashboard_summary(
    provider: RepositoryProvider = Depends(get_repository_provider),
) -> DashboardSummaryOut:
    """Aggregate incident/finding counts and status breakdown from Aurora.

    incident_count == total incidents, finding_count == total findings, and the
    combined status_breakdown values sum to incident_count + finding_count
    (Property 1, Req 2.1/2.2).
    """

    with provider.bundle() as repos:
        incident_status = repos.incidents.count_by_status()
        finding_status = repos.findings.count_by_status()

    incident_count = sum(incident_status.values())
    finding_count = sum(finding_status.values())

    breakdown: dict[str, int] = {}
    for status, count in incident_status.items():
        breakdown[status] = breakdown.get(status, 0) + count
    for status, count in finding_status.items():
        breakdown[status] = breakdown.get(status, 0) + count

    return DashboardSummaryOut(
        incident_count=incident_count,
        finding_count=finding_count,
        status_breakdown=dict(sorted(breakdown.items())),
    )
