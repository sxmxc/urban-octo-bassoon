from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from app.crud import (
    create_endpoint,
    delete_endpoint,
    get_endpoint,
    list_endpoints,
    update_endpoint,
)
from app.db import get_session
from app.models import Connection, EndpointDefinition
from app.schemas import (
    AdminAccountUpdate,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminSessionRead,
    AdminUserCreate,
    AdminUserRead,
    AdminUserUpdate,
    ChangePasswordRequest,
    ConnectionCreate,
    ConnectionRead,
    ConnectionUpdate,
    EndpointCreate,
    EndpointBundle,
    EndpointImportMode,
    EndpointImportOperation,
    EndpointImportRequest,
    EndpointImportResponse,
    EndpointImportSummary,
    EndpointRead,
    EndpointUpdate,
    ExecutionRunDetail,
    ExecutionRunRead,
    PreviewRequest,
    PreviewResponse,
    RouteDeploymentPublishRequest,
    RouteDeploymentRead,
    RouteDeploymentUnpublishRequest,
    RouteImplementationRead,
    RouteImplementationUpsert,
)
from app.services.admin_auth import (
    AdminContext,
    AdminLoginThrottleError,
    authenticate_admin_user,
    build_admin_user_read,
    count_active_superusers,
    create_admin_session,
    create_admin_user,
    delete_admin_user,
    get_admin_context,
    get_admin_user,
    list_admin_users,
    require_route_preview_access,
    require_route_read_access,
    require_route_write_access,
    require_user_management_access,
    resolve_admin_role,
    revoke_admin_session,
    revoke_user_sessions,
    update_admin_user,
    update_own_account,
    update_own_password,
)
from app.rbac import AdminRole, normalize_admin_role
from app.services.admin_endpoint_policy import (
    normalize_endpoint_method,
    normalize_endpoint_path,
    validate_endpoint_path,
)
from app.services.mock_generation import preview_from_schema
from app.services.route_runtime import (
    create_connection,
    get_execution_run_detail,
    get_route_implementation_read,
    invalidate_deployment_registry,
    list_connections,
    list_execution_run_reads,
    list_route_deployments,
    publish_route_implementation,
    unpublish_route_implementation,
    update_connection,
    upsert_route_implementation,
)
from app.services.schema_contract import (
    normalize_request_schema_contract,
    normalize_schema_for_builder,
    validate_response_templates,
)
from app.time_utils import utc_now


router = APIRouter()
ENDPOINT_BUNDLE_PRODUCT = "Mockingbird"
ENDPOINT_BUNDLE_SCHEMA_VERSION = 1
SLUG_SEPARATOR_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass
class _EndpointImportPlanAction:
    action: str
    endpoint: EndpointDefinition | None = None
    payload: dict[str, Any] | None = None


def _normalize_request_schema(schema: dict | None, *, path: str | None = None) -> dict:
    return normalize_request_schema_contract(schema or {}, path=path)


def _normalize_response_schema(schema: dict | None, *, path: str | None = None) -> dict:
    normalized = normalize_schema_for_builder(schema or {}, property_name="root", include_mock=True)
    validate_response_templates(normalized, path=path)
    return normalized


def _build_session_read(context: AdminContext) -> AdminSessionRead:
    return AdminSessionRead(user=build_admin_user_read(context.user), expires_at=context.session.expires_at)


def _raise_user_input_error(error: ValueError) -> None:
    detail = str(error)
    status_code = (
        status.HTTP_409_CONFLICT
        if "already in use" in detail.lower() or "no active deployment" in detail.lower()
        else status.HTTP_400_BAD_REQUEST
    )
    raise HTTPException(status_code=status_code, detail=detail)


