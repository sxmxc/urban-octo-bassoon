import json
import os
import sys
import tempfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, inspect, select, text

# Ensure the backend package is importable when running tests.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEST_DB_PATH = Path(tempfile.gettempdir()) / "mockingbird-test.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB_PATH}")
INITIAL_ADMIN_PASSWORD = "admin123456789"
ACTIVE_ADMIN_PASSWORD = "admin123456789-rotated"
os.environ.setdefault("ADMIN_BOOTSTRAP_USERNAME", "admin")
os.environ.setdefault("ADMIN_BOOTSTRAP_PASSWORD", INITIAL_ADMIN_PASSWORD)

import pytest
import httpx
from fastapi.testclient import TestClient
from sqlmodel import Session

import app.db as db_module
import app.services.admin_auth as admin_auth_module
import app.services.route_runtime as route_runtime_module
import scripts.create_test_admin as create_test_admin_script
from app.db import create_db_and_tables, engine
from app.main import app
from app.models import EndpointDefinition, ExecutionRun, ExecutionStep, RouteDeployment, RouteImplementation
from scripts.create_test_admin import ensure_test_admin_user
from scripts.seed import DEVICE_MODELS


def _reset_db() -> None:
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    create_db_and_tables()
    admin_auth_module.reset_login_rate_limits()


def _bearer_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login_headers(
    client: TestClient,
    *,
    username: str = "admin",
    candidate_passwords: tuple[str, ...] | None = None,
) -> dict[str, str]:
    candidates = candidate_passwords or (ACTIVE_ADMIN_PASSWORD, INITIAL_ADMIN_PASSWORD)

    for password in candidates:
        login_response = client.post(
            "/api/admin/auth/login",
            json={
                "username": username,
                "password": password,
                "remember_me": False,
            },
        )
        if login_response.status_code != 200:
            continue

        token = login_response.json()["token"]
        headers = _bearer_headers(token)

        if login_response.json()["user"]["must_change_password"]:
            change_response = client.post(
                "/api/admin/account/change-password",
                json={
                    "current_password": password,
                    "new_password": ACTIVE_ADMIN_PASSWORD,
                },
                headers=headers,
            )
            assert change_response.status_code == 200

        return headers

    raise AssertionError(f"Unable to authenticate admin user '{username}' with the provided test passwords.")


def _endpoint_payload(*, name: str, path: str, method: str = "GET") -> dict:
    return {
        "name": name,
        "method": method,
        "path": path,
        "category": "testing",
        "tags": ["testing"],
        "summary": f"{name} summary",
        "description": f"{name} description",
        "enabled": True,
        "auth_mode": "none",
        "request_schema": {},
        "response_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "x-mock": {
                        "mode": "fixed",
                        "value": "ok",
                        "options": {},
                    },
                }
            },
            "required": ["status"],
            "x-builder": {"order": ["status"]},
            "x-mock": {"mode": "generate"},
        },
        "success_status_code": 200,
        "error_rate": 0.0,
        "latency_min_ms": 0,
        "latency_max_ms": 0,
        "seed_key": None,
    }


def _live_route_flow_definition(*, status_code: int = 200, body: dict | None = None) -> dict:
    return {
        "schema_version": 1,
        "nodes": [
            {"id": "trigger", "type": "api_trigger", "config": {}},
            {
                "id": "transform",
                "type": "transform",
                "config": {
                    "output": body or {"status": "live"},
                },
            },
            {
                "id": "response",
                "type": "set_response",
                "config": {
                    "status_code": status_code,
                    "body": {"$ref": "state.transform"},
                },
            },
        ],
        "edges": [
            {"source": "trigger", "target": "transform"},
            {"source": "transform", "target": "response"},
        ],
    }


@pytest.fixture
def seeded_db():
    _reset_db()
    from scripts.seed import seed

    seed()
    yield


@pytest.fixture
def empty_db():
    _reset_db()
    yield


def test_create_db_and_tables_uses_alembic_schema():
    _reset_db()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "routeimplementation" in tables
    assert "routedeployment" in tables
    assert "connection" in tables
    assert "executionrun" in tables
    assert "executionstep" in tables
    columns = {column["name"] for column in inspector.get_columns("endpointdefinition")}
    assert "response_schema" in columns
    assert "seed_key" in columns
    assert "example_template" not in columns
    assert "response_mode" not in columns
    admin_columns = {column["name"] for column in inspector.get_columns("adminuser")}
    assert "role" in admin_columns
    assert "full_name" in admin_columns
    assert "email" in admin_columns
    assert "avatar_url" in admin_columns
    assert "failed_login_attempts" in admin_columns
    assert "last_failed_login_at" in admin_columns
    assert "locked_until" in admin_columns


def test_route_runtime_scaffolding_endpoints_publish_and_record_executions(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Live route", path="/api/live-route"),
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    implementation_response = client.get(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        headers=headers,
    )
    assert implementation_response.status_code == 200
    assert implementation_response.json()["version"] == 1
    assert any(node["type"] == "api_trigger" for node in implementation_response.json()["flow_definition"]["nodes"])

    update_implementation_response = client.put(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        json={
            "flow_definition": {
                "schema_version": 1,
                "nodes": [
                    {"id": "trigger", "type": "api_trigger", "config": {}},
                    {
                        "id": "transform",
                        "type": "transform",
                        "config": {
                            "output": {
                                "message": "live-route-response",
                                "method": {"$ref": "route.method"},
                            }
                        },
                    },
                    {
                        "id": "response",
                        "type": "set_response",
                        "config": {
                            "status_code": 201,
                            "body": {"$ref": "state.transform"},
                        },
                    },
                    {
                        "id": "error",
                        "type": "error_response",
                        "config": {
                            "status_code": 400,
                            "body": {"error": "validation failed"},
                        },
                    },
                ],
                "edges": [
                    {"source": "trigger", "target": "transform"},
                    {"source": "transform", "target": "response"},
                ],
            }
        },
        headers=headers,
    )
    assert update_implementation_response.status_code == 200
    assert update_implementation_response.json()["is_draft"] is True

    publish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201
    deployment = publish_response.json()
    assert deployment["environment"] == "production"
    assert deployment["is_active"] is True

    deployments_response = client.get(
        f"/api/admin/endpoints/{endpoint['id']}/deployments",
        headers=headers,
    )
    assert deployments_response.status_code == 200
    assert deployments_response.json()[0]["implementation_id"] == deployment["implementation_id"]

    live_response = client.get("/api/live-route")
    assert live_response.status_code == 201
    assert live_response.json() == {
        "message": "live-route-response",
        "method": "GET",
    }

    executions_response = client.get(
        f"/api/admin/executions?endpoint_id={endpoint['id']}&limit=5",
        headers=headers,
    )
    assert executions_response.status_code == 200
    executions = executions_response.json()
    assert len(executions) == 1
    assert executions[0]["status"] == "success"
    assert executions[0]["response_status_code"] == 201

    execution_detail_response = client.get(
        f"/api/admin/executions/{executions[0]['id']}",
        headers=headers,
    )
    assert execution_detail_response.status_code == 200
    execution_detail = execution_detail_response.json()
    assert [step["node_type"] for step in execution_detail["steps"]] == [
        "api_trigger",
        "transform",
        "set_response",
    ]


def test_live_flow_mapping_can_compose_inline_strings_from_request_and_state(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json={
            **_endpoint_payload(name="Mapped live route", path="/api/mapped-live/{orderId}", method="POST"),
            "request_schema": {
                "type": "object",
                "properties": {
                    "customer": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "format": "email"},
                        },
                        "required": ["email"],
                        "x-builder": {"order": ["email"]},
                    }
                },
                "required": ["customer"],
                "x-builder": {"order": ["customer"]},
                "x-request": {
                    "path": {
                        "type": "object",
                        "properties": {
                            "orderId": {"type": "string"},
                        },
                        "required": ["orderId"],
                        "x-builder": {"order": ["orderId"]},
                    },
                    "query": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string"},
                        },
                        "x-builder": {"order": ["status"]},
                    },
                },
            },
            "success_status_code": 201,
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    update_implementation_response = client.put(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        json={
            "flow_definition": {
                "schema_version": 1,
                "nodes": [
                    {"id": "trigger", "type": "api_trigger", "config": {}},
                    {
                        "id": "transform",
                        "type": "transform",
                        "config": {
                            "output": {
                                "receipt": (
                                    "order={{request.path.orderId}} "
                                    "status={{request.query.status}} "
                                    "email={{request.body.customer.email}}"
                                ),
                                "route_line": "{{route.method}} {{route.path}}",
                                "customer_email": {"$ref": "request.body.customer.email"},
                            }
                        },
                    },
                    {
                        "id": "response",
                        "type": "set_response",
                        "config": {
                            "status_code": "{{route.success_status_code}}",
                            "body": {
                                "summary": "{{state.transform.receipt}}",
                                "route": "{{state.transform.route_line}}",
                                "email": {"$ref": "state.transform.customer_email"},
                            },
                        },
                    },
                ],
                "edges": [
                    {"source": "trigger", "target": "transform"},
                    {"source": "transform", "target": "response"},
                ],
            }
        },
        headers=headers,
    )
    assert update_implementation_response.status_code == 200

    publish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201

    runtime_response = client.post(
        "/api/mapped-live/order-123?status=queued",
        json={"customer": {"email": "alex@example.com"}},
    )
    assert runtime_response.status_code == 201
    assert runtime_response.json() == {
        "summary": "order=order-123 status=queued email=alex@example.com",
        "route": "POST /api/mapped-live/{orderId}",
        "email": "alex@example.com",
    }

    executions_response = client.get(
        f"/api/admin/executions?endpoint_id={endpoint['id']}&limit=5",
        headers=headers,
    )
    assert executions_response.status_code == 200
    execution = executions_response.json()[0]

    execution_detail_response = client.get(
        f"/api/admin/executions/{execution['id']}",
        headers=headers,
    )
    assert execution_detail_response.status_code == 200
    steps = execution_detail_response.json()["steps"]
    assert steps[-2]["node_type"] == "transform"
    assert steps[-2]["output_data"] == {
        "receipt": "order=order-123 status=queued email=alex@example.com",
        "route_line": "POST /api/mapped-live/{orderId}",
        "customer_email": "alex@example.com",
    }
    assert steps[-1]["node_type"] == "set_response"
    assert steps[-1]["output_data"] == {
        "status_code": 201,
        "body": {
            "summary": "order=order-123 status=queued email=alex@example.com",
            "route": "POST /api/mapped-live/{orderId}",
            "email": "alex@example.com",
        },
    }


def test_admin_can_unpublish_active_route_without_deleting_definition(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Unpublish route", path="/api/unpublish-route"),
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    publish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201
    assert publish_response.json()["is_active"] is True

    live_response = client.get("/api/unpublish-route")
    assert live_response.status_code == 200

    unpublish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/unpublish",
        json={"environment": "production"},
        headers=headers,
    )
    assert unpublish_response.status_code == 200
    unpublished = unpublish_response.json()
    assert unpublished["environment"] == "production"
    assert unpublished["is_active"] is False

    deployments_response = client.get(
        f"/api/admin/endpoints/{endpoint['id']}/deployments",
        headers=headers,
    )
    assert deployments_response.status_code == 200
    assert deployments_response.json()[0]["is_active"] is False

    implementation_response = client.get(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        headers=headers,
    )
    assert implementation_response.status_code == 200
    assert implementation_response.json()["route_id"] == endpoint["id"]

    endpoints_response = client.get("/api/admin/endpoints", headers=headers)
    assert endpoints_response.status_code == 200
    assert any(candidate["id"] == endpoint["id"] for candidate in endpoints_response.json())

    assert client.get("/api/unpublish-route").status_code == 404
    assert "/api/unpublish-route" not in client.get("/openapi.json").json()["paths"]
    reference_paths = {item["path"] for item in client.get("/api/reference.json").json()["endpoints"]}
    assert "/api/unpublish-route" not in reference_paths

    repeat_unpublish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/unpublish",
        json={"environment": "production"},
        headers=headers,
    )
    assert repeat_unpublish_response.status_code == 409


