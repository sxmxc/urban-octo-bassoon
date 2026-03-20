import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/vue";
import { flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import EndpointPreviewView from "./EndpointPreviewView.vue";
import {
  getCurrentRouteImplementation,
  getEndpoint,
  listRouteDeployments,
  previewResponse,
} from "../api/admin";
import { vuetify } from "../plugins/vuetify";
import type { Endpoint, RouteDeployment, RouteImplementation } from "../types/endpoints";

const authStub = vi.hoisted(() => ({
  logout: vi.fn(),
  canPreviewRoutes: { value: true },
  canWriteRoutes: { value: true },
  mustChangePassword: { value: false },
  session: {
    value: {
      expires_at: "2026-03-18T00:00:00Z",
      token: "session-token",
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
        password_changed_at: "2026-03-18T00:00:00Z",
        created_at: "2026-03-18T00:00:00Z",
        updated_at: "2026-03-18T00:00:00Z",
      },
    },
  },
}));

vi.mock("../composables/useAuth", () => ({
  useAuth: () => authStub,
}));

vi.mock("../api/admin", async () => {
  const actual = await vi.importActual<typeof import("../api/admin")>("../api/admin");
  return {
    ...actual,
    getCurrentRouteImplementation: vi.fn(),
    getEndpoint: vi.fn(),
    listRouteDeployments: vi.fn(),
    previewResponse: vi.fn(),
  };
});

function createRouterInstance() {
  const viewStub = { template: "<div />" };

  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/login", name: "login", component: viewStub },
      { path: "/endpoints", name: "endpoints-browse", component: viewStub },
      { path: "/endpoints/:endpointId", name: "endpoints-edit", component: viewStub },
      { path: "/endpoints/:endpointId/schema", name: "schema-editor", component: viewStub },
      { path: "/endpoints/:endpointId/preview", name: "endpoint-preview", component: EndpointPreviewView },
    ],
  });
}

function createEndpoint(overrides: Partial<Endpoint> = {}): Endpoint {
  const enabled = overrides.enabled ?? true;
  return {
    id: 1,
    name: "Inspect order",
    slug: "inspect-order",
    method: "POST",
    path: "/api/orders/{orderId}",
    category: "orders",
    tags: ["orders"],
    summary: null,
    description: null,
    enabled,
    auth_mode: "none",
    request_schema: {
      type: "object",
      properties: {
        value: { type: "number" },
      },
      "x-request": {
        path: {
          type: "object",
          properties: {
            orderId: { type: "string", description: "Order id" },
          },
          required: ["orderId"],
        },
        query: {
          type: "object",
          properties: {
            status: { type: "string", description: "Status filter" },
          },
        },
      },
    },
    response_schema: {
      type: "object",
      properties: {
        source: { type: "string" },
      },
    },
    success_status_code: 200,
    error_rate: 0,
    latency_min_ms: 0,
    latency_max_ms: 0,
    seed_key: "seed-1",
    created_at: "2026-03-18T00:00:00Z",
    updated_at: "2026-03-18T00:00:00Z",
    publication_status: overrides.publication_status ?? {
      code: enabled ? "published_live" : "disabled",
      label: enabled ? "Published live" : "Disabled",
      tone: enabled ? "success" : "error",
      enabled,
      is_public: enabled,
      is_live: enabled,
      uses_legacy_mock: false,
      has_saved_implementation: true,
      has_runtime_history: true,
      has_deployment_history: true,
      has_active_deployment: enabled,
      active_deployment_environment: enabled ? "production" : null,
      active_implementation_id: enabled ? 4 : null,
      active_deployment_id: enabled ? 4 : null,
    },
    ...overrides,
  };
}

function createImplementation(overrides: Partial<RouteImplementation> = {}): RouteImplementation {
  return {
    id: 9,
    route_id: 1,
    version: 3,
    is_draft: true,
    flow_definition: {
      schema_version: 1,
      nodes: [],
      edges: [],
    },
    created_at: "2026-03-18T00:00:00Z",
    updated_at: "2026-03-18T00:00:00Z",
    ...overrides,
  };
}

function createDeployment(overrides: Partial<RouteDeployment> = {}): RouteDeployment {
  return {
    id: 4,
    route_id: 1,
    implementation_id: 4,
    environment: "production",
    is_active: true,
    published_at: "2026-03-18T00:00:00Z",
    created_at: "2026-03-18T00:00:00Z",
    updated_at: "2026-03-18T00:00:00Z",
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    headers: new Headers({ "content-type": "application/json" }),
    text: async () => JSON.stringify(body),
  } as Response;
}