def _client_ip_from_request(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return first_hop

    return request.client.host if request.client else None


def _normalize_endpoint_fields(
    updates: dict,
    *,
    current_path: str | None = None,
    current_request_schema: dict | None = None,
) -> dict:
    normalized_updates = dict(updates)
    normalized_path = current_path

    if "method" in normalized_updates and normalized_updates["method"] is not None:
        normalized_updates["method"] = normalize_endpoint_method(str(normalized_updates["method"]))

    if "path" in normalized_updates and normalized_updates["path"] is not None:
        normalized_path = normalize_endpoint_path(str(normalized_updates["path"]))
        validate_endpoint_path(normalized_path)
        normalized_updates["path"] = normalized_path

    if "request_schema" in normalized_updates:
        normalized_updates["request_schema"] = _normalize_request_schema(
            normalized_updates["request_schema"],
            path=normalized_path,
        )
    elif normalized_path is not None and current_request_schema is not None:
        normalized_updates["request_schema"] = _normalize_request_schema(current_request_schema, path=normalized_path)

    if "response_schema" in normalized_updates:
        normalized_updates["response_schema"] = _normalize_response_schema(
            normalized_updates["response_schema"],
            path=normalized_path,
        )

    return normalized_updates


def _slugify_value(raw_value: str) -> str:
    lowered = raw_value.strip().lower()
    normalized = SLUG_SEPARATOR_PATTERN.sub("-", lowered).strip("-")
    return normalized or "endpoint"


def _build_unique_slug(
    session: Session,
    *,
    name: str,
    requested_slug: str | None = None,
    exclude_endpoint_id: int | None = None,
) -> str:
    base_slug = _slugify_value(requested_slug or name)
    candidate = base_slug
    suffix = 2

    while True:
        statement = select(EndpointDefinition).where(EndpointDefinition.slug == candidate)
        existing = session.execute(statement).scalars().first()
        if not existing or existing.id == exclude_endpoint_id:
            return candidate

        candidate = f"{base_slug}-{suffix}"
        suffix += 1


def _build_unique_slug_for_import(
    *,
    name: str,
    requested_slug: str | None,
    used_slugs: set[str],
    exclude_slug: str | None = None,
) -> str:
    base_slug = _slugify_value(requested_slug or name)
    candidate = base_slug
    suffix = 2

    if exclude_slug:
        used_slugs.discard(exclude_slug)

    while candidate in used_slugs:
        candidate = f"{base_slug}-{suffix}"
        suffix += 1

    used_slugs.add(candidate)
    return candidate


def _endpoint_import_key(method: str, path: str) -> tuple[str, str]:
    return method.upper(), path


def _endpoint_import_operation(
    action: str,
    *,
    name: str,
    method: str,
    path: str,
    detail: str | None = None,
) -> EndpointImportOperation:
    return EndpointImportOperation(
        action=action,
        name=name,
        method=method.upper(),
        path=path,
        detail=detail,
    )


def _list_all_endpoints(session: Session, *, batch_size: int = 500) -> list[EndpointDefinition]:
    endpoints: list[EndpointDefinition] = []
    offset = 0

    while True:
        batch = list_endpoints(session, limit=batch_size, offset=offset)
        if not batch:
            return endpoints

        endpoints.extend(batch)
        if len(batch) < batch_size:
            return endpoints

        offset += len(batch)


def _serialize_endpoint_bundle(endpoints: list[EndpointDefinition]) -> EndpointBundle:
    sorted_endpoints = sorted(
        endpoints,
        key=lambda endpoint: (
            endpoint.path.lower(),
            endpoint.method.lower(),
            endpoint.name.lower(),
        ),
    )
    return EndpointBundle(
        schema_version=ENDPOINT_BUNDLE_SCHEMA_VERSION,
        product=ENDPOINT_BUNDLE_PRODUCT,
        exported_at=utc_now(),
        endpoints=[
            EndpointCreate(
                name=endpoint.name,
                slug=endpoint.slug,
                method=endpoint.method,
                path=endpoint.path,
                category=endpoint.category,
                tags=endpoint.tags or [],
                summary=endpoint.summary,
                description=endpoint.description,
                enabled=endpoint.enabled,
                auth_mode=endpoint.auth_mode.value if hasattr(endpoint.auth_mode, "value") else str(endpoint.auth_mode),
                request_schema=endpoint.request_schema or {},
                response_schema=endpoint.response_schema or {},
                success_status_code=endpoint.success_status_code,
                error_rate=endpoint.error_rate,
                latency_min_ms=endpoint.latency_min_ms,
                latency_max_ms=endpoint.latency_max_ms,
                seed_key=endpoint.seed_key,
            )
            for endpoint in sorted_endpoints
        ],
    )


def _summarize_endpoint_import(
    *,
    endpoint_count: int,
    operations: list[EndpointImportOperation],
) -> EndpointImportSummary:
    return EndpointImportSummary(
        endpoint_count=endpoint_count,
        create_count=sum(1 for operation in operations if operation.action == "create"),
        update_count=sum(1 for operation in operations if operation.action == "update"),
        delete_count=sum(1 for operation in operations if operation.action == "delete"),
        skip_count=sum(1 for operation in operations if operation.action == "skip"),
        error_count=sum(1 for operation in operations if operation.action == "error"),
    )


def _plan_endpoint_import(
    session: Session,
    payload: EndpointImportRequest,
) -> tuple[list[_EndpointImportPlanAction], list[EndpointImportOperation], bool]:
    operations: list[EndpointImportOperation] = []
    actions: list[_EndpointImportPlanAction] = []
    has_errors = False

    if payload.bundle.schema_version != ENDPOINT_BUNDLE_SCHEMA_VERSION:
        operations.append(
            _endpoint_import_operation(
                "error",
                name="Bundle metadata",
                method="N/A",
                path="/",
                detail=(
                    f"Bundle schema_version {payload.bundle.schema_version} is not supported. "
                    f"Expected {ENDPOINT_BUNDLE_SCHEMA_VERSION}."
                ),
            )
        )
        return actions, operations, True

    existing_endpoints = _list_all_endpoints(session)
    existing_by_key = {
        _endpoint_import_key(endpoint.method, endpoint.path): endpoint
        for endpoint in existing_endpoints
    }
    imported_keys: set[tuple[str, str]] = set()

    for bundled_endpoint in payload.bundle.endpoints:
        raw_payload = bundled_endpoint.model_dump()

        try:
            normalized_payload = _normalize_endpoint_fields(
                raw_payload,
                current_path=bundled_endpoint.path,
                current_request_schema=bundled_endpoint.request_schema,
            )
        except ValueError as error:
            operations.append(
                _endpoint_import_operation(
                    "error",
                    name=bundled_endpoint.name,
                    method=bundled_endpoint.method,
                    path=bundled_endpoint.path,
                    detail=str(error),
                )
            )
            has_errors = True
            continue

        endpoint_key = _endpoint_import_key(
            str(normalized_payload.get("method") or bundled_endpoint.method),
            str(normalized_payload.get("path") or bundled_endpoint.path),
        )
        if endpoint_key in imported_keys:
            operations.append(
                _endpoint_import_operation(
                    "error",
                    name=str(normalized_payload.get("name") or bundled_endpoint.name),
                    method=endpoint_key[0],
                    path=endpoint_key[1],
                    detail="The import bundle contains the same method/path combination more than once.",
                )
            )
            has_errors = True
            continue

        imported_keys.add(endpoint_key)
        existing_endpoint = existing_by_key.get(endpoint_key)

        if existing_endpoint and payload.mode == EndpointImportMode.create_only:
            operations.append(
                _endpoint_import_operation(
                    "skip",
                    name=existing_endpoint.name,
                    method=existing_endpoint.method,
                    path=existing_endpoint.path,
                    detail="Route already exists in this catalog.",
                )
            )
            continue

        if existing_endpoint:
            actions.append(_EndpointImportPlanAction("update", endpoint=existing_endpoint, payload=normalized_payload))
            operations.append(
                _endpoint_import_operation(
                    "update",
                    name=str(normalized_payload.get("name") or existing_endpoint.name),
                    method=endpoint_key[0],
                    path=endpoint_key[1],
                )
            )
            continue

        actions.append(_EndpointImportPlanAction("create", payload=normalized_payload))
        operations.append(
            _endpoint_import_operation(
                "create",
                name=str(normalized_payload.get("name") or bundled_endpoint.name),
                method=endpoint_key[0],
                path=endpoint_key[1],
            )
        )

    if payload.mode == EndpointImportMode.replace_all:
        if not payload.dry_run and not payload.confirm_replace_all:
            operations.append(
                _endpoint_import_operation(
                    "error",
                    name="Replace all confirmation",
                    method="N/A",
                    path="/",
                    detail="Replace-all imports require explicit confirmation before routes are deleted.",
                )
            )
            has_errors = True

        for endpoint in existing_endpoints:
            endpoint_key = _endpoint_import_key(endpoint.method, endpoint.path)
            if endpoint_key in imported_keys:
                continue

            actions.append(_EndpointImportPlanAction("delete", endpoint=endpoint))
            operations.append(
                _endpoint_import_operation(
                    "delete",
                    name=endpoint.name,
                    method=endpoint.method,
                    path=endpoint.path,
                    detail="Route is not present in the import bundle.",
                )
            )

    return actions, operations, has_errors


def _apply_endpoint_import_plan(session: Session, actions: list[_EndpointImportPlanAction]) -> None:
    all_endpoints = _list_all_endpoints(session)
    used_slugs = {endpoint.slug for endpoint in all_endpoints if endpoint.slug}

    for action in actions:
        if action.action == "delete" and action.endpoint and action.endpoint.slug:
            used_slugs.discard(action.endpoint.slug)

    for action in actions:
        if action.action == "delete":
            continue

        if not action.payload:
            continue

        payload = dict(action.payload)
        if action.action == "create":
            payload["slug"] = _build_unique_slug_for_import(
                name=str(payload.get("name") or "endpoint"),
                requested_slug=payload.get("slug"),
                used_slugs=used_slugs,
            )
            session.add(EndpointDefinition(**payload))
            # Flush each created route immediately so Postgres does not batch them
            # through insertmanyvalues, which reintroduces a broken enum cast for
            # the legacy varchar-backed auth_mode column.
            session.flush()
            continue

        if action.endpoint is None:
            continue

        payload["slug"] = _build_unique_slug_for_import(
            name=str(payload.get("name") or action.endpoint.name),
            requested_slug=payload.get("slug"),
            used_slugs=used_slugs,
            exclude_slug=action.endpoint.slug,
        )
        for key, value in payload.items():
            setattr(action.endpoint, key, value)
        action.endpoint.updated_at = utc_now()
        session.add(action.endpoint)

    for action in actions:
        if action.action == "delete" and action.endpoint is not None:
            delete_endpoint(session, action.endpoint, commit=False)

    session.commit()


@router.post("/auth/login", response_model=AdminLoginResponse)
def login_admin(
    payload: AdminLoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> AdminLoginResponse:
    try:
        user = authenticate_admin_user(
            session,
            payload.username,
            payload.password,
            client_ip=_client_ip_from_request(request),
        )
    except AdminLoginThrottleError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from error

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, admin_session = create_admin_session(session, user, remember_me=payload.remember_me)
    return AdminLoginResponse(token=token, user=build_admin_user_read(user), expires_at=admin_session.expires_at)


@router.get("/auth/me", response_model=AdminSessionRead)
def read_current_admin_session(context: AdminContext = Depends(get_admin_context)) -> AdminSessionRead:
    return _build_session_read(context)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_admin(
    session: Session = Depends(get_session),
    context: AdminContext = Depends(get_admin_context),
) -> Response:
    revoke_admin_session(session=session, admin_session=context.session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/account/change-password", response_model=AdminSessionRead)
def change_own_password(
    payload: ChangePasswordRequest,
    session: Session = Depends(get_session),
    context: AdminContext = Depends(get_admin_context),
) -> AdminSessionRead:
    try:
        update_own_password(
            session,
            context.user,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    revoke_user_sessions(session, context.user.id, exclude_session_id=context.session.id)
    refreshed_user = get_admin_user(session, context.user.id)
    return AdminSessionRead(
        user=build_admin_user_read(refreshed_user or context.user),
        expires_at=context.session.expires_at,
    )


@router.get("/account/me", response_model=AdminUserRead)
def read_own_account(context: AdminContext = Depends(get_admin_context)) -> AdminUserRead:
    return build_admin_user_read(context.user)


@router.put("/account/me", response_model=AdminSessionRead)
def update_own_account_profile(
    payload: AdminAccountUpdate,
    session: Session = Depends(get_session),
    context: AdminContext = Depends(get_admin_context),
) -> AdminSessionRead:
    try:
        account_updates: dict[str, str | None] = {}
        if "username" in payload.model_fields_set:
            account_updates["username"] = payload.username
        if "full_name" in payload.model_fields_set:
            account_updates["full_name"] = payload.full_name
        if "email" in payload.model_fields_set:
            account_updates["email"] = payload.email
        if "avatar_url" in payload.model_fields_set:
            account_updates["avatar_url"] = payload.avatar_url

        updated_user = update_own_account(
            session,
            context.user,
            **account_updates,
        )
    except ValueError as error:
        _raise_user_input_error(error)

    return AdminSessionRead(
        user=build_admin_user_read(updated_user),
        expires_at=context.session.expires_at,
    )


@router.get("/users", response_model=list[AdminUserRead])
def list_dashboard_users(
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_user_management_access),
) -> list[AdminUserRead]:
    return [build_admin_user_read(user) for user in list_admin_users(session)]


@router.get("/users/{user_id}", response_model=AdminUserRead)
def read_dashboard_user(
    user_id: int,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_user_management_access),
) -> AdminUserRead:
    user = get_admin_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found.")
    return build_admin_user_read(user)


@router.post("/users", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
def create_dashboard_user(
    payload: AdminUserCreate,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_user_management_access),
) -> AdminUserRead:
    try:
        created_user = create_admin_user(
            session,
            username=payload.username,
            full_name=payload.full_name,
            email=payload.email,
            avatar_url=payload.avatar_url,
            password=payload.password,
            is_active=payload.is_active,
            role=payload.role,
            must_change_password=payload.must_change_password,
        )
        return build_admin_user_read(created_user)
    except ValueError as error:
        _raise_user_input_error(error)


@router.put("/users/{user_id}", response_model=AdminUserRead)
def update_dashboard_user(
    user_id: int,
    payload: AdminUserUpdate,
    session: Session = Depends(get_session),
    context: AdminContext = Depends(require_user_management_access),
) -> AdminUserRead:
    user = get_admin_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found.")

    if user.id == context.user.id:
        current_role = resolve_admin_role(user)
        requested_role = normalize_admin_role(payload.role) if payload.role is not None else None
        if payload.password is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Use the change-password flow to rotate your own password.",
            )
        if payload.is_active is False or (requested_role is not None and requested_role != current_role):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Use another superuser account to change your own role or access.",
            )

    current_role = resolve_admin_role(user)
    requested_role = normalize_admin_role(payload.role) if payload.role is not None else current_role

    if payload.is_active is False and user.is_active and current_role == AdminRole.superuser and count_active_superusers(session, exclude_user_id=user.id) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mockingbird must keep at least one active superuser.",
        )

    if requested_role != AdminRole.superuser and current_role == AdminRole.superuser and user.is_active and count_active_superusers(session, exclude_user_id=user.id) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mockingbird must keep at least one active superuser.",
        )

    try:
        user_updates: dict[str, Any] = {}
        if "full_name" in payload.model_fields_set:
            user_updates["full_name"] = payload.full_name
        if "email" in payload.model_fields_set:
            user_updates["email"] = payload.email
        if "avatar_url" in payload.model_fields_set:
            user_updates["avatar_url"] = payload.avatar_url

        updated_user = update_admin_user(
            session,
            user,
            username=payload.username,
            password=payload.password,
            is_active=payload.is_active,
            role=payload.role,
            must_change_password=payload.must_change_password,
            **user_updates,
        )
    except ValueError as error:
        _raise_user_input_error(error)

    if payload.password is not None or payload.is_active is False:
        revoke_user_sessions(session, updated_user.id)

    return build_admin_user_read(updated_user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard_user(
    user_id: int,
    session: Session = Depends(get_session),
    context: AdminContext = Depends(require_user_management_access),
) -> Response:
    user = get_admin_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found.")
    if user.id == context.user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sign in with another superuser account before deleting this one.",
        )
    if user.is_active and resolve_admin_role(user) == AdminRole.superuser and count_active_superusers(session, exclude_user_id=user.id) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mockingbird must keep at least one active superuser.",
        )

    delete_admin_user(session, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/endpoints", response_model=list[EndpointRead])
def list_all_endpoints(
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_read_access),
) -> list[EndpointRead]:
    return list_endpoints(session)


