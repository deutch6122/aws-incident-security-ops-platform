"""Shared FastAPI dependencies for the business routers."""

from __future__ import annotations

from fastapi import Request

from app.repository_ports import RepositoryProvider


def get_repository_provider(request: Request) -> RepositoryProvider:
    """Resolve the repository provider from application state.

    Tests override ``app.state.repository_provider`` with an in-memory
    provider; production uses the SQLAlchemy-backed provider wired in
    ``create_app``.
    """

    return request.app.state.repository_provider
