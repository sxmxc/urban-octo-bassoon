import type {
  JsonObject,
  JsonValue,
  RouteFlowDefinition,
  RouteFlowEdge,
  RouteFlowNode,
  RouteFlowNodeType,
  RouteFlowPosition,
} from "../types/endpoints";

const DEFAULT_CANVAS_X = 56;
const DEFAULT_CANVAS_Y = 64;
const NODE_GAP_X = 264;
const NODE_GAP_Y = 156;
const AUTO_LAYOUT_Y_GAP = 184;

export interface RouteFlowNodePreset {
  type: RouteFlowNodeType;
  title: string;
  description: string;
  icon: string;
  color: string;
  allowMultiple: boolean;
}

export const ROUTE_FLOW_NODE_PRESETS: RouteFlowNodePreset[] = [
  {
    type: "api_trigger",
    title: "API Trigger",
    description: "Starts the live route flow when an incoming request matches this route.",
    icon: "mdi-play-circle-outline",
    color: "primary",
    allowMultiple: false,
  },
  {
    type: "validate_request",
    title: "Validate Request",
    description: "Checks the request against the saved route contract before continuing.",
    icon: "mdi-shield-check-outline",
    color: "accent",
    allowMultiple: false,
  },
  {
    type: "transform",
    title: "Transform",
    description: "Shapes route data into a new state payload that downstream nodes can map from.",
    icon: "mdi-tune-variant",
    color: "secondary",
    allowMultiple: true,
  },
  {
    type: "if_condition",
    title: "If",
    description: "Routes the current data path to a true or false branch using an explicit comparison.",
    icon: "mdi-source-branch",
    color: "warning",
    allowMultiple: true,
  },
  {
    type: "switch",
    title: "Switch",
    description: "Routes the current data path to named cases plus a required default branch.",
    icon: "mdi-call-split",
    color: "warning",
    allowMultiple: true,
  },
  {
    type: "http_request",
    title: "HTTP Request",
    description: "Calls an upstream HTTP service through a saved shared HTTP connection.",
    icon: "mdi-cloud-arrow-right-outline",
    color: "success",
    allowMultiple: true,
  },
  {
    type: "postgres_query",
    title: "Postgres Query",
    description: "Runs a read-only parameterized query through a saved Postgres connection.",
    icon: "mdi-database-search-outline",
    color: "warning",
    allowMultiple: true,
  },
  {
    type: "set_response",
    title: "Set Response",
    description: "Returns the live response body and status code to the caller.",
    icon: "mdi-reply-outline",
    color: "info",
    allowMultiple: false,
  },
  {
    type: "error_response",
    title: "Error Response",
    description: "Optional terminal error path used for validation failures or explicit branch exits.",
    icon: "mdi-alert-circle-outline",
    color: "error",
    allowMultiple: false,
  },
];

const ROUTE_FLOW_NODE_PRESET_BY_TYPE = new Map(
  ROUTE_FLOW_NODE_PRESETS.map((preset) => [preset.type, preset]),
);

const SUPPORTED_ROUTE_FLOW_NODE_TYPES = new Set<RouteFlowNodeType>(
  ROUTE_FLOW_NODE_PRESETS.map((preset) => preset.type),
);

function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function copyJsonValue<T extends JsonValue>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function omitJsonKeys(source: JsonObject, keys: string[]): JsonObject {
  return Object.fromEntries(Object.entries(source).filter(([key]) => !keys.includes(key))) as JsonObject;
}

function normalizeNodePosition(value: JsonValue | undefined, index: number): RouteFlowPosition {
  if (isJsonObject(value)) {
    const x = typeof value.x === "number" ? value.x : Number(value.x);
    const y = typeof value.y === "number" ? value.y : Number(value.y);
    if (Number.isFinite(x) && Number.isFinite(y)) {
      return { x, y };
    }
  }

  const column = index % 3;
  const row = Math.floor(index / 3);
  return {
    x: DEFAULT_CANVAS_X + column * NODE_GAP_X,
    y: DEFAULT_CANVAS_Y + row * NODE_GAP_Y,
  };
}

export function isRouteFlowNodeType(value: unknown): value is RouteFlowNodeType {
  return typeof value === "string" && SUPPORTED_ROUTE_FLOW_NODE_TYPES.has(value as RouteFlowNodeType);
}

