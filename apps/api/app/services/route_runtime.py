from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urljoin

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import delete, desc
from sqlmodel import Session, select

from app.models import (
    Connection,
    ConnectionType,
    EndpointDefinition,
    ExecutionRun,
    ExecutionStep,
    RouteDeployment,
    RouteImplementation,
)
from app.schemas import (
    ConnectionCreate,
    ExecutionRunDetail,
    ExecutionRunRead,
    ExecutionStepRead,
    RouteImplementationRead,
    RouteImplementationUpsert,
)
from app.services.schema_contract import extract_request_body_schema, extract_request_parameter_schemas
from app.time_utils import utc_now


BODY_METHODS = {"POST", "PUT", "PATCH"}
HTTP_METHODS = {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}
SUPPORTED_NODE_TYPES = {
    "api_trigger",
    "validate_request",
    "transform",
    "if_condition",
    "switch",
    "http_request",
    "postgres_query",
    "set_response",
    "error_response",
}
PATH_PARAMETER_PATTERN = re.compile(r"\{([^/}]+)\}")
TEMPLATE_EXPRESSION_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
TRACE_MAX_DEPTH = 4
TRACE_MAX_ITEMS = 20
TRACE_MAX_STRING_LENGTH = 280
IF_OPERATORS = {
    "contains",
    "equals",
    "exists",
    "falsy",
    "greater_than",
    "greater_than_or_equal",
    "is_empty",
    "is_not_empty",
    "less_than",
    "less_than_or_equal",
    "not_equals",
    "not_exists",
    "truthy",
}


@dataclass(slots=True)
class ExecutionStepResult:
    node_id: str
    node_type: str
    order_index: int
    status: str
    input_data: dict[str, Any]
    output_data: dict[str, Any] | None
    error_message: str | None = None


@dataclass(slots=True)
class ExecutionResult:
    status_code: int
    body: Any
    status: str
    steps: list[ExecutionStepResult]
    error_message: str | None = None


@dataclass(slots=True)
class RouteExecutionError(Exception):
    public_message: str
    error_message: str
    status_code: int = 500

    def __str__(self) -> str:
        return self.error_message


@dataclass(slots=True)
class CompiledDeployedRoute:
    route_id: int
    route_name: str
    route_method: str
    route_path: str
    route_request_schema: dict[str, Any] | None
    route_success_status_code: int
    implementation_id: int
    deployment_id: int
    deployment_environment: str
    regex: re.Pattern[str]
    parameter_names: list[str]
    flow: "CompiledFlowDefinition"


@dataclass(slots=True)
class CompiledFlowEdge:
    edge_id: str
    source: str
    target: str
    extra: dict[str, Any]

    @property
    def branch(self) -> str:
        return str(self.extra.get("branch") or "").strip().lower()

    @property
    def case_value(self) -> Any:
        return self.extra.get("case_value")


@dataclass(slots=True)
class CompiledFlowDefinition:
    nodes_by_id: dict[str, dict[str, Any]]
    outgoing_edges: dict[str, list[CompiledFlowEdge]]
    incoming_edges: dict[str, list[CompiledFlowEdge]]
    trigger_node_id: str
    response_node_id: str
    error_node: dict[str, Any] | None


@dataclass(slots=True)
class MatchedDeployedRoute:
    compiled_route: CompiledDeployedRoute
    path_parameters: dict[str, str]


_compiled_route_cache: list[CompiledDeployedRoute] | None = None


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


def build_default_flow_definition(route: EndpointDefinition) -> dict[str, Any]:
    status_code = int(route.success_status_code or 200)
    return {
        "schema_version": 1,
        "nodes": [
            {
                "id": "trigger",
                "type": "api_trigger",
                "name": "API Trigger",
                "config": {},
            },
            {
                "id": "validate",
                "type": "validate_request",
                "name": "Validate Request",
                "config": {
                    "body_mode": "contract",
                    "parameters_mode": "contract",
                },
            },
            {
                "id": "transform",
                "type": "transform",
                "name": "Transform",
                "config": {
                    "output": {
                        "route": {
                            "name": {"$ref": "route.name"},
                            "method": {"$ref": "route.method"},
                            "path": {"$ref": "route.path"},
                        },
                        "request": {
                            "path": {"$ref": "request.path"},
                            "query": {"$ref": "request.query"},
                            "body": {"$ref": "request.body"},
                        },
                        "message": "Replace this starter flow in the Flow tab before deploying to production.",
                    },
                },
            },
            {
                "id": "response",
                "type": "set_response",
                "name": "Set Response",
                "config": {
                    "status_code": status_code,
                    "body": {"$ref": "state.transform"},
                },
            },
            {
                "id": "error",
                "type": "error_response",
                "name": "Error Response",
                "config": {
                    "status_code": 400,
                    "body": {
                        "error": "Request validation failed.",
                        "details": {"$ref": "errors"},
                    },
                },
            },
        ],
        "edges": [
            {"source": "trigger", "target": "validate"},
            {"source": "validate", "target": "transform"},
            {"source": "transform", "target": "response"},
        ],
    }


def _edge_extra(raw_edge: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in raw_edge.items()
        if key not in {"id", "source", "target"}
    }


def _reachable_node_ids(
    start_node_id: str,
    adjacency: dict[str, list[CompiledFlowEdge]],
    *,
    reverse: bool = False,
) -> set[str]:
    visited: set[str] = set()
    pending = [start_node_id]

    while pending:
        node_id = pending.pop(0)
        if node_id in visited:
            continue

        visited.add(node_id)
        next_edges = adjacency.get(node_id, [])
        for edge in next_edges:
            pending.append(edge.source if reverse else edge.target)

    return visited


def _validate_if_condition_edges(node: dict[str, Any], outgoing_edges: list[CompiledFlowEdge]) -> None:
    branches = {edge.branch for edge in outgoing_edges}
    if branches != {"true", "false"}:
        raise ValueError(
            f"if_condition node '{node['id']}' requires one 'true' branch edge and one 'false' branch edge."
        )


def _validate_switch_edges(node: dict[str, Any], outgoing_edges: list[CompiledFlowEdge]) -> None:
    default_count = 0
    case_values: set[str] = set()

    for edge in outgoing_edges:
        if edge.branch == "default":
            default_count += 1
            continue
        if edge.branch != "case":
            raise ValueError(
                f"switch node '{node['id']}' requires each outgoing edge to be marked as 'case' or 'default'."
            )

        case_value = edge.case_value
        case_key = json.dumps(case_value, sort_keys=True, default=str)
        if case_value in {None, ""}:
            raise ValueError(f"switch node '{node['id']}' requires every case edge to define case_value.")
        if case_key in case_values:
            raise ValueError(f"switch node '{node['id']}' cannot repeat case_value entries.")
        case_values.add(case_key)

    if default_count != 1:
        raise ValueError(f"switch node '{node['id']}' requires exactly one default edge.")
    if not case_values:
        raise ValueError(f"switch node '{node['id']}' requires at least one case edge.")


