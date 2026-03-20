from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.rbac import AdminPermission, AdminRole
from app.models import ConnectionType


class EndpointBase(BaseModel):
    name: str
    slug: Optional[str] = None
    method: str
    path: str
    category: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    summary: Optional[str] = None
    description: Optional[str] = None
    enabled: bool = True
    auth_mode: str = "none"
    request_schema: Optional[Dict[str, Any]] = Field(default_factory=dict)
    response_schema: Optional[Dict[str, Any]] = Field(default_factory=dict)
    success_status_code: int = 200
    error_rate: float = 0.0
    latency_min_ms: int = 0
    latency_max_ms: int = 0
    seed_key: Optional[str] = None


class EndpointCreate(EndpointBase):
    pass


class EndpointUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    auth_mode: Optional[str] = None
    request_schema: Optional[Dict[str, Any]] = None
    response_schema: Optional[Dict[str, Any]] = None
    success_status_code: Optional[int] = None
    error_rate: Optional[float] = None
    latency_min_ms: Optional[int] = None
    latency_max_ms: Optional[int] = None
    seed_key: Optional[str] = None


class RoutePublicationStatus(BaseModel):
    code: str
    label: str
    tone: str
    enabled: bool
    is_public: bool
    is_live: bool
    uses_legacy_mock: bool
    has_saved_implementation: bool
    has_runtime_history: bool
    has_deployment_history: bool
    has_active_deployment: bool
    active_deployment_environment: Optional[str] = None
    active_implementation_id: Optional[int] = None
    active_deployment_id: Optional[int] = None


class EndpointRead(EndpointBase):
    slug: str
    id: int
    created_at: datetime
    updated_at: datetime
    publication_status: RoutePublicationStatus

    model_config = ConfigDict(from_attributes=True)


class EndpointImportMode(str, Enum):
    create_only = "create_only"
    upsert = "upsert"
    replace_all = "replace_all"


class EndpointBundle(BaseModel):
    schema_version: int = 1
    product: str = "Artificer"
    exported_at: datetime
    endpoints: List[EndpointBase] = Field(default_factory=list)


class EndpointImportRequest(BaseModel):
    bundle: EndpointBundle
    mode: EndpointImportMode = EndpointImportMode.upsert
    dry_run: bool = True
    confirm_replace_all: bool = False


class EndpointImportOperation(BaseModel):
    action: str
    method: str
    path: str
    name: str
    detail: Optional[str] = None


class EndpointImportSummary(BaseModel):
    endpoint_count: int = 0
    create_count: int = 0
    update_count: int = 0
    delete_count: int = 0
    skip_count: int = 0
    error_count: int = 0


class EndpointImportResponse(BaseModel):
    dry_run: bool
    applied: bool
    has_errors: bool
    mode: EndpointImportMode
    summary: EndpointImportSummary
    operations: List[EndpointImportOperation] = Field(default_factory=list)


class PreviewRequest(BaseModel):
    response_schema: Dict[str, Any] = Field(default_factory=dict)
    path_parameters: Dict[str, str] = Field(default_factory=dict)
    query_parameters: Dict[str, str] = Field(default_factory=dict)
    request_body: Any = None
    seed_key: Optional[str] = None


class PreviewResponse(BaseModel):
    preview: Any


