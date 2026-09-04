"""Task 8 business API routers (dashboard, incidents, findings, summaries)."""

from __future__ import annotations

from app.routers.dashboard import router as dashboard_router
from app.routers.findings import router as findings_router
from app.routers.incidents import router as incidents_router
from app.routers.summaries import router as summaries_router

__all__ = [
    "dashboard_router",
    "findings_router",
    "incidents_router",
    "summaries_router",
    "all_routers",
]


def all_routers() -> list:
    """Return every business router in include order."""

    return [dashboard_router, incidents_router, findings_router, summaries_router]