def _validate_flow_definition(flow_definition: dict[str, Any]) -> CompiledFlowDefinition:
    if not isinstance(flow_definition, dict):
        raise ValueError("flow_definition must be an object.")

    raw_nodes = flow_definition.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("flow_definition must include a non-empty nodes array.")

    edges = flow_definition.get("edges", [])
    if not isinstance(edges, list):
        raise ValueError("flow_definition edges must be an array.")

    nodes_by_id: dict[str, dict[str, Any]] = {}
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            raise ValueError("Each flow node must be an object.")

        node_id = str(raw_node.get("id") or "").strip()
        node_type = str(raw_node.get("type") or "").strip()
        if not node_id:
            raise ValueError("Each flow node requires an id.")
        if node_id in nodes_by_id:
            raise ValueError(f"Duplicate flow node id '{node_id}'.")
        if node_type not in SUPPORTED_NODE_TYPES:
            raise ValueError(f"Unsupported flow node type '{node_type}'.")

        node_config = raw_node.get("config", {}) if isinstance(raw_node.get("config"), dict) else {}
        _validate_node_config(node_type, node_config)

        nodes_by_id[node_id] = {
            "id": node_id,
            "type": node_type,
            "name": str(raw_node.get("name") or node_id),
            "config": node_config,
        }

    trigger_nodes = [node for node in nodes_by_id.values() if node["type"] == "api_trigger"]
    response_nodes = [node for node in nodes_by_id.values() if node["type"] == "set_response"]
    error_nodes = [node for node in nodes_by_id.values() if node["type"] == "error_response"]

    if len(trigger_nodes) != 1:
        raise ValueError("flow_definition requires exactly one api_trigger node.")
    if len(response_nodes) != 1:
        raise ValueError("flow_definition requires exactly one set_response node.")
    if len(error_nodes) > 1:
        raise ValueError("flow_definition allows at most one error_response node.")

    outgoing_edges = {node_id: [] for node_id in nodes_by_id}
    incoming_edges = {node_id: [] for node_id in nodes_by_id}
    for raw_edge in edges:
        if not isinstance(raw_edge, dict):
            raise ValueError("Each flow edge must be an object.")
        source = str(raw_edge.get("source") or "").strip()
        target = str(raw_edge.get("target") or "").strip()
        if source not in nodes_by_id or target not in nodes_by_id:
            raise ValueError("Flow edges must connect existing node ids.")
        edge = CompiledFlowEdge(
            edge_id=str(raw_edge.get("id") or f"{source}->{target}"),
            source=source,
            target=target,
            extra=_edge_extra(raw_edge),
        )
        outgoing_edges[source].append(edge)
        incoming_edges[target].append(edge)

    connected_error_node_ids = [
        node_id
        for node_id, node in nodes_by_id.items()
        if node["type"] == "error_response" and incoming_edges[node_id]
    ]
    main_node_ids = [
        node_id
        for node_id, node in nodes_by_id.items()
        if node["type"] != "error_response" or node_id in connected_error_node_ids
    ]
    indegree = {node_id: 0 for node_id in main_node_ids}
    for node_id in main_node_ids:
        for edge in outgoing_edges[node_id]:
            if edge.target in indegree:
                indegree[edge.target] += 1

    ordered_ids = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited_count = 0
    while ordered_ids:
        node_id = ordered_ids.pop(0)
        visited_count += 1
        for edge in outgoing_edges[node_id]:
            if edge.target not in indegree:
                continue
            indegree[edge.target] -= 1
            if indegree[edge.target] == 0:
                ordered_ids.append(edge.target)

    if visited_count != len(main_node_ids):
        raise ValueError("flow_definition contains a cycle.")

    for node_id, node in nodes_by_id.items():
        incoming_count = len(incoming_edges[node_id])
        outgoing_count = len(outgoing_edges[node_id])
        node_type = str(node["type"])

        if node_type == "api_trigger":
            if incoming_count != 0:
                raise ValueError("api_trigger cannot receive incoming edges.")
            if outgoing_count != 1:
                raise ValueError("api_trigger must connect to exactly one next node.")
            continue

        if node_type == "error_response":
            if outgoing_count != 0:
                raise ValueError("error_response is a terminal node and cannot connect downstream.")
            continue

        if node_type == "set_response":
            if incoming_count < 1:
                raise ValueError("set_response must receive at least one incoming edge.")
            if outgoing_count != 0:
                raise ValueError("set_response cannot connect to downstream nodes.")
            continue

        if incoming_count < 1:
            raise ValueError(f"{node_type} node '{node_id}' must receive at least one incoming edge.")

        if node_type == "if_condition":
            if outgoing_count != 2:
                raise ValueError("if_condition nodes require exactly two outgoing edges.")
            _validate_if_condition_edges(node, outgoing_edges[node_id])
            continue

        if node_type == "switch":
            if outgoing_count < 2:
                raise ValueError("switch nodes require at least two outgoing edges.")
            _validate_switch_edges(node, outgoing_edges[node_id])
            continue

        if outgoing_count != 1:
            raise ValueError(f"{node_type} node '{node_id}' must connect to exactly one next node.")

    trigger_node_id = str(trigger_nodes[0]["id"])
    response_node_id = str(response_nodes[0]["id"])
    reachable_from_trigger = _reachable_node_ids(trigger_node_id, outgoing_edges)
    if reachable_from_trigger != set(main_node_ids):
        raise ValueError("Connect every main node into the reachable path from api_trigger.")

    terminal_node_ids = [response_node_id, *connected_error_node_ids]
    reachable_to_terminal: set[str] = set()
    for terminal_node_id in terminal_node_ids:
        reachable_to_terminal.update(_reachable_node_ids(terminal_node_id, incoming_edges, reverse=True))

    if reachable_to_terminal != set(main_node_ids):
        raise ValueError("Every main node must eventually lead to set_response or error_response.")

    return CompiledFlowDefinition(
        nodes_by_id=nodes_by_id,
        outgoing_edges=outgoing_edges,
        incoming_edges=incoming_edges,
        trigger_node_id=trigger_node_id,
        response_node_id=response_node_id,
        error_node=error_nodes[0] if error_nodes else None,
    )


def _lookup_ref(ref: str, context: dict[str, Any]) -> Any:
    parts = [part for part in ref.split(".") if part]
    current: Any = context
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
            continue
        if isinstance(current, list):
            try:
                index = int(part)
            except (TypeError, ValueError):
                return None
            if index < 0 or index >= len(current):
                return None
            current = current[index]
            continue
        return None
    return current


def _render_template(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        if set(value.keys()) == {"$ref"}:
            return _lookup_ref(str(value["$ref"]), context)
        return {
            key: _render_template(child, context)
            for key, child in value.items()
        }

    if isinstance(value, list):
        return [_render_template(child, context) for child in value]

    if isinstance(value, str) and "{{" in value and "}}" in value:
        return _render_string_template(value, context)

    return value


def _stringify_template_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), default=str)
    return str(value)


def _render_string_template(template: str, context: dict[str, Any]) -> str:
    return TEMPLATE_EXPRESSION_PATTERN.sub(
        lambda match: _stringify_template_value(_lookup_ref(match.group(1).strip(), context)),
        template,
    )


def _render_connector_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        if set(value.keys()) == {"$ref"}:
            return _lookup_ref(str(value["$ref"]), context)
        return {
            key: _render_connector_value(child, context)
            for key, child in value.items()
        }

    if isinstance(value, list):
        return [_render_connector_value(child, context) for child in value]

    if isinstance(value, str) and "{{" in value and "}}" in value:
        return _render_string_template(value, context)

    return value


def _sanitize_trace_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= TRACE_MAX_DEPTH:
        return "<truncated>"

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        items = list(value.items())
        for key, child in items[:TRACE_MAX_ITEMS]:
            result[str(key)] = _sanitize_trace_value(child, depth=depth + 1)
        if len(items) > TRACE_MAX_ITEMS:
            result["__truncated_keys__"] = len(items) - TRACE_MAX_ITEMS
        return result

    if isinstance(value, list):
        items = [_sanitize_trace_value(child, depth=depth + 1) for child in value[:TRACE_MAX_ITEMS]]
        if len(value) > TRACE_MAX_ITEMS:
            items.append(f"<{len(value) - TRACE_MAX_ITEMS} more items>")
        return items

    if isinstance(value, str) and len(value) > TRACE_MAX_STRING_LENGTH:
        return f"{value[:TRACE_MAX_STRING_LENGTH - 3]}..."

    return value