def test_admin_can_delete_runtime_managed_route_and_clear_history(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Delete live route", path="/api/delete-live-route"),
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    update_response = client.put(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        json={"flow_definition": _live_route_flow_definition(body={"status": "deleted"})},
        headers=headers,
    )
    assert update_response.status_code == 200

    publish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201

    live_response = client.get("/api/delete-live-route")
    assert live_response.status_code == 200
    assert live_response.json() == {"status": "deleted"}

    executions_response = client.get(
        f"/api/admin/executions?endpoint_id={endpoint['id']}&limit=5",
        headers=headers,
    )
    assert executions_response.status_code == 200
    execution_id = executions_response.json()[0]["id"]

    delete_response = client.delete(f"/api/admin/endpoints/{endpoint['id']}", headers=headers)
    assert delete_response.status_code == 204

    assert client.get("/api/delete-live-route").status_code == 404
    assert client.get(f"/api/admin/endpoints/{endpoint['id']}", headers=headers).status_code == 404
    assert client.get("/openapi.json").json()["paths"].get("/api/delete-live-route") is None
    reference_paths = {item["path"] for item in client.get("/api/reference.json").json()["endpoints"]}
    assert "/api/delete-live-route" not in reference_paths

    with Session(engine) as session:
        assert session.get(EndpointDefinition, endpoint["id"]) is None
        assert session.execute(
            select(RouteImplementation).where(RouteImplementation.route_id == endpoint["id"])
        ).scalars().all() == []
        assert session.execute(
            select(RouteDeployment).where(RouteDeployment.route_id == endpoint["id"])
        ).scalars().all() == []
        assert session.execute(
            select(ExecutionRun).where(ExecutionRun.route_id == endpoint["id"])
        ).scalars().all() == []
        assert session.execute(
            select(ExecutionStep).where(ExecutionStep.run_id == execution_id)
        ).scalars().all() == []


def test_runtime_connections_can_be_created_and_listed(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/connections",
        json={
            "name": "Primary upstream",
            "connector_type": "http",
            "description": "Primary live API target",
            "config": {"base_url": "https://api.example.com"},
            "is_active": True,
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    assert create_response.json()["name"] == "Primary upstream"

    duplicate_response = client.post(
        "/api/admin/connections",
        json={
            "name": "Primary upstream",
            "connector_type": "http",
            "description": None,
            "config": {},
            "is_active": True,
        },
        headers=headers,
    )
    assert duplicate_response.status_code == 409

    list_response = client.get("/api/admin/connections", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json() == [
        {
            "id": 1,
            "name": "Primary upstream",
            "connector_type": "http",
            "description": "Primary live API target",
            "config": {"base_url": "https://api.example.com"},
            "is_active": True,
            "created_at": list_response.json()[0]["created_at"],
            "updated_at": list_response.json()[0]["updated_at"],
        }
    ]


def test_route_runtime_rejects_invalid_connector_node_config(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Invalid connector route", path="/api/invalid-connector"),
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    update_response = client.put(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        json={
            "flow_definition": {
                "schema_version": 1,
                "nodes": [
                    {"id": "trigger", "type": "api_trigger", "config": {}},
                    {
                        "id": "http",
                        "type": "http_request",
                        "config": {
                            "method": "GET",
                            "path": "/status",
                        },
                    },
                    {
                        "id": "response",
                        "type": "set_response",
                        "config": {
                            "status_code": 200,
                            "body": {"ok": True},
                        },
                    },
                ],
                "edges": [
                    {"source": "trigger", "target": "http"},
                    {"source": "http", "target": "response"},
                ],
            }
        },
        headers=headers,
    )
    assert update_response.status_code == 400
    assert "connection_id" in update_response.json()["detail"]


def test_route_runtime_rejects_invalid_if_branch_metadata(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Invalid if route", path="/api/invalid-if"),
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    update_response = client.put(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        json={
            "flow_definition": {
                "schema_version": 1,
                "nodes": [
                    {"id": "trigger", "type": "api_trigger", "config": {}},
                    {
                        "id": "if-1",
                        "type": "if_condition",
                        "config": {
                            "left": {"$ref": "request.query.mode"},
                            "operator": "equals",
                            "right": "live",
                        },
                    },
                    {"id": "live", "type": "transform", "config": {"output": {"branch": "live"}}},
                    {"id": "fallback", "type": "transform", "config": {"output": {"branch": "fallback"}}},
                    {"id": "response", "type": "set_response", "config": {"status_code": 200, "body": {"ok": True}}},
                ],
                "edges": [
                    {"source": "trigger", "target": "if-1"},
                    {"source": "if-1", "target": "live", "branch": "true"},
                    {"source": "if-1", "target": "fallback", "branch": "true"},
                    {"source": "live", "target": "response"},
                    {"source": "fallback", "target": "response"},
                ],
            }
        },
        headers=headers,
    )
    assert update_response.status_code == 400
    assert "true" in update_response.json()["detail"].lower()
    assert "false" in update_response.json()["detail"].lower()


def test_runtime_if_condition_branches_and_records_steps(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="If route", path="/api/if-route"),
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    update_implementation_response = client.put(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        json={
            "flow_definition": {
                "schema_version": 1,
                "nodes": [
                    {"id": "trigger", "type": "api_trigger", "config": {}},
                    {
                        "id": "if-1",
                        "type": "if_condition",
                        "config": {
                            "left": {"$ref": "request.query.mode"},
                            "operator": "equals",
                            "right": "live",
                        },
                    },
                    {"id": "live", "type": "transform", "config": {"output": {"branch_name": "live"}}},
                    {"id": "fallback", "type": "transform", "config": {"output": {"branch_name": "fallback"}}},
                    {
                        "id": "response",
                        "type": "set_response",
                        "config": {
                            "status_code": 200,
                            "body": {
                                "matched": {"$ref": "state.if-1.matched"},
                                "branch": {"$ref": "state.if-1.branch"},
                            },
                        },
                    },
                ],
                "edges": [
                    {"source": "trigger", "target": "if-1"},
                    {"source": "if-1", "target": "live", "branch": "true"},
                    {"source": "if-1", "target": "fallback", "branch": "false"},
                    {"source": "live", "target": "response"},
                    {"source": "fallback", "target": "response"},
                ],
            }
        },
        headers=headers,
    )
    assert update_implementation_response.status_code == 200

    publish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201

    live_response = client.get("/api/if-route?mode=live")
    assert live_response.status_code == 200
    assert live_response.json() == {
        "matched": True,
        "branch": "true",
    }

    fallback_response = client.get("/api/if-route")
    assert fallback_response.status_code == 200
    assert fallback_response.json() == {
        "matched": False,
        "branch": "false",
    }

    executions_response = client.get(
        f"/api/admin/executions?endpoint_id={endpoint['id']}&limit=5",
        headers=headers,
    )
    assert executions_response.status_code == 200
    execution_id = executions_response.json()[0]["id"]

    execution_detail_response = client.get(
        f"/api/admin/executions/{execution_id}",
        headers=headers,
    )
    assert execution_detail_response.status_code == 200
    execution_detail = execution_detail_response.json()
    assert [step["node_type"] for step in execution_detail["steps"]] == [
        "api_trigger",
        "if_condition",
        "transform",
        "set_response",
    ]
    assert execution_detail["steps"][1]["output_data"]["branch"] == "false"
    assert execution_detail["steps"][2]["node_id"] == "fallback"


def test_runtime_can_branch_directly_to_error_response(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Error branch route", path="/api/error-branch-route"),
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    update_implementation_response = client.put(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        json={
            "flow_definition": {
                "schema_version": 1,
                "nodes": [
                    {"id": "trigger", "type": "api_trigger", "config": {}},
                    {
                        "id": "if-1",
                        "type": "if_condition",
                        "config": {
                            "left": {"$ref": "request.query.mode"},
                            "operator": "equals",
                            "right": "live",
                        },
                    },
                    {
                        "id": "response",
                        "type": "set_response",
                        "config": {
                            "status_code": 200,
                            "body": {"ok": True},
                        },
                    },
                    {
                        "id": "error",
                        "type": "error_response",
                        "config": {
                            "status_code": 409,
                            "body": {
                                "error": "branch blocked",
                                "branch": {"$ref": "state.if-1.branch"},
                            },
                        },
                    },
                ],
                "edges": [
                    {"source": "trigger", "target": "if-1"},
                    {"source": "if-1", "target": "response", "branch": "true"},
                    {"source": "if-1", "target": "error", "branch": "false"},
                ],
            }
        },
        headers=headers,
    )
    assert update_implementation_response.status_code == 200

    publish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201

    live_response = client.get("/api/error-branch-route?mode=live")
    assert live_response.status_code == 200
    assert live_response.json() == {"ok": True}

    error_response = client.get("/api/error-branch-route")
    assert error_response.status_code == 409
    assert error_response.json() == {
        "error": "branch blocked",
        "branch": "false",
    }

    executions_response = client.get(
        f"/api/admin/executions?endpoint_id={endpoint['id']}&limit=5",
        headers=headers,
    )
    assert executions_response.status_code == 200
    execution_id = executions_response.json()[0]["id"]

    execution_detail_response = client.get(
        f"/api/admin/executions/{execution_id}",
        headers=headers,
    )
    assert execution_detail_response.status_code == 200
    execution_detail = execution_detail_response.json()
    assert [step["node_type"] for step in execution_detail["steps"]] == [
        "api_trigger",
        "if_condition",
        "error_response",
    ]
    assert execution_detail["steps"][2]["output_data"]["status_code"] == 409


def test_runtime_switch_routes_to_case_and_default(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Switch route", path="/api/switch-route"),
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    update_implementation_response = client.put(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        json={
            "flow_definition": {
                "schema_version": 1,
                "nodes": [
                    {"id": "trigger", "type": "api_trigger", "config": {}},
                    {"id": "switch-1", "type": "switch", "config": {"value": {"$ref": "request.query.status"}}},
                    {"id": "queued", "type": "transform", "config": {"output": {"branch_name": "queued"}}},
                    {"id": "default-path", "type": "transform", "config": {"output": {"branch_name": "default"}}},
                    {
                        "id": "response",
                        "type": "set_response",
                        "config": {
                            "status_code": 200,
                            "body": {
                                "branch": {"$ref": "state.switch-1.branch"},
                                "case_value": {"$ref": "state.switch-1.case_value"},
                            },
                        },
                    },
                ],
                "edges": [
                    {"source": "trigger", "target": "switch-1"},
                    {"source": "switch-1", "target": "queued", "branch": "case", "case_value": "queued"},
                    {"source": "switch-1", "target": "default-path", "branch": "default"},
                    {"source": "queued", "target": "response"},
                    {"source": "default-path", "target": "response"},
                ],
            }
        },
        headers=headers,
    )
    assert update_implementation_response.status_code == 200

    publish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201

    case_response = client.get("/api/switch-route?status=queued")
    assert case_response.status_code == 200
    assert case_response.json() == {
        "branch": "case",
        "case_value": "queued",
    }

    default_response = client.get("/api/switch-route?status=missing")
    assert default_response.status_code == 200
    assert default_response.json() == {
        "branch": "default",
        "case_value": None,
    }

    executions_response = client.get(
        f"/api/admin/executions?endpoint_id={endpoint['id']}&limit=5",
        headers=headers,
    )
    assert executions_response.status_code == 200
    execution_id = executions_response.json()[0]["id"]

    execution_detail_response = client.get(
        f"/api/admin/executions/{execution_id}",
        headers=headers,
    )
    assert execution_detail_response.status_code == 200
    execution_detail = execution_detail_response.json()
    assert [step["node_type"] for step in execution_detail["steps"]] == [
        "api_trigger",
        "switch",
        "transform",
        "set_response",
    ]
    assert execution_detail["steps"][1]["output_data"]["branch"] == "default"
    assert execution_detail["steps"][2]["node_id"] == "default-path"


def test_runtime_http_request_connector_executes_and_records_steps(empty_db, monkeypatch):
    client = TestClient(app)
    headers = _login_headers(client)
    called: dict[str, object] = {}

    def fake_http_request(*, method, url, headers, query, body, timeout_ms):
        called["method"] = method
        called["url"] = url
        called["headers"] = dict(headers)
        called["query"] = dict(query)
        called["body"] = body
        called["timeout_ms"] = timeout_ms
        return {
            "status_code": 202,
            "headers": {
                "content-type": "application/json",
                "x-upstream": "mocked",
            },
            "content_type": "application/json",
            "body": {
                "device_id": "device-1",
                "include": query.get("include"),
            },
        }

    monkeypatch.setattr(route_runtime_module, "_perform_http_request", fake_http_request)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="HTTP connector route", path="/api/http-proxy/{deviceId}"),
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    connection_response = client.post(
        "/api/admin/connections",
        json={
            "name": "HTTP upstream",
            "connector_type": "http",
            "description": "Shared upstream",
            "config": {
                "base_url": "https://api.example.com",
                "headers": {"x-api-key": "shared-secret"},
                "timeout_ms": 2400,
            },
            "is_active": True,
        },
        headers=headers,
    )
    assert connection_response.status_code == 201
    connection = connection_response.json()

    update_implementation_response = client.put(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        json={
            "flow_definition": {
                "schema_version": 1,
                "nodes": [
                    {"id": "trigger", "type": "api_trigger", "config": {}},
                    {
                        "id": "http-upstream",
                        "type": "http_request",
                        "config": {
                            "connection_id": connection["id"],
                            "method": "GET",
                            "path": "/devices/{{request.path.deviceId}}",
                            "query": {
                                "include": {"$ref": "request.query.include"},
                            },
                            "headers": {
                                "x-route-path": "{{route.path}}",
                            },
                            "timeout_ms": 1500,
                        },
                    },
                    {
                        "id": "response",
                        "type": "set_response",
                        "config": {
                            "status_code": {"$ref": "state.http-upstream.response.status_code"},
                            "body": {
                                "upstream": {"$ref": "state.http-upstream.response.body"},
                                "request_url": {"$ref": "state.http-upstream.request.url"},
                            },
                        },
                    },
                ],
                "edges": [
                    {"source": "trigger", "target": "http-upstream"},
                    {"source": "http-upstream", "target": "response"},
                ],
            }
        },
        headers=headers,
    )
    assert update_implementation_response.status_code == 200

    publish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201

    live_response = client.get("/api/http-proxy/device-1?include=specs")
    assert live_response.status_code == 202
    assert live_response.json() == {
        "upstream": {
            "device_id": "device-1",
            "include": "specs",
        },
        "request_url": "https://api.example.com/devices/device-1",
    }

    assert called == {
        "method": "GET",
        "url": "https://api.example.com/devices/device-1",
        "headers": {
            "x-api-key": "shared-secret",
            "x-route-path": "/api/http-proxy/{deviceId}",
        },
        "query": {"include": "specs"},
        "body": None,
        "timeout_ms": 1500,
    }

    executions_response = client.get(
        f"/api/admin/executions?endpoint_id={endpoint['id']}&limit=5",
        headers=headers,
    )
    assert executions_response.status_code == 200
    execution_id = executions_response.json()[0]["id"]

    execution_detail_response = client.get(
        f"/api/admin/executions/{execution_id}",
        headers=headers,
    )
    assert execution_detail_response.status_code == 200
    execution_detail = execution_detail_response.json()
    assert [step["node_type"] for step in execution_detail["steps"]] == [
        "api_trigger",
        "http_request",
        "set_response",
    ]
    http_step = execution_detail["steps"][1]
    assert http_step["output_data"]["connection"]["id"] == connection["id"]
    assert http_step["output_data"]["response"]["status_code"] == 202
    assert http_step["output_data"]["response"]["body"] == {
        "device_id": "device-1",
        "include": "specs",
    }


def test_runtime_postgres_query_connector_executes_and_records_steps(empty_db, monkeypatch):
    client = TestClient(app)
    headers = _login_headers(client)
    called: dict[str, object] = {}

    def fake_postgres_query(*, connection_config, sql, parameters):
        called["connection_config"] = dict(connection_config)
        called["sql"] = sql
        called["parameters"] = dict(parameters)
        return [
            {
                "order_id": parameters["order_id"],
                "status": "shipped",
            }
        ]

    monkeypatch.setattr(route_runtime_module, "_perform_postgres_query", fake_postgres_query)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Postgres connector route", path="/api/orders/{orderId}"),
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    connection_response = client.post(
        "/api/admin/connections",
        json={
            "name": "Orders database",
            "connector_type": "postgres",
            "description": "Read-only reporting replica",
            "config": {
                "dsn": "postgresql://readonly:secret@db.internal:5432/mockingbird",
            },
            "is_active": True,
        },
        headers=headers,
    )
    assert connection_response.status_code == 201
    connection = connection_response.json()

    update_implementation_response = client.put(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        json={
            "flow_definition": {
                "schema_version": 1,
                "nodes": [
                    {"id": "trigger", "type": "api_trigger", "config": {}},
                    {
                        "id": "orders-query",
                        "type": "postgres_query",
                        "config": {
                            "connection_id": connection["id"],
                            "sql": "select order_id, status from orders where order_id = %(order_id)s",
                            "parameters": {
                                "order_id": {"$ref": "request.path.orderId"},
                            },
                        },
                    },
                    {
                        "id": "response",
                        "type": "set_response",
                        "config": {
                            "status_code": 200,
                            "body": {
                                "count": {"$ref": "state.orders-query.row_count"},
                                "rows": {"$ref": "state.orders-query.rows"},
                            },
                        },
                    },
                ],
                "edges": [
                    {"source": "trigger", "target": "orders-query"},
                    {"source": "orders-query", "target": "response"},
                ],
            }
        },
        headers=headers,
    )
    assert update_implementation_response.status_code == 200

    publish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201

    live_response = client.get("/api/orders/ord_123")
    assert live_response.status_code == 200
    assert live_response.json() == {
        "count": 1,
        "rows": [
            {
                "order_id": "ord_123",
                "status": "shipped",
            }
        ],
    }

    assert called == {
        "connection_config": {
            "dsn": "postgresql://readonly:secret@db.internal:5432/mockingbird",
        },
        "sql": "select order_id, status from orders where order_id = %(order_id)s",
        "parameters": {"order_id": "ord_123"},
    }

    executions_response = client.get(
        f"/api/admin/executions?endpoint_id={endpoint['id']}&limit=5",
        headers=headers,
    )
    assert executions_response.status_code == 200
    execution_id = executions_response.json()[0]["id"]

    execution_detail_response = client.get(
        f"/api/admin/executions/{execution_id}",
        headers=headers,
    )
    assert execution_detail_response.status_code == 200
    execution_detail = execution_detail_response.json()
    assert [step["node_type"] for step in execution_detail["steps"]] == [
        "api_trigger",
        "postgres_query",
        "set_response",
    ]
    query_step = execution_detail["steps"][1]
    assert query_step["output_data"]["connection"]["id"] == connection["id"]
    assert query_step["output_data"]["row_count"] == 1
    assert query_step["output_data"]["rows"] == [
        {
            "order_id": "ord_123",
            "status": "shipped",
        }
    ]


def test_runtime_http_request_connector_failures_return_error_runs(empty_db, monkeypatch):
    client = TestClient(app)
    headers = _login_headers(client)

    def fake_http_request(*, method, url, headers, query, body, timeout_ms):
        raise httpx.ReadTimeout("upstream timed out")

    monkeypatch.setattr(route_runtime_module, "_perform_http_request", fake_http_request)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="HTTP failure route", path="/api/http-failure"),
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    connection_response = client.post(
        "/api/admin/connections",
        json={
            "name": "Failing upstream",
            "connector_type": "http",
            "description": None,
            "config": {"base_url": "https://api.example.com"},
            "is_active": True,
        },
        headers=headers,
    )
    assert connection_response.status_code == 201
    connection = connection_response.json()

    update_implementation_response = client.put(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        json={
            "flow_definition": {
                "schema_version": 1,
                "nodes": [
                    {"id": "trigger", "type": "api_trigger", "config": {}},
                    {
                        "id": "http",
                        "type": "http_request",
                        "config": {
                            "connection_id": connection["id"],
                            "method": "GET",
                            "path": "/status",
                        },
                    },
                    {
                        "id": "response",
                        "type": "set_response",
                        "config": {
                            "status_code": 200,
                            "body": {"ok": True},
                        },
                    },
                ],
                "edges": [
                    {"source": "trigger", "target": "http"},
                    {"source": "http", "target": "response"},
                ],
            }
        },
        headers=headers,
    )
    assert update_implementation_response.status_code == 200

    publish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201

    live_response = client.get("/api/http-failure")
    assert live_response.status_code == 502
    assert live_response.json() == {
        "error": "HTTP Request step failed to reach the upstream service.",
        "details": "upstream timed out",
    }

    executions_response = client.get(
        f"/api/admin/executions?endpoint_id={endpoint['id']}&limit=5",
        headers=headers,
    )
    assert executions_response.status_code == 200
    execution = executions_response.json()[0]
    assert execution["status"] == "error"
    assert execution["response_status_code"] == 502

    execution_detail_response = client.get(
        f"/api/admin/executions/{execution['id']}",
        headers=headers,
    )
    assert execution_detail_response.status_code == 200
    error_step = execution_detail_response.json()["steps"][1]
    assert error_step["node_type"] == "http_request"
    assert error_step["status"] == "error"
    assert error_step["error_message"] == "upstream timed out"


def test_openapi_endpoint(seeded_db):
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200


def test_public_contract_surfaces_hide_runtime_managed_routes_without_active_deployment(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    legacy_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Legacy public route", path="/api/legacy-public"),
        headers=headers,
    )
    assert legacy_response.status_code == 201

    draft_only_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Draft-only runtime route", path="/api/draft-only"),
        headers=headers,
    )
    assert draft_only_response.status_code == 201
    draft_only_endpoint = draft_only_response.json()

    current_implementation_response = client.get(
        f"/api/admin/endpoints/{draft_only_endpoint['id']}/implementation/current",
        headers=headers,
    )
    assert current_implementation_response.status_code == 200
    save_draft_response = client.put(
        f"/api/admin/endpoints/{draft_only_endpoint['id']}/implementation/current",
        json={"flow_definition": current_implementation_response.json()["flow_definition"]},
        headers=headers,
    )
    assert save_draft_response.status_code == 200

    published_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Published runtime route", path="/api/published-runtime"),
        headers=headers,
    )
    assert published_response.status_code == 201
    published_endpoint = published_response.json()

    publish_response = client.post(
        f"/api/admin/endpoints/{published_endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201

    deactivated_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Deactivated runtime route", path="/api/deactivated-runtime"),
        headers=headers,
    )
    assert deactivated_response.status_code == 201
    deactivated_endpoint = deactivated_response.json()

    deactivate_publish_response = client.post(
        f"/api/admin/endpoints/{deactivated_endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert deactivate_publish_response.status_code == 201

    with Session(engine) as session:
        deployment = session.get(RouteDeployment, deactivate_publish_response.json()["id"])
        assert deployment is not None
        deployment.is_active = False
        session.add(deployment)
        session.commit()
    route_runtime_module.invalidate_deployment_registry()

    openapi = client.get("/openapi.json").json()
    assert "/api/legacy-public" in openapi["paths"]
    assert "/api/published-runtime" in openapi["paths"]
    assert "/api/draft-only" not in openapi["paths"]
    assert "/api/deactivated-runtime" not in openapi["paths"]

    reference_payload = client.get("/api/reference.json").json()
    reference_paths = {endpoint["path"] for endpoint in reference_payload["endpoints"]}
    assert "/api/legacy-public" in reference_paths
    assert "/api/published-runtime" in reference_paths
    assert "/api/draft-only" not in reference_paths
    assert "/api/deactivated-runtime" not in reference_paths

    public_legacy_response = client.get("/api/legacy-public")
    assert public_legacy_response.status_code == 200
    assert public_legacy_response.json() == {"status": "ok"}

    public_draft_only_response = client.get("/api/draft-only")
    assert public_draft_only_response.status_code == 404

    public_deactivated_response = client.get("/api/deactivated-runtime")
    assert public_deactivated_response.status_code == 404

    public_published_response = client.get("/api/published-runtime")
    assert public_published_response.status_code == 200
    assert public_published_response.json()["route"] == {
        "name": "Published runtime route",
        "method": "GET",
        "path": "/api/published-runtime",
    }


def test_public_landing_reference_and_brand_asset(seeded_db):
    client = TestClient(app)

    landing = client.get("/")
    assert landing.status_code == 200
    assert "Mockingbird" in landing.text
    assert "data and no bedside manner" in landing.text
    assert "WARNING: The API may sometimes mock back." in landing.text
    assert "hero-title-accent" in landing.text
    assert "hero-panel-bottom" in landing.text
    assert "hero-panel-media" in landing.text
    assert "/static/landing/hero-top.svg" in landing.text
    assert "/static/landing/hero-bottom.svg" in landing.text
    assert "/api/reference.json" in landing.text
    assert "reference-table-body" in landing.text
    assert "payload-popover" in landing.text
    assert "payload-popover-request-section" in landing.text
    assert "modal-card-head-content" in landing.text
    assert "theme-toggle" in landing.text
    assert "bulma@1.0.4" in landing.text
    assert "status-success" in landing.text

    api_landing = client.get("/api")
    assert api_landing.status_code == 200
    assert "Browse live routes, inspect example payloads" in api_landing.text

    reference = client.get("/api/reference.json")
    assert reference.status_code == 200
    payload = reference.json()
    assert payload["product_name"] == "Mockingbird"
    assert payload["endpoint_count"] >= 1
    assert any(endpoint["sample_response"] is not None for endpoint in payload["endpoints"])

    post_endpoint = next(endpoint for endpoint in payload["endpoints"] if endpoint["method"] == "POST")
    assert post_endpoint["sample_request"] is not None
    assert post_endpoint["sample_response"] is not None

    get_endpoint = next(endpoint for endpoint in payload["endpoints"] if endpoint["method"] == "GET")
    assert get_endpoint["sample_request"] is None

    asset = client.get("/static/mockingbird-icon.svg")
    assert asset.status_code == 200
    assert asset.headers["content-type"].startswith("image/svg+xml")


def test_public_surfaces_follow_route_level_deployment_history(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    published_route_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Published boundary route", path="/api/published-boundary"),
        headers=headers,
    )
    assert published_route_response.status_code == 201
    published_route = published_route_response.json()

    legacy_route_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Legacy boundary route", path="/api/legacy-boundary"),
        headers=headers,
    )
    assert legacy_route_response.status_code == 201

    initial_openapi = client.get("/openapi.json").json()
    assert "/api/published-boundary" in initial_openapi["paths"]
    assert "/api/legacy-boundary" in initial_openapi["paths"]

    initial_reference_paths = {
        endpoint["path"] for endpoint in client.get("/api/reference.json").json()["endpoints"]
    }
    assert "/api/published-boundary" in initial_reference_paths
    assert "/api/legacy-boundary" in initial_reference_paths
    assert client.get("/api/published-boundary").json() == {"status": "ok"}

    implementation_response = client.put(
        f"/api/admin/endpoints/{published_route['id']}/implementation/current",
        json={
            "flow_definition": {
                "schema_version": 1,
                "nodes": [
                    {"id": "trigger", "type": "api_trigger", "config": {}},
                    {
                        "id": "transform",
                        "type": "transform",
                        "config": {"output": {"status": "published"}},
                    },
                    {
                        "id": "response",
                        "type": "set_response",
                        "config": {"status_code": 200, "body": {"$ref": "state.transform"}},
                    },
                ],
                "edges": [
                    {"source": "trigger", "target": "transform"},
                    {"source": "transform", "target": "response"},
                ],
            }
        },
        headers=headers,
    )
    assert implementation_response.status_code == 200

    publish_response = client.post(
        f"/api/admin/endpoints/{published_route['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201
    assert client.get("/api/published-boundary").json() == {"status": "published"}

    active_reference_paths = {
        endpoint["path"] for endpoint in client.get("/api/reference.json").json()["endpoints"]
    }
    assert "/api/published-boundary" in active_reference_paths
    assert "/api/legacy-boundary" in active_reference_paths

    with Session(engine) as session:
        deployments = list(
            session.execute(
                select(RouteDeployment).where(RouteDeployment.route_id == int(published_route["id"]))
            ).scalars()
        )
        assert len(deployments) == 1
        deployments[0].is_active = False
        session.add(deployments[0])
        session.commit()

    route_runtime_module.invalidate_deployment_registry()

    updated_openapi = client.get("/openapi.json").json()
    assert "/api/published-boundary" not in updated_openapi["paths"]
    assert "/api/legacy-boundary" in updated_openapi["paths"]

    updated_reference_paths = {
        endpoint["path"] for endpoint in client.get("/api/reference.json").json()["endpoints"]
    }
    assert "/api/published-boundary" not in updated_reference_paths
    assert "/api/legacy-boundary" in updated_reference_paths

    unpublished_response = client.get("/api/published-boundary")
    assert unpublished_response.status_code == 404

    legacy_response = client.get("/api/legacy-boundary")
    assert legacy_response.status_code == 200
    assert legacy_response.json() == {"status": "ok"}


def test_public_landing_escapes_embedded_reference_payload(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(
            name='</script><script>window.__MB_XSS__="pwned"</script>',
            path="/api/xss-test.+",
        ),
        headers=headers,
    )
    assert create_response.status_code == 201

    landing = client.get("/")
    assert landing.status_code == 200
    assert '<script id="initial-reference-data" type="application/json">' in landing.text
    assert "\\u003c/script\\u003e\\u003cscript\\u003ewindow.__MB_XSS__" in landing.text
    assert '</script><script>window.__MB_XSS__="pwned"</script>' not in landing.text


def test_security_headers_are_present_on_public_and_api_responses(seeded_db):
    client = TestClient(app)

    landing = client.get("/")
    assert landing.headers["x-content-type-options"] == "nosniff"
    assert landing.headers["x-frame-options"] == "DENY"
    assert landing.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "content-security-policy" in landing.headers

    reference = client.get("/api/reference.json")
    assert reference.headers["x-content-type-options"] == "nosniff"
    assert reference.headers["x-frame-options"] == "DENY"
    assert reference.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert reference.headers["content-security-policy"] == "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"

    secure_client = TestClient(app, base_url="https://testserver")
    secure_reference = secure_client.get("/api/reference.json")
    assert secure_reference.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_admin_endpoints_require_admin_session(empty_db):
    client = TestClient(app)
    response = client.get("/api/admin/endpoints")
    assert response.status_code == 401


def test_bootstrap_password_must_be_rotated_before_admin_access(empty_db):
    client = TestClient(app)

    login_response = client.post(
        "/api/admin/auth/login",
        json={
            "username": "admin",
            "password": INITIAL_ADMIN_PASSWORD,
            "remember_me": False,
        },
    )
    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["user"]["must_change_password"] is True
    headers = _bearer_headers(login_payload["token"])

    blocked_response = client.get("/api/admin/endpoints", headers=headers)
    assert blocked_response.status_code == 403
    assert "Password change required" in blocked_response.json()["detail"]

    change_response = client.post(
        "/api/admin/account/change-password",
        json={
            "current_password": INITIAL_ADMIN_PASSWORD,
            "new_password": ACTIVE_ADMIN_PASSWORD,
        },
        headers=headers,
    )
    assert change_response.status_code == 200
    assert change_response.json()["user"]["must_change_password"] is False

    restored_response = client.get("/api/admin/endpoints", headers=headers)
    assert restored_response.status_code == 200

    stale_login_response = client.post(
        "/api/admin/auth/login",
        json={
            "username": "admin",
            "password": INITIAL_ADMIN_PASSWORD,
            "remember_me": False,
        },
    )
    assert stale_login_response.status_code == 401


def test_ensure_test_admin_user_creates_and_updates_a_dedicated_qa_account(empty_db):
    with Session(engine) as session:
        created = ensure_test_admin_user(
            session,
            username="ui-agent",
            password="ui-agent-password-123",
            full_name="UI Test Agent",
            email="ui-agent@example.com",
            role="editor",
            must_change_password=False,
        )
        created_user = admin_auth_module.get_admin_user_by_username(session, "ui-agent")

        assert created.action == "created"
        assert created.generated_password is False
        assert created.password == "ui-agent-password-123"
        assert created_user is not None
        assert created_user.full_name == "UI Test Agent"
        assert created_user.email == "ui-agent@example.com"
        assert created_user.role == "editor"
        assert created_user.is_active is True
        assert created_user.must_change_password is False
        assert admin_auth_module.verify_password("ui-agent-password-123", created_user.password_hash)

        updated = ensure_test_admin_user(
            session,
            username="ui-agent",
            password="ui-agent-password-456",
            full_name="UI Reviewer",
            email="ui-reviewer@example.com",
            role="superuser",
            must_change_password=False,
        )
        updated_user = admin_auth_module.get_admin_user_by_username(session, "ui-agent")

        assert updated.action == "updated"
        assert updated.generated_password is False
        assert updated.password == "ui-agent-password-456"
        assert updated_user is not None
        assert updated_user.full_name == "UI Reviewer"
        assert updated_user.email == "ui-reviewer@example.com"
        assert updated_user.role == "superuser"
        assert updated_user.is_active is True
        assert updated_user.must_change_password is False
        assert admin_auth_module.verify_password("ui-agent-password-456", updated_user.password_hash)


def test_ensure_test_admin_user_rejects_shared_or_non_test_usernames(empty_db):
    with Session(engine) as session:
        with pytest.raises(ValueError, match="bootstrap admin account"):
            ensure_test_admin_user(
                session,
                username="admin",
                password="admin-password-123",
                must_change_password=False,
            )

        with pytest.raises(ValueError, match="must start with one of"):
            ensure_test_admin_user(
                session,
                username="reviewer",
                password="reviewer-password-123",
                must_change_password=False,
            )


def test_create_test_admin_parser_preserves_defaults_when_env_vars_are_blank(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(create_test_admin_script.USERNAME_ENV, "")
    monkeypatch.setenv(create_test_admin_script.PASSWORD_FILE_ENV, "   ")
    monkeypatch.setenv(create_test_admin_script.FULL_NAME_ENV, "")
    monkeypatch.setenv(create_test_admin_script.EMAIL_ENV, "")
    monkeypatch.setenv(create_test_admin_script.AVATAR_URL_ENV, "   ")
    monkeypatch.setenv(create_test_admin_script.ROLE_ENV, "")

    args = create_test_admin_script._build_parser().parse_args([])

    assert args.username == create_test_admin_script.DEFAULT_USERNAME
    assert args.password_file is None
    assert args.full_name == create_test_admin_script.DEFAULT_FULL_NAME
    assert args.email is None
    assert args.avatar_url is None
    assert args.role == create_test_admin_script.DEFAULT_ROLE.value


def test_admin_account_profile_endpoints_update_the_current_user(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    read_response = client.get("/api/admin/account/me", headers=headers)
    assert read_response.status_code == 200
    assert read_response.json()["username"] == "admin"

    update_response = client.put(
        "/api/admin/account/me",
        json={
            "username": "admin-renamed",
            "full_name": "Admin Example",
            "email": "admin@example.com",
            "avatar_url": "https://cdn.example.com/admin.png",
        },
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["user"]["username"] == "admin-renamed"
    assert update_response.json()["user"]["full_name"] == "Admin Example"
    assert update_response.json()["user"]["email"] == "admin@example.com"
    assert update_response.json()["user"]["avatar_url"] == "https://cdn.example.com/admin.png"
    assert "gravatar_url" in update_response.json()["user"]

    renamed_login_response = client.post(
        "/api/admin/auth/login",
        json={
            "username": "admin-renamed",
            "password": ACTIVE_ADMIN_PASSWORD,
            "remember_me": False,
        },
    )
    assert renamed_login_response.status_code == 200

    partial_update_response = client.put(
        "/api/admin/account/me",
        json={"full_name": "Renamed Admin"},
        headers=headers,
    )
    assert partial_update_response.status_code == 200
    assert partial_update_response.json()["user"]["username"] == "admin-renamed"
    assert partial_update_response.json()["user"]["full_name"] == "Renamed Admin"


def test_admin_login_locks_user_after_repeated_failures(empty_db, monkeypatch: pytest.MonkeyPatch):
    client = TestClient(app)
    monkeypatch.setattr(admin_auth_module.settings, "admin_login_max_attempts", 2)
    monkeypatch.setattr(admin_auth_module.settings, "admin_login_ip_max_attempts", 99)
    monkeypatch.setattr(admin_auth_module.settings, "admin_login_window_seconds", 300)
    monkeypatch.setattr(admin_auth_module.settings, "admin_login_lockout_seconds", 60)

    for _ in range(2):
        failed_response = client.post(
            "/api/admin/auth/login",
            json={
                "username": "admin",
                "password": "wrong-password",
                "remember_me": False,
            },
        )
        assert failed_response.status_code == 401

    locked_response = client.post(
        "/api/admin/auth/login",
        json={
            "username": "admin",
            "password": INITIAL_ADMIN_PASSWORD,
            "remember_me": False,
        },
    )
    assert locked_response.status_code == 429
    assert int(locked_response.headers["retry-after"]) >= 1


def test_admin_login_throttles_repeated_failures_from_the_same_ip(empty_db, monkeypatch: pytest.MonkeyPatch):
    client = TestClient(app)
    monkeypatch.setattr(admin_auth_module.settings, "admin_login_max_attempts", 99)
    monkeypatch.setattr(admin_auth_module.settings, "admin_login_ip_max_attempts", 2)
    monkeypatch.setattr(admin_auth_module.settings, "admin_login_window_seconds", 300)
    monkeypatch.setattr(admin_auth_module.settings, "admin_login_lockout_seconds", 60)

    for _ in range(2):
        failed_response = client.post(
            "/api/admin/auth/login",
            json={
                "username": "unknown-user",
                "password": "wrong-password",
                "remember_me": False,
            },
        )
        assert failed_response.status_code == 401

    throttled_response = client.post(
        "/api/admin/auth/login",
        json={
            "username": "unknown-user",
            "password": "wrong-password",
            "remember_me": False,
        },
    )
    assert throttled_response.status_code == 429
    assert int(throttled_response.headers["retry-after"]) >= 1


def test_get_session_dependency_closes_session_context():
    events: list[tuple[str, object | None]] = []

    class FakeSession:
        def __init__(self, bound_engine):
            events.append(("init", bound_engine))

        def __enter__(self):
            events.append(("enter", None))
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append(("exit", exc_type))

    original_session = db_module.Session
    db_module.Session = FakeSession
    try:
        dependency = db_module.get_session()
        session = next(dependency)

        assert isinstance(session, FakeSession)
        assert [event[0] for event in events] == ["init", "enter"]

        with pytest.raises(StopIteration):
            next(dependency)

        assert [event[0] for event in events] == ["init", "enter", "exit"]
    finally:
        db_module.Session = original_session


def test_superusers_can_manage_dashboard_users(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/users",
        json={
            "username": "editor",
            "full_name": "Editor Person",
            "email": "editor@example.com",
            "avatar_url": "https://cdn.example.com/editor.png",
            "password": "editor-password-123",
            "role": "editor",
            "must_change_password": True,
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    created_user = create_response.json()
    assert created_user["username"] == "editor"
    assert created_user["full_name"] == "Editor Person"
    assert created_user["email"] == "editor@example.com"
    assert created_user["avatar_url"] == "https://cdn.example.com/editor.png"
    assert "gravatar_url" in created_user
    assert created_user["role"] == "editor"
    assert "routes.write" in created_user["permissions"]
    assert created_user["must_change_password"] is True

    list_response = client.get("/api/admin/users", headers=headers)
    assert list_response.status_code == 200
    assert {user["username"] for user in list_response.json()} >= {"admin", "editor"}

    read_response = client.get(f"/api/admin/users/{created_user['id']}", headers=headers)
    assert read_response.status_code == 200
    assert read_response.json()["username"] == "editor"

    update_response = client.put(
        f"/api/admin/users/{created_user['id']}",
        json={
            "is_active": False,
            "must_change_password": False,
            "full_name": "Editor Person Updated",
            "email": "editor-updated@example.com",
            "avatar_url": "https://cdn.example.com/editor-updated.png",
        },
        headers=headers,
    )
    assert update_response.status_code == 200
    updated_user = update_response.json()
    assert updated_user["is_active"] is False
    assert updated_user["must_change_password"] is False
    assert updated_user["full_name"] == "Editor Person Updated"
    assert updated_user["email"] == "editor-updated@example.com"
    assert updated_user["avatar_url"] == "https://cdn.example.com/editor-updated.png"

    delete_response = client.delete(f"/api/admin/users/{created_user['id']}", headers=headers)
    assert delete_response.status_code == 204


def test_deleting_dashboard_user_removes_historical_sessions(empty_db):
    client = TestClient(app)
    admin_headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/users",
        json={
            "username": "audited-user",
            "password": "audited-user-password-123",
            "role": "editor",
            "must_change_password": False,
        },
        headers=admin_headers,
    )
    assert create_response.status_code == 201
    created_user = create_response.json()

    user_headers = _login_headers(
        client,
        username="audited-user",
        candidate_passwords=("audited-user-password-123",),
    )

    logout_response = client.post("/api/admin/auth/logout", headers=user_headers)
    assert logout_response.status_code == 204

    delete_response = client.delete(f"/api/admin/users/{created_user['id']}", headers=admin_headers)
    assert delete_response.status_code == 204

    list_response = client.get("/api/admin/users", headers=admin_headers)
    assert list_response.status_code == 200
    assert all(user["id"] != created_user["id"] for user in list_response.json())


def test_roles_gate_admin_api_access(empty_db):
    client = TestClient(app)
    admin_headers = _login_headers(client)

    viewer_create_response = client.post(
        "/api/admin/users",
        json={
            "username": "viewer-user",
            "password": "viewer-password-123",
            "role": "viewer",
            "must_change_password": False,
        },
        headers=admin_headers,
    )
    assert viewer_create_response.status_code == 201
    assert viewer_create_response.json()["permissions"] == ["routes.read", "routes.preview"]

    editor_create_response = client.post(
        "/api/admin/users",
        json={
            "username": "editor-user",
            "password": "editor-password-123",
            "role": "editor",
            "must_change_password": False,
        },
        headers=admin_headers,
    )
    assert editor_create_response.status_code == 201
    assert "routes.write" in editor_create_response.json()["permissions"]

    viewer_headers = _login_headers(
        client,
        username="viewer-user",
        candidate_passwords=("viewer-password-123",),
    )
    editor_headers = _login_headers(
        client,
        username="editor-user",
        candidate_passwords=("editor-password-123",),
    )

    viewer_list_response = client.get("/api/admin/endpoints", headers=viewer_headers)
    assert viewer_list_response.status_code == 200

    viewer_preview_response = client.post(
        "/api/admin/endpoints/preview-response",
        json={
            "response_schema": {
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
        },
        headers=viewer_headers,
    )
    assert viewer_preview_response.status_code == 200
    assert viewer_preview_response.json()["preview"] == {"status": "ok"}

    viewer_create_route_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Viewer route", path="/api/viewer-route"),
        headers=viewer_headers,
    )
    assert viewer_create_route_response.status_code == 403
    assert "cannot create, edit, import, or delete routes" in viewer_create_route_response.json()["detail"]

    viewer_users_response = client.get("/api/admin/users", headers=viewer_headers)
    assert viewer_users_response.status_code == 403

    viewer_read_user_response = client.get("/api/admin/users/1", headers=viewer_headers)
    assert viewer_read_user_response.status_code == 403

    editor_list_response = client.get("/api/admin/endpoints", headers=editor_headers)
    assert editor_list_response.status_code == 200

    editor_create_route_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Editor route", path="/api/editor-route"),
        headers=editor_headers,
    )
    assert editor_create_route_response.status_code == 201
    assert editor_create_route_response.json()["name"] == "Editor route"

    editor_users_response = client.get("/api/admin/users", headers=editor_headers)
    assert editor_users_response.status_code == 403


def test_private_admin_paths_cannot_be_created_as_public_mocks(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    response = client.post(
        "/api/admin/endpoints",
        json={
            "name": "Shadow Admin",
            "method": "GET",
            "path": "/api/admin/shadow",
            "category": "security",
            "tags": [],
            "summary": "Should be rejected",
            "description": "Reserved path",
            "enabled": True,
            "auth_mode": "none",
            "request_schema": {},
            "response_schema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "x-mock": {"mode": "fixed", "value": "blocked", "options": {}},
                    }
                },
                "required": ["status"],
                "x-builder": {"order": ["status"]},
                "x-mock": {"mode": "generate"},
            },
            "success_status_code": 200,
            "error_rate": 0.0,
            "latency_min_ms": 0,
            "latency_max_ms": 0,
            "seed_key": None,
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert "reserved for private admin routes" in response.json()["detail"]


def test_public_route_matching_treats_saved_paths_as_literals(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Regex Literal", path="/api/regex-test.+"),
        headers=headers,
    )
    assert create_response.status_code == 201

    literal_response = client.get("/api/regex-test.+")
    assert literal_response.status_code == 200

    fuzzy_response = client.get("/api/regex-testXYZ")
    assert fuzzy_response.status_code == 404

    child_response = client.get("/api/regex-test.+/child")
    assert child_response.status_code == 404


def test_admin_crud_lifecycle_supports_builder_extensions(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)
    payload = {
        "name": "List Gadgets",
        "method": "GET",
        "path": "/api/gadgets",
        "category": "gadgets",
        "tags": ["gadgets", "inventory"],
        "summary": "List gadgets",
        "description": "Returns the current gadget catalog.",
        "enabled": True,
        "auth_mode": "none",
        "request_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
            },
            "required": [],
            "x-builder": {"order": ["limit"]},
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "format": "uuid",
                    "x-mock": {"mode": "generate", "type": "id", "options": {}},
                },
                "status": {
                    "type": "string",
                    "enum": ["ok", "queued"],
                    "x-mock": {"mode": "generate", "type": "enum", "options": {}},
                },
            },
            "required": ["id", "status"],
            "x-builder": {"order": ["id", "status"]},
            "x-mock": {"mode": "generate"},
        },
        "success_status_code": 200,
        "error_rate": 0.0,
        "latency_min_ms": 0,
        "latency_max_ms": 0,
        "seed_key": "gadgets",
    }

    create_response = client.post("/api/admin/endpoints", json=payload, headers=headers)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["slug"] == "list-gadgets"
    assert created["response_schema"]["properties"]["id"]["x-mock"]["type"] == "id"
    assert "example_template" not in created
    assert "response_mode" not in created

    read_response = client.get(f"/api/admin/endpoints/{created['id']}", headers=headers)
    assert read_response.status_code == 200

    update_response = client.put(
        f"/api/admin/endpoints/{created['id']}",
        json={
            "enabled": False,
            "response_schema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "x-mock": {"mode": "fixed", "value": "offline", "options": {}},
                    }
                },
                "required": ["status"],
                "x-builder": {"order": ["status"]},
                "x-mock": {"mode": "generate"},
            },
        },
        headers=headers,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["enabled"] is False
    assert updated["response_schema"]["properties"]["status"]["x-mock"]["mode"] == "fixed"

    delete_response = client.delete(f"/api/admin/endpoints/{created['id']}", headers=headers)
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/admin/endpoints/{created['id']}", headers=headers)
    assert missing_response.status_code == 404


def test_admin_endpoint_slugs_auto_generate_and_stay_unique(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    first_response = client.post(
        "/api/admin/endpoints",
        json={
            "name": "Sync Job",
            "method": "GET",
            "path": "/api/sync-job",
            "category": "jobs",
            "tags": [],
            "summary": "First sync job",
            "description": "",
            "enabled": True,
            "auth_mode": "none",
            "request_schema": {},
            "response_schema": {"type": "object", "properties": {}, "required": [], "x-builder": {"order": []}, "x-mock": {"mode": "generate"}},
            "success_status_code": 200,
            "error_rate": 0.0,
            "latency_min_ms": 0,
            "latency_max_ms": 0,
            "seed_key": None,
        },
        headers=headers,
    )
    assert first_response.status_code == 201
    first_endpoint = first_response.json()
    assert first_endpoint["slug"] == "sync-job"

    second_response = client.post(
        "/api/admin/endpoints",
        json={
            "name": "Sync Job",
            "method": "GET",
            "path": "/api/sync-job-copy",
            "category": "jobs",
            "tags": [],
            "summary": "Second sync job",
            "description": "",
            "enabled": True,
            "auth_mode": "none",
            "request_schema": {},
            "response_schema": {"type": "object", "properties": {}, "required": [], "x-builder": {"order": []}, "x-mock": {"mode": "generate"}},
            "success_status_code": 200,
            "error_rate": 0.0,
            "latency_min_ms": 0,
            "latency_max_ms": 0,
            "seed_key": None,
        },
        headers=headers,
    )
    assert second_response.status_code == 201
    second_endpoint = second_response.json()
    assert second_endpoint["slug"] == "sync-job-2"

    rename_response = client.put(
        f"/api/admin/endpoints/{first_endpoint['id']}",
        json={"name": "Restart Job"},
        headers=headers,
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["slug"] == "restart-job"


def test_preview_endpoint_is_seeded_and_type_correct(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)
    response_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "x-mock": {"mode": "generate", "type": "id", "options": {}}},
            "email": {"type": "string", "x-mock": {"mode": "generate", "type": "email", "options": {}}},
            "firstName": {"type": "string", "x-mock": {"mode": "generate", "type": "first_name", "options": {}}},
            "displayName": {"type": "string", "x-mock": {"mode": "generate", "type": "name", "options": {}}},
            "quote": {
                "type": "string",
                "x-mock": {"mode": "mocking", "type": "long_text", "options": {}},
            },
            "status": {
                "type": "string",
                "enum": ["ok", "queued"],
                "x-mock": {"mode": "generate", "type": "enum", "options": {}},
            },
            "teaser": {
                "type": "string",
                "x-mock": {"mode": "mocking", "type": "text", "options": {"sentences": 1}},
            },
            "contact": {
                "type": "string",
                "x-mock": {"mode": "mocking", "type": "email", "options": {}},
            },
            "passwordHash": {
                "type": "string",
                "x-mock": {"mode": "generate", "type": "password", "options": {}},
            },
            "shortcutKey": {
                "type": "string",
                "x-mock": {"mode": "generate", "type": "keyboard_key", "options": {}},
            },
            "action": {
                "type": "string",
                "x-mock": {"mode": "mocking", "type": "verb", "options": {}},
            },
            "fileName": {
                "type": "string",
                "x-mock": {"mode": "generate", "type": "file_name", "options": {}},
            },
            "contentType": {
                "type": "string",
                "x-mock": {"mode": "generate", "type": "mime_type", "options": {}},
            },
            "price": {
                "type": "number",
                "minimum": 10,
                "maximum": 500,
                "x-mock": {"mode": "mocking", "type": "price", "options": {"precision": 2}},
            },
            "details": {
                "type": "object",
                "x-mock": {"mode": "fixed", "value": {"source": "preview"}, "options": {}},
                "properties": {
                    "source": {"type": "string"},
                },
                "required": ["source"],
                "x-builder": {"order": ["source"]},
            },
            "pathUserId": {
                "type": "string",
                "x-mock": {
                    "mode": "generate",
                    "type": "path_parameter",
                    "generator": "path_parameter",
                    "parameter": "userId",
                    "options": {"parameter": "userId"},
                },
            },
        },
        "required": ["id", "email", "firstName", "displayName", "quote", "status", "teaser", "contact", "passwordHash", "shortcutKey", "action", "fileName", "contentType", "price", "details", "pathUserId"],
        "x-builder": {"order": ["id", "email", "firstName", "displayName", "quote", "status", "teaser", "contact", "passwordHash", "shortcutKey", "action", "fileName", "contentType", "price", "details", "pathUserId"]},
        "x-mock": {"mode": "generate"},
    }

    first = client.post(
        "/api/admin/endpoints/preview-response",
        json={"response_schema": response_schema, "seed_key": "stable-seed", "path_parameters": {"userId": "user-123"}},
        headers=headers,
    )
    second = client.post(
        "/api/admin/endpoints/preview-response",
        json={"response_schema": response_schema, "seed_key": "stable-seed", "path_parameters": {"userId": "user-123"}},
        headers=headers,
    )
    third = client.post(
        "/api/admin/endpoints/preview-response",
        json={"response_schema": response_schema, "seed_key": None, "path_parameters": {"userId": "user-123"}},
        headers=headers,
    )
    fourth = client.post(
        "/api/admin/endpoints/preview-response",
        json={"response_schema": response_schema, "seed_key": None, "path_parameters": {"userId": "user-123"}},
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert fourth.status_code == 200

    first_preview = first.json()["preview"]
    assert first_preview == second.json()["preview"]
    UUID(first_preview["id"])
    assert first_preview["details"] == {"source": "preview"}
    assert first_preview["status"] in {"ok", "queued"}
    assert isinstance(first_preview["firstName"], str) and first_preview["firstName"]
    assert isinstance(first_preview["displayName"], str) and " " in first_preview["displayName"]
    assert isinstance(first_preview["quote"], str) and len(first_preview["quote"]) > 64
    assert first_preview["contact"].endswith("@mockingbird.test")
    assert isinstance(first_preview["passwordHash"], str)
    assert first_preview["passwordHash"].startswith("$2b$12$")
    assert len(first_preview["passwordHash"]) == 60
    assert first_preview["shortcutKey"] in {
        "Enter",
        "Escape",
        "Tab",
        "Space",
        "Backspace",
        "Delete",
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
        "Shift",
        "Control",
        "Alt",
        "Meta",
        "F1",
        "F5",
        "F12",
        "A",
        "C",
        "K",
        "/",
    }
    assert first_preview["action"] in {
        "Start",
        "Stop",
        "Restart",
        "Shutdown",
        "Halt",
        "Pause",
        "Resume",
        "Retry",
        "Cancel",
        "Enable",
        "Disable",
        "Start Job",
        "Restart Job",
        "Cancel Job",
        "Stop Job",
        "Archive",
        "Restore",
    }
    assert isinstance(first_preview["fileName"], str) and "." in first_preview["fileName"]
    assert first_preview["contentType"] in {
        "application/json",
        "application/pdf",
        "application/xml",
        "application/zip",
        "image/jpeg",
        "image/png",
        "text/csv",
        "text/plain",
    }
    assert first_preview["pathUserId"] == "user-123"
    assert any(
        token in first_preview["teaser"].lower()
        for token in {"mock", "payload", "response", "sample", "schema", "staging", "tests", "demo"}
    )
    assert isinstance(first_preview["price"], float)
    assert first_preview != fourth.json()["preview"] or third.json()["preview"] != fourth.json()["preview"]


def test_preview_endpoint_upgrades_legacy_text_quotes_to_long_text(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)
    response_schema = {
        "type": "object",
        "properties": {
            "quote": {
                "type": "string",
                "x-mock": {"mode": "mocking", "type": "text", "options": {"sentences": 2}},
            },
        },
        "required": ["quote"],
        "x-builder": {"order": ["quote"]},
        "x-mock": {"mode": "generate"},
    }

    response = client.post(
        "/api/admin/endpoints/preview-response",
        json={"response_schema": response_schema, "seed_key": "stable-seed"},
        headers=headers,
    )

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert isinstance(preview["quote"], str)
    assert len(preview["quote"]) > 64


def test_preview_endpoint_can_render_request_aware_templates(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)
    response_schema = {
        "type": "object",
        "properties": {
            "receipt": {
                "type": "string",
                "x-mock": {
                    "mode": "fixed",
                    "value": "approved",
                    "options": {},
                    "template": "order={{request.path.orderId}} status={{request.query.status}} email={{request.body.customer.email}} base={{value}} missing={{request.query.missing}}",
                },
            },
            "slugLine": {
                "type": "string",
                "x-mock": {
                    "mode": "generate",
                    "type": "slug",
                    "options": {"words": 2},
                    "template": "slug={{value}}",
                },
            },
        },
        "required": ["receipt", "slugLine"],
        "x-builder": {"order": ["receipt", "slugLine"]},
        "x-mock": {"mode": "generate"},
    }

    response = client.post(
        "/api/admin/endpoints/preview-response",
        json={
            "response_schema": response_schema,
            "seed_key": "template-seed",
            "path_parameters": {"orderId": "ord-123"},
            "query_parameters": {"status": "queued"},
            "request_body": {"customer": {"email": "alex@example.com"}},
        },
        headers=headers,
    )

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert preview["receipt"] == "order=ord-123 status=queued email=alex@example.com base=approved missing="
    assert preview["slugLine"].startswith("slug=")
    assert len(preview["slugLine"]) > len("slug=")


def test_runtime_dispatch_matches_seeded_endpoints(seeded_db):
    client = TestClient(app)

    list_response = client.get("/api/quotes")
    assert list_response.status_code == 200
    quotes = list_response.json()
    assert isinstance(quotes, list)
    assert len(quotes) >= 2
    assert {"id", "quote", "author"} <= set(quotes[0].keys())

    detail_response = client.get("/api/users/example-user")
    assert detail_response.status_code == 200
    user = detail_response.json()
    assert {"id", "displayName", "email", "role"} <= set(user.keys())

    create_response = client.post("/api/users", json={"displayName": "Alex", "email": "alex@example.mock"})
    assert create_response.status_code == 201
    created_user = create_response.json()
    assert {"id", "displayName", "email", "createdAt"} <= set(created_user.keys())

    devices_response = client.get("/api/devices")
    assert devices_response.status_code == 200
    devices = devices_response.json()
    assert isinstance(devices, list)
    assert len(devices) >= 2
    assert {"deviceId", "model", "status"} <= set(devices[0].keys())
    UUID(devices[0]["deviceId"])

    device_detail_response = client.get("/api/devices/example-device")
    assert device_detail_response.status_code == 200
    device = device_detail_response.json()
    assert {"deviceId", "model", "status", "lastSeen"} <= set(device.keys())
    UUID(device["deviceId"])

    health_response = client.get("/api/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}


def test_runtime_dispatch_can_echo_path_parameters_from_the_route(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json={
            "name": "Get route echo",
            "method": "GET",
            "path": "/api/orders/{orderId}",
            "category": "orders",
            "tags": ["orders"],
            "summary": "Echo the order id from the route",
            "description": "Uses the route parameter as a response value.",
            "enabled": True,
            "auth_mode": "none",
            "request_schema": {},
            "response_schema": {
                "type": "object",
                "properties": {
                    "orderId": {
                        "type": "string",
                        "x-mock": {
                            "mode": "generate",
                            "type": "path_parameter",
                            "generator": "path_parameter",
                            "parameter": "orderId",
                            "options": {"parameter": "orderId"},
                        },
                    }
                },
                "required": ["orderId"],
                "x-builder": {"order": ["orderId"]},
                "x-mock": {"mode": "generate"},
            },
            "success_status_code": 200,
            "error_rate": 0.0,
            "latency_min_ms": 0,
            "latency_max_ms": 0,
            "seed_key": "orders",
        },
        headers=headers,
    )

    assert create_response.status_code == 201

    runtime_response = client.get("/api/orders/order-123")
    assert runtime_response.status_code == 200
    assert runtime_response.json() == {"orderId": "order-123"}


def test_runtime_dispatch_can_render_request_aware_templates(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json={
            "name": "Create order email",
            "method": "POST",
            "path": "/api/orders/{orderId}/emails",
            "category": "orders",
            "tags": ["orders"],
            "summary": "Render request-aware template fields",
            "description": "Combines path, query, body, and generated values in a response template.",
            "enabled": True,
            "auth_mode": "none",
            "request_schema": {
                "type": "object",
                "properties": {
                    "customer": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "format": "email"},
                        },
                        "required": ["email"],
                        "x-builder": {"order": ["email"]},
                    }
                },
                "required": ["customer"],
                "x-builder": {"order": ["customer"]},
                "x-request": {
                    "path": {
                        "type": "object",
                        "properties": {
                            "orderId": {"type": "string"},
                        },
                        "required": ["orderId"],
                        "x-builder": {"order": ["orderId"]},
                    },
                    "query": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string"},
                        },
                        "required": [],
                        "x-builder": {"order": ["status"]},
                    },
                },
            },
            "response_schema": {
                "type": "object",
                "properties": {
                    "receipt": {
                        "type": "string",
                        "x-mock": {
                            "mode": "fixed",
                            "value": "accepted",
                            "options": {},
                            "template": "order={{request.path.orderId}} status={{request.query.status}} email={{request.body.customer.email}} value={{value}}",
                        },
                    },
                    "token": {
                        "type": "string",
                        "x-mock": {
                            "mode": "generate",
                            "type": "slug",
                            "options": {"words": 2},
                            "template": "token={{value}}",
                        },
                    },
                },
                "required": ["receipt", "token"],
                "x-builder": {"order": ["receipt", "token"]},
                "x-mock": {"mode": "generate"},
            },
            "success_status_code": 201,
            "error_rate": 0.0,
            "latency_min_ms": 0,
            "latency_max_ms": 0,
            "seed_key": "templated-orders",
        },
        headers=headers,
    )

    assert create_response.status_code == 201

    runtime_response = client.post(
        "/api/orders/order-123/emails?status=queued",
        json={"customer": {"email": "alex@example.com"}},
    )
    assert runtime_response.status_code == 201

    payload = runtime_response.json()
    assert payload["receipt"] == "order=order-123 status=queued email=alex@example.com value=accepted"
    assert payload["token"].startswith("token=")
    assert len(payload["token"]) > len("token=")


