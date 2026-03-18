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

from app.crud import list_endpoints
from app.db import session_scope
from app.services.mock_generation import preview_from_schema
from app.services.route_runtime import execute_deployed_route_request

router = APIRouter()
PATH_PARAMETER_PATTERN = re.compile(r"\{([^/}]+)\}")


@dataclass(slots=True)
class MatchedEndpoint:
    id: int
    method: str
    path: str
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


def _find_matching_endpoint(request_path: str, method: str) -> tuple[MatchedEndpoint | None, dict[str, str]]:
    with session_scope() as session:
        endpoints = list_endpoints(session, limit=1000)

    for endpoint in endpoints:
        if not endpoint.enabled:
            continue
        if endpoint.method.upper() != method:
            continue

        path_parameters = _match_path_parameters(request_path, endpoint.path)
        if path_parameters is None:
            continue

        return (
            MatchedEndpoint(
                id=int(endpoint.id or 0),
                method=endpoint.method,
                path=endpoint.path,
                response_schema=endpoint.response_schema,
                seed_key=endpoint.seed_key,
                success_status_code=endpoint.success_status_code,
                latency_min_ms=endpoint.latency_min_ms,
                latency_max_ms=endpoint.latency_max_ms,
                error_rate=endpoint.error_rate,
            ),
            path_parameters,
        )

    return None, {}


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