def _coerce_positive_int(raw_value: Any) -> int | None:
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, int):
        return raw_value if raw_value > 0 else None
    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if not stripped:
            return None
        try:
            parsed = int(stripped)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _http_connection_summary(connection: Connection) -> dict[str, Any]:
    connector_type = (
        connection.connector_type.value
        if isinstance(connection.connector_type, ConnectionType)
        else str(connection.connector_type)
    )
    return {
        "id": int(connection.id or 0),
        "name": connection.name,
        "connector_type": connector_type,
    }


def _validate_http_connection_config(config: dict[str, Any]) -> None:
    base_url = str(config.get("base_url") or "").strip()
    if not base_url:
        raise ValueError("HTTP connections require config.base_url.")


def _postgres_connect_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    dsn = str(config.get("dsn") or config.get("database_url") or config.get("url") or "").strip()
    if dsn:
        return {"dsn": dsn}

    host = str(config.get("host") or "").strip()
    database = str(config.get("database") or config.get("dbname") or "").strip()
    user = str(config.get("user") or config.get("username") or "").strip()
    if not host or not database or not user:
        raise ValueError("Postgres connections require config.dsn or config.host/config.database/config.user.")

    connect_kwargs: dict[str, Any] = {
        "host": host,
        "dbname": database,
        "user": user,
    }
    if config.get("password") not in {None, ""}:
        connect_kwargs["password"] = str(config["password"])
    if config.get("port") not in {None, ""}:
        port = _coerce_positive_int(config.get("port"))
        if port is None:
            raise ValueError("Postgres connections require a numeric config.port when provided.")
        connect_kwargs["port"] = port
    if config.get("sslmode") not in {None, ""}:
        connect_kwargs["sslmode"] = str(config["sslmode"])
    return connect_kwargs


def _validate_postgres_connection_config(config: dict[str, Any]) -> None:
    _postgres_connect_kwargs(config)


def _validate_connection_payload(payload: ConnectionCreate) -> None:
    config = payload.config if isinstance(payload.config, dict) else {}
    if payload.connector_type == ConnectionType.http:
        _validate_http_connection_config(config)
        return
    if payload.connector_type == ConnectionType.postgres:
        _validate_postgres_connection_config(config)
        return
    raise ValueError(f"Unsupported connection type '{payload.connector_type}'.")


def _validate_http_request_node_config(config: dict[str, Any]) -> None:
    if _coerce_positive_int(config.get("connection_id")) is None:
        raise ValueError("HTTP Request nodes require a numeric connection_id.")

    method = str(config.get("method") or "GET").strip().upper()
    if method not in HTTP_METHODS:
        raise ValueError("HTTP Request nodes require a supported HTTP method.")

    if not str(config.get("path") or "").strip():
        raise ValueError("HTTP Request nodes require a non-empty path.")

    if config.get("headers") is not None and not isinstance(config.get("headers"), dict):
        raise ValueError("HTTP Request node headers must be a JSON object.")

    if config.get("query") is not None and not isinstance(config.get("query"), dict):
        raise ValueError("HTTP Request node query parameters must be a JSON object.")

    if config.get("timeout_ms") is not None and _coerce_positive_int(config.get("timeout_ms")) is None:
        raise ValueError("HTTP Request nodes require timeout_ms to be a positive integer when provided.")


def _validate_if_condition_node_config(config: dict[str, Any]) -> None:
    if "left" not in config:
        raise ValueError("If nodes require a left comparison value.")

    operator = str(config.get("operator") or "").strip().lower()
    if operator not in IF_OPERATORS:
        raise ValueError("If nodes require a supported operator.")

    if operator in {
        "contains",
        "equals",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "not_equals",
    } and "right" not in config:
        raise ValueError(f"If nodes require a right comparison value for the '{operator}' operator.")


def _normalized_sql_lead(sql: str) -> str | None:
    without_block_comments = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    without_comments = re.sub(r"--[^\n]*", " ", without_block_comments)
    stripped = without_comments.strip()
    if not stripped:
        return None
    if ";" in stripped.rstrip(";"):
        return None

    first_token = re.match(r"[A-Za-z]+", stripped)
    return first_token.group(0).lower() if first_token else None


def _validate_postgres_query_node_config(config: dict[str, Any]) -> None:
    if _coerce_positive_int(config.get("connection_id")) is None:
        raise ValueError("Postgres Query nodes require a numeric connection_id.")

    sql = str(config.get("sql") or "").strip()
    lead = _normalized_sql_lead(sql)
    if lead is None:
        raise ValueError("Postgres Query nodes require a single SQL statement.")
    if lead not in {"select", "with"}:
        raise ValueError("Postgres Query nodes only support read-only SELECT or WITH statements.")

    if config.get("parameters") is not None and not isinstance(config.get("parameters"), dict):
        raise ValueError("Postgres Query node parameters must be a JSON object.")


def _validate_switch_node_config(config: dict[str, Any]) -> None:
    if "value" not in config:
        raise ValueError("Switch nodes require a value to evaluate.")


def _validate_node_config(node_type: str, config: dict[str, Any]) -> None:
    if node_type == "if_condition":
        _validate_if_condition_node_config(config)
        return
    if node_type == "switch":
        _validate_switch_node_config(config)
        return
    if node_type == "http_request":
        _validate_http_request_node_config(config)
        return
    if node_type == "postgres_query":
        _validate_postgres_query_node_config(config)


def _resolve_connection(
    session: Session,
    connection_id: int,
    *,
    expected_type: ConnectionType,
    node_label: str,
) -> Connection:
    connection = session.get(Connection, connection_id)
    if connection is None:
        raise RouteExecutionError(
            public_message=f"{node_label} could not resolve its configured connection.",
            error_message=f"{node_label} references missing connection {connection_id}.",
        )
    if not connection.is_active:
        raise RouteExecutionError(
            public_message=f"{node_label} connection is inactive.",
            error_message=f"{node_label} references inactive connection '{connection.name}'.",
        )
    if connection.connector_type != expected_type:
        raise RouteExecutionError(
            public_message=f"{node_label} is bound to the wrong connection type.",
            error_message=(
                f"{node_label} requires a {expected_type.value} connection, but '{connection.name}' is "
                f"{connection.connector_type.value}."
            ),
        )
    return connection


def _coerce_http_header_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), default=str)
    return str(value)


def _normalize_http_mapping(value: Any, *, label: str) -> dict[str, str]:
    if value is None or value == "":
        return {}
    if not isinstance(value, dict):
        raise RouteExecutionError(
            public_message=f"{label} must be a JSON object.",
            error_message=f"{label} rendered as {type(value).__name__}, expected an object.",
        )
    normalized: dict[str, str] = {}
    for key, child in value.items():
        child_value = _coerce_http_header_value(child)
        if child_value == "":
            continue
        normalized[str(key)] = child_value
    return normalized


def _normalize_http_timeout(raw_timeout: Any, *, fallback: int = 10000) -> int:
    timeout_ms = _coerce_positive_int(raw_timeout)
    return timeout_ms if timeout_ms is not None else fallback


def _build_http_url(base_url: str, path: str) -> str:
    if re.match(r"^https?://", path, flags=re.IGNORECASE):
        return path
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))