def test_admin_rejects_response_templates_on_non_string_fields(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    response = client.post(
        "/api/admin/endpoints",
        json={
            "name": "Invalid template endpoint",
            "method": "GET",
            "path": "/api/invalid-template",
            "category": "testing",
            "tags": [],
            "summary": "Reject invalid templates",
            "description": "Templates should only be allowed on string fields.",
            "enabled": True,
            "auth_mode": "none",
            "request_schema": {},
            "response_schema": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "x-mock": {
                            "mode": "generate",
                            "type": "integer",
                            "options": {},
                            "template": "count={{value}}",
                        },
                    }
                },
                "required": ["count"],
                "x-builder": {"order": ["count"]},
                "x-mock": {"mode": "generate"},
            },
            "success_status_code": 200,
            "error_rate": 0.0,
            "latency_min_ms": 0,
            "latency_max_ms": 0,
            "seed_key": None,
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert "only supported on string fields" in response.json()["detail"]


def test_seeded_device_schemas_use_curated_model_enum_defaults(seeded_db):
    with Session(engine) as session:
        endpoints = {
            endpoint.slug: endpoint
            for endpoint in session.execute(
                select(EndpointDefinition).where(EndpointDefinition.slug.in_(["list-devices", "get-device"]))
            )
            .scalars()
            .all()
        }

    list_devices_model_schema = endpoints["list-devices"].response_schema["items"]["properties"]["model"]
    get_device_model_schema = endpoints["get-device"].response_schema["properties"]["model"]
    list_devices_id_schema = endpoints["list-devices"].response_schema["items"]["properties"]["deviceId"]
    get_device_id_schema = endpoints["get-device"].response_schema["properties"]["deviceId"]

    assert list_devices_model_schema["enum"] == DEVICE_MODELS
    assert get_device_model_schema["enum"] == DEVICE_MODELS
    assert list_devices_id_schema["format"] == "uuid"
    assert get_device_id_schema["format"] == "uuid"
    assert list_devices_id_schema["x-mock"]["type"] == "id"
    assert get_device_id_schema["x-mock"]["type"] == "id"


