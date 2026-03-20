import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/vue";
import { flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { defineComponent } from "vue";
import EndpointsView from "./EndpointsView.vue";
import {
  deleteEndpoint,
  getExecution,
  getExecutionTelemetryOverview,
  getCurrentRouteImplementation,
  listConnections,
  listExecutions,
  listEndpoints,
  listRouteDeployments,
  publishRouteImplementation,
  saveCurrentRouteImplementation,
  unpublishRouteDeployment,
  updateEndpoint,
} from "../api/admin";
import { vuetify } from "../plugins/vuetify";
import type {
  Connection,
  Endpoint,
  EndpointDraft,
  ExecutionRun,
  ExecutionRunDetail,
  ExecutionTelemetryOverview,
  RouteDeployment,
  RouteImplementation,
} from "../types/endpoints";

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
    getExecutionTelemetryOverview: vi.fn(),
    listEndpoints: vi.fn(),
    listRouteDeployments: vi.fn(),
    getExecution: vi.fn(),
    publishRouteImplementation: vi.fn(),
    saveCurrentRouteImplementation: vi.fn(),
    unpublishRouteDeployment: vi.fn(),
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
        <button type="button" @click="$emit('open-schema')">Open contract</button>
        <button type="button" @click="$emit('delete')">Delete route</button>
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
    saveDisabled: {
      type: Boolean,
      default: false,
    },
    saveLoading: {
      type: Boolean,
      default: false,
    },
    successStatusCode: {
      type: Number,
      default: 200,
    },
  },
  emits: ["update:modelValue", "validation-change", "focus-mode-change", "save-requested"],
  template: `
    <div data-testid="route-flow-editor">
      <div data-testid="route-flow-success">{{ successStatusCode }}</div>
      <div data-testid="route-flow-connections">{{ availableConnections.length }}</div>
      <div data-testid="route-flow-error">{{ errorMessage ?? "" }}</div>
      <button type="button" @click="$emit('focus-mode-change', true)">Enter focus mode</button>
      <button
        type="button"
        @click="$emit('update:modelValue', {
          ...modelValue,
          nodes: [
            ...modelValue.nodes,
            { id: 'draft-change', type: 'transform', name: 'Draft change', config: {}, position: { x: 0, y: 0 } },
          ],
          edges: [...modelValue.edges],
        })"
      >
        Make flow dirty
      </button>
      <button type="button" :disabled="saveDisabled || saveLoading" @click="$emit('save-requested')">Request flow save</button>
    </div>
  `,
});

// eslint-disable-next-line vue/one-component-per-file
const RouteContractEditorStub = defineComponent({
  props: {
    activeTab: {
      type: String,
      default: "response",
    },
    activeRequestSection: {
      type: String,
      default: "body",
    },
  },
  emits: ["update:activeTab", "update:activeRequestSection", "update:requestSchema", "update:responseSchema", "update:seedKey"],
  template: `
    <div data-testid="route-contract-editor">
      <div data-testid="route-contract-editor-tab">{{ activeTab }}</div>
      <div data-testid="route-contract-editor-request-section">{{ activeRequestSection }}</div>
      <button type="button" @click="$emit('update:activeTab', 'request')">Show request schema</button>
      <button type="button" @click="$emit('update:activeTab', 'response')">Show response schema</button>
      <button
        type="button"
        @click="$emit('update:responseSchema', { type: 'object', properties: { status: { type: 'string' } } })"
      >
        Edit response schema
      </button>
      <button
        type="button"
        @click="$emit('update:requestSchema', {
          type: 'object',
          'x-request': {
            query: {
              type: 'object',
              properties: {
                '': { type: 'string' },
              },
              required: [],
              'x-builder': {
                order: [''],
              },
            },
          },
        })"
      >
        Edit invalid request schema
      </button>
    </div>
  `,
});