def _parse_http_response_body(response: httpx.Response) -> Any:
    if not response.content:
        return None

    content_type = response.headers.get("content-type", "").lower()
    if "json" in content_type:
        try:
            return response.json()
        except ValueError:
            pass

    text = response.text
    return text if text else None


def _perform_http_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    query: dict[str, str],
    body: Any,
    timeout_ms: int,
) -> dict[str, Any]:
    with httpx.Client(timeout=max(timeout_ms, 1) / 1000.0) as client:
        response = client.request(
            method=method,
            url=url,
            headers=headers or None,
            params=query or None,
            json=body if body is not None else None,
        )

    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "content_type": response.headers.get("content-type", ""),
        "body": _parse_http_response_body(response),
    }


def _perform_postgres_query(
    *,
    connection_config: dict[str, Any],
    sql: str,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    connect_kwargs = _postgres_connect_kwargs(connection_config)
    dsn = connect_kwargs.pop("dsn", None)
    connection = (
        psycopg2.connect(dsn, cursor_factory=RealDictCursor, **connect_kwargs)
        if dsn is not None
        else psycopg2.connect(cursor_factory=RealDictCursor, **connect_kwargs)
    )
    try:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            rows = cursor.fetchall() if cursor.description is not None else []
            return [dict(row) for row in rows]
    finally:
        connection.close()


def _node_error_result(
    *,
    node_id: str,
    node_type: str,
    order_index: int,
    step_input: dict[str, Any],
    error: RouteExecutionError,
    steps: list[ExecutionStepResult],
) -> ExecutionResult:
    steps.append(
        ExecutionStepResult(
            node_id=node_id,
            node_type=node_type,
            order_index=order_index,
            status="error",
            input_data=_to_json_object(_sanitize_trace_value(step_input)),
            output_data=None,
            error_message=error.error_message,
        )
    )
    return ExecutionResult(
        status_code=error.status_code,
        body={
            "error": error.public_message,
            "details": error.error_message,
        },
        status="error",
        steps=steps,
        error_message=error.error_message,
    )


def _single_next_edge(flow: CompiledFlowDefinition, node_id: str) -> CompiledFlowEdge | None:
    outgoing_edges = flow.outgoing_edges.get(node_id, [])
    return outgoing_edges[0] if len(outgoing_edges) == 1 else None


def _logic_value_is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _logic_values_equal(left: Any, right: Any) -> bool:
    if left == right:
        return True

    if isinstance(left, bool) or isinstance(right, bool):
        return False

    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return _stringify_template_value(left) == _stringify_template_value(right)


def _logic_compare_numbers(left: Any, right: Any) -> tuple[float, float] | None:
    if isinstance(left, bool) or isinstance(right, bool):
        return None

    try:
        return float(left), float(right)
    except (TypeError, ValueError):
        return None


def _evaluate_if_condition(config: dict[str, Any], context: dict[str, Any]) -> tuple[bool, Any, Any, str]:
    left = _render_connector_value(config.get("left"), context)
    right = _render_connector_value(config.get("right"), context) if "right" in config else None
    operator = str(config.get("operator") or "equals").strip().lower()

    if operator == "equals":
        return _logic_values_equal(left, right), left, right, operator
    if operator == "not_equals":
        return not _logic_values_equal(left, right), left, right, operator
    if operator == "exists":
        return left is not None, left, right, operator
    if operator == "not_exists":
        return left is None, left, right, operator
    if operator == "truthy":
        return bool(left), left, right, operator
    if operator == "falsy":
        return not bool(left), left, right, operator
    if operator == "is_empty":
        return _logic_value_is_empty(left), left, right, operator
    if operator == "is_not_empty":
        return not _logic_value_is_empty(left), left, right, operator
    if operator == "contains":
        if isinstance(left, str):
            return _stringify_template_value(right) in left, left, right, operator
        if isinstance(left, (list, tuple, set)):
            return right in left, left, right, operator
        if isinstance(left, dict):
            return str(right) in left, left, right, operator
        return False, left, right, operator

    numeric_pair = _logic_compare_numbers(left, right)
    if numeric_pair is None:
        return False, left, right, operator

    numeric_left, numeric_right = numeric_pair
    if operator == "greater_than":
        return numeric_left > numeric_right, left, right, operator
    if operator == "greater_than_or_equal":
        return numeric_left >= numeric_right, left, right, operator
    if operator == "less_than":
        return numeric_left < numeric_right, left, right, operator
    if operator == "less_than_or_equal":
        return numeric_left <= numeric_right, left, right, operator

    return False, left, right, operator


def _select_if_branch_edge(flow: CompiledFlowDefinition, node_id: str, *, matched: bool) -> CompiledFlowEdge | None:
    branch_name = "true" if matched else "false"
    for edge in flow.outgoing_edges.get(node_id, []):
        if edge.branch == branch_name:
            return edge
    return None


def _select_switch_edge(flow: CompiledFlowDefinition, node_id: str, value: Any) -> tuple[CompiledFlowEdge | None, str]:
    default_edge: CompiledFlowEdge | None = None

    for edge in flow.outgoing_edges.get(node_id, []):
        if edge.branch == "default":
            default_edge = edge
            continue
        if edge.branch == "case" and _logic_values_equal(value, edge.case_value):
            return edge, "case"

    return default_edge, "default"


def _coerce_scalar_value(schema: dict[str, Any], raw_value: Any) -> tuple[Any, str | None]:
    schema_type = str(schema.get("type") or "").lower()
    if not schema_type:
        return raw_value, None

    if schema_type == "string":
        return str(raw_value), None

    if schema_type == "integer":
        try:
            return int(raw_value), None
        except (TypeError, ValueError):
            return raw_value, "must be an integer"

    if schema_type == "number":
        try:
            return float(raw_value), None
        except (TypeError, ValueError):
            return raw_value, "must be a number"

    if schema_type == "boolean":
        if isinstance(raw_value, bool):
            return raw_value, None
        normalized = str(raw_value).strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True, None
        if normalized in {"false", "0", "no"}:
            return False, None
        return raw_value, "must be a boolean"

    return raw_value, None


def _validate_scalar(schema: dict[str, Any], value: Any) -> list[str]:
    errors: list[str] = []
    schema_type = str(schema.get("type") or "").lower()
    if not schema_type:
        return errors

    if schema_type == "string":
        if not isinstance(value, str):
            return ["must be a string"]
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append(f"must be at least {min_length} characters long")
        if isinstance(max_length, int) and len(value) > max_length:
            errors.append(f"must be at most {max_length} characters long")

    elif schema_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return ["must be an integer"]
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"must be >= {minimum}")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append(f"must be <= {maximum}")

    elif schema_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return ["must be a number"]
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"must be >= {minimum}")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append(f"must be <= {maximum}")

    elif schema_type == "boolean":
        if not isinstance(value, bool):
            return ["must be a boolean"]

    if "enum" in schema and value not in schema.get("enum", []):
        errors.append("must match one of the allowed enum values")

    return errors


