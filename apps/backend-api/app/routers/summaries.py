"""Monthly summary API (Task 8.7, Req 5.1/5.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.errors import NotFoundError
from app.repository_ports import RepositoryProvider
from app.routers.deps import get_repository_provider
from app.schemas import MonthlySummaryOut, is_valid_period
from app.security import require_bearer_auth

router = APIRouter(
    prefix="/summaries",
    tags=["summaries"],
    dependencies=[Depends(require_bearer_auth)],
)


@router.get("/{yyyymm}", response_model=MonthlySummaryOut)
def get_monthly_summary(
    yyyymm: str,
    provider: RepositoryProvider = Depends(get_repository_provider),
) -> MonthlySummaryOut:
    """Return the monthly summary for ``yyyymm``; 404 when unknown (Req 5.1/5.2).

    A malformed period cannot exist in the store, so it is reported as a 404
    for the requested identifier (consistent with the shared not-found contract).
    """

    with provider.bundle() as repos:
        if not is_valid_period(yyyymm):
            raise NotFoundError("summary", yyyymm)
        summary = repos.summaries.get_by_period(yyyymm)
        if summary is None:
            raise NotFoundError("summary", yyyymm)
        return MonthlySummaryOut.model_validate(summary)