function createRouterInstance() {
  const viewStub = { template: "<div />" };

  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/login", name: "login", component: viewStub },
      { path: "/connectors", name: "connectors", component: viewStub },
      { path: "/endpoints", name: "endpoints-browse", component: viewStub },
      { path: "/endpoints/new", name: "endpoints-create", component: viewStub },
      { path: "/endpoints/:endpointId", name: "endpoints-edit", component: viewStub },
      { path: "/endpoints/:endpointId/schema", name: "schema-editor", component: viewStub },
      { path: "/endpoints/:endpointId/preview", name: "endpoint-preview", component: viewStub },
    ],
  });
}

function createEndpoint(id: number, overrides: Partial<Endpoint> = {}): Endpoint {
  const enabled = overrides.enabled ?? true;
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
    enabled,
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
      active_implementation_id: enabled ? id : null,
      active_deployment_id: enabled ? id : null,
    },
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

function createDeployment(routeId: number, overrides: Partial<RouteDeployment> = {}): RouteDeployment {
  return {
    id: routeId,
    route_id: routeId,
    implementation_id: routeId,
    environment: "production",
    is_active: true,
    published_at: "2026-03-18T00:00:00Z",
    created_at: "2026-03-18T00:00:00Z",
    updated_at: "2026-03-18T00:00:00Z",
    ...overrides,
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

function createExecutionDetail(routeId: number): ExecutionRunDetail {
  return {
    ...createExecution(routeId),
    request_data: {
      path_parameters: {
        orderId: "ord-42",
      },
      query_parameters: {
        include: "items",
      },
      body_present: true,
    },
    steps: [
      {
        id: 11,
        node_id: "trigger",
        node_type: "api_trigger",
        order_index: 1,
        status: "success",
        input_data: { method: "GET" },
        output_data: { request: true },
        error_message: null,
        started_at: "2026-03-18T00:00:00Z",
        completed_at: "2026-03-18T00:00:00Z",
      },
      {
        id: 12,
        node_id: "response",
        node_type: "set_response",
        order_index: 2,
        status: "success",
        input_data: { status_code: 200 },
        output_data: { done: true },
        error_message: null,
        started_at: "2026-03-18T00:00:00Z",
        completed_at: "2026-03-18T00:00:01Z",
      },
    ],
  };
}

function createConnection(id: number): Connection {
  return {
    id,
    project: "default",
    environment: "production",
    name: `Connection ${id}`,
    connector_type: "http",
    description: null,
    config: {},
    is_active: true,
    created_at: "2026-03-18T00:00:00Z",
    updated_at: "2026-03-18T00:00:00Z",
  };
}

function createTelemetryOverview(overrides: Partial<ExecutionTelemetryOverview> = {}): ExecutionTelemetryOverview {
  return {
    sample_limit: 200,
    sampled_runs: 0,
    sampled_steps: 0,
    route_count: 0,
    success_runs: 0,
    error_runs: 0,
    success_rate: null,
    average_response_time_ms: null,
    p95_response_time_ms: null,
    average_flow_time_ms: null,
    p95_flow_time_ms: null,
    average_steps_per_run: null,
    latest_completed_at: null,
    precise_step_run_count: 0,
    slow_routes: [],
    slow_flow_steps: [],
    ...overrides,
  };
}

function createDeferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T | PromiseLike<T>) => void;
  reject: (reason?: unknown) => void;
} {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });

  return { promise, resolve, reject };
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
          RouteContractEditor: RouteContractEditorStub,
          RouteFlowEditor: RouteFlowEditorStub,
        },
      },
    }),
  };
}