def _validate_json_schema_like(schema: dict[str, Any], value: Any, path: str = "$") -> list[str]:
    if not isinstance(schema, dict) or not schema:
        return []

    schema_type = str(schema.get("type") or "").lower()
    if not schema_type:
        return []

    if schema_type == "object":
        if not isinstance(value, dict):
            return [f"{path}: must be an object"]

        errors: list[str] = []
        properties = schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required", []) if isinstance(schema.get("required"), list) else []
        for required_key in required:
            if required_key not in value:
                errors.append(f"{path}.{required_key}: is required")

        for key, child_value in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                errors.extend(_validate_json_schema_like(child_schema, child_value, f"{path}.{key}"))
        return errors

    if schema_type == "array":
        if not isinstance(value, list):
            return [f"{path}: must be an array"]

        errors: list[str] = []
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append(f"{path}: must contain at least {min_items} items")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(f"{path}: must contain at most {max_items} items")

        item_schema = schema.get("items") if isinstance(schema.get("items"), dict) else None
        if item_schema:
            for index, item in enumerate(value):
                errors.extend(_validate_json_schema_like(item_schema, item, f"{path}[{index}]"))
        return errors

    scalar_errors = _validate_scalar(schema, value)
    return [f"{path}: {error}" for error in scalar_errors]


def _validate_parameter_values(
    location: str,
    schema_root: dict[str, Any],
    values: dict[str, str],
) -> tuple[list[str], dict[str, Any]]:
    properties = schema_root.get("properties", {}) if isinstance(schema_root.get("properties"), dict) else {}
    required = schema_root.get("required", []) if isinstance(schema_root.get("required"), list) else []
    errors: list[str] = []
    coerced_values: dict[str, Any] = {}

    for required_key in required:
        raw_required_value = values.get(required_key)
        if raw_required_value is None or str(raw_required_value).strip() == "":
            errors.append(f"{location}.{required_key}: is required")

    for key, raw_value in values.items():
        schema = properties.get(key)
        if not isinstance(schema, dict):
            coerced_values[key] = raw_value
            continue

        coerced_value, coercion_error = _coerce_scalar_value(schema, raw_value)
        if coercion_error:
            errors.append(f"{location}.{key}: {coercion_error}")
            coerced_values[key] = raw_value
            continue

        scalar_errors = _validate_scalar(schema, coerced_value)
        if scalar_errors:
            errors.extend(f"{location}.{key}: {error}" for error in scalar_errors)
        coerced_values[key] = coerced_value

    return errors, coerced_values


def _validate_request_contract(
    *,
    method: str,
    request_schema: dict[str, Any] | None,
    path_parameters: dict[str, str],
    query_parameters: dict[str, str],
    request_body: Any,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    request_contract = request_schema or {}
    parameter_schemas = extract_request_parameter_schemas(request_contract)
    body_schema = extract_request_body_schema(request_contract)

    errors: list[str] = []
    path_errors, coerced_path = _validate_parameter_values("path", parameter_schemas["path"], path_parameters)
    query_errors, coerced_query = _validate_parameter_values("query", parameter_schemas["query"], query_parameters)
    errors.extend(path_errors)
    errors.extend(query_errors)

    if method.upper() in BODY_METHODS and body_schema:
        has_structured_body = bool(body_schema.get("properties")) or bool(body_schema.get("required"))
        if request_body is None and has_structured_body:
            errors.append("body: is required")
        elif request_body is not None:
            errors.extend(_validate_json_schema_like(body_schema, request_body, "body"))

    return errors, coerced_path, coerced_query


def _to_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"items": value}
    if value is None:
        return {}
    return {"value": value}


