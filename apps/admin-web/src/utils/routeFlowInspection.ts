import type { Connection, JsonObject, JsonValue, RouteFlowDefinition, RouteFlowNode } from "../types/endpoints";
import { buildDefaultParameterValue, extractRequestBodySchema, extractRequestParameterDefinitions } from "./requestSchema";
import { buildSampleRequestBody as buildSchemaSample } from "./responseTemplates";

const TEMPLATE_EXPRESSION_PATTERN = /\{\{\s*([^{}]+?)\s*\}\}/g;

export interface RouteFlowInspectionRouteContext {
  routeId?: number | null;
  routeMethod?: string | null;
  routeName?: string | null;
  routePath?: string | null;
  requestSchema?: JsonObject | null;
  responseSchema?: JsonObject | null;
  successStatusCode?: number | null;
}

export interface RouteFlowInspectionScopeEntry {
  json: string;
  kind: "errors" | "request" | "route" | "state";
  label: string;
  refPath: string;
  sample: JsonValue;
  shape: string;
}

export interface RouteFlowResponseComparison {
  contractJson: string | null;
  contractSample: JsonValue | null;
  matchesContract: boolean | null;
  message: string;
  statusCode: number;
  tone: "info" | "success" | "warning";
}

export interface RouteFlowNodeInspection {
  boundaryMessage: string;
  boundaryTone: "info" | "success" | "warning";
  inputShape: string;
  outputJson: string;
  outputSample: JsonValue;
  outputShape: string;
  outputTitle: string;
  responseComparison: RouteFlowResponseComparison | null;
  scopeEntries: RouteFlowInspectionScopeEntry[];
  unresolvedRefs: string[];
  notes: string[];
}

export interface RouteFlowInspectionSnapshot {
  contractResponseSample: JsonValue | null;
  contractResponseShape: string;
  contractResponseJson: string | null;
  executedNodeIds: string[];
  generatedRequestSample: {
    body: JsonValue | null;
    path: Record<string, string>;
    query: Record<string, string>;
  };
  nodesById: Record<string, RouteFlowNodeInspection>;
}

interface FlowRuntimeContext {
  errors: string[];
  request: {
    body: JsonValue | null;
    path: Record<string, string>;
    query: Record<string, string>;
  };
  route: {
    id: number | null;
    method: string;
    name: string;
    path: string;
    success_status_code: number;
  };
  state: Record<string, JsonValue>;
}

interface ResolutionTracker {
  unresolvedRefs: Set<string>;
}

function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function cloneJsonValue<T extends JsonValue>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function toJsonValue(value: unknown): JsonValue {
  if (
    value === null
    || typeof value === "string"
    || typeof value === "number"
    || typeof value === "boolean"
  ) {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => toJsonValue(item));
  }

  if (isJsonObject(value)) {
    return Object.entries(value).reduce<JsonObject>((accumulator, [key, child]) => {
      accumulator[key] = toJsonValue(child);
      return accumulator;
    }, {});
  }

  return null;
}

function stringifyJson(value: JsonValue | null): string {
  return JSON.stringify(value ?? null, null, 2);
}

function describeJsonShape(value: JsonValue | null): string {
  if (value === null) {
    return "null";
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return "array (empty)";
    }

    return `array (${value.length} item${value.length === 1 ? "" : "s"})`;
  }

  if (isJsonObject(value)) {
    const keys = Object.keys(value);
    if (keys.length === 0) {
      return "object (empty)";
    }
    if (keys.length <= 3) {
      return `object (${keys.join(", ")})`;
    }
    return `object (${keys.length} keys)`;
  }

  return typeof value;
}

function buildRequestPathSample(schema: JsonObject | null | undefined, routePath: string): Record<string, string> {
  const definitions = extractRequestParameterDefinitions(schema, "path");
  if (definitions.length > 0) {
    return definitions.reduce<Record<string, string>>((accumulator, definition) => {
      accumulator[definition.name] = buildDefaultParameterValue(definition);
      return accumulator;
    }, {});
  }

  const matches = routePath.matchAll(/\{([^}]+)\}/g);
  const values: Record<string, string> = {};
  for (const match of matches) {
    const key = match[1]?.trim();
    if (!key || key in values) {
      continue;
    }
    values[key] = `sample-${key}`;
  }
  return values;
}