export function getRouteFlowNodePreset(nodeType: RouteFlowNodeType): RouteFlowNodePreset {
  return ROUTE_FLOW_NODE_PRESET_BY_TYPE.get(nodeType) ?? ROUTE_FLOW_NODE_PRESETS[0];
}

export function normalizeRouteFlowDefinition(
  value: JsonObject | null | undefined,
): RouteFlowDefinition {
  const source = isJsonObject(value) ? value : {};
  const rawNodes = Array.isArray(source.nodes) ? source.nodes : [];
  const rawEdges = Array.isArray(source.edges) ? source.edges : [];

  const nodes: RouteFlowNode[] = [];
  for (const [index, rawNode] of rawNodes.entries()) {
    if (!isJsonObject(rawNode)) {
      continue;
    }

    const nodeType = isRouteFlowNodeType(rawNode.type) ? rawNode.type : null;
    if (!nodeType) {
      continue;
    }

    const preset = getRouteFlowNodePreset(nodeType);
    nodes.push({
      id: String(rawNode.id || `${nodeType}-${index + 1}`),
      type: nodeType,
      name: typeof rawNode.name === "string" && rawNode.name.trim() ? rawNode.name : preset.title,
      config: isJsonObject(rawNode.config) ? copyJsonValue(rawNode.config) : defaultRouteFlowNodeConfig(nodeType),
      position: normalizeNodePosition(rawNode.position, index),
      extra: omitJsonKeys(rawNode, ["id", "type", "name", "config", "position"]),
    });
  }

  const edges: RouteFlowEdge[] = [];
  for (const [index, rawEdge] of rawEdges.entries()) {
    if (!isJsonObject(rawEdge)) {
      continue;
    }

    const sourceId = String(rawEdge.source || "").trim();
    const targetId = String(rawEdge.target || "").trim();
    if (!sourceId || !targetId) {
      continue;
    }

    edges.push({
      id: typeof rawEdge.id === "string" && rawEdge.id.trim() ? rawEdge.id : `edge-${sourceId}-${targetId}-${index + 1}`,
      source: sourceId,
      target: targetId,
      extra: omitJsonKeys(rawEdge, ["id", "source", "target"]),
    });
  }

  return {
    schema_version: typeof source.schema_version === "number" ? source.schema_version : 1,
    nodes,
    edges,
    extra: omitJsonKeys(source, ["schema_version", "nodes", "edges"]),
  };
}

export function serializeRouteFlowDefinition(definition: RouteFlowDefinition): JsonObject {
  const serialized: JsonObject = {
    ...(definition.extra ? copyJsonValue(definition.extra) : {}),
    schema_version: typeof definition.schema_version === "number" ? definition.schema_version : 1,
    nodes: definition.nodes.map((node) => {
      const serializedNode: JsonObject = {
        ...(node.extra ? copyJsonValue(node.extra) : {}),
        id: node.id,
        type: node.type,
        name: node.name,
        config: copyJsonValue(node.config),
      };

      if (node.position) {
        serializedNode.position = {
          x: node.position.x,
          y: node.position.y,
        };
      }

      return serializedNode;
    }),
    edges: definition.edges.map((edge, index) => ({
      ...(edge.extra ? copyJsonValue(edge.extra) : {}),
      id: typeof edge.id === "string" && edge.id.trim() ? edge.id : `edge-${edge.source}-${edge.target}-${index + 1}`,
      source: edge.source,
      target: edge.target,
    })),
  };

  return serialized;
}