def execute_live_route(
    session: Session,
    compiled_route: CompiledDeployedRoute,
    *,
    path_parameters: dict[str, str],
    query_parameters: dict[str, str],
    request_body: Any,
) -> ExecutionResult:
    context = {
        "route": {
            "id": compiled_route.route_id,
            "name": compiled_route.route_name,
            "method": compiled_route.route_method,
            "path": compiled_route.route_path,
            "success_status_code": compiled_route.route_success_status_code,
        },
        "request": {
            "path": dict(path_parameters),
            "query": dict(query_parameters),
            "body": request_body,
        },
        "state": {},
        "errors": [],
    }
    flow = compiled_route.flow
    steps: list[ExecutionStepResult] = []

    current_node_id: str | None = flow.trigger_node_id
    order_index = 0
    while current_node_id is not None:
        node = flow.nodes_by_id[current_node_id]
        node_type = str(node["type"])
        node_id = str(node["id"])
        step_input = {
            "request": {
                "path": dict(context["request"]["path"]),
                "query": dict(context["request"]["query"]),
                "body_present": context["request"]["body"] is not None,
            },
            "state_keys": list(context["state"].keys()),
        }

        if node_type == "api_trigger":
            output = {
                "route": dict(context["route"]),
                "request": {
                    "path": dict(context["request"]["path"]),
                    "query": dict(context["request"]["query"]),
                    "body_present": context["request"]["body"] is not None,
                },
            }
            steps.append(
                ExecutionStepResult(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    status="success",
                    input_data=step_input,
                    output_data=output,
                )
            )
            context["state"][node_id] = output
            next_edge = _single_next_edge(flow, node_id)
            if next_edge is None:
                return _node_error_result(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    step_input=step_input,
                    error=RouteExecutionError(
                        public_message="API Trigger could not continue the flow.",
                        error_message="api_trigger is missing its next edge.",
                    ),
                    steps=steps,
                )
            current_node_id = next_edge.target
            order_index += 1
            continue

        if node_type == "validate_request":
            errors, coerced_path, coerced_query = _validate_request_contract(
                method=compiled_route.route_method,
                request_schema=compiled_route.route_request_schema,
                path_parameters=context["request"]["path"],
                query_parameters=context["request"]["query"],
                request_body=context["request"]["body"],
            )
            context["request"]["path"] = coerced_path
            context["request"]["query"] = coerced_query
            if errors:
                context["errors"] = errors
                output = {"valid": False, "errors": errors}
                steps.append(
                    ExecutionStepResult(
                        node_id=node_id,
                        node_type=node_type,
                        order_index=order_index,
                        status="validation_error",
                        input_data=step_input,
                        output_data=output,
                        error_message="; ".join(errors),
                    )
                )
                error_node = flow.error_node
                if error_node is not None:
                    error_body = _render_template(error_node.get("config", {}).get("body", {"error": "Request validation failed"}), context)
                    error_status_code = int(error_node.get("config", {}).get("status_code", 400))
                    steps.append(
                        ExecutionStepResult(
                            node_id=str(error_node["id"]),
                            node_type=str(error_node["type"]),
                            order_index=order_index + 1,
                            status="success",
                            input_data={"errors": errors},
                            output_data={"status_code": error_status_code, "body": _to_json_object(error_body)},
                        )
                    )
                    return ExecutionResult(
                        status_code=error_status_code,
                        body=error_body,
                        status="validation_error",
                        steps=steps,
                        error_message="; ".join(errors),
                    )

                return ExecutionResult(
                    status_code=400,
                    body={"error": "Request validation failed", "details": errors},
                    status="validation_error",
                    steps=steps,
                    error_message="; ".join(errors),
                )

            output = {"valid": True}
            steps.append(
                ExecutionStepResult(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    status="success",
                    input_data=step_input,
                    output_data=output,
                )
            )
            context["state"][node_id] = output
            next_edge = _single_next_edge(flow, node_id)
            if next_edge is None:
                return _node_error_result(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    step_input=step_input,
                    error=RouteExecutionError(
                        public_message="Validate Request could not continue the flow.",
                        error_message="validate_request is missing its next edge.",
                    ),
                    steps=steps,
                )
            current_node_id = next_edge.target
            order_index += 1
            continue

        if node_type == "transform":
            output = _render_template(node.get("config", {}).get("output", {}), context)
            context["state"][node_id] = output
            steps.append(
                ExecutionStepResult(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    status="success",
                    input_data=step_input,
                    output_data=_to_json_object(output),
                )
            )
            next_edge = _single_next_edge(flow, node_id)
            if next_edge is None:
                return _node_error_result(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    step_input=step_input,
                    error=RouteExecutionError(
                        public_message="Transform could not continue the flow.",
                        error_message="transform is missing its next edge.",
                    ),
                    steps=steps,
                )
            current_node_id = next_edge.target
            order_index += 1
            continue

        if node_type == "if_condition":
            matched, left, right, operator = _evaluate_if_condition(node.get("config", {}), context)
            branch_edge = _select_if_branch_edge(flow, node_id, matched=matched)
            output = {
                "matched": matched,
                "branch": "true" if matched else "false",
                "operator": operator,
                "left": _sanitize_trace_value(left),
                "right": _sanitize_trace_value(right),
            }
            context["state"][node_id] = output
            steps.append(
                ExecutionStepResult(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    status="success",
                    input_data=step_input,
                    output_data=_to_json_object(output),
                )
            )
            if branch_edge is None:
                return _node_error_result(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    step_input=step_input,
                    error=RouteExecutionError(
                        public_message="If could not find a matching branch.",
                        error_message="if_condition is missing its configured true/false branch edge.",
                    ),
                    steps=steps,
                )
            current_node_id = branch_edge.target
            order_index += 1
            continue

        if node_type == "switch":
            value = _render_connector_value(node.get("config", {}).get("value"), context)
            selected_edge, branch = _select_switch_edge(flow, node_id, value)
            output = {
                "value": _sanitize_trace_value(value),
                "branch": branch,
                "case_value": _sanitize_trace_value(selected_edge.case_value) if selected_edge and branch == "case" else None,
            }
            context["state"][node_id] = output
            steps.append(
                ExecutionStepResult(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    status="success",
                    input_data=step_input,
                    output_data=_to_json_object(output),
                )
            )
            if selected_edge is None:
                return _node_error_result(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    step_input=step_input,
                    error=RouteExecutionError(
                        public_message="Switch could not find a branch.",
                        error_message="switch did not resolve to any case or default edge.",
                    ),
                    steps=steps,
                )
            current_node_id = selected_edge.target
            order_index += 1
            continue

        if node_type == "http_request":
            connector_step_input = dict(step_input)
            try:
                node_config = node.get("config", {})
                connection_id = _coerce_positive_int(node_config.get("connection_id"))
                if connection_id is None:
                    raise RouteExecutionError(
                        public_message="HTTP Request step is missing its connection.",
                        error_message="HTTP Request step requires a numeric connection_id.",
                    )

                connection = _resolve_connection(
                    session,
                    connection_id,
                    expected_type=ConnectionType.http,
                    node_label="HTTP Request",
                )
                connection_config = connection.config if isinstance(connection.config, dict) else {}
                try:
                    _validate_http_connection_config(connection_config)
                except ValueError as error:
                    raise RouteExecutionError(
                        public_message="HTTP Request connection is incomplete.",
                        error_message=str(error),
                    ) from error

                raw_path = _render_connector_value(node_config.get("path", ""), context)
                path = str(raw_path or "").strip()
                if not path:
                    raise RouteExecutionError(
                        public_message="HTTP Request step needs a path.",
                        error_message="HTTP Request step rendered an empty request path.",
                    )

                method = str(node_config.get("method") or "GET").strip().upper()
                if method not in HTTP_METHODS:
                    raise RouteExecutionError(
                        public_message="HTTP Request step has an invalid method.",
                        error_message=f"HTTP Request step rendered unsupported method '{method}'.",
                    )

                connection_headers = _normalize_http_mapping(connection_config.get("headers"), label="HTTP connection headers")
                node_headers = _normalize_http_mapping(
                    _render_connector_value(node_config.get("headers", {}), context),
                    label="HTTP Request node headers",
                )
                query = _normalize_http_mapping(
                    _render_connector_value(node_config.get("query", {}), context),
                    label="HTTP Request query parameters",
                )
                body = _render_connector_value(node_config.get("body"), context) if "body" in node_config else None
                timeout_ms = _normalize_http_timeout(
                    node_config.get("timeout_ms", connection_config.get("timeout_ms")),
                    fallback=10000,
                )
                url = _build_http_url(str(connection_config.get("base_url") or ""), path)
                request_headers = {
                    **connection_headers,
                    **node_headers,
                }

                connector_step_input = {
                    **step_input,
                    "connector": {
                        "connection": _http_connection_summary(connection),
                        "method": method,
                        "url": url,
                        "query": _sanitize_trace_value(query),
                        "body_present": body is not None,
                        "header_keys": sorted(request_headers.keys()),
                    },
                }

                try:
                    response_payload = _perform_http_request(
                        method=method,
                        url=url,
                        headers=request_headers,
                        query=query,
                        body=body,
                        timeout_ms=timeout_ms,
                    )
                except httpx.HTTPError as error:
                    raise RouteExecutionError(
                        public_message="HTTP Request step failed to reach the upstream service.",
                        error_message=str(error),
                        status_code=502,
                    ) from error

                output = {
                    "connection": _http_connection_summary(connection),
                    "request": {
                        "method": method,
                        "url": url,
                        "query": query,
                        "body": body,
                    },
                    "response": {
                        "status_code": int(response_payload["status_code"]),
                        "content_type": str(response_payload.get("content_type") or ""),
                        "headers": dict(response_payload.get("headers") or {}),
                        "body": response_payload.get("body"),
                    },
                }
                context["state"][node_id] = output
                steps.append(
                    ExecutionStepResult(
                        node_id=node_id,
                        node_type=node_type,
                        order_index=order_index,
                        status="success",
                        input_data=_to_json_object(_sanitize_trace_value(connector_step_input)),
                        output_data={
                            "connection": _http_connection_summary(connection),
                            "response": {
                                "status_code": int(response_payload["status_code"]),
                                "content_type": str(response_payload.get("content_type") or ""),
                                "header_keys": sorted((response_payload.get("headers") or {}).keys()),
                                "body": _sanitize_trace_value(response_payload.get("body")),
                            },
                        },
                    )
                )
            except RouteExecutionError as error:
                return _node_error_result(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    step_input=connector_step_input,
                    error=error,
                    steps=steps,
                )
            next_edge = _single_next_edge(flow, node_id)
            if next_edge is None:
                return _node_error_result(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    step_input=connector_step_input,
                    error=RouteExecutionError(
                        public_message="HTTP Request could not continue the flow.",
                        error_message="http_request is missing its next edge.",
                    ),
                    steps=steps,
                )
            current_node_id = next_edge.target
            order_index += 1
            continue

        if node_type == "postgres_query":
            connector_step_input = dict(step_input)
            try:
                node_config = node.get("config", {})
                connection_id = _coerce_positive_int(node_config.get("connection_id"))
                if connection_id is None:
                    raise RouteExecutionError(
                        public_message="Postgres Query step is missing its connection.",
                        error_message="Postgres Query step requires a numeric connection_id.",
                    )

                connection = _resolve_connection(
                    session,
                    connection_id,
                    expected_type=ConnectionType.postgres,
                    node_label="Postgres Query",
                )
                connection_config = connection.config if isinstance(connection.config, dict) else {}
                try:
                    _validate_postgres_connection_config(connection_config)
                except ValueError as error:
                    raise RouteExecutionError(
                        public_message="Postgres connection is incomplete.",
                        error_message=str(error),
                    ) from error

                sql = str(node_config.get("sql") or "").strip()
                lead = _normalized_sql_lead(sql)
                if lead not in {"select", "with"}:
                    raise RouteExecutionError(
                        public_message="Postgres Query only supports read-only statements.",
                        error_message="Postgres Query only supports a single SELECT or WITH statement.",
                    )

                rendered_parameters = _render_connector_value(node_config.get("parameters", {}), context)
                if rendered_parameters is None or rendered_parameters == "":
                    rendered_parameters = {}
                if not isinstance(rendered_parameters, dict):
                    raise RouteExecutionError(
                        public_message="Postgres Query parameters must be a JSON object.",
                        error_message=(
                            "Postgres Query rendered parameters as "
                            f"{type(rendered_parameters).__name__}, expected an object."
                        ),
                    )

                connector_step_input = {
                    **step_input,
                    "connector": {
                        "connection": _http_connection_summary(connection),
                        "sql": sql,
                        "parameters": _sanitize_trace_value(rendered_parameters),
                    },
                }

                try:
                    rows = _perform_postgres_query(
                        connection_config=connection_config,
                        sql=sql,
                        parameters=rendered_parameters,
                    )
                except (psycopg2.Error, ValueError) as error:
                    raise RouteExecutionError(
                        public_message="Postgres Query step failed against the configured database.",
                        error_message=str(error),
                        status_code=502,
                    ) from error

                output = {
                    "connection": _http_connection_summary(connection),
                    "query": sql,
                    "parameters": rendered_parameters,
                    "row_count": len(rows),
                    "rows": rows,
                }
                context["state"][node_id] = output
                steps.append(
                    ExecutionStepResult(
                        node_id=node_id,
                        node_type=node_type,
                        order_index=order_index,
                        status="success",
                        input_data=_to_json_object(_sanitize_trace_value(connector_step_input)),
                        output_data={
                            "connection": _http_connection_summary(connection),
                            "row_count": len(rows),
                            "rows": _sanitize_trace_value(rows),
                        },
                    )
                )
            except RouteExecutionError as error:
                return _node_error_result(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    step_input=connector_step_input,
                    error=error,
                    steps=steps,
                )
            next_edge = _single_next_edge(flow, node_id)
            if next_edge is None:
                return _node_error_result(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    step_input=connector_step_input,
                    error=RouteExecutionError(
                        public_message="Postgres Query could not continue the flow.",
                        error_message="postgres_query is missing its next edge.",
                    ),
                    steps=steps,
                )
            current_node_id = next_edge.target
            order_index += 1
            continue

        if node_type == "set_response":
            raw_status_code = _render_template(node.get("config", {}).get("status_code", compiled_route.route_success_status_code), context)
            try:
                status_code = int(raw_status_code)
            except (TypeError, ValueError):
                status_code = int(compiled_route.route_success_status_code or 200)
            body = _render_template(node.get("config", {}).get("body", {}), context)
            steps.append(
                ExecutionStepResult(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    status="success",
                    input_data=step_input,
                    output_data={"status_code": status_code, "body": _to_json_object(body)},
                )
            )
            return ExecutionResult(
                status_code=status_code,
                body=body,
                status="success",
                steps=steps,
            )

        if node_type == "error_response":
            raw_status_code = _render_template(node.get("config", {}).get("status_code", 400), context)
            try:
                status_code = int(raw_status_code)
            except (TypeError, ValueError):
                status_code = 400
            body = _render_template(node.get("config", {}).get("body", {"error": "Route returned an error response."}), context)
            steps.append(
                ExecutionStepResult(
                    node_id=node_id,
                    node_type=node_type,
                    order_index=order_index,
                    status="success",
                    input_data=step_input,
                    output_data={"status_code": status_code, "body": _to_json_object(body)},
                )
            )
            return ExecutionResult(
                status_code=status_code,
                body=body,
                status="success",
                steps=steps,
            )

        return _node_error_result(
            node_id=node_id,
            node_type=node_type,
            order_index=order_index,
            step_input=step_input,
            error=RouteExecutionError(
                public_message="This route hit an unsupported flow node.",
                error_message=f"Unsupported executable node type '{node_type}'.",
            ),
            steps=steps,
        )

    return ExecutionResult(
        status_code=500,
        body={"error": "No response node completed for this route implementation."},
        status="error",
        steps=steps,
        error_message="No response node completed.",
    )