async function renderView(path = "/endpoints/1/preview") {
  const router = createRouterInstance();
  await router.push(path);
  await router.isReady();

  return render(EndpointPreviewView, {
    global: {
      plugins: [vuetify, router],
    },
  });
}

describe("EndpointPreviewView", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.mocked(getEndpoint).mockReset();
    vi.mocked(getCurrentRouteImplementation).mockReset();
    vi.mocked(listRouteDeployments).mockReset();
    vi.mocked(previewResponse).mockReset();
    authStub.logout.mockReset();
    authStub.canWriteRoutes.value = true;
    authStub.mustChangePassword.value = false;

    class ResizeObserverStub {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    }

    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("ResizeObserver", ResizeObserverStub);

    vi.mocked(getEndpoint).mockResolvedValue(createEndpoint());
    vi.mocked(getCurrentRouteImplementation).mockResolvedValue(createImplementation());
    vi.mocked(listRouteDeployments).mockResolvedValue([createDeployment()]);
    vi.mocked(previewResponse).mockResolvedValue({
      preview: {
        source: "contract",
      },
    });
    fetchMock.mockResolvedValue(jsonResponse({ source: "live" }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("separates contract preview generation from the live request path", async () => {
    const view = await renderView();
    await flushPromises();

    expect(screen.getByText("Compare admin-only contract previews with live/public request results for this route.")).toBeInTheDocument();
    expect(screen.getByText("Schema-driven contract preview")).toBeInTheDocument();
    expect(screen.getByText("Implementation 4 is live")).toBeInTheDocument();
    expect(screen.getByText("Draft v3 is ahead of live")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Response preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate contract preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send live request" })).toBeInTheDocument();

    expect(vi.mocked(previewResponse)).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "object",
      }),
      "seed-1",
      expect.objectContaining({ orderId: expect.any(String) }),
      expect.objectContaining({ token: "session-token" }),
      {
        queryParameters: { status: "" },
        requestBody: { value: 1 },
      },
    );

    const requestBodyField = screen.getByLabelText("Request body") as HTMLTextAreaElement;
    expect(JSON.parse(requestBodyField.value)).toEqual({ value: 1 });

    await fireEvent.update(screen.getByLabelText("Path parameter: orderId"), "ord-123");
    await fireEvent.update(screen.getByLabelText("Query parameter: status"), "queued");
    await fireEvent.update(screen.getByLabelText("Request body"), "{\"value\":1}");
    await fireEvent.click(screen.getByRole("button", { name: "Request preview" }));
    await flushPromises();

    const requestPreviewBlock = view.container.querySelectorAll("pre.code-block")[0];
    expect(requestPreviewBlock).toHaveTextContent('"method": "POST"');
    expect(requestPreviewBlock).toHaveTextContent('"path_template": "/api/orders/{orderId}"');
    expect(requestPreviewBlock).toHaveTextContent('"resolved_path": "/api/orders/ord-123"');
    expect(requestPreviewBlock).toHaveTextContent('"query_string": "status=queued"');
    expect(requestPreviewBlock).toHaveTextContent('"request_body": {');
    expect(requestPreviewBlock).toHaveTextContent('"value": 1');

    await fireEvent.click(screen.getByRole("button", { name: "Response preview" }));
    await fireEvent.click(screen.getByRole("button", { name: "Generate contract preview" }));
    await flushPromises();

    expect(vi.mocked(previewResponse)).toHaveBeenLastCalledWith(
      expect.objectContaining({
        type: "object",
      }),
      "seed-1",
      { orderId: "ord-123" },
      expect.objectContaining({ token: "session-token" }),
      {
        queryParameters: { status: "queued" },
        requestBody: { value: 1 },
      },
    );
    const codeBlocks = view.container.querySelectorAll("pre.code-block");
    expect(codeBlocks[0]).toHaveTextContent('"source": "contract"');

    await fireEvent.click(screen.getByRole("button", { name: "Send live request" }));
    await flushPromises();

    expect(vi.mocked(previewResponse)).toHaveBeenCalledTimes(3);
    expect(vi.mocked(previewResponse)).toHaveBeenLastCalledWith(
      expect.objectContaining({
        type: "object",
      }),
      "seed-1",
      { orderId: "ord-123" },
      expect.objectContaining({ token: "session-token" }),
      {
        queryParameters: { status: "queued" },
        requestBody: { value: 1 },
      },
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/orders/ord-123?status=queued",
      expect.objectContaining({
        method: "POST",
        body: "{\"value\":1}",
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(codeBlocks[1]).toHaveTextContent('"source": "live"');
  });

  it("routes contract editing back into the route Contract tab", async () => {
    const router = createRouterInstance();
    await router.push("/endpoints/1/preview");
    await router.isReady();
    const pushSpy = vi.spyOn(router, "push");

    render(EndpointPreviewView, {
      global: {
        plugins: [vuetify, router],
      },
    });
    await flushPromises();

    await fireEvent.click(screen.getByRole("button", { name: "Edit contract" }));
    await flushPromises();

    expect(pushSpy).toHaveBeenCalledWith({
      name: "endpoints-edit",
      params: { endpointId: 1 },
      query: { tab: "contract" },
    });
  });

  it("keeps contract preview available when a saved draft has no active deployment", async () => {
    vi.mocked(getEndpoint).mockResolvedValue(createEndpoint({
      publication_status: {
        code: "draft_only",
        label: "Draft only",
        tone: "warning",
        enabled: true,
        is_public: false,
        is_live: false,
        uses_legacy_mock: false,
        has_saved_implementation: true,
        has_runtime_history: true,
        has_deployment_history: false,
        has_active_deployment: false,
        active_deployment_environment: null,
        active_implementation_id: null,
        active_deployment_id: null,
      },
    }));
    vi.mocked(getCurrentRouteImplementation).mockResolvedValue(createImplementation({ id: 7, version: 2 }));
    vi.mocked(listRouteDeployments).mockResolvedValue([]);

    const view = await renderView();
    await flushPromises();

    expect(screen.getAllByText("Draft only").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        "This route has a saved flow draft but no active deployment. Live/public requests return 404 until you publish a flow implementation.",
      ).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Draft v2 is saved")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate contract preview" })).toBeInTheDocument();
    expect(view.container.querySelector("pre.code-block")).toHaveTextContent('"source": "contract"');
  });

  it("keeps the tester usable when runtime-state metadata fails to load", async () => {
    vi.mocked(getCurrentRouteImplementation).mockRejectedValue(new Error("runtime metadata timeout"));

    const view = await renderView();
    await flushPromises();

    expect(
      screen.getByText(
        "Live deployment status is temporarily unavailable. You can still generate contract previews and send public requests from this page.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Runtime state unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText("Live status unavailable")).toBeInTheDocument();
    expect(screen.getByText("Draft status unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate contract preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send live request" })).toBeInTheDocument();
    expect(view.container.querySelector("pre.code-block")).toHaveTextContent('"source": "contract"');
  });

  it("prefills shared inputs from replay query params and explains when body replay is unavailable", async () => {
    await renderView(
      "/endpoints/1/preview?replayRunId=77&replayBodyCaptured=0&replay_path_orderId=ord-9&replay_query_status=queued",
    );
    await flushPromises();

    expect(screen.getByDisplayValue("ord-9")).toBeInTheDocument();
    expect(screen.getByDisplayValue("queued")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Replaying run #77: path/query inputs were prefilled, but request body replay is unavailable because only body-presence metadata was captured for this trace.",
      ),
    ).toBeInTheDocument();
    expect(vi.mocked(previewResponse)).toHaveBeenLastCalledWith(
      expect.objectContaining({
        type: "object",
      }),
      "seed-1",
      { orderId: "ord-9" },
      expect.objectContaining({ token: "session-token" }),
      {
        queryParameters: { status: "queued" },
        requestBody: { value: 1 },
      },
    );
  });

  it("leaves the request body input blank when a body route has no saved request-body contract", async () => {
    vi.mocked(getEndpoint).mockResolvedValue(
      createEndpoint({
        request_schema: null,
      }),
    );

    await renderView();
    await flushPromises();

    const requestBodyField = screen.getByLabelText("Request body") as HTMLTextAreaElement;
    expect(requestBodyField.value).toBe("");
    expect(vi.mocked(previewResponse)).toHaveBeenLastCalledWith(
      expect.objectContaining({
        type: "object",
      }),
      "seed-1",
      { orderId: "sample-orderId" },
      expect.objectContaining({ token: "session-token" }),
      {
        queryParameters: {},
        requestBody: null,
      },
    );
  });

  it("explains when a replayed trace has no path or query inputs to prefill", async () => {
    vi.mocked(getEndpoint).mockResolvedValue(
      createEndpoint({
        method: "GET",
        path: "/api/quote",
        request_schema: {
          type: "object",
          properties: {},
          required: [],
        },
      }),
    );

    await renderView("/endpoints/1/preview?replayRunId=30&replayBodyCaptured=none");
    await flushPromises();

    expect(
      screen.getByText("Replaying run #30: this trace had no path or query inputs to prefill."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Path parameter: orderId")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Query parameter: status")).not.toBeInTheDocument();
  });
});
