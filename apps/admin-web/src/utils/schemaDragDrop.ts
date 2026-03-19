import type { BuilderNodeType, MockMode } from "../schemaBuilder";
import type { RequestParameterDefinition } from "./requestSchema";

const SCHEMA_DRAG_SOURCE = "schema-builder";

export type SchemaDragPayload =
  | { source: typeof SCHEMA_DRAG_SOURCE; kind: "mode-palette"; mode: MockMode }
  | { source: typeof SCHEMA_DRAG_SOURCE; kind: "node-palette"; nodeType: BuilderNodeType }
  | { source: typeof SCHEMA_DRAG_SOURCE; kind: "path-parameter"; parameter: RequestParameterDefinition }
  | { source: typeof SCHEMA_DRAG_SOURCE; kind: "value-palette"; valueType: string }
  | { source: typeof SCHEMA_DRAG_SOURCE; kind: "node"; nodeId: string };

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function createSchemaModePaletteDragPayload(mode: MockMode): SchemaDragPayload {
  return { source: SCHEMA_DRAG_SOURCE, kind: "mode-palette", mode };
}

export function createSchemaNodeDragPayload(nodeId: string): SchemaDragPayload {
  return { source: SCHEMA_DRAG_SOURCE, kind: "node", nodeId };
}

export function createSchemaNodePaletteDragPayload(nodeType: BuilderNodeType): SchemaDragPayload {
  return { source: SCHEMA_DRAG_SOURCE, kind: "node-palette", nodeType };
}

export function createSchemaPathParameterDragPayload(parameter: RequestParameterDefinition): SchemaDragPayload {
  return { source: SCHEMA_DRAG_SOURCE, kind: "path-parameter", parameter };
}

export function createSchemaValuePaletteDragPayload(valueType: string): SchemaDragPayload {
  return { source: SCHEMA_DRAG_SOURCE, kind: "value-palette", valueType };
}

export function getSchemaDragPayload(value: unknown): SchemaDragPayload | null {
  if (!isObjectRecord(value) || value.source !== SCHEMA_DRAG_SOURCE || typeof value.kind !== "string") {
    return null;
  }

  switch (value.kind) {
    case "mode-palette":
      return typeof value.mode === "string" ? value as SchemaDragPayload : null;
    case "node-palette":
      return typeof value.nodeType === "string" ? value as SchemaDragPayload : null;
    case "path-parameter":
      return isObjectRecord(value.parameter) && typeof value.parameter.name === "string"
        ? value as SchemaDragPayload
        : null;
    case "value-palette":
      return typeof value.valueType === "string" ? value as SchemaDragPayload : null;
    case "node":
      return typeof value.nodeId === "string" ? value as SchemaDragPayload : null;
    default:
      return null;
  }
}

export function isSchemaContainerDragPayload(payload: SchemaDragPayload | null): payload is SchemaDragPayload {
  return payload?.kind === "node-palette" || payload?.kind === "node";
}

export function isSchemaValueLaneDragPayload(payload: SchemaDragPayload | null): payload is SchemaDragPayload {
  return payload?.kind === "path-parameter" || payload?.kind === "value-palette" || payload?.kind === "mode-palette";
}