@router.get("/endpoints/export", response_model=EndpointBundle)
def export_all_endpoints(
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_read_access),
) -> EndpointBundle:
    return _serialize_endpoint_bundle(_list_all_endpoints(session))


@router.post("/endpoints/import", response_model=EndpointImportResponse)
def import_endpoints_bundle(
    payload: EndpointImportRequest,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_write_access),
) -> EndpointImportResponse:
    actions, operations, has_errors = _plan_endpoint_import(session, payload)
    applied = False

    if not payload.dry_run and not has_errors:
        _apply_endpoint_import_plan(session, actions)
        invalidate_deployment_registry()
        applied = True

    return EndpointImportResponse(
        dry_run=payload.dry_run,
        applied=applied,
        has_errors=has_errors,
        mode=payload.mode,
        summary=_summarize_endpoint_import(
            endpoint_count=len(payload.bundle.endpoints),
            operations=operations,
        ),
        operations=operations,
    )


@router.get("/endpoints/{endpoint_id}", response_model=EndpointRead)
def read_endpoint(
    endpoint_id: int,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_read_access),
) -> EndpointRead:
    endpoint = get_endpoint(session, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")
    return endpoint


@router.post("/endpoints", response_model=EndpointRead, status_code=status.HTTP_201_CREATED)
def create_new_endpoint(
    endpoint_in: EndpointCreate,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_write_access),
) -> EndpointRead:
    try:
        normalized_fields = _normalize_endpoint_fields(
            endpoint_in.model_dump(),
            current_path=endpoint_in.path,
            current_request_schema=endpoint_in.request_schema,
        )
    except ValueError as error:
        _raise_user_input_error(error)
    normalized_fields["slug"] = _build_unique_slug(
        session,
        name=str(normalized_fields.get("name") or endpoint_in.name),
        requested_slug=normalized_fields.get("slug"),
    )
    payload = EndpointCreate(**normalized_fields)
    endpoint = create_endpoint(session, payload)
    invalidate_deployment_registry()
    return endpoint


