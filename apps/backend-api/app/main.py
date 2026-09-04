"""FastAPI application factory wiring the Task 7 foundation and Task 8 business APIs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.config import Settings, get_settings
from app.contract_store import ContractLookup, InMemoryContractLookup
from app.contracts import router as contract_router
from app.db.secrets import SecretReader
from app.db.session import Database
from app.errors import install_error_handlers
from app.repository_ports import RepositoryProvider, SqlAlchemyRepositoryProvider
from app.routers import all_routers
from app.security import (
    _token_matches,
    choose_correlation_id,
    is_protected_path,
    parse_authorization,
    unauthorized_response,
)


def create_app(
    settings: Settings | None = None,
    contract_lookup: ContractLookup | None = None,
    secret_reader: SecretReader | None = None,
    repository_provider: RepositoryProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    application = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        description="Product_A Backend API: dashboard, incidents, findings, and monthly summaries.",
    )
    application.state.settings = resolved_settings
    application.state.contract_lookup = contract_lookup or InMemoryContractLookup()
    database = Database(resolved_settings, secret_reader=secret_reader)
    application.state.database = database
    # The SQLAlchemy provider opens sessions lazily (request time only); tests
    # inject an in-memory provider so no DB/AWS access is required.
    application.state.repository_provider = repository_provider or SqlAlchemyRepositoryProvider(
        database
    )

    @application.middleware("http")
    async def correlation_and_authentication(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        cid = choose_correlation_id(request.headers.get("X-Correlation-ID"))
        request.state.correlation_id = cid

        if is_protected_path(request.url.path):
            supplied = parse_authorization(request.headers.get("Authorization"))
            if supplied is None or not _token_matches(
                request.app.state.settings.internal_bearer_token, supplied
            ):
                return unauthorized_response(cid)

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(contract_router)
    for business_router in all_routers():
        application.include_router(business_router)
    install_error_handlers(application)
    return application


app = create_app()
