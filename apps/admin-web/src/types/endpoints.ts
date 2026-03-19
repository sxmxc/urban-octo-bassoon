export type JsonValue = string | number | boolean | null | JsonObject | JsonValue[];

export interface JsonObject {
  [key: string]: JsonValue;
}

export type RouteFlowNodeType =
  | "api_trigger"
  | "validate_request"
  | "transform"
  | "if_condition"
  | "switch"
  | "http_request"
  | "postgres_query"
  | "set_response"
  | "error_response";

export interface RouteFlowPosition extends JsonObject {
  x: number;
  y: number;
}

export interface RouteFlowNode {
  id: string;
  type: RouteFlowNodeType;
  name: string;
  config: JsonObject;
  position?: RouteFlowPosition;
  extra?: JsonObject;
}

export interface RouteFlowEdge {
  id?: string;
  source: string;
  target: string;
  extra?: JsonObject;
}

export interface RouteFlowDefinition {
  schema_version: number;
  nodes: RouteFlowNode[];
  edges: RouteFlowEdge[];
  extra?: JsonObject;
}

export type AdminRole = "viewer" | "editor" | "superuser";
export type AdminPermission = "routes.read" | "routes.write" | "routes.preview" | "users.manage";

export interface AdminUser {
  id: number;
  username: string;
  full_name: string | null;
  email: string | null;
  avatar_url: string | null;
  gravatar_url: string;
  is_active: boolean;
  role: AdminRole;
  permissions: AdminPermission[];
  is_superuser: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  password_changed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminSession {
  token: string;
  expires_at: string;
  user: AdminUser;
}

export interface AdminSessionSnapshot {
  expires_at: string;
  user: AdminUser;
}

export interface AdminLoginPayload {
  username: string;
  password: string;
  remember_me: boolean;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

export interface AdminAccountUpdatePayload {
  username?: string;
  full_name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
}

export interface AdminUserCreatePayload {
  username: string;
  full_name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  password: string;
  is_active?: boolean;
  role?: AdminRole;
  must_change_password?: boolean;
}

export interface AdminUserUpdatePayload {
  username?: string;
  full_name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  password?: string;
  is_active?: boolean;
  role?: AdminRole;
  must_change_password?: boolean;
}

export interface EndpointPayload {
  name: string;
  slug?: string | null;
  method: string;
  path: string;
  category: string | null;
  tags: string[];
  summary: string | null;
  description: string | null;
  enabled: boolean;
  auth_mode: string;
  request_schema: JsonObject | null;
  response_schema: JsonObject | null;
  success_status_code: number;
  error_rate: number;
  latency_min_ms: number;
  latency_max_ms: number;
  seed_key: string | null;
}

export interface Endpoint extends Omit<EndpointPayload, "slug"> {
  slug: string;
  id: number;
  created_at: string;
  updated_at: string;
}

export type EndpointImportMode = "create_only" | "upsert" | "replace_all";

export interface EndpointBundle {
  schema_version: number;
  product: string;
  exported_at: string;
  endpoints: EndpointPayload[];
}

export interface EndpointImportRequestPayload {
  bundle: EndpointBundle;
  mode: EndpointImportMode;
  dry_run: boolean;
  confirm_replace_all: boolean;
}

export interface EndpointImportOperation {
  action: string;
  method: string;
  path: string;
  name: string;
  detail: string | null;
}

export interface EndpointImportSummary {
  endpoint_count: number;
  create_count: number;
  update_count: number;
  delete_count: number;
  skip_count: number;
  error_count: number;
}

export interface EndpointImportResponse {
  dry_run: boolean;
  applied: boolean;
  has_errors: boolean;
  mode: EndpointImportMode;
  summary: EndpointImportSummary;
  operations: EndpointImportOperation[];
}

export interface EndpointDraft {
  name: string;
  method: string;
  path: string;
  category: string;
  tags: string;
  summary: string;
  description: string;
  enabled: boolean;
  auth_mode: string;
  request_schema: JsonObject;
  response_schema: JsonObject;
  success_status_code: number;
  error_rate: number;
  latency_min_ms: number;
  latency_max_ms: number;
  seed_key: string;
}

export interface PreviewResponsePayload {
  preview: JsonValue;
}

export type ConnectionType = "http" | "postgres";

export interface RouteImplementation {
  id: number | null;
  route_id: number;
  version: number;
  is_draft: boolean;
  flow_definition: JsonObject;
  created_at: string | null;
  updated_at: string | null;
}

export interface RouteImplementationPayload {
  flow_definition: JsonObject;
}

export interface RouteDeployment {
  id: number;
  route_id: number;
  implementation_id: number;
  environment: string;
  is_active: boolean;
  published_at: string;
  created_at: string;
  updated_at: string;
}

export interface RouteDeploymentPublishPayload {
  environment: string;
}

export interface RouteDeploymentUnpublishPayload {
  environment: string;
}

export interface ConnectionPayload {
  project?: string;
  environment?: string;
  name: string;
  connector_type: ConnectionType;
  description?: string | null;
  config: JsonObject;
  is_active?: boolean;
}

export interface Connection extends ConnectionPayload {
  project: string;
  environment: string;
  id: number;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ExecutionStep {
  id: number;
  node_id: string;
  node_type: string;
  order_index: number;
  status: string;
  input_data: JsonObject;
  output_data: JsonObject | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface ExecutionRun {
  id: number;
  route_id: number;
  deployment_id: number | null;
  implementation_id: number | null;
  environment: string;
  method: string;
  path: string;
  status: string;
  request_data: JsonObject;
  response_status_code: number | null;
  response_body: JsonObject | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface ExecutionRunDetail extends ExecutionRun {
  steps: ExecutionStep[];
}
