import type { RouteFlowNodeType } from "../types/endpoints";

const ROUTE_FLOW_DRAG_SOURCE = "route-flow-palette";

export interface RouteFlowPaletteDragPayload {
  source: typeof ROUTE_FLOW_DRAG_SOURCE;
  nodeType: RouteFlowNodeType;
}

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function createRouteFlowPaletteDragPayload(nodeType: RouteFlowNodeType): RouteFlowPaletteDragPayload {
  return {
    source: ROUTE_FLOW_DRAG_SOURCE,
    nodeType,
  };
}

export function getRouteFlowPaletteDragPayload(value: unknown): RouteFlowPaletteDragPayload | null {
  if (!isObjectRecord(value) || value.source !== ROUTE_FLOW_DRAG_SOURCE || typeof value.nodeType !== "string") {
    return null;
  }

  return value as unknown as RouteFlowPaletteDragPayload;
}
