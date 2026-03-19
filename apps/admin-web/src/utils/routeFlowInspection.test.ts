import { describe, expect, it } from "vitest";
import type { Connection, JsonObject, RouteFlowDefinition } from "../types/endpoints";
import { buildRouteFlowInspectionSnapshot } from "./routeFlowInspection";

function createRouteContext(overrides: Partial<Parameters<typeof buildRouteFlowInspectionSnapshot>[1]> = {}) {
  return {
    routeId: 7,
    routeMethod: "POST",
    routeName: "Create health",
    routePath: "/api/health/{service}",
    requestSchema: {
      type: "object",
      properties: {
        healthy: {
          type: "boolean",
        },
      },
      "x-request": {
        query: {
          type: "object",
          properties: {
            mode: {
              type: "string",
              enum: ["simple", "verbose"],
            },
          },
          required: ["mode"],
          "x-builder": {
            order: ["mode"],
          },
        },
      },
    } as JsonObject,
    responseSchema: {
      type: "object",
      properties: {
        ok: {
          type: "boolean",
        },
      },
      required: ["ok"],
      "x-builder": {
        order: ["ok"],
      },
    } as JsonObject,
    successStatusCode: 200,
    ...overrides,
  };
}

describe("routeFlowInspection", () => {
  it("treats request contract data as the entry scope and resolves transform refs against it", () => {
    const definition: RouteFlowDefinition = {
      schema_version: 1,
      nodes: [
        { id: "trigger", type: "api_trigger", name: "API Trigger", config: {} },
        {
          id: "transform",
          type: "transform",
          name: "Transform",
          config: {
            output: {
              method: { $ref: "route.method" },
              service: { $ref: "request.path.service" },
              mode: { $ref: "request.query.mode" },
              healthy: { $ref: "request.body.healthy" },
            },
          },
        },
        {
          id: "response",
          type: "set_response",
          name: "Set Response",
          config: {
            status_code: 200,
            body: { $ref: "state.transform" },
          },
        },
      ],
      edges: [
        { source: "trigger", target: "transform" },
        { source: "transform", target: "response" },
      ],
    };

    const snapshot = buildRouteFlowInspectionSnapshot(definition, createRouteContext());

    expect(snapshot.generatedRequestSample.path).toEqual({ service: "sample-service" });
    expect(snapshot.generatedRequestSample.query).toEqual({ mode: "simple" });
    expect(snapshot.generatedRequestSample.body).toEqual({ healthy: true });
    expect(snapshot.nodesById.transform.scopeEntries.map((entry) => entry.refPath)).toEqual([
      "route",
      "request.path",
      "request.query",
      "request.body",
      "state.trigger",
    ]);
    expect(snapshot.nodesById.transform.outputSample).toEqual({
      method: "POST",
      service: "sample-service",
      mode: "simple",
      healthy: true,
    });
  });

  it("makes Set Response comparison explicit when live flow output diverges from response_schema", () => {
    const definition: RouteFlowDefinition = {
      schema_version: 1,
      nodes: [
        { id: "trigger", type: "api_trigger", name: "API Trigger", config: {} },
        {
          id: "transform",
          type: "transform",
          name: "Transform",
          config: {
            output: {
              route: {
                method: { $ref: "route.method" },
                path: { $ref: "route.path" },
              },
              message: "Replace this starter flow in the Flow tab before deploying to production.",
            },
          },
        },
        {
          id: "response",
          type: "set_response",
          name: "Set Response",
          config: {
            status_code: 200,
            body: { $ref: "state.transform" },
          },
        },
      ],
      edges: [
        { source: "trigger", target: "transform" },
        { source: "transform", target: "response" },
      ],
    };

    const snapshot = buildRouteFlowInspectionSnapshot(definition, createRouteContext());
    const responseInspection = snapshot.nodesById.response;

    expect(responseInspection.outputSample).toEqual({
      body: {
        route: {
          method: "POST",
          path: "/api/health/{service}",
        },
        message: "Replace this starter flow in the Flow tab before deploying to production.",
      },
      status_code: 200,
    });
    expect(responseInspection.responseComparison?.matchesContract).toBe(false);
    expect(responseInspection.responseComparison?.message).toContain("differ");
    expect(responseInspection.boundaryMessage).toContain("Deploy returns this Set Response body");
  });

  it("renders inline string interpolation while preserving whole-value refs across transform and Set Response", () => {
    const definition: RouteFlowDefinition = {
      schema_version: 1,
      nodes: [
        { id: "trigger", type: "api_trigger", name: "API Trigger", config: {} },
        {
          id: "transform",
          type: "transform",
          name: "Transform",
          config: {
            output: {
              greeting: "svc={{request.path.service}} mode={{request.query.mode}} ok={{request.body.healthy}} missing={{request.query.missing}}",
              service: { $ref: "request.path.service" },
            },
          },
        },
        {
          id: "response",
          type: "set_response",
          name: "Set Response",
          config: {
            status_code: 200,
            body: {
              message: "Flow says {{state.transform.greeting}}",
              service: { $ref: "state.transform.service" },
            },
          },
        },
      ],
      edges: [
        { source: "trigger", target: "transform" },
        { source: "transform", target: "response" },
      ],
    };

    const snapshot = buildRouteFlowInspectionSnapshot(definition, createRouteContext());

    expect(snapshot.nodesById.transform.outputSample).toEqual({
      greeting: "svc=sample-service mode=simple ok=true missing=",
      service: "sample-service",
    });
    expect(snapshot.nodesById.transform.unresolvedRefs).toContain("request.query.missing");
    expect(snapshot.nodesById.response.outputSample).toEqual({
      body: {
        message: "Flow says svc=sample-service mode=simple ok=true missing=",
        service: "sample-service",
      },
      status_code: 200,
    });
  });

  it("renders inline string interpolation and whole-value refs for Error Response output samples", () => {
    const definition: RouteFlowDefinition = {
      schema_version: 1,
      nodes: [
        { id: "trigger", type: "api_trigger", name: "API Trigger", config: {} },
        {
          id: "error",
          type: "error_response",
          name: "Error Response",
          config: {
            status_code: 422,
            body: {
              error: "bad request for {{request.path.service}}",
              mode: { $ref: "request.query.mode" },
              first_error: "{{errors.0}}",
            },
          },
        },
      ],
      edges: [
        { source: "trigger", target: "error" },
      ],
    };

    const snapshot = buildRouteFlowInspectionSnapshot(definition, createRouteContext());

    expect(snapshot.nodesById.error.outputSample).toEqual({
      body: {
        error: "bad request for sample-service",
        mode: "simple",
        first_error: "",
      },
      status_code: 422,
    });
    expect(snapshot.nodesById.error.unresolvedRefs).toContain("errors.0");
  });

  it("uses explicit placeholder samples for connector nodes until live execution data exists", () => {
    const connections: Connection[] = [
      {
        id: 12,
        name: "Health upstream",
        connector_type: "http",
        description: null,
        config: {
          base_url: "https://status.example.test",
        },
        is_active: true,
        created_at: "2026-03-19T00:00:00Z",
        updated_at: "2026-03-19T00:00:00Z",
      },
    ];
    const definition: RouteFlowDefinition = {
      schema_version: 1,
      nodes: [
        { id: "trigger", type: "api_trigger", name: "API Trigger", config: {} },
        {
          id: "http-request-1",
          type: "http_request",
          name: "HTTP Request",
          config: {
            connection_id: 12,
            method: "GET",
            path: "/services/{{request.path.service}}",
            query: {
              mode: { $ref: "request.query.mode" },
            },
          },
        },
      ],
      edges: [{ source: "trigger", target: "http-request-1" }],
    };

    const snapshot = buildRouteFlowInspectionSnapshot(definition, createRouteContext(), connections);
    const inspection = snapshot.nodesById["http-request-1"];

    expect(inspection.outputSample).toMatchObject({
      connection: {
        id: 12,
        name: "Health upstream",
      },
      request: {
        method: "GET",
        query: { mode: "simple" },
        url: "https://status.example.test/services/sample-service",
      },
      response: {
        body: {
          _sample: "Connector output is not executed in the editor.",
        },
      },
    });
    expect(inspection.notes[0]).toContain("do not call the upstream service");
  });

  it("treats empty object request schemas as body-less request contracts", () => {
    const definition: RouteFlowDefinition = {
      schema_version: 1,
      nodes: [
        { id: "trigger", type: "api_trigger", name: "API Trigger", config: {} },
      ],
      edges: [],
    };

    const snapshot = buildRouteFlowInspectionSnapshot(
      definition,
      createRouteContext({
        routeMethod: "GET",
        routePath: "/api/health",
        requestSchema: {
          type: "object",
          properties: {},
          required: [],
          "x-builder": {
            order: [],
          },
        } as JsonObject,
      }),
    );

    expect(snapshot.generatedRequestSample.body).toBeNull();
    expect(snapshot.nodesById.trigger.outputSample).toMatchObject({
      request: {
        body_present: false,
      },
    });
  });

  it("only keeps state from the executable branch path when branches converge", () => {
    const definition: RouteFlowDefinition = {
      schema_version: 1,
      nodes: [
        { id: "trigger", type: "api_trigger", name: "API Trigger", config: {} },
        {
          id: "if-1",
          type: "if_condition",
          name: "If",
          config: {
            left: { $ref: "request.query.mode" },
            operator: "equals",
            right: "simple",
          },
        },
        {
          id: "transform-true",
          type: "transform",
          name: "Transform true",
          config: {
            output: {
              branch: "true",
            },
          },
        },
        {
          id: "transform-false",
          type: "transform",
          name: "Transform false",
          config: {
            output: {
              branch: "false",
            },
          },
        },
        {
          id: "response",
          type: "set_response",
          name: "Set Response",
          config: {
            status_code: 200,
            body: {
              active: { $ref: "state.transform-true" },
              inactive: { $ref: "state.transform-false" },
            },
          },
        },
      ],
      edges: [
        { source: "trigger", target: "if-1" },
        { source: "if-1", target: "transform-true", extra: { branch: "true" } },
        { source: "if-1", target: "transform-false", extra: { branch: "false" } },
        { source: "transform-true", target: "response" },
        { source: "transform-false", target: "response" },
      ],
    };

    const snapshot = buildRouteFlowInspectionSnapshot(definition, createRouteContext());

    expect(snapshot.executedNodeIds).toEqual(["trigger", "if-1", "transform-true", "response"]);
    expect(snapshot.nodesById.response.scopeEntries.map((entry) => entry.refPath)).toEqual([
      "route",
      "request.path",
      "request.query",
      "request.body",
      "state.trigger",
      "state.if-1",
      "state.transform-true",
    ]);
    expect(snapshot.nodesById.response.outputSample).toEqual({
      body: {
        active: {
          branch: "true",
        },
        inactive: null,
      },
      status_code: 200,
    });
    expect(snapshot.nodesById.response.unresolvedRefs).toContain("state.transform-false");
    expect(snapshot.nodesById["transform-false"]).toBeUndefined();
  });

  it("matches backend contains semantics when the right operand resolves to an empty string", () => {
    const definition: RouteFlowDefinition = {
      schema_version: 1,
      nodes: [
        { id: "trigger", type: "api_trigger", name: "API Trigger", config: {} },
        {
          id: "if-1",
          type: "if_condition",
          name: "If",
          config: {
            left: { $ref: "request.query.mode" },
            operator: "contains",
            right: { $ref: "request.query.missing" },
          },
        },
      ],
      edges: [
        { source: "trigger", target: "if-1" },
      ],
    };

    const snapshot = buildRouteFlowInspectionSnapshot(definition, createRouteContext());

    expect(snapshot.nodesById["if-1"].outputSample).toMatchObject({
      matched: true,
      branch: "true",
      left: "simple",
      right: null,
    });
  });
});