@router.put("/endpoints/{endpoint_id}", response_model=EndpointRead)
def update_existing_endpoint(
    endpoint_id: int,
    endpoint_in: EndpointUpdate,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_write_access),
) -> EndpointRead:
    endpoint = get_endpoint(session, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    try:
        updates = _normalize_endpoint_fields(
            endpoint_in.model_dump(exclude_unset=True),
            current_path=endpoint.path,
            current_request_schema=endpoint.request_schema,
        )
    except ValueError as error:
        _raise_user_input_error(error)
    if "name" in updates or "slug" in updates:
        updates["slug"] = _build_unique_slug(
            session,
            name=str(updates.get("name") or endpoint.name),
            requested_slug=updates.get("slug"),
            exclude_endpoint_id=endpoint.id,
        )
    updated_endpoint = update_endpoint(session, endpoint, EndpointUpdate(**updates))
    invalidate_deployment_registry()
    return updated_endpoint


@router.delete("/endpoints/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_existing_endpoint(
    endpoint_id: int,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_write_access),
) -> Response:
    endpoint = get_endpoint(session, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")
    delete_endpoint(session, endpoint)
    invalidate_deployment_registry()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/endpoints/{endpoint_id}/implementation/current", response_model=RouteImplementationRead)
def read_current_route_implementation(
    endpoint_id: int,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_read_access),
) -> RouteImplementationRead:
    endpoint = get_endpoint(session, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")
    return get_route_implementation_read(session, endpoint)


@router.put("/endpoints/{endpoint_id}/implementation/current", response_model=RouteImplementationRead)
def save_current_route_implementation(
    endpoint_id: int,
    payload: RouteImplementationUpsert,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_write_access),
) -> RouteImplementationRead:
    endpoint = get_endpoint(session, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")
    try:
        implementation = upsert_route_implementation(session, endpoint, payload)
    except ValueError as error:
        _raise_user_input_error(error)
    return RouteImplementationRead.model_validate(implementation)


@router.get("/endpoints/{endpoint_id}/deployments", response_model=list[RouteDeploymentRead])
def read_route_deployments(
    endpoint_id: int,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_read_access),
) -> list[RouteDeploymentRead]:
    endpoint = get_endpoint(session, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")
    return [RouteDeploymentRead.model_validate(deployment) for deployment in list_route_deployments(session, endpoint_id)]


@router.post("/endpoints/{endpoint_id}/deployments/publish", response_model=RouteDeploymentRead, status_code=status.HTTP_201_CREATED)
def publish_current_route_implementation(
    endpoint_id: int,
    payload: RouteDeploymentPublishRequest,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_write_access),
) -> RouteDeploymentRead:
    endpoint = get_endpoint(session, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")
    deployment = publish_route_implementation(session, endpoint, environment=payload.environment)
    return RouteDeploymentRead.model_validate(deployment)


@router.post("/endpoints/{endpoint_id}/deployments/unpublish", response_model=RouteDeploymentRead)
def unpublish_current_route_implementation(
    endpoint_id: int,
    payload: RouteDeploymentUnpublishRequest,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_write_access),
) -> RouteDeploymentRead:
    endpoint = get_endpoint(session, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")
    try:
        deployment = unpublish_route_implementation(session, endpoint, environment=payload.environment)
    except ValueError as error:
        _raise_user_input_error(error)
    return RouteDeploymentRead.model_validate(deployment)


@router.get("/connections", response_model=list[ConnectionRead])
def list_runtime_connections(
    project: str | None = None,
    environment: str | None = None,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_read_access),
) -> list[ConnectionRead]:
    return [
        ConnectionRead.model_validate(connection)
        for connection in list_connections(session, project=project, environment=environment)
    ]


