import { describe, expect, it } from "vitest";
import { buildRouteTestState } from "./routeTestState";
import type { Endpoint, RouteDeployment, RouteImplementation } from "../types/endpoints";

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
    request_schema: {},
    response_schema: {},
    success_status_code: 200,
    error_rate: 0,
    latency_min_ms: 0,
    latency_max_ms: 0,
    seed_key: null,
    created_at: "2026-03-19T00:00:00Z",
    updated_at: "2026-03-19T00:00:00Z",
    publication_status: overrides.publication_status ?? {
      code: "legacy_mock",
      label: "Legacy mock",
      tone: "secondary",
      enabled,
      is_public: enabled,
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
    created_at: "2026-03-19T00:00:00Z",
    updated_at: "2026-03-19T00:00:00Z",
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
    published_at: "2026-03-19T00:00:00Z",
    created_at: "2026-03-19T00:00:00Z",
    updated_at: "2026-03-19T00:00:00Z",
    ...overrides,
  };
}

describe("buildRouteTestState", () => {
  it("preserves backend published-live status when deployments are unavailable", () => {
    const state = buildRouteTestState(
      createEndpoint({
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
          active_implementation_id: 4,
          active_deployment_id: 4,
        },
      }),
      createImplementation(),
      [],
    );

    expect(state.liveMode).toBe("live_active");
    expect(state.liveStatusLabel).toBe("Published live");
    expect(state.liveHeadline).toBe("Implementation 4 is live");
    expect(state.draftHeadline).toBe("Draft v3 is ahead of live");
  });

  it("preserves deployment-history status when deployments are unavailable", () => {
    const state = buildRouteTestState(
      createEndpoint({
        publication_status: {
          code: "live_disabled",
          label: "Live disabled",
          tone: "warning",
          enabled: true,
          is_public: false,
          is_live: false,
          uses_legacy_mock: false,
          has_saved_implementation: true,
          has_runtime_history: true,
          has_deployment_history: true,
          has_active_deployment: false,
          active_deployment_environment: null,
          active_implementation_id: null,
          active_deployment_id: null,
        },
      }),
      createImplementation(),
      [],
    );

    expect(state.liveMode).toBe("live_disabled");
    expect(state.liveStatusLabel).toBe("Live disabled");
    expect(state.liveHeadline).toBe("No active deployment");
    expect(state.draftHeadline).toBe("Draft v3 is saved");
  });

  it("treats an active deployment as live even when the cached publication status is still draft only", () => {
    const state = buildRouteTestState(
      createEndpoint({
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
      createImplementation(),
      [createDeployment()],
    );

    expect(state.liveMode).toBe("live_active");
    expect(state.liveStatusLabel).toBe("Published live");
    expect(state.liveHeadline).toBe("Implementation 4 is live");
    expect(state.draftHeadline).toBe("Draft v3 is ahead of live");
  });

  it("treats retained deployment history as live disabled even when the cached publication status still says published live", () => {
    const state = buildRouteTestState(
      createEndpoint({
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
          active_implementation_id: 4,
          active_deployment_id: 4,
        },
      }),
      createImplementation(),
      [createDeployment({ is_active: false })],
    );

    expect(state.liveMode).toBe("live_disabled");
    expect(state.liveStatusLabel).toBe("Live disabled");
    expect(state.liveHeadline).toBe("No active deployment");
    expect(state.draftHeadline).toBe("Draft v3 is saved");
  });
});
