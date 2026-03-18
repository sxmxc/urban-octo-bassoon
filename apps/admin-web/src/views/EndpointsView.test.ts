import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/vue";
import { flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { defineComponent } from "vue";
import EndpointsView from "./EndpointsView.vue";
import {
  getCurrentRouteImplementation,
  listConnections,
  listExecutions,
  listEndpoints,
  listRouteDeployments,
} from "../api/admin";
import { vuetify } from "../plugins/vuetify";
import type { Connection, Endpoint, EndpointDraft, ExecutionRun, RouteDeployment, RouteImplementation } from "../types/endpoints";

const authStub = vi.hoisted(() => ({
  logout: vi.fn(),
  canPreviewRoutes: { value: true },
  canWriteRoutes: { value: true },
  mustChangePassword: { value: false },
  session: {
    value: {
      expires_at: "2026-03-16T00:00:00Z",
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
        password_changed_at: "2026-03-16T00:00:00Z",
        created_at: "2026-03-16T00:00:00Z",
        updated_at: "2026-03-16T00:00:00Z",
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
    listConnections: vi.fn(),
    listExecutions: vi.fn(),
    listEndpoints: vi.fn(),
    listRouteDeployments: vi.fn(),
    createEndpoint: vi.fn(),
    updateEndpoint: vi.fn(),
    deleteEndpoint: vi.fn(),
  };
});

// eslint-disable-next-line vue/one-component-per-file
const EndpointCatalogStub = defineComponent({
  props: {
    activeEndpointId: {
      type: Number,
      default: null,
    },
    allowCreate: {
      type: Boolean,
      default: true,
    },
    allowDuplicate: {
      type: Boolean,
      default: true,
    },
    endpoints: {
      type: Array as () => Endpoint[],
      required: true,
    },
    error: {
      type: String,
      default: null,
    },
    loading: {
      type: Boolean,
      default: false,
    },
  },
  emits: ["create", "duplicate", "refresh", "select"],
  template: `
    <div>
      <button type="button" @click="$emit('refresh')">Refresh catalog</button>
      <button type="button" @click="$emit('select', endpoints[0]?.id)" :disabled="!endpoints.length">Select first</button>
      <div data-testid="catalog-error">{{ error ?? "" }}</div>
      <div data-testid="catalog-loading">{{ loading ? "loading" : "idle" }}</div>
      <div data-testid="catalog-active">{{ activeEndpointId ?? "" }}</div>
      <div data-testid="catalog-allow-create">{{ allowCreate ? "yes" : "no" }}</div>
      <div data-testid="catalog-allow-duplicate">{{ allowDuplicate ? "yes" : "no" }}</div>
      <div data-testid="catalog-names">{{ endpoints.map((endpoint) => endpoint.name).join(" | ") }}</div>
    </div>
  `,
});

// eslint-disable-next-line vue/one-component-per-file
const EndpointSettingsFormStub = defineComponent({
  props: {
    draft: {
      type: Object as () => EndpointDraft,
      required: true,
    },
    isCreating: {
      type: Boolean,
      default: false,
    },
    showContractCard: {
      type: Boolean,
      default: true,
    },
  },
  emits: ["change", "delete", "duplicate", "open-schema", "preview", "submit"],
  template: `
    <div>
      <div v-if="showContractCard">
        <div data-testid="identity-fields">Name Method Path</div>
        <button type="button">{{ isCreating ? "Create route" : "Save changes" }}</button>
      </div>
      <div data-testid="draft-name">{{ draft.name }}</div>
      <button type="button" @click="$emit('change', { name: 'Working copy' })">Edit draft</button>
    </div>
  `,
});

// eslint-disable-next-line vue/one-component-per-file
const RouteFlowEditorStub = defineComponent({
  props: {
    modelValue: {
      type: Object,
      required: true,
    },
    availableConnections: {
      type: Array as () => Connection[],
      default: () => [],
    },
    errorMessage: {
      type: String,
      default: null,
    },
    successStatusCode: {
      type: Number,
      default: 200,
    },
  },
  emits: ["update:modelValue", "validation-change", "focus-mode-change"],
  template: `
    <div data-testid="route-flow-editor">
      <div data-testid="route-flow-success">{{ successStatusCode }}</div>
      <div data-testid="route-flow-connections">{{ availableConnections.length }}</div>
      <div data-testid="route-flow-error">{{ errorMessage ?? "" }}</div>
      <button type="button" @click="$emit('focus-mode-change', true)">Enter focus mode</button>
    </div>
  `,
});

function createRouterInstance() {
  const viewStub = { template: "<div />" };

  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/login", name: "login", component: viewStub },
      { path: "/endpoints", name: "endpoints-browse", component: viewStub },
      { path: "/endpoints/new", name: "endpoints-create", component: viewStub },
      { path: "/endpoints/:endpointId", name: "endpoints-edit", component: viewStub },
      { path: "/endpoints/:endpointId/schema", name: "schema-editor", component: viewStub },
      { path: "/endpoints/:endpointId/preview", name: "endpoint-preview", component: viewStub },
    ],
  });
}