export function defaultRouteFlowNodeConfig(
  nodeType: RouteFlowNodeType,
  options: { successStatusCode?: number } = {},
): JsonObject {
  const successStatusCode = Number.isFinite(options.successStatusCode)
    ? Number(options.successStatusCode)
    : 200;

  switch (nodeType) {
    case "api_trigger":
      return {};
    case "validate_request":
      return {
        body_mode: "contract",
        parameters_mode: "contract",
      };
    case "transform":
      return {
        output: {
          route: {
            name: { $ref: "route.name" },
            method: { $ref: "route.method" },
            path: { $ref: "route.path" },
          },
          request: {
            path: { $ref: "request.path" },
            query: { $ref: "request.query" },
            body: { $ref: "request.body" },
          },
          message: "Replace this starter flow in the Flow tab before deploying to production.",
        },
      };
    case "if_condition":
      return {
        left: { $ref: "request.body" },
        operator: "exists",
      };
    case "switch":
      return {
        value: { $ref: "request.query.mode" },
      };
    case "http_request":
      return {
        connection_id: null,
        method: "GET",
        path: "/status",
        query: {},
        headers: {},
        timeout_ms: 10000,
      };
    case "postgres_query":
      return {
        connection_id: null,
        sql: "select now() as current_time",
        parameters: {},
      };
    case "set_response":
      return {
        status_code: successStatusCode,
        body: { $ref: "state.transform" },
      };
    case "error_response":
      return {
        status_code: 400,
        body: {
          error: "Request validation failed.",
          details: { $ref: "errors" },
        },
      };
  }
}

function nextNodeIndex(nodes: RouteFlowNode[], nodeType: RouteFlowNodeType): number {
  return nodes.filter((node) => node.type === nodeType).length + 1;
}

function nodeBaseId(nodeType: RouteFlowNodeType): string {
  return nodeType.replace(/_/g, "-");
}

function buildNodeId(nodes: RouteFlowNode[], nodeType: RouteFlowNodeType): string {
  const existingIds = new Set(nodes.map((node) => node.id));
  let nextIndex = nextNodeIndex(nodes, nodeType);
  let candidate = `${nodeBaseId(nodeType)}-${nextIndex}`;

  while (existingIds.has(candidate)) {
    nextIndex += 1;
    candidate = `${nodeBaseId(nodeType)}-${nextIndex}`;
  }

  return candidate;
}

function nodePositionIsTaken(position: RouteFlowPosition, nodes: RouteFlowNode[]): boolean {
  return nodes.some(
    (node) =>
      Math.abs((node.position?.x ?? 0) - position.x) < 24 &&
      Math.abs((node.position?.y ?? 0) - position.y) < 24,
  );
}

export function suggestRouteFlowNodePosition(
  nodes: RouteFlowNode[],
  anchorNodeId?: string | null,
): RouteFlowPosition {
  const anchorNode = anchorNodeId ? nodes.find((node) => node.id === anchorNodeId) : null;
  let position = anchorNode?.position
    ? {
        x: anchorNode.position.x + NODE_GAP_X,
        y: anchorNode.position.y,
      }
    : normalizeNodePosition(undefined, nodes.length);

  while (nodePositionIsTaken(position, nodes)) {
    position = {
      x: position.x,
      y: position.y + NODE_GAP_Y / 2,
    };
  }

  return position;
}

function sortOutgoingEdgesForLayout(edges: RouteFlowEdge[]): RouteFlowEdge[] {
  return [...edges].sort((left, right) => {
    const leftBranch = edgeBranch(left);
    const rightBranch = edgeBranch(right);
    const branchOrder = (branch: string): number => {
      if (branch === "true") {
        return 0;
      }
      if (branch === "case") {
        return 1;
      }
      if (branch === "false") {
        return 2;
      }
      if (branch === "default") {
        return 3;
      }
      return 4;
    };

    const branchDelta = branchOrder(leftBranch) - branchOrder(rightBranch);
    if (branchDelta !== 0) {
      return branchDelta;
    }

    return String(edgeCaseValue(left) ?? "").localeCompare(String(edgeCaseValue(right) ?? ""));
  });
}

