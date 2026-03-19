"""Reserve /api/health for the system health endpoint.

Revision ID: 20260319_0009
Revises: 20260319_0008
Create Date: 2026-03-19 18:05:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from alembic import op
import sqlalchemy as sa


revision = "20260319_0009"
down_revision = "20260319_0008"
branch_labels = None
depends_on = None


SYSTEM_HEALTH_PATH = "/api/health"
LEGACY_SEEDED_HEALTH_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "x-mock": {"mode": "fixed", "value": "ok", "options": {}},
        }
    },
    "required": ["status"],
    "x-builder": {"order": ["status"]},
    "x-mock": {"mode": "generate"},
}


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _is_legacy_seeded_health_route(route: Mapping[str, Any]) -> bool:
    return (
        route.get("name") == "Health"
        and route.get("slug") == "health"
        and route.get("method") == "GET"
        and route.get("path") == SYSTEM_HEALTH_PATH
        and route.get("category") == "system"
        and _json_value(route.get("tags")) == ["system"]
        and route.get("summary") == "Health check"
        and route.get("description") is None
        and bool(route.get("enabled")) is True
        and route.get("auth_mode") == "none"
        and _json_value(route.get("request_schema")) == {}
        and _json_value(route.get("response_schema")) == LEGACY_SEEDED_HEALTH_RESPONSE_SCHEMA
        and int(route.get("success_status_code") or 0) == 200
        and float(route.get("error_rate") or 0.0) == 0.0
        and int(route.get("latency_min_ms") or 0) == 0
        and int(route.get("latency_max_ms") or 0) == 0
        and route.get("seed_key") is None
    )


def _delete_route_runtime_history(bind: sa.Connection, route_id: int) -> None:
    bind.execute(
        sa.text(
            """
            DELETE FROM executionstep
            WHERE run_id IN (
                SELECT id
                FROM executionrun
                WHERE route_id = :route_id
            )
            """
        ),
        {"route_id": route_id},
    )
    bind.execute(
        sa.text("DELETE FROM executionrun WHERE route_id = :route_id"),
        {"route_id": route_id},
    )
    bind.execute(
        sa.text("DELETE FROM routedeployment WHERE route_id = :route_id"),
        {"route_id": route_id},
    )
    bind.execute(
        sa.text("DELETE FROM routeimplementation WHERE route_id = :route_id"),
        {"route_id": route_id},
    )
    bind.execute(
        sa.text("DELETE FROM endpointdefinition WHERE id = :route_id"),
        {"route_id": route_id},
    )


def upgrade() -> None:
    bind = op.get_bind()
    routes = bind.execute(
        sa.text(
            """
            SELECT
                id,
                name,
                slug,
                method,
                path,
                category,
                tags,
                summary,
                description,
                enabled,
                auth_mode,
                request_schema,
                response_schema,
                success_status_code,
                error_rate,
                latency_min_ms,
                latency_max_ms,
                seed_key
            FROM endpointdefinition
            WHERE path = :path
            """
        ),
        {"path": SYSTEM_HEALTH_PATH},
    ).mappings().all()

    if not routes:
        return

    conflicting_route_ids = [int(route["id"]) for route in routes if not _is_legacy_seeded_health_route(route)]
    if conflicting_route_ids:
        route_list = ", ".join(str(route_id) for route_id in conflicting_route_ids)
        raise RuntimeError(
            "Migration 20260319_0009 found non-seeded routes using /api/health "
            f"(endpointdefinition.id in {route_list}). Rename or remove those routes manually before upgrading."
        )

    for route in routes:
        _delete_route_runtime_history(bind, int(route["id"]))


def downgrade() -> None:
    bind = op.get_bind()
    existing_id = bind.execute(
        sa.text("SELECT id FROM endpointdefinition WHERE path = :path"),
        {"path": SYSTEM_HEALTH_PATH},
    ).scalar_one_or_none()
    if existing_id is not None:
        return

    bind.execute(
        sa.text(
            """
            INSERT INTO endpointdefinition (
                name,
                slug,
                method,
                path,
                category,
                tags,
                summary,
                description,
                enabled,
                auth_mode,
                request_schema,
                response_schema,
                success_status_code,
                error_rate,
                latency_min_ms,
                latency_max_ms,
                seed_key,
                created_at,
                updated_at
            )
            VALUES (
                :name,
                :slug,
                :method,
                :path,
                :category,
                :tags,
                :summary,
                :description,
                :enabled,
                :auth_mode,
                :request_schema,
                :response_schema,
                :success_status_code,
                :error_rate,
                :latency_min_ms,
                :latency_max_ms,
                :seed_key,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "name": "Health",
            "slug": "health",
            "method": "GET",
            "path": SYSTEM_HEALTH_PATH,
            "category": "system",
            "tags": json.dumps(["system"]),
            "summary": "Health check",
            "description": None,
            "enabled": True,
            "auth_mode": "none",
            "request_schema": json.dumps({}),
            "response_schema": json.dumps(
                {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "x-mock": {"mode": "fixed", "value": "ok", "options": {}},
                        }
                    },
                    "required": ["status"],
                    "x-builder": {"order": ["status"]},
                    "x-mock": {"mode": "generate"},
                }
            ),
            "success_status_code": 200,
            "error_rate": 0.0,
            "latency_min_ms": 0,
            "latency_max_ms": 0,
            "seed_key": None,
        },
    )