function buildRequestQuerySample(schema: JsonObject | null | undefined): Record<string, string> {
  return extractRequestParameterDefinitions(schema, "query").reduce<Record<string, string>>((accumulator, definition) => {
    accumulator[definition.name] = buildDefaultParameterValue(definition);
    return accumulator;
  }, {});
}

function hasMeaningfulRequestBodySchema(schema: JsonObject | null | undefined): boolean {
  if (!schema || !isJsonObject(schema) || Object.keys(schema).length === 0) {
    return false;
  }

  const properties = isJsonObject(schema.properties) ? Object.keys(schema.properties) : [];
  const required = Array.isArray(schema.required) ? schema.required : [];
  const meaningfulKeys = Object.keys(schema).filter(
    (key) => !["type", "properties", "required", "x-builder", "title", "description"].includes(key),
  );

  if ((schema.type === "object" || "properties" in schema) && properties.length === 0 && required.length === 0 && meaningfulKeys.length === 0) {
    return false;
  }

  return true;
}

function createFlowRuntimeContext(routeContext: RouteFlowInspectionRouteContext): FlowRuntimeContext {
  const routePath = String(routeContext.routePath ?? "/api/example");
  const requestBodySchema = extractRequestBodySchema(routeContext.requestSchema);
  return {
    route: {
      id: typeof routeContext.routeId === "number" ? routeContext.routeId : null,
      name: String(routeContext.routeName ?? "Draft route"),
      method: String(routeContext.routeMethod ?? "GET").toUpperCase(),
      path: routePath,
      success_status_code: Number.isFinite(routeContext.successStatusCode)
        ? Number(routeContext.successStatusCode)
        : 200,
    },
    request: {
      path: buildRequestPathSample(routeContext.requestSchema, routePath),
      query: buildRequestQuerySample(routeContext.requestSchema),
      body: hasMeaningfulRequestBodySchema(requestBodySchema)
        ? toJsonValue(buildSchemaSample(requestBodySchema))
        : null,
    },
    state: {},
    errors: [],
  };
}

function lookupRef(ref: string, context: FlowRuntimeContext, tracker: ResolutionTracker): JsonValue {
  const parts = ref.split(".").map((part) => part.trim()).filter(Boolean);
  let current: unknown = context;

  for (const part of parts) {
    if (Array.isArray(current)) {
      const index = Number(part);
      if (!Number.isInteger(index) || index < 0 || index >= current.length) {
        tracker.unresolvedRefs.add(ref);
        return null;
      }
      current = current[index];
      continue;
    }

    if (isJsonObject(current)) {
      if (!(part in current)) {
        tracker.unresolvedRefs.add(ref);
        return null;
      }
      current = current[part];
      continue;
    }

    tracker.unresolvedRefs.add(ref);
    return null;
  }

  return toJsonValue(current);
}

function stringifyTemplateValue(value: JsonValue): string {
  if (value === null) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (Array.isArray(value) || isJsonObject(value)) {
    return JSON.stringify(value);
  }
  return String(value);
}

function renderStringTemplate(template: string, context: FlowRuntimeContext, tracker: ResolutionTracker): string {
  return template.replace(TEMPLATE_EXPRESSION_PATTERN, (_, refPath: string) =>
    stringifyTemplateValue(lookupRef(String(refPath).trim(), context, tracker)),
  );
}

function hasTemplateTokens(value: string): boolean {
  return value.includes("{{") && value.includes("}}");
}

