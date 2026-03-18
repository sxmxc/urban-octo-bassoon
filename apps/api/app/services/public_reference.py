from __future__ import annotations

import re
from typing import Any, Iterable

from app.services.mock_generation import preview_from_schema
from app.services.schema_contract import extract_request_body_schema, sanitize_public_schema
from app.time_utils import utc_now


PRODUCT_NAME = "Mockingbird"
PRODUCT_DESCRIPTION = (
    "A route-first API platform whose public routes, samples, and OpenAPI reference stay aligned with the active"
    " route catalog in the database."
)
BODY_METHODS = {"POST", "PUT", "PATCH"}


def _example_path(path: str) -> str:
    def replace_match(match: re.Match[str]) -> str:
        param_name = match.group(1)
        normalized = param_name.lower()
        if normalized in {"id", "uuid"} or normalized.endswith("id"):
            return "example-id"
        return f"{param_name}-sample"

    return re.sub(r"\{([^}]+)\}", replace_match, path)


def _endpoint_sort_key(endpoint: Any) -> tuple[str, str, str]:
    return (
        (endpoint.category or "uncategorized").lower(),
        endpoint.path.lower(),
        endpoint.method.lower(),
    )


def _sample_request(endpoint: Any) -> Any | None:
    body_schema = extract_request_body_schema(endpoint.request_schema)
    if str(endpoint.method or "").upper() not in BODY_METHODS or not body_schema:
        return None

    return preview_from_schema(
        body_schema,
        seed_key=endpoint.seed_key,
        identity=f"reference-request:{endpoint.id}:{endpoint.method}:{endpoint.path}",
    )


def serialize_public_endpoint(endpoint: Any) -> dict[str, Any]:
    return {
        "id": endpoint.id,
        "name": endpoint.name,
        "method": endpoint.method.upper(),
        "path": endpoint.path,
        "example_path": _example_path(endpoint.path),
        "category": endpoint.category,
        "tags": endpoint.tags or [],
        "summary": endpoint.summary,
        "description": endpoint.description,
        "success_status_code": endpoint.success_status_code,
        "request_schema": sanitize_public_schema(extract_request_body_schema(endpoint.request_schema)),
        "response_schema": sanitize_public_schema(endpoint.response_schema or {}),
        "sample_request": _sample_request(endpoint),
        "sample_response": preview_from_schema(
            endpoint.response_schema,
            seed_key=endpoint.seed_key,
            identity=f"reference:{endpoint.id}:{endpoint.method}:{endpoint.path}",
        ),
        "updated_at": endpoint.updated_at,
    }


def build_public_reference(endpoints: Iterable[Any]) -> dict[str, Any]:
    live_endpoints = [serialize_public_endpoint(endpoint) for endpoint in sorted(endpoints, key=_endpoint_sort_key) if endpoint.enabled]
    return {
        "product_name": PRODUCT_NAME,
        "description": PRODUCT_DESCRIPTION,
        "endpoint_count": len(live_endpoints),
        "refreshed_at": utc_now(),
        "endpoints": live_endpoints,
    }