export function autoLayoutRouteFlowDefinition(definition: RouteFlowDefinition): RouteFlowDefinition {
  const triggerNode = definition.nodes.find((node) => node.type === "api_trigger") ?? definition.nodes[0];
  if (!triggerNode) {
    return definition;
  }

  const depthById = new Map<string, number>();
  const queue: string[] = [triggerNode.id];
  depthById.set(triggerNode.id, 0);

  while (queue.length > 0) {
    const nodeId = queue.shift();
    if (!nodeId) {
      continue;
    }

    const currentDepth = depthById.get(nodeId) ?? 0;
    for (const edge of sortOutgoingEdgesForLayout(outgoingEdgesForNode(definition.edges, nodeId))) {
      const nextDepth = currentDepth + 1;
      if ((depthById.get(edge.target) ?? -1) < nextDepth) {
        depthById.set(edge.target, nextDepth);
      }
      queue.push(edge.target);
    }
  }

  const traversalOrder: string[] = [];
  const visited = new Set<string>();
  const walk = (nodeId: string) => {
    if (visited.has(nodeId)) {
      return;
    }

    visited.add(nodeId);
    traversalOrder.push(nodeId);
    for (const edge of sortOutgoingEdgesForLayout(outgoingEdgesForNode(definition.edges, nodeId))) {
      walk(edge.target);
    }
  };
  walk(triggerNode.id);
  for (const node of definition.nodes) {
    if (!visited.has(node.id)) {
      traversalOrder.push(node.id);
    }
  }

  const orderById = new Map(traversalOrder.map((nodeId, index) => [nodeId, index]));
  const columns = new Map<number, RouteFlowNode[]>();
  for (const node of definition.nodes) {
    const depth = depthById.get(node.id) ?? 0;
    const existing = columns.get(depth) ?? [];
    existing.push(node);
    columns.set(depth, existing);
  }

  const positionedNodes = definition.nodes.map((node) => {
    const depth = depthById.get(node.id) ?? 0;
    const columnNodes = [...(columns.get(depth) ?? [node])].sort(
      (left, right) => (orderById.get(left.id) ?? 0) - (orderById.get(right.id) ?? 0),
    );
    const rowIndex = Math.max(
      0,
      columnNodes.findIndex((columnNode) => columnNode.id === node.id),
    );

    return {
      ...node,
      position: {
        x: DEFAULT_CANVAS_X + depth * NODE_GAP_X,
        y: DEFAULT_CANVAS_Y + rowIndex * AUTO_LAYOUT_Y_GAP,
      },
    };
  });

  return {
    ...definition,
    nodes: positionedNodes,
  };
}

export function canAddRouteFlowNode(
  nodeType: RouteFlowNodeType,
  nodes: RouteFlowNode[],
): boolean {
  const preset = getRouteFlowNodePreset(nodeType);
  return preset.allowMultiple || !nodes.some((node) => node.type === nodeType);
}

export function createRouteFlowNode(
  nodeType: RouteFlowNodeType,
  nodes: RouteFlowNode[],
  options: {
    anchorNodeId?: string | null;
    successStatusCode?: number;
  } = {},
): RouteFlowNode {
  const preset = getRouteFlowNodePreset(nodeType);
  return {
    id: buildNodeId(nodes, nodeType),
    type: nodeType,
    name: preset.title,
    config: defaultRouteFlowNodeConfig(nodeType, options),
    position: suggestRouteFlowNodePosition(nodes, options.anchorNodeId),
    extra: {},
  };
}

const IF_OPERATORS = new Set([
  "contains",
  "equals",
  "exists",
  "falsy",
  "greater_than",
  "greater_than_or_equal",
  "is_empty",
  "is_not_empty",
  "less_than",
  "less_than_or_equal",
  "not_equals",
  "not_exists",
  "truthy",
]);

function incomingEdgesForNode(edges: RouteFlowEdge[], nodeId: string): RouteFlowEdge[] {
  return edges.filter((edge) => edge.target === nodeId);
}

function outgoingEdgesForNode(edges: RouteFlowEdge[], nodeId: string): RouteFlowEdge[] {
  return edges.filter((edge) => edge.source === nodeId);
}

function countIncomingEdges(edges: RouteFlowEdge[], nodeId: string): number {
  return incomingEdgesForNode(edges, nodeId).length;
}

function countOutgoingEdges(edges: RouteFlowEdge[], nodeId: string): number {
  return outgoingEdgesForNode(edges, nodeId).length;
}

function edgeBranch(edge: RouteFlowEdge): string {
  const rawValue = edge.extra?.branch;
  return typeof rawValue === "string" ? rawValue.trim().toLowerCase() : "";
}

function edgeCaseValue(edge: RouteFlowEdge): JsonValue | undefined {
  return edge.extra?.case_value;
}

function caseValueKey(value: JsonValue | undefined): string {
  return JSON.stringify(value ?? null);
}