def get_latest_route_implementation(
    session: Session,
    route_id: int,
    *,
    draft_only: bool | None = None,
) -> RouteImplementation | None:
    statement = select(RouteImplementation).where(RouteImplementation.route_id == route_id)
    if draft_only is True:
        statement = statement.where(RouteImplementation.is_draft == True)
    elif draft_only is False:
        statement = statement.where(RouteImplementation.is_draft == False)
    statement = statement.order_by(desc(RouteImplementation.version), desc(RouteImplementation.id))
    return session.execute(statement).scalars().first()


def get_route_implementation_read(
    session: Session,
    route: EndpointDefinition,
) -> RouteImplementationRead:
    latest_draft = get_latest_route_implementation(session, int(route.id or 0), draft_only=True)
    current = latest_draft or get_latest_route_implementation(session, int(route.id or 0))
    if current is not None:
        return RouteImplementationRead.model_validate(current)

    return RouteImplementationRead(
        route_id=int(route.id or 0),
        version=1,
        is_draft=True,
        flow_definition=build_default_flow_definition(route),
    )


def upsert_route_implementation(
    session: Session,
    route: EndpointDefinition,
    payload: RouteImplementationUpsert,
) -> RouteImplementation:
    latest_draft = get_latest_route_implementation(session, int(route.id or 0), draft_only=True)
    latest_any = get_latest_route_implementation(session, int(route.id or 0))
    flow = _validate_flow_definition(payload.flow_definition)
    if not flow.nodes_by_id:
        raise ValueError("flow_definition must include executable nodes.")

    if latest_draft is not None:
        latest_draft.flow_definition = payload.flow_definition
        latest_draft.updated_at = utc_now()
        session.add(latest_draft)
        session.commit()
        session.refresh(latest_draft)
        invalidate_deployment_registry()
        return latest_draft

    next_version = (latest_any.version if latest_any is not None else 0) + 1
    implementation = RouteImplementation(
        route_id=int(route.id or 0),
        version=next_version,
        is_draft=True,
        flow_definition=payload.flow_definition,
    )
    session.add(implementation)
    session.commit()
    session.refresh(implementation)
    invalidate_deployment_registry()
    return implementation


def list_route_deployments(session: Session, route_id: int) -> list[RouteDeployment]:
    statement = (
        select(RouteDeployment)
        .where(RouteDeployment.route_id == route_id)
        .order_by(desc(RouteDeployment.published_at), desc(RouteDeployment.id))
    )
    return list(session.execute(statement).scalars())


def publish_route_implementation(
    session: Session,
    route: EndpointDefinition,
    *,
    environment: str = "production",
) -> RouteDeployment:
    environment_name = str(environment or "production").strip() or "production"
    latest_draft = get_latest_route_implementation(session, int(route.id or 0), draft_only=True)
    latest_published = get_latest_route_implementation(session, int(route.id or 0), draft_only=False)

    implementation = latest_draft or latest_published
    if implementation is None:
        implementation = RouteImplementation(
            route_id=int(route.id or 0),
            version=1,
            is_draft=False,
            flow_definition=build_default_flow_definition(route),
        )
        session.add(implementation)
        session.flush()
    elif implementation.is_draft:
        implementation.is_draft = False
        implementation.updated_at = utc_now()
        session.add(implementation)

    existing_active = session.execute(
        select(RouteDeployment).where(
            RouteDeployment.route_id == int(route.id or 0),
            RouteDeployment.environment == environment_name,
            RouteDeployment.is_active == True,
        )
    ).scalars()
    for deployment in existing_active:
        deployment.is_active = False
        deployment.updated_at = utc_now()
        session.add(deployment)

    deployment = RouteDeployment(
        route_id=int(route.id or 0),
        implementation_id=int(implementation.id or 0),
        environment=environment_name,
        is_active=True,
    )
    session.add(deployment)
    session.commit()
    session.refresh(deployment)
    invalidate_deployment_registry()
    return deployment