def test_runtime_dispatch_ignores_disabled_endpoints(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json={
            "name": "Disabled Endpoint",
            "method": "GET",
            "path": "/api/disabled",
            "category": "testing",
            "tags": [],
            "summary": "Disabled endpoint",
            "description": "Should not be publicly reachable.",
            "enabled": False,
            "auth_mode": "none",
            "request_schema": {},
            "response_schema": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "x-mock": {"mode": "fixed", "value": "You should not see this.", "options": {}},
                    }
                },
                "required": ["message"],
                "x-builder": {"order": ["message"]},
                "x-mock": {"mode": "generate"},
            },
            "success_status_code": 200,
            "error_rate": 0.0,
            "latency_min_ms": 0,
            "latency_max_ms": 0,
            "seed_key": None,
        },
        headers=headers,
    )
    assert create_response.status_code == 201

    response = client.get("/api/disabled")
    assert response.status_code == 404


def test_openapi_strips_internal_extensions_and_emits_request_body(seeded_db):
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200

    openapi = response.json()
    create_user = openapi["paths"]["/api/users"]["post"]
    assert "requestBody" in create_user
    get_user = openapi["paths"]["/api/users/{id}"]["get"]
    assert get_user["parameters"] == [
        {
            "in": "path",
            "name": "id",
            "required": True,
            "schema": {"type": "string"},
        }
    ]

    response_schema = create_user["responses"]["201"]["content"]["application/json"]["schema"]
    assert "x-mock" not in response_schema
    assert "x-builder" not in response_schema
    assert "x-mock" not in response_schema["properties"]["id"]