function createEndpoint(id: number, overrides: Partial<Endpoint> = {}): Endpoint {
  return {
    id,
    name: `Endpoint ${id}`,
    slug: `endpoint-${id}`,
    method: "GET",
    path: `/api/resource-${id}`,
    category: id % 2 === 0 ? "billing" : "users",
    tags: [id % 2 === 0 ? "billing" : "users"],
    summary: null,
    description: null,
    enabled: true,
    auth_mode: "none",
    request_schema: {},
    response_schema: {},
    success_status_code: 200,
    error_rate: 0,
    latency_min_ms: 0,
    latency_max_ms: 0,
    seed_key: null,
    created_at: "2026-03-16T00:00:00Z",
    updated_at: "2026-03-16T00:00:00Z",
    ...overrides,
  };
}

function createImplementation(routeId: number): RouteImplementation {
  return {
    id: routeId,
    route_id: routeId,
    version: 1,
    is_draft: true,
    flow_definition: {
      schema_version: 1,
      nodes: [
        { id: "trigger", type: "api_trigger", config: {} },
        { id: "response", type: "set_response", config: { status_code: 200, body: { status: "ok" } } },
      ],
      edges: [{ source: "trigger", target: "response" }],
    },
    created_at: "2026-03-18T00:00:00Z",
    updated_at: "2026-03-18T00:00:00Z",
  };
}

function createDeployment(routeId: number): RouteDeployment {
  return {
    id: routeId,
    route_id: routeId,
    implementation_id: routeId,
    environment: "production",
    is_active: true,
    published_at: "2026-03-18T00:00:00Z",
    created_at: "2026-03-18T00:00:00Z",
    updated_at: "2026-03-18T00:00:00Z",
  };
}

function createExecution(routeId: number): ExecutionRun {
  return {
    id: routeId,
    route_id: routeId,
    deployment_id: routeId,
    implementation_id: routeId,
    environment: "production",
    method: "GET",
    path: `/api/resource-${routeId}`,
    status: "success",
    request_data: {
      path_parameters: {},
      query_parameters: {},
      body_present: false,
    },
    response_status_code: 200,
    response_body: { status: "ok" },
    error_message: null,
    started_at: "2026-03-18T00:00:00Z",
    completed_at: "2026-03-18T00:00:01Z",
  };
}

function createConnection(id: number): Connection {
  return {
    id,
    name: `Connection ${id}`,
    connector_type: "http",
    description: null,
    config: {},
    is_active: true,
    created_at: "2026-03-18T00:00:00Z",
    updated_at: "2026-03-18T00:00:00Z",
  };
}

async function renderView(path: string, mode: "browse" | "create" | "edit") {
  const router = createRouterInstance();
  await router.push(path);
  await router.isReady();

  return {
    router,
    ...render(EndpointsView, {
      props: {
        mode,
      },
      global: {
        plugins: [vuetify, router],
        stubs: {
          EndpointCatalog: EndpointCatalogStub,
          EndpointSettingsForm: EndpointSettingsFormStub,
          RouteFlowEditor: RouteFlowEditorStub,
        },
      },
    }),
  };
}

