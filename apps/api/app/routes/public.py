from __future__ import annotations

import asyncio
import json
import random
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app.db import session_scope
from app.services.api_health import build_api_health
from app.services.mock_generation import preview_from_schema
from app.services.public_routes import list_legacy_fallback_endpoints, list_unsupported_auth_public_endpoints
from app.services.route_runtime import execute_deployed_route_request

router = APIRouter()
PATH_PARAMETER_PATTERN = re.compile(r"\{([^/}]+)\}")


@dataclass(slots=True)
class MatchedEndpoint:
    id: int
    method: str
    path: str
    auth_mode: str
    response_schema: Any
    seed_key: str | None
    success_status_code: int
    latency_min_ms: int
    latency_max_ms: int
    error_rate: float


def _path_regex(pattern: str) -> tuple[re.Pattern[str], list[str]]:
    parameter_names: list[str] = []
    cursor = 0
    regex_parts = ["^"]

    for match in PATH_PARAMETER_PATTERN.finditer(pattern):
        start, end = match.span()
        regex_parts.append(re.escape(pattern[cursor:start]))
        regex_parts.append(r"([^/]+)")
        parameter_names.append(match.group(1))
        cursor = end

    regex_parts.append(re.escape(pattern[cursor:]))
    regex_parts.append("$")
    return re.compile("".join(regex_parts)), parameter_names


def _match_path_parameters(request_path: str, pattern: str) -> dict[str, str] | None:
    # Normalize
    request_path = request_path.rstrip("/") or "/"
    pattern = pattern.rstrip("/") or "/"

    regex, parameter_names = _path_regex(pattern)
    match = regex.match(request_path)
    if not match:
        return None

    return {
        name: unquote(value)
        for name, value in zip(parameter_names, match.groups())
    }


def _path_specificity(path: str) -> tuple[int, int, int]:
    segments = [segment for segment in path.split("/") if segment]
    static_segments = sum(1 for segment in segments if not (segment.startswith("{") and segment.endswith("}")))
    dynamic_segments = len(segments) - static_segments
    return static_segments, -dynamic_segments, len(segments)


def _matched_endpoint_from_model(endpoint) -> MatchedEndpoint:
    return MatchedEndpoint(
        id=int(endpoint.id or 0),
        method=endpoint.method,
        path=endpoint.path,
        auth_mode=str(endpoint.auth_mode.value if hasattr(endpoint.auth_mode, "value") else endpoint.auth_mode),
        response_schema=endpoint.response_schema,
        seed_key=endpoint.seed_key,
        success_status_code=endpoint.success_status_code,
        latency_min_ms=endpoint.latency_min_ms,
        latency_max_ms=endpoint.latency_max_ms,
        error_rate=endpoint.error_rate,
    )


def _find_best_matching_endpoint(
    request_path: str,
    method: str,
    endpoints,
) -> tuple[MatchedEndpoint | None, dict[str, str]]:
    best_match: MatchedEndpoint | None = None
    best_path_parameters: dict[str, str] = {}
    best_specificity: tuple[int, int, int] | None = None

    for endpoint in endpoints:
        if endpoint.method.upper() != method:
            continue

        path_parameters = _match_path_parameters(request_path, endpoint.path)
        if path_parameters is None:
            continue

        specificity = _path_specificity(endpoint.path)
        if best_specificity is not None and specificity <= best_specificity:
            continue

        best_match = _matched_endpoint_from_model(endpoint)
        best_path_parameters = path_parameters
        best_specificity = specificity

    return best_match, best_path_parameters


def _find_matching_endpoint(request_path: str, method: str) -> tuple[MatchedEndpoint | None, dict[str, str]]:
    with session_scope() as session:
        endpoints = list_legacy_fallback_endpoints(session, limit=1000)

    return _find_best_matching_endpoint(request_path, method, endpoints)


def _find_unsupported_auth_endpoint(request_path: str, method: str) -> MatchedEndpoint | None:
    with session_scope() as session:
        endpoints = list_unsupported_auth_public_endpoints(session, limit=1000)

    match, _ = _find_best_matching_endpoint(request_path, method, endpoints)
    return match


def _pick_response(
    endpoint: MatchedEndpoint,
    path_parameters: dict[str, str],
    query_parameters: dict[str, str],
    request_body: Any,
) -> Any:
    return preview_from_schema(
        endpoint.response_schema,
        path_parameters=path_parameters,
        query_parameters=query_parameters,
        request_body=request_body,
        seed_key=endpoint.seed_key,
        identity=f"endpoint:{endpoint.id}:{endpoint.method}:{endpoint.path}",
    )


async def _parse_json_request_body(request: Request) -> Any:
    body = await request.body()
    if not body:
        return None

    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


@router.get("/health", include_in_schema=False)
async def health() -> Response:
    payload = await run_in_threadpool(build_api_health)
    status_code = 503 if payload.status == "unhealthy" else 200
    return Response(
        status_code=status_code,
        content=payload.model_dump_json(),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def catchall(full_path: str, request: Request) -> Response:
    request_path = request.url.path
    method = request.method.upper()
    request_body = await _parse_json_request_body(request)
    query_parameters = {key: value for key, value in request.query_params.items()}

    deployed_result = await run_in_threadpool(
        _dispatch_deployed_route,
        request_path,
        method,
        query_parameters,
        request_body,
    )
    if deployed_result is not None:
        return Response(
            status_code=deployed_result.status_code,
            content=json.dumps(deployed_result.body, default=str),
            media_type="application/json",
        )

    match, matched_path_parameters = await run_in_threadpool(_find_matching_endpoint, request_path, method)

    if not match:
        unsupported_auth_match = await run_in_threadpool(_find_unsupported_auth_endpoint, request_path, method)
        if unsupported_auth_match is not None:
            return Response(
                status_code=501,
                content=json.dumps(
                    {
                        "error": (
                            "This route's auth mode is not supported by the public runtime yet. "
                            "Only auth_mode 'none' is currently supported."
                        ),
                        "auth_mode": unsupported_auth_match.auth_mode,
                    }
                ),
                media_type="application/json",
            )
        return Response(status_code=404, content=json.dumps({"error": "Not found"}), media_type="application/json")

    # Simulate latency
    if match.latency_max_ms > 0:
        wait_ms = random.randint(match.latency_min_ms, match.latency_max_ms)
        await asyncio.sleep(wait_ms / 1000.0)

    # Simulate errors
    if match.error_rate > 0 and random.random() < match.error_rate:
        return Response(
            status_code=500,
            content=json.dumps({"error": "Simulated error"}),
            media_type="application/json",
        )

    body = await run_in_threadpool(_pick_response, match, matched_path_parameters, query_parameters, request_body)
    return Response(
        status_code=match.success_status_code,
        content=json.dumps(body, default=str),
        media_type="application/json",
    )


def _dispatch_deployed_route(
    request_path: str,
    method: str,
    query_parameters: dict[str, str],
    request_body: Any,
):
    with session_scope() as session:
        return execute_deployed_route_request(
            session,
            request_path=request_path,
            method=method,
            query_parameters=query_parameters,
            request_body=request_body,
        )