class AdminUserRead(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    gravatar_url: str
    is_active: bool
    role: AdminRole
    permissions: List[AdminPermission] = Field(default_factory=list)
    is_superuser: bool
    must_change_password: bool
    last_login_at: Optional[datetime] = None
    password_changed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminLoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class AdminSessionRead(BaseModel):
    user: AdminUserRead
    expires_at: datetime


class AdminLoginResponse(AdminSessionRead):
    token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AdminAccountUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None


class AdminUserCreate(BaseModel):
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    password: str
    is_active: bool = True
    role: AdminRole = AdminRole.editor
    must_change_password: bool = True


class AdminUserUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[AdminRole] = None
    must_change_password: Optional[bool] = None


class PublicEndpointReference(BaseModel):
    id: int
    name: str
    method: str
    path: str
    example_path: str
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    description: Optional[str] = None
    success_status_code: int
    request_schema: Dict[str, Any] = Field(default_factory=dict)
    response_schema: Dict[str, Any] = Field(default_factory=dict)
    sample_request: Any = None
    sample_response: Any = None
    updated_at: datetime
    publication_status: RoutePublicationStatus


class PublicReferenceResponse(BaseModel):
    product_name: str
    description: str
    endpoint_count: int
    refreshed_at: datetime
    endpoints: List[PublicEndpointReference] = Field(default_factory=list)


class ApiDependencyHealth(BaseModel):
    name: str
    label: str
    status: str
    detail: str
    latency_ms: Optional[float] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ApiHealthResponse(BaseModel):
    status: str
    checked_at: datetime
    dependencies: List[ApiDependencyHealth] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


class RouteImplementationUpsert(BaseModel):
    flow_definition: Dict[str, Any] = Field(default_factory=dict)


class RouteImplementationRead(BaseModel):
    id: Optional[int] = None
    route_id: int
    version: int
    is_draft: bool = True
    flow_definition: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RouteDeploymentPublishRequest(BaseModel):
    environment: str = "production"


class RouteDeploymentUnpublishRequest(BaseModel):
    environment: str = "production"


class RouteDeploymentRead(BaseModel):
    id: int
    route_id: int
    implementation_id: int
    environment: str
    is_active: bool
    published_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConnectionBase(BaseModel):
    project: str = "default"
    environment: str = "production"
    name: str
    connector_type: ConnectionType = ConnectionType.http
    description: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class ConnectionCreate(ConnectionBase):
    pass


class ConnectionUpdate(ConnectionBase):
    pass


class ConnectionRead(ConnectionBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExecutionStepRead(BaseModel):
    id: int
    node_id: str
    node_type: str
    order_index: int
    status: str
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ExecutionRunRead(BaseModel):
    id: int
    route_id: int
    deployment_id: Optional[int] = None
    implementation_id: Optional[int] = None
    environment: str
    method: str
    path: str
    status: str
    request_data: Dict[str, Any] = Field(default_factory=dict)
    response_status_code: Optional[int] = None
    response_body: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ExecutionRunDetail(ExecutionRunRead):
    steps: List[ExecutionStepRead] = Field(default_factory=list)


class ExecutionTelemetryRouteSummary(BaseModel):
    route_id: int
    total_runs: int
    success_runs: int
    error_runs: int
    success_rate: Optional[float] = None
    average_response_time_ms: Optional[float] = None
    p95_response_time_ms: Optional[float] = None
    max_response_time_ms: Optional[float] = None
    average_flow_time_ms: Optional[float] = None
    p95_flow_time_ms: Optional[float] = None
    latest_completed_at: Optional[datetime] = None


class ExecutionTelemetryStepSummary(BaseModel):
    route_id: int
    node_type: str
    total_steps: int
    average_duration_ms: Optional[float] = None
    p95_duration_ms: Optional[float] = None
    max_duration_ms: Optional[float] = None
    latest_completed_at: Optional[datetime] = None


class ExecutionTelemetryOverview(BaseModel):
    sample_limit: int = 200
    sampled_runs: int = 0
    sampled_steps: int = 0
    route_count: int = 0
    success_runs: int = 0
    error_runs: int = 0
    success_rate: Optional[float] = None
    average_response_time_ms: Optional[float] = None
    p95_response_time_ms: Optional[float] = None
    average_flow_time_ms: Optional[float] = None
    p95_flow_time_ms: Optional[float] = None
    average_steps_per_run: Optional[float] = None
    latest_completed_at: Optional[datetime] = None
    precise_step_run_count: int = 0
    slow_routes: List[ExecutionTelemetryRouteSummary] = Field(default_factory=list)
    slow_flow_steps: List[ExecutionTelemetryStepSummary] = Field(default_factory=list)