def test_admin_can_export_endpoint_bundle(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json={
            "name": "List accounts",
            "method": "GET",
            "path": "/api/accounts/{accountId}",
            "category": "accounts",
            "tags": ["accounts"],
            "summary": "List accounts",
            "description": "Exports in the native bundle format.",
            "enabled": True,
            "auth_mode": "none",
            "request_schema": {
                "type": "object",
                "properties": {},
                "required": [],
                "x-builder": {"order": []},
                "x-request": {
                    "path": {
                        "type": "object",
                        "properties": {
                            "accountId": {
                                "type": "string",
                                "format": "uuid",
                            }
                        },
                        "required": ["accountId"],
                        "x-builder": {"order": ["accountId"]},
                    }
                },
            },
            "response_schema": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "x-mock": {"mode": "generate", "type": "id", "options": {}},
                    }
                },
                "required": ["id"],
                "x-builder": {"order": ["id"]},
                "x-mock": {"mode": "generate"},
            },
            "success_status_code": 200,
            "error_rate": 0.0,
            "latency_min_ms": 0,
            "latency_max_ms": 0,
            "seed_key": "accounts-export",
        },
        headers=headers,
    )
    assert create_response.status_code == 201

    export_response = client.get("/api/admin/endpoints/export", headers=headers)
    assert export_response.status_code == 200

    bundle = export_response.json()
    assert bundle["schema_version"] == 1
    assert bundle["product"] == "Mockingbird"
    assert len(bundle["endpoints"]) == 1

    exported_endpoint = bundle["endpoints"][0]
    assert exported_endpoint["name"] == "List accounts"
    assert exported_endpoint["slug"] == "list-accounts"
    assert exported_endpoint["method"] == "GET"
    assert exported_endpoint["path"] == "/api/accounts/{accountId}"
    assert exported_endpoint["category"] == "accounts"
    assert exported_endpoint["tags"] == ["accounts"]
    assert exported_endpoint["summary"] == "List accounts"
    assert exported_endpoint["description"] == "Exports in the native bundle format."
    assert exported_endpoint["enabled"] is True
    assert exported_endpoint["auth_mode"] == "none"
    assert exported_endpoint["success_status_code"] == 200
    assert exported_endpoint["error_rate"] == 0.0
    assert exported_endpoint["latency_min_ms"] == 0
    assert exported_endpoint["latency_max_ms"] == 0
    assert exported_endpoint["seed_key"] == "accounts-export"
    assert exported_endpoint["request_schema"] == {
        "type": "object",
        "properties": {},
        "required": [],
        "x-builder": {"order": []},
        "x-request": {
            "path": {
                "type": "object",
                "properties": {
                    "accountId": {
                        "type": "string",
                        "format": "uuid",
                    }
                },
                "required": ["accountId"],
                "x-builder": {"order": ["accountId"]},
            }
        },
    }
    assert exported_endpoint["response_schema"]["type"] == "object"
    assert exported_endpoint["response_schema"]["required"] == ["id"]
    assert exported_endpoint["response_schema"]["x-builder"] == {"order": ["id"]}
    assert exported_endpoint["response_schema"]["x-mock"]["mode"] == "generate"
    assert exported_endpoint["response_schema"]["properties"]["id"] == {
        "type": "string",
        "format": "uuid",
        "x-mock": {"mode": "generate", "type": "id", "generator": "id", "options": {}},
    }