function reachableNodeIds(
  startNodeId: string,
  edges: RouteFlowEdge[],
  options: { reverse?: boolean } = {},
): Set<string> {
  const reverse = options.reverse ?? false;
  const visited = new Set<string>();
  const pending = [startNodeId];

  while (pending.length > 0) {
    const nodeId = pending.shift();
    if (!nodeId || visited.has(nodeId)) {
      continue;
    }

    visited.add(nodeId);
    const nextEdges = reverse ? incomingEdgesForNode(edges, nodeId) : outgoingEdgesForNode(edges, nodeId);
    for (const edge of nextEdges) {
      pending.push(reverse ? edge.source : edge.target);
    }
  }

  return visited;
}

export function routeFlowEdgeLabel(edge: RouteFlowEdge): string {
  const branch = edgeBranch(edge);
  if (branch === "true") {
    return "True";
  }
  if (branch === "false") {
    return "False";
  }
  if (branch === "default") {
    return "Default";
  }
  if (branch === "case") {
    const caseValue = edgeCaseValue(edge);
    return caseValue === undefined || caseValue === null || caseValue === ""
      ? "Case"
      : `Case: ${typeof caseValue === "string" ? caseValue : JSON.stringify(caseValue)}`;
  }
  return "";
}

export function defaultRouteFlowEdgeExtra(
  definition: RouteFlowDefinition,
  sourceNodeId: string,
  sourceHandle?: string | null,
): JsonObject {
  const sourceNode = definition.nodes.find((node) => node.id === sourceNodeId);
  if (!sourceNode) {
    return {};
  }

  const outgoingEdges = outgoingEdgesForNode(definition.edges, sourceNodeId);
  if (sourceNode.type === "if_condition") {
    if (sourceHandle === "true" || sourceHandle === "false") {
      return {
        branch: sourceHandle,
      };
    }

    const branches = new Set(outgoingEdges.map(edgeBranch));
    return {
      branch: branches.has("true") ? "false" : "true",
    };
  }

  if (sourceNode.type === "switch") {
    if (sourceHandle === "default") {
      return { branch: "default" };
    }

    if (sourceHandle === "case") {
      return {
        branch: "case",
        case_value: `case-${outgoingEdges.filter((edge) => edgeBranch(edge) === "case").length + 1}`,
      };
    }

    const hasDefault = outgoingEdges.some((edge) => edgeBranch(edge) === "default");
    if (!hasDefault) {
      return { branch: "default" };
    }

    return {
      branch: "case",
      case_value: `case-${outgoingEdges.filter((edge) => edgeBranch(edge) === "case").length + 1}`,
    };
  }

  return {};
}

function positiveInt(value: JsonValue | undefined): number | null {
  if (typeof value === "number" && Number.isInteger(value) && value > 0) {
    return value;
  }

  if (typeof value === "string" && /^\d+$/.test(value.trim())) {
    const parsed = Number(value.trim());
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
  }

  return null;
}

function validateNodeConfig(node: RouteFlowNode): string | null {
  switch (node.type) {
    case "if_condition": {
      if (!("left" in node.config)) {
        return "If needs a left comparison value.";
      }
      const operator = String(node.config.operator ?? "").trim().toLowerCase();
      if (!IF_OPERATORS.has(operator)) {
        return "If needs a supported operator.";
      }
      if (
        ["contains", "equals", "greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal", "not_equals"].includes(operator)
        && !("right" in node.config)
      ) {
        return `If needs a right comparison value for '${operator}'.`;
      }
      return null;
    }
    case "switch":
      if (!("value" in node.config)) {
        return "Switch needs a value to evaluate.";
      }
      return null;
    case "http_request":
      if (positiveInt(node.config.connection_id) === null) {
        return "HTTP Request requires a saved connection.";
      }
      if (!String(node.config.path ?? "").trim()) {
        return "HTTP Request needs a path or absolute URL.";
      }
      if (node.config.query !== undefined && !isJsonObject(node.config.query)) {
        return "HTTP Request query parameters must stay a JSON object.";
      }
      if (node.config.headers !== undefined && !isJsonObject(node.config.headers)) {
        return "HTTP Request headers must stay a JSON object.";
      }
      return null;
    case "postgres_query":
      if (positiveInt(node.config.connection_id) === null) {
        return "Postgres Query requires a saved connection.";
      }
      if (!String(node.config.sql ?? "").trim()) {
        return "Postgres Query needs a SQL statement.";
      }
      if (node.config.parameters !== undefined && !isJsonObject(node.config.parameters)) {
        return "Postgres Query parameters must stay a JSON object.";
      }
      return null;
    default:
      return null;
  }
}

