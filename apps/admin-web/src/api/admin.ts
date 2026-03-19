import type {
  AdminAccountUpdatePayload,
  AdminLoginPayload,
  AdminSession,
  AdminSessionSnapshot,
  AdminUser,
  AdminUserCreatePayload,
  AdminUserUpdatePayload,
  ChangePasswordPayload,
  Connection,
  ConnectionPayload,
  Endpoint,
  EndpointBundle,
  EndpointImportRequestPayload,
  EndpointImportResponse,
  EndpointPayload,
  ExecutionRun,
  ExecutionRunDetail,
  JsonObject,
  JsonValue,
  PreviewResponsePayload,
  RouteDeployment,
  RouteDeploymentPublishPayload,
  RouteDeploymentUnpublishPayload,
  RouteImplementation,
  RouteImplementationPayload,
} from "../types/endpoints";

const REMEMBERED_SESSION_KEY = "mockingbird.admin-remembered-session";
const ACTIVE_SESSION_KEY = "mockingbird.admin-active-session";

interface RequestOptions {
  body?: string;
  headers?: Record<string, string>;
  method?: string;
}

interface ConnectionListOptions {
  project?: string;
  environment?: string;
}

interface ExecutionListOptions {
  endpointId?: number;
  limit?: number;
}

export class AdminApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "AdminApiError";
    this.status = status;
  }
}

function buildAuthorizationHeader(session: AdminSession | string): string {
  const token = typeof session === "string" ? session : session.token;
  return `Bearer ${token}`;
}

function parseJsonIfPossible(value: string): unknown {
  if (!value) {
    return null;
  }

  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function readStoredSession(storage: Storage | undefined): AdminSession | null {
  if (!storage) {
    return null;
  }

  try {
    const rawValue = storage.getItem(ACTIVE_SESSION_KEY) ?? storage.getItem(REMEMBERED_SESSION_KEY);
    if (!rawValue) {
      return null;
    }

    return JSON.parse(rawValue) as AdminSession;
  } catch {
    return null;
  }
}

async function request<T>(path: string, session: AdminSession | string, init: RequestOptions = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", buildAuthorizationHeader(session));

  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    ...init,
    headers,
  });
  const rawBody = await response.text();
  const parsedBody = parseJsonIfPossible(rawBody);

  if (!response.ok) {
    const detail =
      typeof parsedBody === "object" && parsedBody && "detail" in parsedBody
        ? String(parsedBody.detail)
        : rawBody || `${response.status} ${response.statusText}`;

    throw new AdminApiError(detail, response.status);
  }

  return parsedBody as T;
}

async function publicRequest<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const headers = new Headers(init.headers);

  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    ...init,
    headers,
  });
  const rawBody = await response.text();
  const parsedBody = parseJsonIfPossible(rawBody);

  if (!response.ok) {
    const detail =
      typeof parsedBody === "object" && parsedBody && "detail" in parsedBody
        ? String(parsedBody.detail)
        : rawBody || `${response.status} ${response.statusText}`;

    throw new AdminApiError(detail, response.status);
  }

  return parsedBody as T;
}

export function hasSession(session: AdminSession | null): session is AdminSession {
  return Boolean(session?.token && session.user?.username);
}

export function loadStoredSession(): AdminSession | null {
  if (typeof window === "undefined") {
    return null;
  }

  return readStoredSession(window.sessionStorage) ?? readStoredSession(window.localStorage);
}

export function persistSession(session: AdminSession, rememberMe: boolean): void {
  if (typeof window === "undefined") {
    return;
  }

  const serialized = JSON.stringify(session);
  window.sessionStorage.setItem(ACTIVE_SESSION_KEY, serialized);

  if (rememberMe) {
    window.localStorage.setItem(REMEMBERED_SESSION_KEY, serialized);
  } else {
    window.localStorage.removeItem(REMEMBERED_SESSION_KEY);
  }
}

export function updateStoredSession(session: AdminSession): void {
  if (typeof window === "undefined") {
    return;
  }

  const serialized = JSON.stringify(session);

  if (window.sessionStorage.getItem(ACTIVE_SESSION_KEY)) {
    window.sessionStorage.setItem(ACTIVE_SESSION_KEY, serialized);
  }

  if (window.localStorage.getItem(REMEMBERED_SESSION_KEY)) {
    window.localStorage.setItem(REMEMBERED_SESSION_KEY, serialized);
  }
}

export function clearStoredSession(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.sessionStorage.removeItem(ACTIVE_SESSION_KEY);
  window.localStorage.removeItem(REMEMBERED_SESSION_KEY);
}