function renderTemplate(value: JsonValue | undefined, context: FlowRuntimeContext, tracker: ResolutionTracker): JsonValue {
  if (value === undefined) {
    return null;
  }

  if (Array.isArray(value)) {
    return value.map((child) => renderTemplate(child, context, tracker));
  }

  if (isJsonObject(value)) {
    if (Object.keys(value).length === 1 && typeof value.$ref === "string") {
      return lookupRef(value.$ref, context, tracker);
    }

    return Object.entries(value).reduce<JsonObject>((accumulator, [key, child]) => {
      accumulator[key] = renderTemplate(child, context, tracker);
      return accumulator;
    }, {});
  }

  if (typeof value === "string" && hasTemplateTokens(value)) {
    return renderStringTemplate(value, context, tracker);
  }

  return value;
}

function renderConnectorValue(value: JsonValue | undefined, context: FlowRuntimeContext, tracker: ResolutionTracker): JsonValue {
  if (value === undefined) {
    return null;
  }

  if (Array.isArray(value)) {
    return value.map((child) => renderConnectorValue(child, context, tracker));
  }

  if (isJsonObject(value)) {
    if (Object.keys(value).length === 1 && typeof value.$ref === "string") {
      return lookupRef(value.$ref, context, tracker);
    }

    return Object.entries(value).reduce<JsonObject>((accumulator, [key, child]) => {
      accumulator[key] = renderConnectorValue(child, context, tracker);
      return accumulator;
    }, {});
  }

  if (typeof value === "string" && hasTemplateTokens(value)) {
    return renderStringTemplate(value, context, tracker);
  }

  return value;
}

function logicValueIsEmpty(value: JsonValue): boolean {
  return value === null || value === "" || (Array.isArray(value) && value.length === 0) || (isJsonObject(value) && Object.keys(value).length === 0);
}

function logicValuesEqual(left: JsonValue, right: JsonValue): boolean {
  if (JSON.stringify(left) === JSON.stringify(right)) {
    return true;
  }

  if (typeof left === "boolean" || typeof right === "boolean") {
    return false;
  }

  const leftNumber = Number(left);
  const rightNumber = Number(right);
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
    return leftNumber === rightNumber;
  }

  return stringifyTemplateValue(left) === stringifyTemplateValue(right);
}

function logicCompareNumbers(left: JsonValue, right: JsonValue): [number, number] | null {
  if (typeof left === "boolean" || typeof right === "boolean") {
    return null;
  }

  const leftNumber = Number(left);
  const rightNumber = Number(right);
  if (!Number.isFinite(leftNumber) || !Number.isFinite(rightNumber)) {
    return null;
  }

  return [leftNumber, rightNumber];
}

function evaluateIfCondition(node: RouteFlowNode, context: FlowRuntimeContext, tracker: ResolutionTracker): JsonObject {
  const left = renderConnectorValue(node.config.left, context, tracker);
  const right = "right" in node.config ? renderConnectorValue(node.config.right, context, tracker) : null;
  const operator = String(node.config.operator ?? "equals").trim().toLowerCase();
  let matched = false;

  if (operator === "equals") {
    matched = logicValuesEqual(left, right);
  } else if (operator === "not_equals") {
    matched = !logicValuesEqual(left, right);
  } else if (operator === "exists") {
    matched = left !== null;
  } else if (operator === "not_exists") {
    matched = left === null;
  } else if (operator === "truthy") {
    matched = Boolean(left);
  } else if (operator === "falsy") {
    matched = !left;
  } else if (operator === "is_empty") {
    matched = logicValueIsEmpty(left);
  } else if (operator === "is_not_empty") {
    matched = !logicValueIsEmpty(left);
  } else if (operator === "contains") {
    if (typeof left === "string") {
      matched = left.includes(stringifyTemplateValue(right));
    } else if (Array.isArray(left)) {
      matched = left.some((item) => logicValuesEqual(item, right));
    } else if (isJsonObject(left)) {
      matched = right !== null && String(right) in left;
    }
  } else {
    const numericPair = logicCompareNumbers(left, right);
    if (numericPair) {
      const [numericLeft, numericRight] = numericPair;
      if (operator === "greater_than") {
        matched = numericLeft > numericRight;
      } else if (operator === "greater_than_or_equal") {
        matched = numericLeft >= numericRight;
      } else if (operator === "less_than") {
        matched = numericLeft < numericRight;
      } else if (operator === "less_than_or_equal") {
        matched = numericLeft <= numericRight;
      }
    }
  }

  return {
    matched,
    branch: matched ? "true" : "false",
    operator,
    left,
    right,
  };
}