def unpublish_route_implementation(
    session: Session,
    route: EndpointDefinition,
    *,
    environment: str = "production",
) -> RouteDeployment:
    environment_name = str(environment or "production").strip() or "production"
    active_deployments = list(
        session.execute(
            select(RouteDeployment)
            .where(
                RouteDeployment.route_id == int(route.id or 0),
                RouteDeployment.environment == environment_name,
                RouteDeployment.is_active == True,
            )
            .order_by(desc(RouteDeployment.published_at), desc(RouteDeployment.id))
        ).scalars()
    )
    if not active_deployments:
        raise ValueError(f"No active deployment is published for environment '{environment_name}'.")

    for deployment in active_deployments:
        deployment.is_active = False
        deployment.updated_at = utc_now()
        session.add(deployment)

    session.commit()
    session.refresh(active_deployments[0])
    invalidate_deployment_registry()
    return active_deployments[0]


def list_connections(session: Session) -> list[Connection]:
    statement = select(Connection).order_by(Connection.name)
    return list(session.execute(statement).scalars())


def create_connection(session: Session, payload: ConnectionCreate) -> Connection:
    existing = session.execute(select(Connection).where(Connection.name == payload.name)).scalars().first()
    if existing is not None:
        raise ValueError(f"Connection '{payload.name}' is already in use.")

    _validate_connection_payload(payload)
    connection = Connection(**payload.model_dump())
    session.add(connection)
    session.commit()
    session.refresh(connection)
    return connection


def list_execution_runs(session: Session, *, route_id: int | None = None, limit: int = 50) -> list[ExecutionRun]:
    statement = select(ExecutionRun)
    if route_id is not None:
        statement = statement.where(ExecutionRun.route_id == route_id)
    statement = statement.order_by(desc(ExecutionRun.started_at), desc(ExecutionRun.id)).limit(limit)
    return list(session.execute(statement).scalars())


def delete_route_runtime_records(session: Session, route_id: int) -> None:
    if route_id <= 0:
        return

    run_ids = select(ExecutionRun.id).where(ExecutionRun.route_id == route_id)
    session.execute(delete(ExecutionStep).where(ExecutionStep.run_id.in_(run_ids)))
    session.execute(delete(ExecutionRun).where(ExecutionRun.route_id == route_id))
    session.execute(delete(RouteDeployment).where(RouteDeployment.route_id == route_id))
    session.execute(delete(RouteImplementation).where(RouteImplementation.route_id == route_id))


def get_execution_run_detail(session: Session, run_id: int) -> ExecutionRunDetail | None:
    run = session.get(ExecutionRun, run_id)
    if run is None:
        return None

    steps = list(
        session.execute(
            select(ExecutionStep)
            .where(ExecutionStep.run_id == run_id)
            .order_by(ExecutionStep.order_index, ExecutionStep.id)
        ).scalars()
    )
    detail = ExecutionRunDetail.model_validate(run)
    detail.steps = [ExecutionStepRead.model_validate(step) for step in steps]
    return detail


def _compile_deployed_routes(session: Session) -> list[CompiledDeployedRoute]:
    deployments = list(
        session.execute(
            select(RouteDeployment)
            .where(RouteDeployment.is_active == True)
            .order_by(RouteDeployment.environment, RouteDeployment.id)
        ).scalars()
    )

    compiled_routes: list[CompiledDeployedRoute] = []
    for deployment in deployments:
        route = session.get(EndpointDefinition, deployment.route_id)
        implementation = session.get(RouteImplementation, deployment.implementation_id)
        if route is None or implementation is None or not route.enabled:
            continue

        flow = _validate_flow_definition(
            implementation.flow_definition or build_default_flow_definition(route)
        )
        regex, parameter_names = _path_regex(route.path)
        compiled_routes.append(
            CompiledDeployedRoute(
                route_id=int(route.id or 0),
                route_name=route.name,
                route_method=route.method,
                route_path=route.path,
                route_request_schema=route.request_schema if isinstance(route.request_schema, dict) else {},
                route_success_status_code=int(route.success_status_code or 200),
                implementation_id=int(implementation.id or 0),
                deployment_id=int(deployment.id or 0),
                deployment_environment=deployment.environment,
                regex=regex,
                parameter_names=parameter_names,
                flow=flow,
            )
        )

    compiled_routes.sort(
        key=lambda compiled: (
            compiled.route_method.upper(),
            *_path_specificity(compiled.route_path),
        ),
        reverse=True,
    )
    return compiled_routes


def invalidate_deployment_registry() -> None:
    global _compiled_route_cache
    _compiled_route_cache = None


def _load_compiled_routes(session: Session) -> list[CompiledDeployedRoute]:
    global _compiled_route_cache
    if _compiled_route_cache is None:
        _compiled_route_cache = _compile_deployed_routes(session)
    return _compiled_route_cache


def match_deployed_route(
    session: Session,
    request_path: str,
    method: str,
) -> MatchedDeployedRoute | None:
    for compiled_route in _load_compiled_routes(session):
        if compiled_route.route_method.upper() != method.upper():
            continue

        match = compiled_route.regex.match((request_path.rstrip("/") or "/"))
        if not match:
            continue

        path_parameters = {
            name: unquote(value)
            for name, value in zip(compiled_route.parameter_names, match.groups())
        }
        return MatchedDeployedRoute(compiled_route=compiled_route, path_parameters=path_parameters)

    return None


def execute_deployed_route_request(
    session: Session,
    *,
    request_path: str,
    method: str,
    query_parameters: dict[str, str],
    request_body: Any,
) -> ExecutionResult | None:
    matched = match_deployed_route(session, request_path, method)
    if matched is None:
        return None

    started_at = utc_now()
    result = execute_live_route(
        session,
        matched.compiled_route,
        path_parameters=matched.path_parameters,
        query_parameters=query_parameters,
        request_body=request_body,
    )

    run = ExecutionRun(
        route_id=matched.compiled_route.route_id,
        deployment_id=matched.compiled_route.deployment_id,
        implementation_id=matched.compiled_route.implementation_id,
        environment=matched.compiled_route.deployment_environment,
        method=matched.compiled_route.route_method.upper(),
        path=matched.compiled_route.route_path,
        status=result.status,
        request_data={
            "path_parameters": matched.path_parameters,
            "query_parameters": query_parameters,
            "body_present": request_body is not None,
        },
        response_status_code=result.status_code,
        response_body=_to_json_object(result.body),
        error_message=result.error_message,
        started_at=started_at,
        completed_at=utc_now(),
    )
    session.add(run)
    session.flush()

    for step in result.steps:
        session.add(
            ExecutionStep(
                run_id=int(run.id or 0),
                node_id=step.node_id,
                node_type=step.node_type,
                order_index=step.order_index,
                status=step.status,
                input_data=step.input_data,
                output_data=step.output_data,
                error_message=step.error_message,
                started_at=started_at,
                completed_at=utc_now(),
            )
        )

    session.commit()
    return result


def list_execution_run_reads(session: Session, *, route_id: int | None = None, limit: int = 50) -> list[ExecutionRunRead]:
    return [
        ExecutionRunRead.model_validate(run)
        for run in list_execution_runs(session, route_id=route_id, limit=limit)
    ]
