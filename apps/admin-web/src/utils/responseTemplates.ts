import type { JsonObject, JsonValue } from "../types/endpoints";

const TEMPLATE_EXPRESSION_PATTERN = /\{\{\s*([^{}]+?)\s*\}\}/g;
const TEMPLATE_REQUEST_LOCATIONS = new Set(["path", "query", "body"]);
const DEFAULT_BODY_PATH_LIMIT = 8;
const DEFAULT_BODY_PATH_DEPTH = 3;

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function schemaOrder(schema: JsonObject): string[] {
  const properties = isJsonObject(schema.properties) ? (schema.properties as JsonObject) : {};
  const orderedKeys = Array.isArray((schema["x-builder"] as JsonObject | undefined)?.order)
    ? ((schema["x-builder"] as JsonObject).order as JsonValue[]).map(String)
    : [];

  for (const key of Object.keys(properties)) {
    if (!orderedKeys.includes(key)) {
      orderedKeys.push(key);
    }
  }

  return orderedKeys.filter((key) => key in properties);
}

function sampleStringValue(schema: JsonObject): string {
  const format = typeof schema.format === "string" ? schema.format.trim().toLowerCase() : "";
  if (Array.isArray(schema.enum) && schema.enum.length > 0) {
    return String(schema.enum[0]);
  }
  if (format === "uuid") {
    return "11111111-1111-4111-8111-111111111111";
  }
  if (format === "email") {
    return "person@example.com";
  }
  if (format === "uri" || format === "url") {
    return "https://artificer.test/example";
  }
  if (format === "date") {
    return "2026-03-17";
  }
  if (format === "date-time") {
    return "2026-03-17T12:00:00Z";
  }
  if (format === "time") {
    return "12:00:00Z";
  }
  return "sample";
}

function buildBodySampleValue(schema: JsonObject | null | undefined, depth = 0): JsonValue {
  if (!schema || !isJsonObject(schema)) {
    return {};
  }

  if ((schema.type === "object" || "properties" in schema) && depth < 4) {
    const properties = isJsonObject(schema.properties) ? (schema.properties as JsonObject) : {};
    return schemaOrder(schema).reduce<JsonObject>((accumulator, key) => {
      accumulator[key] = buildBodySampleValue(properties[key] as JsonObject | undefined, depth + 1);
      return accumulator;
    }, {});
  }

  if (schema.type === "array" || "items" in schema) {
    const items = isJsonObject(schema.items) ? (schema.items as JsonObject) : null;
    return items ? [buildBodySampleValue(items, depth + 1)] : [];
  }

  if (schema.type === "integer") {
    return typeof schema.minimum === "number" ? Math.trunc(schema.minimum) : 1;
  }

  if (schema.type === "number") {
    return typeof schema.minimum === "number" ? schema.minimum : 1;
  }

  if (schema.type === "boolean") {
    return true;
  }

  return sampleStringValue(schema);
}

function collectBodyPaths(
  schema: JsonObject | null | undefined,
  segments: string[] = [],
  depth = 0,
  maxCount = DEFAULT_BODY_PATH_LIMIT,
  paths: string[] = [],
): string[] {
  if (!schema || !isJsonObject(schema) || paths.length >= maxCount || depth >= DEFAULT_BODY_PATH_DEPTH) {
    return paths;
  }

  if (schema.type === "object" || "properties" in schema) {
    const properties = isJsonObject(schema.properties) ? (schema.properties as JsonObject) : {};
    for (const key of schemaOrder(schema)) {
      const nextSegments = [...segments, key];
      paths.push(nextSegments.join("."));
      if (paths.length >= maxCount) {
        return paths;
      }
      collectBodyPaths(properties[key] as JsonObject | undefined, nextSegments, depth + 1, maxCount, paths);
      if (paths.length >= maxCount) {
        return paths;
      }
    }
    return paths;
  }

  if (schema.type === "array" || "items" in schema) {
    const nextSegments = [...segments, "0"];
    paths.push(nextSegments.join("."));
    if (paths.length >= maxCount) {
      return paths;
    }
    const items = isJsonObject(schema.items) ? (schema.items as JsonObject) : null;
    collectBodyPaths(items, nextSegments, depth + 1, maxCount, paths);
  }

  return paths;
}

export function buildSampleRequestBody(schema: JsonObject | null | undefined): JsonValue | null {
  if (!schema || !isJsonObject(schema) || Object.keys(schema).length === 0) {
    return null;
  }

  return buildBodySampleValue(schema);
}

export function collectRequestBodyTemplatePaths(
  schema: JsonObject | null | undefined,
  maxCount = DEFAULT_BODY_PATH_LIMIT,
): string[] {
  if (!schema || !isJsonObject(schema) || Object.keys(schema).length === 0) {
    return [];
  }

  return collectBodyPaths(schema, [], 0, maxCount, []);
}

export function extractTemplateTokens(template: string): string[] {
  const tokens = Array.from(template.matchAll(TEMPLATE_EXPRESSION_PATTERN)).map((match) => match[1]?.trim() ?? "");
  const remainder = template.replace(TEMPLATE_EXPRESSION_PATTERN, "");
  if (remainder.includes("{{") || remainder.includes("}}")) {
    throw new Error("Response templates must use balanced {{token}} placeholders.");
  }

  return tokens;
}

export function validateResponseTemplate(
  template: string | null | undefined,
  options: { pathParameterNames?: string[] } = {},
): string | null {
  const normalized = String(template ?? "");
  if (!normalized.trim()) {
    return null;
  }

  let tokens: string[];
  try {
    tokens = extractTemplateTokens(normalized);
  } catch (error) {
    return error instanceof Error ? error.message : "Response templates must use balanced {{token}} placeholders.";
  }

  const pathParameterNames = new Set((options.pathParameterNames ?? []).map((name) => name.trim()).filter(Boolean));

  for (const token of tokens) {
    if (token === "value") {
      continue;
    }

    const parts = token.split(".").map((segment) => segment.trim());
    if (
      parts.length < 3
      || parts[0] !== "request"
      || !TEMPLATE_REQUEST_LOCATIONS.has(parts[1])
      || parts.slice(2).some((segment) => !segment)
    ) {
      return `Unsupported response template token '${token}'. Use {{value}}, {{request.path.*}}, {{request.query.*}}, or {{request.body.*}}.`;
    }

    if (parts[1] === "path" && pathParameterNames.size > 0 && !pathParameterNames.has(parts[2])) {
      return `Response template references unknown path parameter '${parts[2]}'.`;
    }
  }

  return null;
}