def test_admin_endpoint_import_supports_upsert_dry_run_and_apply(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    existing_response = client.post(
        "/api/admin/endpoints",
        json={
            "name": "List accounts",
            "method": "GET",
            "path": "/api/accounts/{accountId}",
            "category": "accounts",
            "tags": ["accounts"],
            "summary": "Original summary",
            "description": "Original description",
            "enabled": True,
            "auth_mode": "none",
            "request_schema": {},
            "response_schema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "x-mock": {"mode": "fixed", "value": "original", "options": {}},
                    }
                },
                "required": ["status"],
                "x-builder": {"order": ["status"]},
                "x-mock": {"mode": "generate"},
            },
            "success_status_code": 200,
            "error_rate": 0.0,
            "latency_min_ms": 0,
            "latency_max_ms": 0,
            "seed_key": None,
        },
        headers=headers,
    )
    assert existing_response.status_code == 201

    bundle_payload = {
        "bundle": {
            "schema_version": 1,
            "product": "Mockingbird",
            "exported_at": "2026-03-17T00:00:00Z",
            "endpoints": [
                {
                    "name": "List accounts imported",
                    "slug": "list-accounts-imported",
                    "method": "GET",
                    "path": "/api/accounts/{accountId}",
                    "category": "accounts",
                    "tags": ["accounts", "imported"],
                    "summary": "Updated from bundle",
                    "description": "Updated by import",
                    "enabled": True,
                    "auth_mode": "none",
                    "request_schema": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "x-builder": {"order": []},
                        "x-request": {
                            "path": {
                                "type": "object",
                                "properties": {
                                    "accountId": {
                                        "type": "string",
                                        "format": "uuid",
                                    }
                                },
                                "required": ["accountId"],
                                "x-builder": {"order": ["accountId"]},
                            }
                        },
                    },
                    "response_schema": {
                        "type": "object",
                        "properties": {
                            "status": {
                                "type": "string",
                                "x-mock": {"mode": "fixed", "value": "imported", "options": {}},
                            }
                        },
                        "required": ["status"],
                        "x-builder": {"order": ["status"]},
                        "x-mock": {"mode": "generate"},
                    },
                    "success_status_code": 200,
                    "error_rate": 0.0,
                    "latency_min_ms": 0,
                    "latency_max_ms": 0,
                    "seed_key": "accounts-bundle",
                },
                {
                    "name": "Create audit log",
                    "slug": "create-audit-log",
                    "method": "POST",
                    "path": "/api/audit-logs",
                    "category": "audit",
                    "tags": ["audit"],
                    "summary": "Create an audit log entry",
                    "description": "Imported create route",
                    "enabled": False,
                    "auth_mode": "none",
                    "request_schema": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "minLength": 3,
                            }
                        },
                        "required": ["message"],
                        "x-builder": {"order": ["message"]},
                    },
                    "response_schema": {
                        "type": "object",
                        "properties": {
                            "ok": {
                                "type": "boolean",
                                "x-mock": {"mode": "fixed", "value": True, "options": {}},
                            }
                        },
                        "required": ["ok"],
                        "x-builder": {"order": ["ok"]},
                        "x-mock": {"mode": "generate"},
                    },
                    "success_status_code": 201,
                    "error_rate": 0.0,
                    "latency_min_ms": 10,
                    "latency_max_ms": 25,
                    "seed_key": None,
                },
            ],
        },
        "mode": "upsert",
        "dry_run": True,
        "confirm_replace_all": False,
    }

    dry_run_response = client.post("/api/admin/endpoints/import", json=bundle_payload, headers=headers)
    assert dry_run_response.status_code == 200
    assert dry_run_response.json() == {
        "dry_run": True,
        "applied": False,
        "has_errors": False,
        "mode": "upsert",
        "summary": {
            "endpoint_count": 2,
            "create_count": 1,
            "update_count": 1,
            "delete_count": 0,
            "skip_count": 0,
            "error_count": 0,
        },
        "operations": [
            {
                "action": "update",
                "name": "List accounts imported",
                "method": "GET",
                "path": "/api/accounts/{accountId}",
                "detail": None,
            },
            {
                "action": "create",
                "name": "Create audit log",
                "method": "POST",
                "path": "/api/audit-logs",
                "detail": None,
            },
        ],
    }

    list_after_dry_run = client.get("/api/admin/endpoints", headers=headers)
    assert list_after_dry_run.status_code == 200
    assert [endpoint["name"] for endpoint in list_after_dry_run.json()] == ["List accounts"]

    apply_response = client.post(
        "/api/admin/endpoints/import",
        json={**bundle_payload, "dry_run": False},
        headers=headers,
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["applied"] is True

    list_after_import = client.get("/api/admin/endpoints", headers=headers)
    assert list_after_import.status_code == 200
    imported_endpoints = sorted(list_after_import.json(), key=lambda endpoint: (endpoint["path"], endpoint["method"]))
    assert [endpoint["name"] for endpoint in imported_endpoints] == [
        "List accounts imported",
        "Create audit log",
    ]
    assert imported_endpoints[0]["request_schema"]["x-request"]["path"]["properties"]["accountId"]["format"] == "uuid"
    assert imported_endpoints[0]["slug"] == "list-accounts-imported"
    assert imported_endpoints[1]["success_status_code"] == 201
    assert imported_endpoints[1]["enabled"] is False


def test_admin_endpoint_import_replace_all_requires_confirmation_and_deletes_missing_routes(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    for name, path in (
        ("List users", "/api/users"),
        ("List invoices", "/api/invoices"),
    ):
        create_response = client.post(
            "/api/admin/endpoints",
            json={
                "name": name,
                "method": "GET",
                "path": path,
                "category": "testing",
                "tags": [],
                "summary": name,
                "description": "",
                "enabled": True,
                "auth_mode": "none",
                "request_schema": {},
                "response_schema": {
                    "type": "object",
                    "properties": {
                        "ok": {
                            "type": "boolean",
                            "x-mock": {"mode": "fixed", "value": True, "options": {}},
                        }
                    },
                    "required": ["ok"],
                    "x-builder": {"order": ["ok"]},
                    "x-mock": {"mode": "generate"},
                },
                "success_status_code": 200,
                "error_rate": 0.0,
                "latency_min_ms": 0,
                "latency_max_ms": 0,
                "seed_key": None,
            },
            headers=headers,
        )
        assert create_response.status_code == 201

    replace_bundle = {
        "bundle": {
            "schema_version": 1,
            "product": "Mockingbird",
            "exported_at": "2026-03-17T00:00:00Z",
            "endpoints": [
                {
                    "name": "List devices",
                    "slug": "list-devices",
                    "method": "GET",
                    "path": "/api/devices",
                    "category": "devices",
                    "tags": ["devices"],
                    "summary": "List devices",
                    "description": "Replace-all import",
                    "enabled": True,
                    "auth_mode": "none",
                    "request_schema": {},
                    "response_schema": {
                        "type": "object",
                        "properties": {
                            "ok": {
                                "type": "boolean",
                                "x-mock": {"mode": "fixed", "value": True, "options": {}},
                            }
                        },
                        "required": ["ok"],
                        "x-builder": {"order": ["ok"]},
                        "x-mock": {"mode": "generate"},
                    },
                    "success_status_code": 200,
                    "error_rate": 0.0,
                    "latency_min_ms": 0,
                    "latency_max_ms": 0,
                    "seed_key": None,
                }
            ],
        },
        "mode": "replace_all",
        "dry_run": False,
        "confirm_replace_all": False,
    }

    blocked_replace_response = client.post("/api/admin/endpoints/import", json=replace_bundle, headers=headers)
    assert blocked_replace_response.status_code == 200
    assert blocked_replace_response.json()["applied"] is False
    assert blocked_replace_response.json()["has_errors"] is True
    assert blocked_replace_response.json()["summary"]["delete_count"] == 2
    assert blocked_replace_response.json()["summary"]["error_count"] == 1

    unchanged_list = client.get("/api/admin/endpoints", headers=headers)
    assert unchanged_list.status_code == 200
    assert sorted(endpoint["path"] for endpoint in unchanged_list.json()) == ["/api/invoices", "/api/users"]

    confirmed_replace_response = client.post(
        "/api/admin/endpoints/import",
        json={**replace_bundle, "confirm_replace_all": True},
        headers=headers,
    )
    assert confirmed_replace_response.status_code == 200
    assert confirmed_replace_response.json()["applied"] is True
    assert confirmed_replace_response.json()["summary"] == {
        "endpoint_count": 1,
        "create_count": 1,
        "update_count": 0,
        "delete_count": 2,
        "skip_count": 0,
        "error_count": 0,
    }

    replaced_list = client.get("/api/admin/endpoints", headers=headers)
    assert replaced_list.status_code == 200
    assert len(replaced_list.json()) == 1
    replaced_endpoint = replaced_list.json()[0]
    assert replaced_endpoint["name"] == "List devices"
    assert replaced_endpoint["slug"] == "list-devices"
    assert replaced_endpoint["method"] == "GET"
    assert replaced_endpoint["path"] == "/api/devices"
    assert replaced_endpoint["category"] == "devices"
    assert replaced_endpoint["tags"] == ["devices"]
    assert replaced_endpoint["summary"] == "List devices"
    assert replaced_endpoint["description"] == "Replace-all import"
    assert replaced_endpoint["enabled"] is True
    assert replaced_endpoint["auth_mode"] == "none"
    assert replaced_endpoint["request_schema"] == {
        "type": "object",
        "properties": {},
        "required": [],
        "x-builder": {"order": []},
    }
    assert replaced_endpoint["response_schema"]["type"] == "object"
    assert replaced_endpoint["response_schema"]["required"] == ["ok"]
    assert replaced_endpoint["response_schema"]["x-builder"] == {"order": ["ok"]}
    assert replaced_endpoint["response_schema"]["x-mock"]["mode"] == "generate"
    assert replaced_endpoint["response_schema"]["properties"]["ok"] == {
        "type": "boolean",
        "x-mock": {"mode": "fixed", "value": True, "options": {}},
    }
    assert replaced_endpoint["success_status_code"] == 200
    assert replaced_endpoint["error_rate"] == 0.0
    assert replaced_endpoint["latency_min_ms"] == 0
    assert replaced_endpoint["latency_max_ms"] == 0
    assert replaced_endpoint["seed_key"] is None
    assert replaced_endpoint["created_at"]
    assert replaced_endpoint["updated_at"]


def test_admin_endpoint_import_replace_all_deletes_runtime_history_for_removed_routes(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json=_endpoint_payload(name="Replace me", path="/api/replace-me"),
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint = create_response.json()

    update_response = client.put(
        f"/api/admin/endpoints/{endpoint['id']}/implementation/current",
        json={"flow_definition": _live_route_flow_definition()},
        headers=headers,
    )
    assert update_response.status_code == 200

    publish_response = client.post(
        f"/api/admin/endpoints/{endpoint['id']}/deployments/publish",
        json={"environment": "production"},
        headers=headers,
    )
    assert publish_response.status_code == 201

    live_response = client.get("/api/replace-me")
    assert live_response.status_code == 200
    assert live_response.json() == {"status": "live"}

    executions_response = client.get(
        f"/api/admin/executions?endpoint_id={endpoint['id']}&limit=5",
        headers=headers,
    )
    assert executions_response.status_code == 200
    execution_id = executions_response.json()[0]["id"]

    replace_all_response = client.post(
        "/api/admin/endpoints/import",
        json={
            "bundle": {
                "schema_version": 1,
                "product": "Mockingbird",
                "exported_at": "2026-03-19T00:00:00Z",
                "endpoints": [
                    {
                        **_endpoint_payload(name="Replacement route", path="/api/replacement-route"),
                        "slug": "replacement-route",
                    }
                ],
            },
            "mode": "replace_all",
            "dry_run": False,
            "confirm_replace_all": True,
        },
        headers=headers,
    )
    assert replace_all_response.status_code == 200
    assert replace_all_response.json()["applied"] is True
    assert replace_all_response.json()["summary"]["delete_count"] == 1

    with Session(engine) as session:
        assert session.get(EndpointDefinition, endpoint["id"]) is None
        assert session.execute(
            select(RouteImplementation).where(RouteImplementation.route_id == endpoint["id"])
        ).scalars().all() == []
        assert session.execute(
            select(RouteDeployment).where(RouteDeployment.route_id == endpoint["id"])
        ).scalars().all() == []
        assert session.execute(
            select(ExecutionRun).where(ExecutionRun.route_id == endpoint["id"])
        ).scalars().all() == []
        assert session.execute(
            select(ExecutionStep).where(ExecutionStep.run_id == execution_id)
        ).scalars().all() == []


def test_admin_endpoint_import_plans_against_catalogs_beyond_the_first_thousand_rows(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    with Session(engine) as session:
        session.add_all(
            [
                EndpointDefinition(
                    name=f"Bulk route {index}",
                    slug=f"bulk-route-{index}",
                    method="GET",
                    path=f"/api/bulk/{index}",
                    category="bulk",
                    tags=[],
                    summary=f"Bulk route {index}",
                    description="",
                    enabled=True,
                    auth_mode="none",
                    request_schema={},
                    response_schema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "x-builder": {"order": []},
                        "x-mock": {"mode": "generate"},
                    },
                    success_status_code=200,
                    error_rate=0.0,
                    latency_min_ms=0,
                    latency_max_ms=0,
                    seed_key=None,
                )
                for index in range(1001)
            ]
        )
        session.commit()

    bundle = {
        "bundle": {
            "schema_version": 1,
            "product": "Mockingbird",
            "exported_at": "2026-03-17T00:00:00Z",
            "endpoints": [
                {
                    "name": "Bulk route 1000 updated",
                    "slug": "bulk-route-1000-updated",
                    "method": "GET",
                    "path": "/api/bulk/1000",
                    "category": "bulk",
                    "tags": ["imported"],
                    "summary": "Bulk route 1000",
                    "description": "Updated from import planning.",
                    "enabled": True,
                    "auth_mode": "none",
                    "request_schema": {},
                    "response_schema": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "x-builder": {"order": []},
                        "x-mock": {"mode": "generate"},
                    },
                    "success_status_code": 200,
                    "error_rate": 0.0,
                    "latency_min_ms": 0,
                    "latency_max_ms": 0,
                    "seed_key": None,
                }
            ],
        },
        "dry_run": True,
        "mode": "upsert",
        "confirm_replace_all": False,
    }

    upsert_response = client.post("/api/admin/endpoints/import", json=bundle, headers=headers)
    assert upsert_response.status_code == 200
    assert upsert_response.json()["summary"] == {
        "endpoint_count": 1,
        "create_count": 0,
        "update_count": 1,
        "delete_count": 0,
        "skip_count": 0,
        "error_count": 0,
    }
    assert upsert_response.json()["operations"] == [
        {
            "action": "update",
            "name": "Bulk route 1000 updated",
            "method": "GET",
            "path": "/api/bulk/1000",
            "detail": None,
        }
    ]

    replace_all_response = client.post(
        "/api/admin/endpoints/import",
        json={**bundle, "mode": "replace_all"},
        headers=headers,
    )
    assert replace_all_response.status_code == 200
    assert replace_all_response.json()["summary"] == {
        "endpoint_count": 1,
        "create_count": 0,
        "update_count": 1,
        "delete_count": 1000,
        "skip_count": 0,
        "error_count": 0,
    }


def test_openapi_emits_request_parameters_from_request_contract(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json={
            "name": "Create item",
            "method": "POST",
            "path": "/api/items/{itemId}",
            "category": "inventory",
            "tags": ["inventory"],
            "summary": "Create an inventory item",
            "description": "Exercises body, path, and query request inputs.",
            "enabled": True,
            "auth_mode": "none",
            "request_schema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "minLength": 3,
                    }
                },
                "required": ["name"],
                "x-builder": {"order": ["name"]},
                "x-request": {
                    "path": {
                        "type": "object",
                        "properties": {
                            "itemId": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "Numeric item identifier",
                            }
                        },
                        "required": ["itemId"],
                        "x-builder": {"order": ["itemId"]},
                    },
                    "query": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "Maximum result size",
                            },
                            "state": {
                                "type": "string",
                                "enum": ["active", "archived"],
                                "description": "Optional status filter",
                            },
                        },
                        "required": ["limit"],
                        "x-builder": {"order": ["limit", "state"]},
                    },
                },
            },
            "response_schema": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "x-mock": {"mode": "generate", "type": "id", "options": {}},
                    }
                },
                "required": ["id"],
                "x-builder": {"order": ["id"]},
                "x-mock": {"mode": "generate"},
            },
            "success_status_code": 201,
            "error_rate": 0.0,
            "latency_min_ms": 0,
            "latency_max_ms": 0,
            "seed_key": None,
        },
        headers=headers,
    )
    assert create_response.status_code == 201

    openapi = client.get("/openapi.json").json()
    operation = openapi["paths"]["/api/items/{itemId}"]["post"]

    assert operation["parameters"] == [
        {
            "in": "path",
            "name": "itemId",
            "required": True,
            "description": "Numeric item identifier",
            "schema": {
                "type": "integer",
                "minimum": 1,
            },
        },
        {
            "in": "query",
            "name": "limit",
            "required": True,
            "description": "Maximum result size",
            "schema": {
                "type": "integer",
                "minimum": 1,
            },
        },
        {
            "in": "query",
            "name": "state",
            "required": False,
            "description": "Optional status filter",
            "schema": {
                "type": "string",
                "enum": ["active", "archived"],
            },
        },
    ]

    request_body_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert request_body_schema == {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "minLength": 3,
            }
        },
        "required": ["name"],
    }


