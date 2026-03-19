from __future__ import annotations

from time import perf_counter

from sqlalchemy import text

from app.config import Settings
from app.db import session_scope
from app.openapi import build_public_openapi_document
from app.schemas import ApiDependencyHealth, ApiHealthResponse
from app.services.public_reference import build_public_reference
from app.services.public_routes import list_public_endpoints
from app.services.route_runtime import inspect_deployment_registry
from app.services.route_status import build_route_publication_status, load_route_publication_facts
from app.time_utils import utc_now


def _dependency(
    *,
    name: str,
    label: str,
    status: str,
    detail: str,
    latency_ms: float | None = None,
    meta: dict | None = None,
) -> ApiDependencyHealth:
    return ApiDependencyHealth(
        name=name,
        label=label,
        status=status,
        detail=detail,
        latency_ms=round(latency_ms, 2) if latency_ms is not None else None,
        meta=meta or {},
    )


def _overall_status(dependencies: list[ApiDependencyHealth]) -> str:
    statuses = {dependency.status for dependency in dependencies}
    if "unhealthy" in statuses:
        return "unhealthy"
    if "degraded" in statuses:
        return "degraded"
    return "healthy"


def build_api_health() -> ApiHealthResponse:
    checked_at = utc_now()
    settings = Settings()
    dependencies: list[ApiDependencyHealth] = [
        _dependency(
            name="api",
            label="API process",
            status="healthy",
            detail="The API process is serving requests.",
        )
    ]
    summary: dict[str, object] = {
        "public_route_count": 0,
        "published_live_routes": 0,
        "legacy_mock_routes": 0,
    }

    try:
        with session_scope() as session:
            db_started_at = perf_counter()
            session.execute(text("SELECT 1")).scalar_one()
            dependencies.append(
                _dependency(
                    name="database",
                    label="Database",
                    status="healthy",
                    detail="Postgres responded to a lightweight health query.",
                    latency_ms=(perf_counter() - db_started_at) * 1000,
                    meta={"dialect": session.bind.dialect.name if session.bind is not None else "unknown"},
                )
            )

            registry_started_at = perf_counter()
            registry_snapshot = inspect_deployment_registry(session)
            dependencies.append(
                _dependency(
                    name="deployment_registry",
                    label="Deployment registry",
                    status="healthy",
                    detail="The compiled live-route registry loaded successfully.",
                    latency_ms=(perf_counter() - registry_started_at) * 1000,
                    meta=registry_snapshot,
                )
            )

            endpoints = list_public_endpoints(session, limit=1000)
            publication_facts = load_route_publication_facts(
                session,
                [int(endpoint.id) for endpoint in endpoints if endpoint.id is not None],
            )
            publication_statuses = [
                build_route_publication_status(endpoint, publication_facts.get(int(endpoint.id or 0)))
                for endpoint in endpoints
            ]

            summary = {
                "public_route_count": len(endpoints),
                "published_live_routes": sum(1 for status in publication_statuses if status.code == "published_live"),
                "legacy_mock_routes": sum(1 for status in publication_statuses if status.code == "legacy_mock"),
            }

            reference_started_at = perf_counter()
            reference_payload = build_public_reference(endpoints, session=session)
            dependencies.append(
                _dependency(
                    name="public_reference",
                    label="Reference feed",
                    status="healthy",
                    detail="The public reference payload generated successfully.",
                    latency_ms=(perf_counter() - reference_started_at) * 1000,
                    meta={"endpoint_count": int(reference_payload.get("endpoint_count", 0))},
                )
            )

            openapi_started_at = perf_counter()
            openapi_document = build_public_openapi_document(
                title="Artificer API",
                version=settings.app_version,
                endpoints=endpoints,
            )
            dependencies.append(
                _dependency(
                    name="openapi",
                    label="OpenAPI generation",
                    status="healthy",
                    detail="The published OpenAPI document generated successfully.",
                    latency_ms=(perf_counter() - openapi_started_at) * 1000,
                    meta={"path_count": len(openapi_document.get("paths", {}))},
                )
            )
    except Exception as error:
        detail = str(error) or error.__class__.__name__
        if not any(dependency.name == "database" for dependency in dependencies):
            dependencies.append(
                _dependency(
                    name="database",
                    label="Database",
                    status="unhealthy",
                    detail=f"Database health check failed: {detail}",
                )
            )

        fallback_dependencies = [
            _dependency(
                name="deployment_registry",
                label="Deployment registry",
                status="unhealthy",
                detail=f"Registry inspection failed because backend dependencies are unavailable: {detail}",
            ),
            _dependency(
                name="public_reference",
                label="Reference feed",
                status="unhealthy",
                detail=f"Reference generation failed because backend dependencies are unavailable: {detail}",
            ),
            _dependency(
                name="openapi",
                label="OpenAPI generation",
                status="unhealthy",
                detail=f"OpenAPI generation failed because backend dependencies are unavailable: {detail}",
            ),
        ]
        existing_dependency_names = {dependency.name for dependency in dependencies}
        dependencies.extend(
            dependency
            for dependency in fallback_dependencies
            if dependency.name not in existing_dependency_names
        )

    return ApiHealthResponse(
        status=_overall_status(dependencies),
        checked_at=checked_at,
        dependencies=dependencies,
        summary=summary,
    )