export function loginAdmin(payload: AdminLoginPayload): Promise<AdminSession> {
  return publicRequest<AdminSession>("/api/admin/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getCurrentSession(session: AdminSession | string): Promise<AdminSessionSnapshot> {
  return request<AdminSessionSnapshot>("/api/admin/auth/me", session);
}

export function logoutAdmin(session: AdminSession | string): Promise<null> {
  return request<null>("/api/admin/auth/logout", session, {
    method: "POST",
  });
}

export function changePassword(
  payload: ChangePasswordPayload,
  session: AdminSession | string,
): Promise<AdminSessionSnapshot> {
  return request<AdminSessionSnapshot>("/api/admin/account/change-password", session, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAccountProfile(session: AdminSession | string): Promise<AdminUser> {
  return request<AdminUser>("/api/admin/account/me", session);
}

export function updateAccountProfile(
  payload: AdminAccountUpdatePayload,
  session: AdminSession | string,
): Promise<AdminSessionSnapshot> {
  return request<AdminSessionSnapshot>("/api/admin/account/me", session, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function listAdminUsers(session: AdminSession): Promise<AdminUser[]> {
  return request<AdminUser[]>("/api/admin/users", session);
}

export function getAdminUser(userId: number, session: AdminSession): Promise<AdminUser> {
  return request<AdminUser>(`/api/admin/users/${userId}`, session);
}

export function createAdminUser(payload: AdminUserCreatePayload, session: AdminSession): Promise<AdminUser> {
  return request<AdminUser>("/api/admin/users", session, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminUser(
  userId: number,
  payload: AdminUserUpdatePayload,
  session: AdminSession,
): Promise<AdminUser> {
  return request<AdminUser>(`/api/admin/users/${userId}`, session, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteAdminUser(userId: number, session: AdminSession): Promise<null> {
  return request<null>(`/api/admin/users/${userId}`, session, {
    method: "DELETE",
  });
}

export function listEndpoints(session: AdminSession): Promise<Endpoint[]> {
  return request<Endpoint[]>("/api/admin/endpoints", session);
}

export function getEndpoint(endpointId: number, session: AdminSession): Promise<Endpoint> {
  return request<Endpoint>(`/api/admin/endpoints/${endpointId}`, session);
}

export function exportEndpointBundle(session: AdminSession): Promise<EndpointBundle> {
  return request<EndpointBundle>("/api/admin/endpoints/export", session);
}

export function importEndpointBundle(
  payload: EndpointImportRequestPayload,
  session: AdminSession,
): Promise<EndpointImportResponse> {
  return request<EndpointImportResponse>("/api/admin/endpoints/import", session, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createEndpoint(payload: EndpointPayload, session: AdminSession): Promise<Endpoint> {
  return request<Endpoint>("/api/admin/endpoints", session, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateEndpoint(endpointId: number, payload: EndpointPayload, session: AdminSession): Promise<Endpoint> {
  return request<Endpoint>(`/api/admin/endpoints/${endpointId}`, session, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteEndpoint(endpointId: number, session: AdminSession): Promise<null> {
  return request<null>(`/api/admin/endpoints/${endpointId}`, session, {
    method: "DELETE",
  });
}

export function getCurrentRouteImplementation(
  endpointId: number,
  session: AdminSession,
): Promise<RouteImplementation> {
  return request<RouteImplementation>(`/api/admin/endpoints/${endpointId}/implementation/current`, session);
}

export function saveCurrentRouteImplementation(
  endpointId: number,
  payload: RouteImplementationPayload,
  session: AdminSession,
): Promise<RouteImplementation> {
  return request<RouteImplementation>(`/api/admin/endpoints/${endpointId}/implementation/current`, session, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function listRouteDeployments(endpointId: number, session: AdminSession): Promise<RouteDeployment[]> {
  return request<RouteDeployment[]>(`/api/admin/endpoints/${endpointId}/deployments`, session);
}

export function publishRouteImplementation(
  endpointId: number,
  payload: RouteDeploymentPublishPayload,
  session: AdminSession,
): Promise<RouteDeployment> {
  return request<RouteDeployment>(`/api/admin/endpoints/${endpointId}/deployments/publish`, session, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function unpublishRouteDeployment(
  endpointId: number,
  payload: RouteDeploymentUnpublishPayload,
  session: AdminSession,
): Promise<RouteDeployment> {
  return request<RouteDeployment>(`/api/admin/endpoints/${endpointId}/deployments/unpublish`, session, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listConnections(session: AdminSession, options: ConnectionListOptions = {}): Promise<Connection[]> {
  const params = new URLSearchParams();
  if (options.project) {
    params.set("project", options.project);
  }
  if (options.environment) {
    params.set("environment", options.environment);
  }

  const query = params.toString();
  return request<Connection[]>(`/api/admin/connections${query ? `?${query}` : ""}`, session);
}

export function createConnection(payload: ConnectionPayload, session: AdminSession): Promise<Connection> {
  return request<Connection>("/api/admin/connections", session, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateConnection(connectionId: number, payload: ConnectionPayload, session: AdminSession): Promise<Connection> {
  return request<Connection>(`/api/admin/connections/${connectionId}`, session, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function listExecutions(
  session: AdminSession,
  options: ExecutionListOptions = {},
): Promise<ExecutionRun[]> {
  const params = new URLSearchParams();
  if (typeof options.endpointId === "number") {
    params.set("endpoint_id", String(options.endpointId));
  }
  if (typeof options.limit === "number") {
    params.set("limit", String(options.limit));
  }

  const query = params.toString();
  return request<ExecutionRun[]>(`/api/admin/executions${query ? `?${query}` : ""}`, session);
}

export function getExecution(runId: number, session: AdminSession): Promise<ExecutionRunDetail> {
  return request<ExecutionRunDetail>(`/api/admin/executions/${runId}`, session);
}

export function previewResponse(
  responseSchema: JsonObject,
  seedKey: string | null,
  pathParameters: Record<string, string>,
  session: AdminSession,
  options: {
    queryParameters?: Record<string, string>;
    requestBody?: JsonValue | null;
  } = {},
): Promise<PreviewResponsePayload> {
  return request<PreviewResponsePayload>("/api/admin/endpoints/preview-response", session, {
    method: "POST",
    body: JSON.stringify({
      path_parameters: pathParameters,
      query_parameters: options.queryParameters ?? {},
      request_body: options.requestBody ?? null,
      response_schema: responseSchema,
      seed_key: seedKey,
    }),
  });
}