def test_updating_route_path_resyncs_request_path_parameter_contract(empty_db):
    client = TestClient(app)
    headers = _login_headers(client)

    create_response = client.post(
        "/api/admin/endpoints",
        json={
            "name": "Inspect device",
            "method": "GET",
            "path": "/api/devices/{deviceId}",
            "category": "devices",
            "tags": ["devices"],
            "summary": "Inspect a device",
            "description": "Checks path parameter normalization.",
            "enabled": True,
            "auth_mode": "none",
            "request_schema": {
                "type": "object",
                "properties": {},
                "required": [],
                "x-builder": {"order": []},
                "x-request": {
                    "path": {
                        "type": "object",
                        "properties": {
                            "deviceId": {
                                "type": "integer",
                                "minimum": 1,
                            }
                        },
                        "required": ["deviceId"],
                        "x-builder": {"order": ["deviceId"]},
                    }
                },
            },
            "response_schema": {
                "type": "object",
                "properties": {
                    "ok": {
                        "type": "boolean",
                        "x-mock": {"mode": "fixed", "value": True, "options": {}},
                    }
                },
                "required": ["ok"],
                "x-builder": {"order": ["ok"]},
                "x-mock": {"mode": "generate"},
            },
            "success_status_code": 200,
            "error_rate": 0.0,
            "latency_min_ms": 0,
            "latency_max_ms": 0,
            "seed_key": None,
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    endpoint_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/admin/endpoints/{endpoint_id}",
        json={
            "path": "/api/devices/{serialNumber}",
        },
        headers=headers,
    )
    assert update_response.status_code == 200

    request_path_schema = update_response.json()["request_schema"]["x-request"]["path"]
    assert request_path_schema["required"] == ["serialNumber"]
    assert request_path_schema["x-builder"]["order"] == ["serialNumber"]
    assert list(request_path_schema["properties"]) == ["serialNumber"]
    assert request_path_schema["properties"]["serialNumber"]["type"] == "string"


def test_legacy_rows_migrate_to_unified_response_schema():
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    legacy_engine = create_engine(f"sqlite:///{TEST_DB_PATH}")
    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE endpointdefinition (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    slug VARCHAR NOT NULL,
                    method VARCHAR NOT NULL,
                    path VARCHAR NOT NULL,
                    category VARCHAR,
                    tags JSON,
                    summary VARCHAR,
                    description VARCHAR,
                    enabled BOOLEAN NOT NULL,
                    auth_mode VARCHAR NOT NULL,
                    request_schema JSON,
                    response_schema JSON,
                    example_template JSON,
                    response_mode VARCHAR NOT NULL,
                    success_status_code INTEGER NOT NULL,
                    error_rate FLOAT NOT NULL,
                    latency_min_ms INTEGER NOT NULL,
                    latency_max_ms INTEGER NOT NULL,
                    seed_key VARCHAR,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO endpointdefinition (
                    id, name, slug, method, path, category, tags, summary, description, enabled, auth_mode,
                    request_schema, response_schema, example_template, response_mode, success_status_code,
                    error_rate, latency_min_ms, latency_max_ms, seed_key, created_at, updated_at
                ) VALUES (
                    1, 'Legacy Endpoint', 'legacy-endpoint', 'GET', '/api/legacy', 'legacy', :tags, 'Legacy',
                    'Migrated from old contract', 1, 'none', :request_schema, :response_schema, :example_template,
                    'fixed', 200, 0, 0, 0, NULL, '2026-03-14 00:00:00', '2026-03-14 00:00:00'
                )
                """
            ),
            {
                "tags": json.dumps(["legacy"]),
                "request_schema": json.dumps({}),
                "response_schema": json.dumps(
                    {
                        "type": "object",
                        "properties": {"message": {"type": "string"}},
                    }
                ),
                "example_template": json.dumps({"message": "Legacy hello"}),
            },
        )

    create_db_and_tables()

    with Session(engine) as session:
        endpoint = session.execute(select(EndpointDefinition)).scalars().one()
        assert endpoint.response_schema["x-mock"]["mode"] == "fixed"
        assert endpoint.response_schema["x-mock"]["value"] == {"message": "Legacy hello"}
        assert endpoint.request_schema == {}
