import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { exportEndpointBundle, getAccountProfile, importEndpointBundle, updateAccountProfile } from "./admin";
import type { AdminSession, EndpointBundle, EndpointImportRequestPayload } from "../types/endpoints";

const session: AdminSession = {
  token: "session-token",
  expires_at: "2026-03-17T00:00:00Z",
  user: {
    id: 1,
    username: "admin",
    full_name: "Admin User",
    email: "admin@example.com",
    avatar_url: null,
    gravatar_url: "https://www.gravatar.com/avatar/admin?d=identicon&s=160",
    is_active: true,
    role: "superuser",
    permissions: ["routes.read", "routes.write", "routes.preview", "users.manage"],
    is_superuser: true,
    must_change_password: false,
    last_login_at: null,
    password_changed_at: "2026-03-17T00:00:00Z",
    created_at: "2026-03-17T00:00:00Z",
    updated_at: "2026-03-17T00:00:00Z",
  },
};

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    text: async () => JSON.stringify(body),
  } as Response;
}

describe("admin endpoint bundle API", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests the endpoint export bundle with bearer auth", async () => {
    const bundle: EndpointBundle = {
      schema_version: 1,
      product: "Artificer",
      exported_at: "2026-03-17T00:00:00Z",
      endpoints: [],
    };
    fetchMock.mockResolvedValue(jsonResponse(bundle));

    const result = await exportEndpointBundle(session);

    expect(result).toEqual(bundle);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/endpoints/export",
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    );

    const [, init] = fetchMock.mock.calls[0] as [string, { headers: Headers }];
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer session-token");
  });

  it("posts import bundles with mode and confirmation flags", async () => {
    const payload: EndpointImportRequestPayload = {
      bundle: {
        schema_version: 1,
        product: "Artificer",
        exported_at: "2026-03-17T00:00:00Z",
        endpoints: [
          {
            name: "List users",
            slug: "list-users",
            method: "GET",
            path: "/api/users",
            category: "users",
            tags: ["users"],
            summary: "List users",
            description: "Imported from bundle",
            enabled: true,
            auth_mode: "none",
            request_schema: {},
            response_schema: {},
            success_status_code: 200,
            error_rate: 0,
            latency_min_ms: 0,
            latency_max_ms: 0,
            seed_key: null,
          },
        ],
      },
      mode: "replace_all",
      dry_run: false,
      confirm_replace_all: true,
    };
    fetchMock.mockResolvedValue(
      jsonResponse({
        dry_run: false,
        applied: true,
        has_errors: false,
        mode: "replace_all",
        summary: {
          endpoint_count: 1,
          create_count: 1,
          update_count: 0,
          delete_count: 2,
          skip_count: 0,
          error_count: 0,
        },
        operations: [
          {
            action: "create",
            name: "List users",
            method: "GET",
            path: "/api/users",
            detail: null,
          },
        ],
      }),
    );

    const result = await importEndpointBundle(payload, session);

    expect(result.applied).toBe(true);
    expect(result.summary.create_count).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/endpoints/import",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
        headers: expect.any(Headers),
      }),
    );

    const [, init] = fetchMock.mock.calls[0] as [string, { headers: Headers }];
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer session-token");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("loads the current account profile with bearer auth", async () => {
    fetchMock.mockResolvedValue(jsonResponse(session.user));

    const result = await getAccountProfile(session);

    expect(result.username).toBe("admin");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/account/me",
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    );
  });

  it("updates the current account profile through the dedicated account endpoint", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        expires_at: session.expires_at,
        user: {
          ...session.user,
          full_name: "Admin Renamed",
          email: "admin-renamed@example.com",
          avatar_url: "https://cdn.example.com/admin.png",
          username: "admin-renamed",
        },
      }),
    );

    const result = await updateAccountProfile(
      {
        username: "admin-renamed",
        full_name: "Admin Renamed",
        email: "admin-renamed@example.com",
        avatar_url: "https://cdn.example.com/admin.png",
      },
      session,
    );

    expect(result.user.username).toBe("admin-renamed");
    expect(result.user.full_name).toBe("Admin Renamed");
    expect(result.user.email).toBe("admin-renamed@example.com");
    expect(result.user.avatar_url).toBe("https://cdn.example.com/admin.png");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/account/me",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          username: "admin-renamed",
          full_name: "Admin Renamed",
          email: "admin-renamed@example.com",
          avatar_url: "https://cdn.example.com/admin.png",
        }),
        headers: expect.any(Headers),
      }),
    );
  });
});
