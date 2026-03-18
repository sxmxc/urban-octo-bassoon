import { describe, expect, it } from "vitest";
import type { JsonObject, RouteFlowDefinition, RouteFlowEdge } from "../types/endpoints";
import {
  buildRouteFlowEdgeId,
  canAddRouteFlowNode,
  createRouteFlowNode,
  defaultRouteFlowEdgeExtra,
  normalizeRouteFlowDefinition,
  serializeRouteFlowDefinition,
  validateRouteFlowConnection,
  validateRouteFlowDefinition,
} from "./routeFlow";

describe("routeFlow utilities", () => {
  it("normalizes raw flow definitions into canvas-friendly nodes and edges", () => {
    const normalized = normalizeRouteFlowDefinition({
      schema_version: 1,
      viewport: {
        x: 24,
        y: 48,
      },
      nodes: [
        {
          id: "trigger",
          type: "api_trigger",
          config: {},
        },
        {
          id: "response",
          type: "set_response",
          name: "Return quote",
          config: {
            status_code: 202,
            body: {
              status: "queued",
            },
          },
          position: {
            x: 320,
            y: 96,
          },
        },
      ],
      edges: [
        {
          source: "trigger",
          target: "response",
        },
      ],
    });

    expect(normalized.extra?.viewport).toEqual({ x: 24, y: 48 });
    expect(normalized.nodes[0].position).toEqual({ x: 56, y: 64 });
    expect(normalized.nodes[1].position).toEqual({ x: 320, y: 96 });
    expect(normalized.edges[0].id).toBe("edge-trigger-response-1");
  });

  it("serializes edited flows back into the backend flow_definition shape", () => {
    const serialized = serializeRouteFlowDefinition({
      schema_version: 1,
      nodes: [
        {
          id: "trigger",
          type: "api_trigger",
          name: "API Trigger",
          config: {},
          position: {
            x: 56,
            y: 64,
          },
        },
      ],
      edges: [],
      extra: {
        notes: {
          keep: true,
        },
      },
    } as RouteFlowDefinition);

    expect(serialized).toEqual({
      schema_version: 1,
      nodes: [
        {
          id: "trigger",
          type: "api_trigger",
          name: "API Trigger",
          config: {},
          position: {
            x: 56,
            y: 64,
          },
        },
      ],
      edges: [],
      notes: {
        keep: true,
      },
    });
  });

  it("creates starter nodes with route-aware defaults and additive ids", () => {
    const nodes = [
      createRouteFlowNode("api_trigger", []),
      createRouteFlowNode("transform", []),
    ];
    const response = createRouteFlowNode("set_response", nodes, { anchorNodeId: "transform-1", successStatusCode: 204 });
    const httpRequest = createRouteFlowNode("http_request", nodes);
    const ifCondition = createRouteFlowNode("if_condition", nodes);
    const switchNode = createRouteFlowNode("switch", nodes);

    expect(response.id).toBe("set-response-1");
    expect(response.config.status_code).toBe(204);
    expect(response.position).toEqual({ x: 320, y: 64 });
    expect(httpRequest.config).toMatchObject({
      method: "GET",
      path: "/status",
      query: {},
      headers: {},
      timeout_ms: 10000,
    });
    expect(ifCondition.config).toMatchObject({
      left: { $ref: "request.body" },
      operator: "exists",
    });
    expect(switchNode.config).toMatchObject({
      value: { $ref: "request.query.mode" },
    });
    expect(canAddRouteFlowNode("api_trigger", nodes)).toBe(false);
    expect(canAddRouteFlowNode("transform", nodes)).toBe(true);
  });

  it("rejects invalid connections and accepts a branched if flow", () => {
    const definition = normalizeRouteFlowDefinition({
      schema_version: 1,
      nodes: [
        {
          id: "trigger",
          type: "api_trigger",
          config: {},
        },
        {
          id: "if-1",
          type: "if_condition",
          config: {
            left: { $ref: "request.query.mode" },
            operator: "equals",
            right: "live",
          },
        },
        {
          id: "live",
          type: "transform",
          config: {
            output: { branch: "live" },
          },
        },
        {
          id: "fallback",
          type: "transform",
          config: {
            output: { branch: "fallback" },
          },
        },
        {
          id: "response",
          type: "set_response",
          config: {
            status_code: 200,
            body: { ok: true },
          },
        },
      ],
      edges: [
        {
          id: "edge-trigger-if-1-1",
          source: "trigger",
          target: "if-1",
        },
      ],
    });

    expect(validateRouteFlowConnection(definition, "trigger", "response")).toBe(
      "API Trigger currently supports one outgoing path.",
    );
    expect(validateRouteFlowConnection(definition, "if-1", "live")).toBeNull();
    expect(validateRouteFlowConnection(definition, "if-1", "fallback")).toBeNull();

    const simpleChain: RouteFlowDefinition = {
      ...definition,
      edges: [
        ...definition.edges,
        {
          id: buildRouteFlowEdgeId(definition.edges, "if-1", "live"),
          source: "if-1",
          target: "live",
          extra: { branch: "true" },
        },
        {
          id: buildRouteFlowEdgeId([...definition.edges, { source: "if-1", target: "live" } as RouteFlowEdge], "if-1", "fallback"),
          source: "if-1",
          target: "fallback",
          extra: { branch: "false" },
        },
        {
          id: "edge-live-response-1",
          source: "live",
          target: "response",
        },
        {
          id: "edge-fallback-response-1",
          source: "fallback",
          target: "response",
        },
      ],
    };

    expect(validateRouteFlowDefinition(simpleChain)).toEqual([]);
  });

  it("surfaces blocking flow-shape problems before save", () => {
    const broken = normalizeRouteFlowDefinition({
      schema_version: 1,
      nodes: [
        {
          id: "trigger",
          type: "api_trigger",
          config: {},
        },
        {
          id: "orphan",
          type: "transform",
          config: {
            output: {},
          },
        },
      ],
      edges: [],
    } as JsonObject);

    expect(validateRouteFlowDefinition(broken)).toEqual([
      "Add exactly one Set Response node.",
    ]);
  });

  it("flags connector configuration gaps before save", () => {
    const connectorFlow = normalizeRouteFlowDefinition({
      schema_version: 1,
      nodes: [
        {
          id: "trigger",
          type: "api_trigger",
          config: {},
        },
        {
          id: "http",
          type: "http_request",
          config: {
            method: "GET",
            path: "/status",
          },
        },
        {
          id: "response",
          type: "set_response",
          config: {
            status_code: 200,
            body: {},
          },
        },
      ],
      edges: [
        {
          source: "trigger",
          target: "http",
        },
        {
          source: "http",
          target: "response",
        },
      ],
    } as JsonObject);

    expect(validateRouteFlowDefinition(connectorFlow)).toEqual([
      "HTTP Request requires a saved connection.",
    ]);
  });

  it("flags invalid branch metadata before save", () => {
    const invalidIfFlow = normalizeRouteFlowDefinition({
      schema_version: 1,
      nodes: [
        { id: "trigger", type: "api_trigger", config: {} },
        { id: "if-1", type: "if_condition", config: { left: { $ref: "request.query.mode" }, operator: "equals", right: "live" } },
        { id: "live", type: "transform", config: { output: { branch: "live" } } },
        { id: "fallback", type: "transform", config: { output: { branch: "fallback" } } },
        { id: "response", type: "set_response", config: { status_code: 200, body: {} } },
      ],
      edges: [
        { source: "trigger", target: "if-1" },
        { source: "if-1", target: "live", branch: "true" },
        { source: "if-1", target: "fallback", branch: "true" },
        { source: "live", target: "response" },
        { source: "fallback", target: "response" },
      ],
    } as JsonObject);

    expect(validateRouteFlowDefinition(invalidIfFlow)).toContain("If must define one True branch and one False branch.");
  });

  it("supports explicit branch handles plus Error Response terminals", () => {
    const branchedFlow = normalizeRouteFlowDefinition({
      schema_version: 1,
      nodes: [
        { id: "trigger", type: "api_trigger", config: {} },
        { id: "if-1", type: "if_condition", config: { left: { $ref: "request.query.mode" }, operator: "equals", right: "live" } },
        { id: "response", type: "set_response", config: { status_code: 200, body: { ok: true } } },
        { id: "error", type: "error_response", config: { status_code: 404, body: { error: "missing" } } },
      ],
      edges: [
        { source: "trigger", target: "if-1" },
        { source: "if-1", target: "response", branch: "true" },
        { source: "if-1", target: "error", branch: "false" },
      ],
    } as JsonObject);

    expect(validateRouteFlowDefinition(branchedFlow)).toEqual([]);
  });

  it("builds branch metadata from explicit source handles", () => {
    const definition = normalizeRouteFlowDefinition({
      schema_version: 1,
      nodes: [
        { id: "if-1", type: "if_condition", config: { left: { $ref: "request.body" }, operator: "exists" } },
        { id: "switch-1", type: "switch", config: { value: { $ref: "request.query.mode" } } },
      ],
      edges: [],
    } as JsonObject);

    expect(defaultRouteFlowEdgeExtra(definition, "if-1", "true")).toEqual({ branch: "true" });
    expect(defaultRouteFlowEdgeExtra(definition, "if-1", "false")).toEqual({ branch: "false" });
    expect(defaultRouteFlowEdgeExtra(definition, "switch-1", "default")).toEqual({ branch: "default" });
    expect(defaultRouteFlowEdgeExtra(definition, "switch-1", "case")).toEqual({
      branch: "case",
      case_value: "case-1",
    });
  });
});