export function buildRouteFlowEdgeId(
  edges: RouteFlowEdge[],
  source: string,
  target: string,
): string {
  const existingIds = new Set(edges.map((edge) => edge.id).filter((value): value is string => typeof value === "string"));
  let nextIndex = 1;
  let candidate = `edge-${source}-${target}-${nextIndex}`;

  while (existingIds.has(candidate)) {
    nextIndex += 1;
    candidate = `edge-${source}-${target}-${nextIndex}`;
  }

  return candidate;
}

export function validateRouteFlowConnection(
  definition: RouteFlowDefinition,
  source: string,
  target: string,
): string | null {
  if (!source || !target) {
    return "Pick both a source and target node before creating a connection.";
  }

  if (source === target) {
    return "A flow node cannot connect to itself.";
  }

  const sourceNode = definition.nodes.find((node) => node.id === source);
  const targetNode = definition.nodes.find((node) => node.id === target);

  if (!sourceNode || !targetNode) {
    return "Flow connections must point at existing nodes.";
  }

  if (sourceNode.type === "set_response" || sourceNode.type === "error_response") {
    return `${getRouteFlowNodePreset(sourceNode.type).title} cannot start a new connection.`;
  }

  if (targetNode.type === "api_trigger") {
    return `${getRouteFlowNodePreset(targetNode.type).title} cannot be used as a connection target.`;
  }

  if (definition.edges.some((edge) => edge.source === source && edge.target === target)) {
    return "Those nodes are already connected.";
  }

  const outgoingCount = countOutgoingEdges(definition.edges, source);
  if (sourceNode.type === "if_condition" && outgoingCount >= 2) {
    return "If supports exactly two outgoing paths.";
  }

  if (!["if_condition", "switch"].includes(sourceNode.type) && outgoingCount >= 1) {
    return `${getRouteFlowNodePreset(sourceNode.type).title} currently supports one outgoing path.`;
  }

  return null;
}