describe("EndpointsView", () => {
  beforeEach(() => {
    vi.mocked(deleteEndpoint).mockReset();
    vi.mocked(getCurrentRouteImplementation).mockReset();
    vi.mocked(getExecution).mockReset();
    vi.mocked(getExecutionTelemetryOverview).mockReset();
    vi.mocked(listConnections).mockReset();
    vi.mocked(listExecutions).mockReset();
    vi.mocked(listEndpoints).mockReset();
    vi.mocked(listRouteDeployments).mockReset();
    vi.mocked(publishRouteImplementation).mockReset();
    vi.mocked(saveCurrentRouteImplementation).mockReset();
    vi.mocked(unpublishRouteDeployment).mockReset();
    vi.mocked(updateEndpoint).mockReset();
    authStub.logout.mockReset();
    authStub.canPreviewRoutes.value = true;
    authStub.canWriteRoutes.value = true;
    authStub.mustChangePassword.value = false;
    vi.mocked(getCurrentRouteImplementation).mockResolvedValue(createImplementation(1));
    vi.mocked(listRouteDeployments).mockResolvedValue([createDeployment(1)]);
    vi.mocked(listExecutions).mockResolvedValue([createExecution(1)]);
    vi.mocked(getExecutionTelemetryOverview).mockResolvedValue(createTelemetryOverview());
    vi.mocked(listConnections).mockResolvedValue([createConnection(1)]);
    vi.mocked(getExecution).mockResolvedValue(createExecutionDetail(1));
    vi.mocked(publishRouteImplementation).mockResolvedValue(createDeployment(1));
    vi.mocked(saveCurrentRouteImplementation).mockResolvedValue(createImplementation(1));
    vi.mocked(unpublishRouteDeployment).mockResolvedValue(
      createDeployment(1, {
        is_active: false,
        updated_at: "2026-03-18T00:01:00Z",
      }),
    );
    vi.mocked(updateEndpoint).mockResolvedValue(
      createEndpoint(1, {
        updated_at: "2026-03-16T00:01:00Z",
      }),
    );
    vi.mocked(deleteEndpoint).mockResolvedValue(null);
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

  it("shows browse-mode route metrics from the loaded catalog", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([
      createEndpoint(1, {
        name: "Live GET",
        method: "GET",
        category: "users",
        publication_status: {
          code: "published_live",
          label: "Published live",
          tone: "success",
          enabled: true,
          is_public: true,
          is_live: true,
          uses_legacy_mock: false,
          has_saved_implementation: true,
          has_runtime_history: true,
          has_deployment_history: true,
          has_active_deployment: true,
          active_deployment_environment: "production",
          active_implementation_id: 1,
          active_deployment_id: 1,
        },
      }),
      createEndpoint(2, {
        name: "Legacy POST",
        method: "POST",
        category: "operations",
        publication_status: {
          code: "legacy_mock",
          label: "Legacy mock",
          tone: "secondary",
          enabled: true,
          is_public: true,
          is_live: false,
          uses_legacy_mock: true,
          has_saved_implementation: false,
          has_runtime_history: false,
          has_deployment_history: false,
          has_active_deployment: false,
          active_deployment_environment: null,
          active_implementation_id: null,
          active_deployment_id: null,
        },
      }),
      createEndpoint(3, {
        name: "Draft GET",
        method: "GET",
        category: "users",
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
      }),
      createEndpoint(4, {
        name: "Disabled DELETE",
        method: "DELETE",
        category: "",
        enabled: false,
        publication_status: {
          code: "disabled",
          label: "Disabled",
          tone: "error",
          enabled: false,
          is_public: false,
          is_live: false,
          uses_legacy_mock: false,
          has_saved_implementation: false,
          has_runtime_history: false,
          has_deployment_history: false,
          has_active_deployment: false,
          active_deployment_environment: null,
          active_implementation_id: null,
          active_deployment_id: null,
        },
      }),
    ]);

    await renderView("/endpoints", "browse");
    await flushPromises();

    expect(screen.getByTestId("browse-metric-total-routes")).toHaveTextContent("4");
    expect(screen.getByTestId("browse-metric-public-routes")).toHaveTextContent("2");
    expect(screen.getByTestId("browse-metric-private-routes")).toHaveTextContent("2");
    expect(screen.getByTestId("browse-metric-disabled-routes")).toHaveTextContent("1");

    expect(screen.getByTestId("browse-method-mix")).toHaveTextContent("GET · 2");
    expect(screen.getByTestId("browse-method-mix")).toHaveTextContent("POST · 1");
    expect(screen.getByTestId("browse-method-mix")).toHaveTextContent("DELETE · 1");

    expect(screen.getByTestId("browse-category-mix")).toHaveTextContent("users · 2");
    expect(screen.getByTestId("browse-category-mix")).toHaveTextContent("operations · 1");
    expect(screen.getByTestId("browse-category-mix")).toHaveTextContent("Uncategorized · 1");
  });

  it("shows browse-mode telemetry metrics and slow-route summaries from execution history", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([
      createEndpoint(1, {
        name: "Fast route",
        method: "GET",
        path: "/api/fast-route",
      }),
      createEndpoint(2, {
        name: "Slow route",
        method: "POST",
        path: "/api/slow-route",
      }),
    ]);
    vi.mocked(getExecutionTelemetryOverview).mockResolvedValue(
      createTelemetryOverview({
        sampled_runs: 8,
        sampled_steps: 24,
        route_count: 2,
        success_runs: 7,
        error_runs: 1,
        success_rate: 87.5,
        average_response_time_ms: 182.4,
        p95_response_time_ms: 420.9,
        average_flow_time_ms: 164.2,
        p95_flow_time_ms: 388.6,
        average_steps_per_run: 3,
        latest_completed_at: "2026-03-20T03:40:00Z",
        precise_step_run_count: 6,
        slow_routes: [
          {
            route_id: 2,
            total_runs: 5,
            success_runs: 4,
            error_runs: 1,
            success_rate: 80,
            average_response_time_ms: 320.1,
            p95_response_time_ms: 501.2,
            max_response_time_ms: 540.2,
            average_flow_time_ms: 285.4,
            p95_flow_time_ms: 472.6,
            latest_completed_at: "2026-03-20T03:40:00Z",
          },
        ],
        slow_flow_steps: [
          {
            route_id: 2,
            node_type: "postgres_query",
            total_steps: 4,
            average_duration_ms: 210.4,
            p95_duration_ms: 340.9,
            max_duration_ms: 351.5,
            latest_completed_at: "2026-03-20T03:39:58Z",
          },
        ],
      }),
    );

    await renderView("/endpoints", "browse");
    await flushPromises();

    expect(screen.getByTestId("browse-telemetry-runs")).toHaveTextContent("8");
    expect(screen.getByTestId("browse-telemetry-avg-response")).toHaveTextContent("182 ms");
    expect(screen.getByTestId("browse-telemetry-p95-response")).toHaveTextContent("421 ms");
    expect(screen.getByTestId("browse-telemetry-avg-flow")).toHaveTextContent("164 ms");

    expect(screen.getByTestId("browse-telemetry-slow-routes")).toHaveTextContent("Slow route");
    expect(screen.getByTestId("browse-telemetry-slow-routes")).toHaveTextContent("POST /api/slow-route");
    expect(screen.getByTestId("browse-telemetry-slow-routes")).toHaveTextContent("Avg 320 ms");
    expect(screen.getByTestId("browse-telemetry-slow-routes")).toHaveTextContent("P95 501 ms");

    expect(screen.getByTestId("browse-telemetry-slow-steps")).toHaveTextContent("postgres_query");
    expect(screen.getByTestId("browse-telemetry-slow-steps")).toHaveTextContent("Avg 210 ms");
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

  it("routes overview contract actions to the route Contract tab", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);

    const { router } = await renderView("/endpoints/1", "edit");
    await flushPromises();
    const pushSpy = vi.spyOn(router, "push");

    await fireEvent.click(screen.getByRole("button", { name: "Open contract" }));
    await flushPromises();

    expect(pushSpy).toHaveBeenCalledWith({
      name: "endpoints-edit",
      params: { endpointId: 1 },
      query: { tab: "contract" },
    });
  });

  it("renders the embedded contract editor and keeps contract tab selection in query state", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);

    const { router } = await renderView("/endpoints/1?tab=contract&contractTab=request", "edit");
    await flushPromises();
    const replaceSpy = vi.spyOn(router, "replace");

    expect(screen.getByTestId("route-contract-editor")).toBeInTheDocument();
    expect(screen.getByTestId("route-contract-editor-tab")).toHaveTextContent("request");

    await fireEvent.click(screen.getByRole("button", { name: "Show response schema" }));
    await flushPromises();

    expect(replaceSpy).toHaveBeenCalledWith({
      query: {
        tab: "contract",
      },
    });
  });

  it("shows contract validation errors when in-tab contract save fails", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);

    await renderView("/endpoints/1?tab=contract", "edit");
    await flushPromises();

    await fireEvent.click(screen.getByRole("button", { name: "Edit invalid request schema" }));
    await fireEvent.click(screen.getByRole("button", { name: "Save contract" }));
    await flushPromises();

    expect(screen.getByText("Every query parameter needs a name before you can save.")).toBeInTheDocument();
    expect(screen.getByTestId("route-contract-editor-tab")).toHaveTextContent("request");
    expect(screen.getByTestId("route-contract-editor-request-section")).toHaveTextContent("query");
  });

  it("saves contract changes without persisting dirty overview fields", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);
    vi.mocked(updateEndpoint).mockResolvedValue(
      createEndpoint(1, {
        name: "List users",
        response_schema: {
          type: "object",
          properties: {
            status: { type: "string" },
          },
        },
        updated_at: "2026-03-16T00:02:00Z",
      }),
    );

    const { router } = await renderView("/endpoints/1", "edit");
    await flushPromises();

    await fireEvent.click(screen.getByRole("button", { name: "Edit draft" }));
    await router.push({ name: "endpoints-edit", params: { endpointId: 1 }, query: { tab: "contract" } });
    await flushPromises();

    await fireEvent.click(screen.getByRole("button", { name: "Edit response schema" }));
    await fireEvent.click(screen.getByRole("button", { name: "Save contract" }));
    await flushPromises();

    expect(vi.mocked(updateEndpoint)).toHaveBeenCalledWith(
      1,
      expect.objectContaining({
        name: "List users",
        response_schema: {
          type: "object",
          properties: {
            status: { type: "string" },
          },
        },
      }),
      expect.objectContaining({ token: "session-token" }),
    );

    await router.push({ name: "endpoints-edit", params: { endpointId: 1 } });
    await flushPromises();

    expect(screen.getByTestId("draft-name")).toHaveTextContent("Working copy");
    expect(screen.getByText("Saved contract changes for List users.")).toBeInTheDocument();
  });

  it("deletes the selected route and returns to browse mode", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    const { router } = await renderView("/endpoints/1", "edit");
    await flushPromises();
    const pushSpy = vi.spyOn(router, "push");

    await fireEvent.click(screen.getByRole("button", { name: "Delete route" }));
    await flushPromises();

    expect(confirmSpy).toHaveBeenCalledWith('Delete "List users" from the catalog?');
    expect(vi.mocked(deleteEndpoint)).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ token: "session-token" }),
    );
    expect(pushSpy).toHaveBeenCalledWith({ name: "endpoints-browse" });
    expect(screen.getByTestId("catalog-names")).toHaveTextContent("");
  });

  it("shows route-first tabs and loads flow scaffolding for an existing route", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);

    await renderView("/endpoints/1?tab=flow", "edit");
    await flushPromises();

    expect(screen.getByRole("tab", { name: "Flow" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("route-flow-editor")).toBeInTheDocument();
    expect(screen.getByTestId("route-flow-success")).toHaveTextContent("200");
    expect(screen.getByTestId("route-flow-connections")).toHaveTextContent("1");
    expect(screen.getByTestId("flow-connection-context")).toHaveTextContent("Scope · default / production");
    expect(screen.getByTestId("flow-connection-context")).toHaveTextContent("1 in scope");
    expect(screen.getByTestId("flow-connection-context")).toHaveTextContent("1 total saved");
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

  it("saves flow when the editor emits save-requested", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);

    await renderView("/endpoints/1?tab=flow", "edit");
    await flushPromises();

    expect(screen.getByRole("button", { name: "Request flow save" })).toBeDisabled();

    await fireEvent.click(screen.getByRole("button", { name: "Make flow dirty" }));
    await flushPromises();

    await fireEvent.click(screen.getByRole("button", { name: "Request flow save" }));
    await flushPromises();

    expect(vi.mocked(saveCurrentRouteImplementation)).toHaveBeenCalledWith(
      1,
      expect.objectContaining({
        flow_definition: expect.objectContaining({
          schema_version: 1,
        }),
      }),
      expect.objectContaining({ token: "session-token" }),
    );
  });

  it("opens the dedicated connectors page from flow connector context", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);
    const { router } = await renderView("/endpoints/1?tab=flow", "edit");
    await flushPromises();
    const pushSpy = vi.spyOn(router, "push");

    await fireEvent.click(screen.getByRole("button", { name: "Open Connectors" }));
    await flushPromises();

    expect(pushSpy).toHaveBeenCalledWith({ name: "connectors" });
  });

  it("warns before browser unload when the flow draft is dirty", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);

    await renderView("/endpoints/1?tab=flow", "edit");
    await flushPromises();

    await fireEvent.click(screen.getByRole("button", { name: "Make flow dirty" }));
    await flushPromises();

    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
  });

  it("blocks switching to another route record when unsaved flow changes are not confirmed", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([
      createEndpoint(1, { name: "List users" }),
      createEndpoint(2, { name: "List invoices" }),
    ]);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    const { router } = await renderView("/endpoints/1?tab=flow", "edit");
    await flushPromises();

    await fireEvent.click(screen.getByRole("button", { name: "Make flow dirty" }));
    await flushPromises();

    await router.push({ name: "endpoints-edit", params: { endpointId: 2 }, query: { tab: "flow" } });
    await flushPromises();

    expect(confirmSpy).toHaveBeenCalledWith(
      "You have unsaved Flow changes. Leave this route and discard the current flow draft?",
    );
    expect(router.currentRoute.value.params.endpointId).toBe("1");

    confirmSpy.mockRestore();
  });

  it("makes the Test tab explicit about contract preview versus live runtime state", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);

    await renderView("/endpoints/1?tab=test", "edit");
    await flushPromises();

    expect(screen.getByRole("tab", { name: "Test" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Contract preview")).toBeInTheDocument();
    expect(screen.getByText("Schema-driven contract preview")).toBeInTheDocument();
    expect(screen.getByText("Live request path")).toBeInTheDocument();
    expect(screen.getByText("Implementation 1 is live")).toBeInTheDocument();
    expect(screen.getByText("Draft vs live")).toBeInTheDocument();
    expect(screen.getByText("Draft v1 is ahead of live")).toBeInTheDocument();
    expect(
      screen.getByText(
        "The route tester compares an admin-only contract preview with real public requests. Only published live deployments can create execution traces below.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Execution history only appears for published live implementations. Legacy mock traffic does not write runtime traces here.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open route tester" })).toBeInTheDocument();
    expect(screen.getByText("Published implementation: 1")).toBeInTheDocument();
  });

  it("lazy-loads selected execution details and opens replay in the tester with path/query prefills", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);

    const { router } = await renderView("/endpoints/1?tab=test", "edit");
    await flushPromises();
    const pushSpy = vi.spyOn(router, "push");

    expect(vi.mocked(getExecution)).not.toHaveBeenCalled();

    await fireEvent.click(screen.getByRole("button", { name: "Inspect run 1" }));
    await flushPromises();

    expect(vi.mocked(getExecution)).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ token: "session-token" }),
    );
    expect(screen.getByText("Execution details")).toBeInTheDocument();
    expect(screen.getByText("Execution steps")).toBeInTheDocument();
    expect(screen.getByText("This run only recorded request body presence metadata, so request body replay is unavailable for this trace.")).toBeInTheDocument();

    await fireEvent.click(screen.getByRole("button", { name: "Replay in tester" }));
    await flushPromises();

    expect(pushSpy).toHaveBeenCalledWith({
      name: "endpoint-preview",
      params: { endpointId: 1 },
      query: {
        replayRunId: "1",
        replayBodyCaptured: "0",
        replay_path_orderId: "ord-42",
        replay_query_include: "items",
      },
    });
  });

  it("ignores stale execution-detail responses after a newer run selection", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);
    vi.mocked(listExecutions).mockResolvedValue([
      createExecution(1),
      {
        ...createExecution(1),
        id: 2,
        deployment_id: 2,
        implementation_id: 2,
        path: "/api/resource-1/replay",
      },
    ]);

    const firstRequest = createDeferred<ExecutionRunDetail>();
    const secondRequest = createDeferred<ExecutionRunDetail>();
    vi.mocked(getExecution).mockImplementation((executionId: number) => {
      if (executionId === 1) {
        return firstRequest.promise;
      }
      if (executionId === 2) {
        return secondRequest.promise;
      }

      return Promise.reject(new Error(`Unexpected execution id ${executionId}`));
    });

    const secondDetail: ExecutionRunDetail = {
      ...createExecutionDetail(1),
      id: 2,
      deployment_id: 2,
      implementation_id: 2,
      path: "/api/resource-1/replay",
      request_data: {
        path_parameters: {
          orderId: "ord-99",
        },
        query_parameters: {
          include: "payments",
        },
        body_present: false,
      },
    };

    const { router } = await renderView("/endpoints/1?tab=test", "edit");
    await flushPromises();
    const pushSpy = vi.spyOn(router, "push");

    await fireEvent.click(screen.getByRole("button", { name: "Inspect run 1" }));
    await fireEvent.click(screen.getByRole("button", { name: "Inspect run 2" }));

    secondRequest.resolve(secondDetail);
    await flushPromises();

    expect(screen.getByText(/Run #2/)).toBeInTheDocument();
    expect(screen.getByText("This run did not include a request body.")).toBeInTheDocument();

    firstRequest.resolve(createExecutionDetail(1));
    await flushPromises();

    expect(screen.getByText(/Run #2/)).toBeInTheDocument();
    expect(screen.queryByText(/Run #1/)).not.toBeInTheDocument();

    await fireEvent.click(screen.getByRole("button", { name: "Replay in tester" }));
    await flushPromises();

    expect(pushSpy).toHaveBeenCalledWith({
      name: "endpoint-preview",
      params: { endpointId: 1 },
      query: {
        replayRunId: "2",
        replayBodyCaptured: "none",
        replay_path_orderId: "ord-99",
        replay_query_include: "payments",
      },
    });
  });

  it("hides the flow connector context card while the flow editor is in focus mode", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);

    await renderView("/endpoints/1?tab=flow", "edit");
    await flushPromises();

    expect(screen.getByTestId("flow-connection-context")).toBeInTheDocument();

    await fireEvent.click(screen.getByRole("button", { name: "Enter focus mode" }));
    await flushPromises();

    expect(screen.queryByTestId("flow-connection-context")).not.toBeInTheDocument();
  });

  it("lets operators disable the live route from the Deploy tab without deleting the draft", async () => {
    vi.mocked(listEndpoints).mockResolvedValue([createEndpoint(1, { name: "List users" })]);
    vi.mocked(listRouteDeployments)
      .mockResolvedValueOnce([createDeployment(1)])
      .mockResolvedValueOnce([
        createDeployment(1, {
          is_active: false,
          updated_at: "2026-03-18T00:01:00Z",
        }),
      ]);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    await renderView("/endpoints/1?tab=deploy", "edit");
    await flushPromises();

    expect(screen.getByText("Implementation 1")).toBeInTheDocument();

    await fireEvent.click(screen.getByRole("button", { name: "Disable live route" }));
    await flushPromises();

    expect(vi.mocked(unpublishRouteDeployment)).toHaveBeenCalledWith(
      1,
      { environment: "production" },
      expect.objectContaining({ token: "session-token" }),
    );
    expect(confirmSpy).toHaveBeenCalledWith(
      "Disable the live production deployment for List users? Public traffic and published docs will stop using this route until it is published again.",
    );
    expect(vi.mocked(listRouteDeployments)).toHaveBeenCalledTimes(2);
    expect(screen.getAllByText("Live disabled").length).toBeGreaterThan(0);
    expect(screen.getByText("Live status")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Disabled the live production deployment. The route definition and flow implementation remain saved.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("This route has deployment history but no active live binding. Publish again to restore public traffic."),
    ).toBeInTheDocument();

    confirmSpy.mockRestore();
  });
});