@router.post("/connections", response_model=ConnectionRead, status_code=status.HTTP_201_CREATED)
def create_runtime_connection(
    payload: ConnectionCreate,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_write_access),
) -> ConnectionRead:
    try:
        connection = create_connection(session, payload)
    except ValueError as error:
        _raise_user_input_error(error)
    return ConnectionRead.model_validate(connection)


@router.put("/connections/{connection_id}", response_model=ConnectionRead)
def update_runtime_connection(
    connection_id: int,
    payload: ConnectionUpdate,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_write_access),
) -> ConnectionRead:
    connection = session.get(Connection, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    try:
        updated_connection = update_connection(session, connection, payload)
    except ValueError as error:
        _raise_user_input_error(error)
    return ConnectionRead.model_validate(updated_connection)


@router.get("/executions", response_model=list[ExecutionRunRead])
def list_route_executions(
    endpoint_id: int | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_read_access),
) -> list[ExecutionRunRead]:
    return list_execution_run_reads(session, route_id=endpoint_id, limit=max(1, min(limit, 200)))


@router.get("/executions/{run_id}", response_model=ExecutionRunDetail)
def read_route_execution(
    run_id: int,
    session: Session = Depends(get_session),
    _: AdminContext = Depends(require_route_read_access),
) -> ExecutionRunDetail:
    run = get_execution_run_detail(session, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution run not found")
    return run


@router.post("/endpoints/preview-response", response_model=PreviewResponse)
def preview_response(
    payload: PreviewRequest,
    _: AdminContext = Depends(require_route_preview_access),
) -> PreviewResponse:
    try:
        preview = preview_from_schema(
            _normalize_response_schema(payload.response_schema),
            path_parameters=payload.path_parameters,
            query_parameters=payload.query_parameters,
            request_body=payload.request_body,
            seed_key=payload.seed_key,
            identity="preview",
        )
    except ValueError as error:
        _raise_user_input_error(error)

    return PreviewResponse(preview=preview)