export function validateRouteFlowDefinition(definition: RouteFlowDefinition): string[] {
  const errors: string[] = [];
  const nodesById = new Map(definition.nodes.map((node) => [node.id, node]));
  const apiTriggers = definition.nodes.filter((node) => node.type === "api_trigger");
  const responseNodes = definition.nodes.filter((node) => node.type === "set_response");
  const errorNodes = definition.nodes.filter((node) => node.type === "error_response");

  if (apiTriggers.length !== 1) {
    errors.push("Add exactly one API Trigger node.");
  }

  if (responseNodes.length !== 1) {
    errors.push("Add exactly one Set Response node.");
  }

  if (errorNodes.length > 1) {
    errors.push("Use at most one Error Response node in the live runtime.");
  }

  for (const edge of definition.edges) {
    if (!nodesById.has(edge.source) || !nodesById.has(edge.target)) {
      errors.push("Every flow connection must point at an existing node.");
      break;
    }
  }

  if (errors.length > 0) {
    return Array.from(new Set(errors));
  }

  const connectedErrorNodes = errorNodes.filter((node) => countIncomingEdges(definition.edges, node.id) > 0);
  const mainNodes = definition.nodes.filter((node) => node.type !== "error_response").concat(connectedErrorNodes);
  const mainNodeIds = new Set(mainNodes.map((node) => node.id));
  const indegree = new Map(mainNodes.map((node) => [node.id, 0]));

  for (const edge of definition.edges) {
    if (mainNodeIds.has(edge.target)) {
      indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1);
    }
  }

  const orderedIds = Array.from(indegree.entries())
    .filter(([, degree]) => degree === 0)
    .map(([nodeId]) => nodeId);
  let visitedCount = 0;
  while (orderedIds.length > 0) {
    const nodeId = orderedIds.shift();
    if (!nodeId) {
      continue;
    }

    visitedCount += 1;
    for (const edge of outgoingEdgesForNode(definition.edges, nodeId)) {
      if (!mainNodeIds.has(edge.target)) {
        continue;
      }

      const nextDegree = (indegree.get(edge.target) ?? 0) - 1;
      indegree.set(edge.target, nextDegree);
      if (nextDegree === 0) {
        orderedIds.push(edge.target);
      }
    }
  }

  if (visitedCount !== mainNodes.length) {
    errors.push("Flows must stay acyclic.");
  }

  for (const node of definition.nodes) {
    const nodeConfigError = validateNodeConfig(node);
    if (nodeConfigError) {
      errors.push(nodeConfigError);
    }

    const incoming = countIncomingEdges(definition.edges, node.id);
    const outgoing = countOutgoingEdges(definition.edges, node.id);

    if (node.type === "error_response") {
      if (outgoing > 0) {
        errors.push("Error Response is a terminal path and cannot connect downstream.");
      }
      continue;
    }

    if (node.type === "api_trigger") {
      if (incoming !== 0) {
        errors.push("API Trigger cannot receive incoming connections.");
      }
      if (outgoing !== 1) {
        errors.push("API Trigger must connect to exactly one next step.");
      }
      continue;
    }

    if (node.type === "set_response") {
      if (incoming < 1) {
        errors.push("Set Response must receive at least one incoming connection.");
      }
      if (outgoing !== 0) {
        errors.push("Set Response is the end of the live flow.");
      }
      continue;
    }

    if (incoming < 1) {
      errors.push(`${getRouteFlowNodePreset(node.type).title} must receive at least one incoming connection.`);
    }

    if (node.type === "if_condition") {
      if (outgoing !== 2) {
        errors.push("If must connect to exactly two outgoing paths.");
      }
      const branches = new Set(outgoingEdgesForNode(definition.edges, node.id).map(edgeBranch));
      if (!(branches.has("true") && branches.has("false")) || branches.size !== 2) {
        errors.push("If must define one True branch and one False branch.");
      }
      continue;
    }

    if (node.type === "switch") {
      if (outgoing < 2) {
        errors.push("Switch must define at least one case plus a default path.");
      }
      const outgoingEdges = outgoingEdgesForNode(definition.edges, node.id);
      const defaultCount = outgoingEdges.filter((edge) => edgeBranch(edge) === "default").length;
      const caseEdges = outgoingEdges.filter((edge) => edgeBranch(edge) === "case");
      const caseKeys = new Set(caseEdges.map((edge) => caseValueKey(edgeCaseValue(edge))));
      if (defaultCount !== 1) {
        errors.push("Switch must include exactly one Default path.");
      }
      if (caseEdges.length < 1) {
        errors.push("Switch must include at least one Case path.");
      }
      if (caseEdges.some((edge) => edgeCaseValue(edge) === undefined || edgeCaseValue(edge) === null || edgeCaseValue(edge) === "")) {
        errors.push("Switch case paths need a case value.");
      }
      if (caseKeys.size !== caseEdges.length) {
        errors.push("Switch case values must stay unique.");
      }
      if (outgoingEdges.some((edge) => !["case", "default"].includes(edgeBranch(edge)))) {
        errors.push("Switch outgoing paths must be marked as Case or Default.");
      }
      continue;
    }

    if (outgoing !== 1) {
      errors.push(`${getRouteFlowNodePreset(node.type).title} must connect to exactly one next node.`);
    }
  }

  const trigger = apiTriggers[0];
  const response = responseNodes[0];

  if (!trigger || !response || errors.length > 0) {
    return Array.from(new Set(errors));
  }

  const reachableFromTrigger = reachableNodeIds(trigger.id, definition.edges);
  if (reachableFromTrigger.size !== mainNodes.length || !mainNodes.every((node) => reachableFromTrigger.has(node.id))) {
    errors.push("Connect every main node into the reachable flow from API Trigger.");
  }

  const terminalNodeIds = new Set([response.id, ...connectedErrorNodes.map((node) => node.id)]);
  const reachableToTerminal = new Set<string>();
  for (const terminalNodeId of terminalNodeIds) {
    for (const nodeId of reachableNodeIds(terminalNodeId, definition.edges, { reverse: true })) {
      reachableToTerminal.add(nodeId);
    }
  }

  if (reachableToTerminal.size !== mainNodes.length || !mainNodes.every((node) => reachableToTerminal.has(node.id))) {
    errors.push("Every connected node must eventually lead to Set Response or Error Response.");
  }

  return Array.from(new Set(errors));
}