function evaluateSwitch(node: RouteFlowNode, definition: RouteFlowDefinition, context: FlowRuntimeContext, tracker: ResolutionTracker): JsonObject {
  const value = renderConnectorValue(node.config.value, context, tracker);
  const outgoingEdges = definition.edges.filter((edge) => edge.source === node.id);
  const matchingCase = outgoingEdges.find(
    (edge) => String(edge.extra?.branch ?? "").toLowerCase() === "case" && logicValuesEqual(value, toJsonValue(edge.extra?.case_value)),
  );
  const branch = matchingCase ? "case" : "default";

  return {
    value,
    branch,
    case_value: branch === "case" ? toJsonValue(matchingCase?.extra?.case_value) : null,
  };
}

function connectionSummary(connection: Connection | undefined, expectedType: Connection["connector_type"]): JsonObject {
  if (!connection) {
    return {
      connector_type: expectedType,
      id: null,
      is_active: false,
      name: "Unbound connection",
    };
  }

  return {
    connector_type: connection.connector_type,
    id: connection.id,
    is_active: connection.is_active,
    name: connection.name,
  };
}

function buildHttpUrl(connection: Connection | undefined, path: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }

  const baseUrl = typeof connection?.config?.base_url === "string" ? connection.config.base_url : "";
  if (!baseUrl) {
    return path;
  }

  try {
    return new URL(path.replace(/^\//, ""), `${baseUrl.replace(/\/$/, "")}/`).toString();
  } catch {
    return path;
  }
}

function evaluateHttpRequest(
  node: RouteFlowNode,
  availableConnections: Connection[],
  context: FlowRuntimeContext,
  tracker: ResolutionTracker,
): { notes: string[]; output: JsonObject } {
  const notes: string[] = [
    "HTTP Request samples do not call the upstream service in the editor. Use Test execution history after publish for real connector output.",
  ];
  const connectionId = typeof node.config.connection_id === "number" ? node.config.connection_id : Number(node.config.connection_id);
  const connection = availableConnections.find((candidate) => candidate.id === connectionId && candidate.connector_type === "http");
  const renderedPath = renderConnectorValue(node.config.path, context, tracker);
  const path = typeof renderedPath === "string" ? renderedPath : stringifyTemplateValue(renderedPath);
  const query = renderConnectorValue(node.config.query, context, tracker);
  const body = "body" in node.config ? renderConnectorValue(node.config.body, context, tracker) : null;
  const method = String(node.config.method ?? "GET").toUpperCase();

  if (!connection) {
    notes.push("Bind this node to an active shared HTTP connection before expecting a real upstream response.");
  } else if (!connection.is_active) {
    notes.push(`Connection '${connection.name}' is inactive, so live requests would fail until it is re-enabled.`);
  }

  return {
    notes,
    output: {
      connection: connectionSummary(connection, "http"),
      request: {
        body,
        method,
        query: isJsonObject(query) ? query : {},
        url: buildHttpUrl(connection, path),
      },
      response: {
        body: {
          _sample: "Connector output is not executed in the editor.",
        },
        content_type: "application/json",
        headers: {},
        status_code: 200,
      },
    },
  };
}

function evaluatePostgresQuery(
  node: RouteFlowNode,
  availableConnections: Connection[],
  context: FlowRuntimeContext,
  tracker: ResolutionTracker,
): { notes: string[]; output: JsonObject } {
  const notes: string[] = [
    "Postgres Query samples do not hit the database in the editor. Use Test execution history after publish for real rows.",
  ];
  const connectionId = typeof node.config.connection_id === "number" ? node.config.connection_id : Number(node.config.connection_id);
  const connection = availableConnections.find((candidate) => candidate.id === connectionId && candidate.connector_type === "postgres");
  const renderedParameters = renderConnectorValue(node.config.parameters, context, tracker);

  if (!connection) {
    notes.push("Bind this node to an active shared Postgres connection before expecting live rows.");
  } else if (!connection.is_active) {
    notes.push(`Connection '${connection.name}' is inactive, so live requests would fail until it is re-enabled.`);
  }

  return {
    notes,
    output: {
      connection: connectionSummary(connection, "postgres"),
      parameters: isJsonObject(renderedParameters) ? renderedParameters : {},
      query: String(node.config.sql ?? ""),
      row_count: 1,
      rows: [
        {
          _sample: "Database rows are not fetched in the editor sample.",
        },
      ],
    },
  };
}

function buildScopeEntries(context: FlowRuntimeContext): RouteFlowInspectionScopeEntry[] {
  const entries: RouteFlowInspectionScopeEntry[] = [
    {
      kind: "route",
      label: "Route metadata",
      refPath: "route",
      sample: cloneJsonValue(context.route),
      shape: describeJsonShape(context.route),
      json: stringifyJson(context.route),
    },
    {
      kind: "request",
      label: "Request path",
      refPath: "request.path",
      sample: cloneJsonValue(context.request.path),
      shape: describeJsonShape(context.request.path),
      json: stringifyJson(context.request.path),
    },
    {
      kind: "request",
      label: "Request query",
      refPath: "request.query",
      sample: cloneJsonValue(context.request.query),
      shape: describeJsonShape(context.request.query),
      json: stringifyJson(context.request.query),
    },
    {
      kind: "request",
      label: "Request body",
      refPath: "request.body",
      sample: cloneJsonValue(context.request.body),
      shape: describeJsonShape(context.request.body),
      json: stringifyJson(context.request.body),
    },
  ];

  for (const [nodeId, value] of Object.entries(context.state)) {
    entries.push({
      kind: "state",
      label: `State: ${nodeId}`,
      refPath: `state.${nodeId}`,
      sample: cloneJsonValue(value),
      shape: describeJsonShape(value),
      json: stringifyJson(value),
    });
  }

  if (context.errors.length > 0) {
    entries.push({
      kind: "errors",
      label: "Validation errors",
      refPath: "errors",
      sample: cloneJsonValue(context.errors),
      shape: describeJsonShape(context.errors),
      json: stringifyJson(context.errors),
    });
  }

  return entries;
}

function outgoingEdgesForNode(definition: RouteFlowDefinition, nodeId: string) {
  return definition.edges.filter((edge) => edge.source === nodeId);
}

function singleNextEdge(definition: RouteFlowDefinition, nodeId: string) {
  const outgoingEdges = outgoingEdgesForNode(definition, nodeId);
  return outgoingEdges.length === 1 ? outgoingEdges[0] : null;
}

function selectIfBranchEdge(definition: RouteFlowDefinition, nodeId: string, matched: boolean) {
  const branch = matched ? "true" : "false";
  return (
    outgoingEdgesForNode(definition, nodeId).find(
      (edge) => String(edge.extra?.branch ?? "").trim().toLowerCase() === branch,
    ) ?? null
  );
}

function selectSwitchEdge(definition: RouteFlowDefinition, nodeId: string, value: JsonValue) {
  let defaultEdge: RouteFlowDefinition["edges"][number] | null = null;

  for (const edge of outgoingEdgesForNode(definition, nodeId)) {
    const branch = String(edge.extra?.branch ?? "").trim().toLowerCase();
    if (branch === "default") {
      defaultEdge = edge;
      continue;
    }
    if (branch === "case" && logicValuesEqual(value, toJsonValue(edge.extra?.case_value))) {
      return {
        branch: "case" as const,
        edge,
      };
    }
  }

  return {
    branch: "default" as const,
    edge: defaultEdge,
  };
}

function nodeOutputTitle(node: RouteFlowNode): string {
  if (node.type === "set_response") {
    return "Live response sample";
  }
  if (node.type === "error_response") {
    return "Error response sample";
  }
  return "Node output sample";
}

function buildBoundaryMessage(
  node: RouteFlowNode,
  responseComparison: RouteFlowResponseComparison | null,
): { message: string; tone: "info" | "success" | "warning" } {
  if (node.type === "set_response" && responseComparison) {
    return {
      message: responseComparison.message,
      tone: responseComparison.tone,
    };
  }

  if (node.type === "transform") {
    return {
      tone: "info",
      message:
        "Transform writes sample data into state only. Deploys return whatever Set Response renders from state, not this object by itself.",
    };
  }

  return {
    tone: "info",
    message:
      "Test contract preview comes from response_schema only. This node affects deployed output only through the live Flow path that eventually reaches Set Response.",
  };
}

export function buildRouteFlowInspectionSnapshot(
  definition: RouteFlowDefinition,
  routeContext: RouteFlowInspectionRouteContext,
  availableConnections: Connection[] = [],
): RouteFlowInspectionSnapshot {
  const runtimeContext = createFlowRuntimeContext(routeContext);
  const contractResponseSample = toJsonValue(buildSchemaSample(routeContext.responseSchema));
  const nodesById: Record<string, RouteFlowNodeInspection> = {};
  const availableNodesById = new Map(definition.nodes.map((node) => [node.id, node]));
  const executedNodeIds: string[] = [];
  const visitedNodeIds = new Set<string>();
  let currentNodeId: string | null =
    definition.nodes.find((node) => node.type === "api_trigger")?.id ?? definition.nodes[0]?.id ?? null;

  while (currentNodeId && !visitedNodeIds.has(currentNodeId)) {
    const node = availableNodesById.get(currentNodeId);
    if (!node) {
      break;
    }

    visitedNodeIds.add(currentNodeId);
    executedNodeIds.push(node.id);
    const tracker: ResolutionTracker = {
      unresolvedRefs: new Set<string>(),
    };
    const scopeEntries = buildScopeEntries(runtimeContext);
    const inputStateCount = Object.keys(runtimeContext.state).length;
    const notes: string[] = [];
    let outputSample: JsonValue = null;
    let nextNodeId: string | null = null;

    if (node.type === "api_trigger") {
      outputSample = {
        request: {
          body_present: runtimeContext.request.body !== null,
          path: cloneJsonValue(runtimeContext.request.path),
          query: cloneJsonValue(runtimeContext.request.query),
        },
        route: cloneJsonValue(runtimeContext.route),
      };
      runtimeContext.state[node.id] = cloneJsonValue(outputSample);
      nextNodeId = singleNextEdge(definition, node.id)?.target ?? null;
    } else if (node.type === "validate_request") {
      outputSample = {
        valid: true,
      };
      runtimeContext.state[node.id] = cloneJsonValue(outputSample);
      nextNodeId = singleNextEdge(definition, node.id)?.target ?? null;
    } else if (node.type === "transform") {
      outputSample = renderTemplate(node.config.output, runtimeContext, tracker);
      runtimeContext.state[node.id] = cloneJsonValue(outputSample);
      nextNodeId = singleNextEdge(definition, node.id)?.target ?? null;
    } else if (node.type === "if_condition") {
      outputSample = evaluateIfCondition(node, runtimeContext, tracker);
      runtimeContext.state[node.id] = cloneJsonValue(outputSample);
      nextNodeId = selectIfBranchEdge(
        definition,
        node.id,
        isJsonObject(outputSample) ? Boolean(outputSample.matched) : false,
      )?.target ?? null;
    } else if (node.type === "switch") {
      outputSample = evaluateSwitch(node, definition, runtimeContext, tracker);
      runtimeContext.state[node.id] = cloneJsonValue(outputSample);
      nextNodeId = selectSwitchEdge(
        definition,
        node.id,
        isJsonObject(outputSample) ? (outputSample.value ?? null) : null,
      ).edge?.target ?? null;
    } else if (node.type === "http_request") {
      const result = evaluateHttpRequest(node, availableConnections, runtimeContext, tracker);
      outputSample = result.output;
      notes.push(...result.notes);
      runtimeContext.state[node.id] = cloneJsonValue(outputSample);
      nextNodeId = singleNextEdge(definition, node.id)?.target ?? null;
    } else if (node.type === "postgres_query") {
      const result = evaluatePostgresQuery(node, availableConnections, runtimeContext, tracker);
      outputSample = result.output;
      notes.push(...result.notes);
      runtimeContext.state[node.id] = cloneJsonValue(outputSample);
      nextNodeId = singleNextEdge(definition, node.id)?.target ?? null;
    } else if (node.type === "set_response") {
      outputSample = {
        body: renderTemplate(node.config.body, runtimeContext, tracker),
        status_code: renderTemplate(
          (node.config.status_code ?? runtimeContext.route.success_status_code) as JsonValue,
          runtimeContext,
          tracker,
        ),
      };
    } else if (node.type === "error_response") {
      outputSample = {
        body: renderTemplate(node.config.body, runtimeContext, tracker),
        status_code: renderTemplate((node.config.status_code ?? 400) as JsonValue, runtimeContext, tracker),
      };
    }

    const responseComparison: RouteFlowResponseComparison | null =
      node.type === "set_response" && isJsonObject(outputSample)
        ? {
            contractSample: contractResponseSample,
            contractJson: contractResponseSample === null ? null : stringifyJson(contractResponseSample),
            matchesContract:
              contractResponseSample === null
                ? null
                : JSON.stringify(outputSample.body ?? null) === JSON.stringify(contractResponseSample),
            message:
              contractResponseSample === null
                ? "Deploy returns this Set Response body. There is no response_schema sample to compare against yet."
                : JSON.stringify(outputSample.body ?? null) === JSON.stringify(contractResponseSample)
                  ? "Deploy returns this Set Response body, and it currently matches the response_schema preview sample."
                  : "Deploy returns this Set Response body. The Test tab preview still comes from response_schema, and these samples differ right now.",
            statusCode: Number(outputSample.status_code ?? runtimeContext.route.success_status_code),
            tone:
              contractResponseSample === null
                ? "info"
                : JSON.stringify(outputSample.body ?? null) === JSON.stringify(contractResponseSample)
                  ? "success"
                  : "warning",
          }
        : null;

    const boundary = buildBoundaryMessage(node, responseComparison);
    const unresolvedRefs = Array.from(tracker.unresolvedRefs);
    if (unresolvedRefs.length > 0) {
      notes.push(
        `Some sample refs could not resolve in the current Flow context: ${unresolvedRefs.join(", ")}.`,
      );
    }

    nodesById[node.id] = {
      boundaryMessage: boundary.message,
      boundaryTone: boundary.tone,
      inputShape: `route + request + state (${inputStateCount} state entr${inputStateCount === 1 ? "y" : "ies"})`,
      outputJson: stringifyJson(outputSample),
      outputSample,
      outputShape: describeJsonShape(outputSample),
      outputTitle: nodeOutputTitle(node),
      responseComparison,
      scopeEntries,
      unresolvedRefs,
      notes,
    };

    currentNodeId = nextNodeId;
  }

  return {
    contractResponseSample,
    contractResponseShape: describeJsonShape(contractResponseSample),
    contractResponseJson: contractResponseSample === null ? null : stringifyJson(contractResponseSample),
    executedNodeIds,
    generatedRequestSample: {
      body: cloneJsonValue(runtimeContext.request.body),
      path: cloneJsonValue(runtimeContext.request.path),
      query: cloneJsonValue(runtimeContext.request.query),
    },
    nodesById,
  };
}