describe("EndpointsView", () => {
  beforeEach(() => {
    vi.mocked(getCurrentRouteImplementation).mockReset();
    vi.mocked(listConnections).mockReset();
    vi.mocked(listExecutions).mockReset();
    vi.mocked(listEndpoints).mockReset();
    vi.mocked(listRouteDeployments).mockReset();
    authStub.logout.mockReset();
    authStub.canPreviewRoutes.value = true;
    authStub.canWriteRoutes.value = true;
    authStub.mustChangePassword.value = false;
    vi.mocked(getCurrentRouteImplementation).mockResolvedValue(createImplementation(1));
    vi.mocked(listRouteDeployments).mockResolvedValue([createDeployment(1)]);
    vi.mocked(listExecutions).mockResolvedValue([createExecution(1)]);
    vi.mocked(listConnections).mockResolvedValue([createConnection(1)]);
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("refreshes the catalog in the background without overwriting a dirty selected draft", async () => {
    vi.useFakeTimers();
    vi.mocked(listEndpoints)
      .mockResolvedValueOnce([
        createEndpoint(1, { name: "List users" }),
        createEndpoint(2, { name: "List invoices" }),
      ])
      .mockResolvedValueOnce([
        createEndpoint(1, {
          name: "List users (remote)",
          updated_at: "2026-03-16T00:01:00Z",
        }),
        createEndpoint(2, {
          name: "List invoices (remote)",
          updated_at: "2026-03-16T00:01:00Z",
        }),
      ]);

    await renderView("/endpoints/1", "edit");
    await flushPromises();

    expect(screen.getByTestId("draft-name")).toHaveTextContent("List users");

    await fireEvent.click(screen.getByRole("button", { name: "Edit draft" }));
    expect(screen.getByTestId("draft-name")).toHaveTextContent("Working copy");

    await vi.advanceTimersByTimeAsync(30_000);
    await flushPromises();

    expect(vi.mocked(listEndpoints)).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("catalog-names")).toHaveTextContent("List users | List invoices (remote)");
    expect(screen.getByTestId("draft-name")).toHaveTextContent("Working copy");
  });

  it("applies a newer selected endpoint version when the current draft is still clean", async () => {
    vi.useFakeTimers();
    vi.mocked(listEndpoints)
      .mockResolvedValueOnce([
        createEndpoint(1, { name: "List users" }),
        createEndpoint(2, { name: "List invoices" }),
      ])
      .mockResolvedValueOnce([
        createEndpoint(1, {
          name: "List users (remote)",
          updated_at: "2026-03-16T00:01:00Z",
        }),
        createEndpoint(2, { name: "List invoices" }),
      ]);

    await renderView("/endpoints/1", "edit");
    await flushPromises();

    expect(screen.getByTestId("draft-name")).toHaveTextContent("List users");

    await vi.advanceTimersByTimeAsync(30_000);
    await flushPromises();

    expect(screen.getByTestId("draft-name")).toHaveTextContent("List users (remote)");
  });

  it("routes catalog selection to preview for read-only viewers", async () => {
    authStub.canWriteRoutes.value = false;

    vi.mocked(listEndpoints).mockResolvedValue([
      createEndpoint(1, { name: "List users" }),
    ]);

    const { router } = await renderView("/endpoints", "browse");
    await flushPromises();
    const pushSpy = vi.spyOn(router, "push");

    expect(screen.getByTestId("catalog-allow-create")).toHaveTextContent("no");
    expect(screen.getByTestId("catalog-allow-duplicate")).toHaveTextContent("no");

    await fireEvent.click(screen.getByRole("button", { name: "Select first" }));
    await flushPromises();

    expect(pushSpy).toHaveBeenCalledWith({
      name: "endpoint-preview",
      params: { endpointId: 1 },
    });
  });

  it("keeps route identity fields and the create action visible on the overview create flow", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([]);

    await renderView("/endpoints/new", "create");
    await flushPromises();

    expect(screen.getByTestId("identity-fields")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create route" })).toBeInTheDocument();
  });

  it("keeps route identity fields and the save action visible on the overview edit flow", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);

    await renderView("/endpoints/1", "edit");
    await flushPromises();

    expect(screen.getByTestId("identity-fields")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument();
  });

  it("shows route-first tabs and loads flow scaffolding for an existing route", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);

    await renderView("/endpoints/1?tab=flow", "edit");
    await flushPromises();

    expect(screen.getByRole("tab", { name: "Flow" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("route-flow-editor")).toBeInTheDocument();
    expect(screen.getByTestId("route-flow-success")).toHaveTextContent("200");
    expect(screen.getByTestId("route-flow-connections")).toHaveTextContent("1");
    expect(screen.getByText("Connection 1 · http")).toBeInTheDocument();
    expect(vi.mocked(getCurrentRouteImplementation)).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ token: "session-token" }),
    );
    expect(vi.mocked(listRouteDeployments)).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ token: "session-token" }),
    );
    expect(vi.mocked(listExecutions)).toHaveBeenCalledWith(
      expect.objectContaining({ token: "session-token" }),
      { endpointId: 1, limit: 12 },
    );
  });

  it("hides the shared connections card while the flow editor is in focus mode", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);

    await renderView("/endpoints/1?tab=flow", "edit");
    await flushPromises();

    expect(screen.getByText("Available connections")).toBeInTheDocument();

    await fireEvent.click(screen.getByRole("button", { name: "Enter focus mode" }));
    await flushPromises();

    expect(screen.queryByText("Available connections")).not.toBeInTheDocument();
  });
});
