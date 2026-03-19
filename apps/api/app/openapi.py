from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI

from app.config import Settings
from app.db import session_scope
from app.services.public_routes import list_public_endpoints
from app.services.schema_contract import (
    extract_request_body_schema,
    extract_request_parameter_schemas,
    request_path_parameter_names,
    sanitize_public_schema,
)


BODY_METHODS = {"post", "put", "patch"}
OPENAPI_DESCRIPTION = (
    "Artificer API publishes a live OpenAPI document generated from active deployments plus legacy routes that have"
    " not entered the live runtime yet."
)


def _schema_or_empty(schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return sanitize_public_schema(schema or {"type": "object", "properties": {}})


def _parameter_from_schema(
    *,
    name: str,
    location: str,
    required: bool,
    schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sanitized_schema = sanitize_public_schema(schema or {"type": "string"})
    parameter = {
        "in": location,
        "name": name,
        "required": True if location == "path" else required,
        "schema": sanitized_schema,
    }
    description = sanitized_schema.pop("description", None)
    if description:
        parameter["description"] = description
    return parameter


def _request_parameters(endpoint: Any) -> List[Dict[str, Any]]:
    parameters: List[Dict[str, Any]] = []
    request_parameters = extract_request_parameter_schemas(endpoint.request_schema or {})

    path_properties = request_parameters["path"].get("properties", {}) or {}
    for name in request_path_parameter_names(endpoint.path or ""):
        parameters.append(
            _parameter_from_schema(
                name=name,
                location="path",
                required=True,
                schema=path_properties.get(name),
            )
        )

    query_schema = request_parameters["query"]
    query_properties = query_schema.get("properties", {}) or {}
    query_required = set(query_schema.get("required", []) or [])
    query_order = list(query_schema.get("x-builder", {}).get("order", []) or [])

    for name in query_properties:
        if name not in query_order:
            query_order.append(name)

    for name in query_order:
        if name not in query_properties:
            continue
        parameters.append(
            _parameter_from_schema(
                name=name,
                location="query",
                required=name in query_required,
                schema=query_properties.get(name),
            )
        )

    return parameters


def _build_operation(endpoint: Any) -> Dict[str, Any]:
    operation = {
        "summary": endpoint.summary or endpoint.name,
        "description": endpoint.description or "",
        "tags": endpoint.tags or [],
        "responses": {
            str(endpoint.success_status_code): {
                "description": "Successful response",
                "content": {
                    "application/json": {"schema": _schema_or_empty(endpoint.response_schema)}
                },
            }
        },
    }

    parameters = _request_parameters(endpoint)
    if parameters:
        operation["parameters"] = parameters

    request_body_schema = extract_request_body_schema(endpoint.request_schema)
    if endpoint.method.lower() in BODY_METHODS and request_body_schema:
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": _schema_or_empty(request_body_schema),
                }
            },
        }

    return operation


def build_public_openapi_document(
    *,
    title: str,
    version: str,
    endpoints: List[Any],
) -> Dict[str, Any]:
    openapi: Dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {
            "title": title or "Artificer API",
            "version": version or "0.0.0",
            "description": OPENAPI_DESCRIPTION,
        },
        "paths": {},
    }

    for endpoint in endpoints:
        path = endpoint.path if endpoint.path.startswith("/") else f"/{endpoint.path}"
        method = endpoint.method.lower()
        operations = openapi["paths"].setdefault(path, {})
        operations[method] = _build_operation(endpoint)

    return openapi


def get_openapi(
    app: FastAPI,
    settings: Settings,
    original_openapi: Callable[[], Dict[str, Any]],
) -> Dict[str, Any]:
    if not settings.enable_openapi:
        return original_openapi()

    with session_scope() as session:
        endpoints = list_public_endpoints(session, limit=1000)

    return build_public_openapi_document(
        title=app.title or "Artificer API",
        version=app.version or "0.0.0",
        endpoints=endpoints,
    )
