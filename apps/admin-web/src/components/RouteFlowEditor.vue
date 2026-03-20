<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch, type ComponentPublicInstance } from "vue";
import { Background } from "@vue-flow/background";
import { ControlButton, Controls } from "@vue-flow/controls";
import { MiniMap } from "@vue-flow/minimap";
import {
  Panel,
  VueFlow,
  type Connection as VueFlowConnection,
  type NodeMouseEvent,
  type VueFlowStore,
} from "@vue-flow/core";
import RouteFlowCanvasNode from "./RouteFlowCanvasNode.vue";
import type {
  Connection,
  JsonObject,
  JsonValue,
  RouteFlowDefinition,
  RouteFlowEdge,
  RouteFlowNode,
  RouteFlowNodeType,
} from "../types/endpoints";
import {
  ROUTE_FLOW_NODE_PRESETS,
  autoLayoutRouteFlowDefinition,
  buildRouteFlowEdgeId,
  canAddRouteFlowNode,
  createRouteFlowNode,
  defaultRouteFlowEdgeExtra,
  getRouteFlowNodePreset,
  normalizeRouteFlowDefinition,
  routeFlowEdgeLabel,
  serializeRouteFlowDefinition,
  validateRouteFlowConnection,
  validateRouteFlowDefinition,
} from "../utils/routeFlow";
import { buildRouteFlowInspectionSnapshot } from "../utils/routeFlowInspection";
import {
  vPragmaticDraggable,
  vPragmaticDropTarget,
  type PragmaticDraggableBinding,
  type PragmaticDropTargetBinding,
} from "../utils/pragmaticDnd";
import {
  createRouteFlowPaletteDragPayload,
  createRouteFlowReferenceDragPayload,
  getRouteFlowPaletteDragPayload,
  getRouteFlowReferenceDragPayload,
} from "../utils/routeFlowDragDrop";

interface RouteFlowCanvasNodeData {
  title: string;
  description: string;
  icon: string;
  color: string;
  runtimeType: RouteFlowNodeType;
  hasIncoming: boolean;
  hasOutgoing: boolean;
  config: JsonObject;
  extra: JsonObject;
}

interface RouteFlowCanvasEdgeData {
  extra: JsonObject;
}

interface CanvasNode {
  id: string;
  type: string;
  label: string;
  position: {
    x: number;
    y: number;
  };
  data: RouteFlowCanvasNodeData;
}

interface CanvasEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  label?: string;
  animated?: boolean;
  data?: RouteFlowCanvasEdgeData;
}

type ReferenceTarget = "transform" | "response" | "error" | "ifLeft" | "ifRight" | "switchValue";
type JsonConfigTarget = "transform" | "response" | "error" | "httpQuery" | "httpHeaders" | "httpBody" | "postgresParameters";
type TextConfigTarget = "httpPath";
type FlexibleConfigTarget = "ifLeft" | "ifRight" | "switchValue";
type JsonEditorSelection = { start: number; end: number };
type FocusPreviewMode = "schema" | "table" | "json";
type FocusEditorTab = "parameters" | "settings";
type FocusSchemaRow = {
  depth: number;
  label: string;
  preview: string;
  refPath: string;
  shape: string;
};
type FocusSchemaSection = {
  label: string;
  refPath: string;
  rows: FocusSchemaRow[];
  shape: string;
};
type FocusPreviewTableRow = {
  path: string;
  source: string;
  type: string;
  value: string;
};
type InspectorGuidanceTone = "info" | "warning";
const BASE_TRANSFORM_REFERENCE_SNIPPETS = [
  { label: "route.path", value: "route.path" },
  { label: "request.path", value: "request.path" },
  { label: "request.query", value: "request.query" },
  { label: "request.body", value: "request.body" },
];

const BASE_RESPONSE_REFERENCE_SNIPPETS = [
  { label: "request.body", value: "request.body" },
  { label: "request.query", value: "request.query" },
];

const ERROR_REFERENCE_SNIPPETS = [
  { label: "errors", value: "errors" },
  { label: "request.path", value: "request.path" },
];

const HTTP_METHOD_OPTIONS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"];
const IF_OPERATOR_OPTIONS = [
  { title: "Equals", value: "equals" },
  { title: "Not equals", value: "not_equals" },
  { title: "Exists", value: "exists" },
  { title: "Does not exist", value: "not_exists" },
  { title: "Truthy", value: "truthy" },
  { title: "Falsy", value: "falsy" },
  { title: "Is empty", value: "is_empty" },
  { title: "Is not empty", value: "is_not_empty" },
  { title: "Contains", value: "contains" },
  { title: "Greater than", value: "greater_than" },
  { title: "Greater than or equal", value: "greater_than_or_equal" },
  { title: "Less than", value: "less_than" },
  { title: "Less than or equal", value: "less_than_or_equal" },
];
const IF_UNARY_OPERATORS = new Set([
  "exists",
  "not_exists",
  "truthy",
  "falsy",
  "is_empty",
  "is_not_empty",
]);
const IF_BRANCH_OPTIONS = [
  { title: "True", value: "true" },
  { title: "False", value: "false" },
];
const SWITCH_BRANCH_OPTIONS = [
  { title: "Case", value: "case" },
  { title: "Default", value: "default" },
];
const ROUTE_FLOW_NODE_WIDTH = 236;
const ROUTE_FLOW_NODE_HEIGHT = 104;
const DEFAULT_CONNECTION_PROJECT = "default";
const DEFAULT_CONNECTION_ENVIRONMENT = "production";
const FOCUS_SELECT_MENU_PROPS = {
  contentClass: "route-flow-editor__select-menu",
  zIndex: 3600,
};

const props = withDefaults(
  defineProps<{
    modelValue: RouteFlowDefinition;
    errorMessage?: string | null;
    availableConnections?: Connection[];
    preferredConnectionEnvironment?: string;
    preferredConnectionProject?: string;
    requestSchema?: JsonObject | null;
    responseSchema?: JsonObject | null;
    routeId?: number | null;
    routeMethod?: string | null;
    routeName?: string | null;
    routePath?: string | null;
    saveDisabled?: boolean;
    saveLoading?: boolean;
    successStatusCode?: number;
  }>(),
  {
    errorMessage: null,
    availableConnections: () => [],
    preferredConnectionEnvironment: DEFAULT_CONNECTION_ENVIRONMENT,
    preferredConnectionProject: DEFAULT_CONNECTION_PROJECT,
    requestSchema: () => ({}),
    responseSchema: () => ({}),
    routeId: null,
    routeMethod: "GET",
    routeName: "Draft route",
    routePath: "/api/example",
    saveDisabled: false,
    saveLoading: false,
    successStatusCode: 200,
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: RouteFlowDefinition];
  "validation-change": [value: string | null];
  "focus-mode-change": [value: boolean];
  "save-requested": [];
}>();

const flowDefinitionState = ref<RouteFlowDefinition>(
  normalizeRouteFlowDefinition(serializeRouteFlowDefinition(props.modelValue)),
);
const canvasNodes = ref<CanvasNode[]>([]);
const canvasEdges = ref<CanvasEdge[]>([]);
const selectedNodeId = ref<string | null>(null);
const transformOutputText = ref("");
const responseBodyText = ref("");
const errorBodyText = ref("");
const ifLeftText = ref("");
const ifRightText = ref("");
const switchValueText = ref("");
const httpPathText = ref("");
const httpQueryText = ref("");
const httpHeadersText = ref("");
const httpBodyText = ref("");
const postgresSqlText = ref("");
const postgresParametersText = ref("");
const transformOutputError = ref<string | null>(null);
const responseBodyError = ref<string | null>(null);
const errorBodyError = ref<string | null>(null);
const ifLeftError = ref<string | null>(null);
const ifRightError = ref<string | null>(null);
const switchValueError = ref<string | null>(null);
const httpQueryError = ref<string | null>(null);
const httpHeadersError = ref<string | null>(null);
const httpBodyError = ref<string | null>(null);
const postgresParametersError = ref<string | null>(null);
const isDesignerJsonOpen = ref<number | undefined>(undefined);
const focusSignalsOpen = ref<number[]>([]);
const inspectorSectionsOpen = ref<string[]>([]);
const flowInstance = ref<VueFlowStore | null>(null);
const hasManualLayout = ref(false);
const isFocusMode = ref(false);
const isFocusPaletteOpen = ref(false);
const isFocusInfoOpen = ref(false);
const isFocusInspectorOpen = ref(false);
const focusInputPreviewMode = ref<FocusPreviewMode>("schema");
const focusOutputPreviewMode = ref<FocusPreviewMode>("schema");
const focusEditorTab = ref<FocusEditorTab>("parameters");
let previousBodyOverflow = "";
const jsonEditorRootElements: Partial<Record<JsonConfigTarget, HTMLElement | null>> = {};
const jsonEditorSelections: Partial<Record<JsonConfigTarget, JsonEditorSelection>> = {};
const textEditorRootElements: Partial<Record<TextConfigTarget, HTMLElement | null>> = {};
const textEditorSelections: Partial<Record<TextConfigTarget, JsonEditorSelection>> = {};

function copyJsonValue<T extends JsonValue>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function canvasHandlesForNode(nodeType: RouteFlowNodeType): { hasIncoming: boolean; hasOutgoing: boolean } {
  if (nodeType === "api_trigger") {
    return { hasIncoming: false, hasOutgoing: true };
  }

  if (nodeType === "set_response" || nodeType === "error_response") {
    return { hasIncoming: true, hasOutgoing: false };
  }

  return { hasIncoming: true, hasOutgoing: true };
}

function edgeSourceHandle(extra: JsonObject | undefined): string | undefined {
  const branch = typeof extra?.branch === "string" ? extra.branch.trim().toLowerCase() : "";
  if (["true", "false", "case", "default"].includes(branch)) {
    return branch;
  }
  return undefined;
}

function miniMapNodeColor(node: { data?: RouteFlowCanvasNodeData }): string {
  return `rgb(var(--v-theme-${node.data?.color ?? "primary"}))`;
}

function miniMapNodeStrokeColor(node: { data?: RouteFlowCanvasNodeData }): string {
  return node.data?.runtimeType === "error_response"
    ? "rgba(248, 113, 113, 0.92)"
    : "rgba(248, 250, 252, 0.92)";
}

function toCanvasNode(node: RouteFlowNode): CanvasNode {
  const preset = getRouteFlowNodePreset(node.type);
  const handles = canvasHandlesForNode(node.type);

  return {
    id: node.id,
    type: "route",
    label: node.name,
    position: node.position ?? { x: 0, y: 0 },
    data: {
      title: preset.title,
      description: preset.description,
      icon: preset.icon,
      color: preset.color,
      runtimeType: node.type,
      hasIncoming: handles.hasIncoming,
      hasOutgoing: handles.hasOutgoing,
      config: copyJsonValue(node.config),
      extra: node.extra ? copyJsonValue(node.extra) : {},
    },
  };
}

function toCanvasEdge(edge: RouteFlowEdge): CanvasEdge {
  return {
    id: typeof edge.id === "string" && edge.id.trim() ? edge.id : `edge-${edge.source}-${edge.target}`,
    source: edge.source,
    target: edge.target,
    sourceHandle: edgeSourceHandle(edge.extra),
    label: routeFlowEdgeLabel(edge) || undefined,
    animated: true,
    data: {
      extra: edge.extra ? copyJsonValue(edge.extra) : {},
    },
  };
}

function toRouteFlowNode(node: CanvasNode): RouteFlowNode {
  return {
    id: node.id,
    type: node.data.runtimeType,
    name: typeof node.label === "string" && node.label.trim() ? node.label : node.data.title,
    config: copyJsonValue(node.data.config),
    position: {
      x: Number(node.position.x ?? 0),
      y: Number(node.position.y ?? 0),
    },
    extra: node.data.extra,
  };
}

function toRouteFlowEdge(edge: CanvasEdge): RouteFlowEdge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    extra: edge.data?.extra ?? {},
  };
}

function stringifyFlexibleValue(value: JsonValue | undefined): string {
  if (value === undefined || value === null) {
    return "";
  }

  if (typeof value === "string") {
    return value;
  }

  return JSON.stringify(value, null, 2);
}

function syncCanvasFromDefinition(definition: RouteFlowDefinition): void {
  canvasNodes.value = definition.nodes.map(toCanvasNode);
  canvasEdges.value = definition.edges.map(toCanvasEdge);
  if (!canvasNodes.value.some((node) => node.id === selectedNodeId.value)) {
    selectedNodeId.value = canvasNodes.value[0]?.id ?? null;
  }
}

function buildDefinitionFromCanvas(): RouteFlowDefinition {
  return {
    schema_version: flowDefinitionState.value.schema_version,
    extra: flowDefinitionState.value.extra ? copyJsonValue(flowDefinitionState.value.extra) : {},
    nodes: canvasNodes.value.map(toRouteFlowNode),
    edges: canvasEdges.value.map(toRouteFlowEdge),
  };
}

function connectionIdFromValue(value: JsonValue | undefined): number | null {
  if (typeof value === "number" && Number.isInteger(value) && value > 0) {
    return value;
  }

  if (typeof value === "string" && /^\d+$/.test(value.trim())) {
    const parsed = Number(value.trim());
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
  }

  return null;
}

function connectionOptionTitle(connection: Connection): string {
  const titleParts = [connection.name, `${connection.project}/${connection.environment}`];
  if (!connection.is_active) {
    titleParts.push("inactive");
  }
  return titleParts.join(" · ");
}

function buildStateReferenceSnippets(node: RouteFlowNode): { label: string; value: string }[] {
  const base = `state.${node.id}`;

  switch (node.type) {
    case "validate_request":
      return [{ label: `${node.id}.valid`, value: `${base}.valid` }];
    case "transform":
      return [{ label: base, value: base }];
    case "http_request":
      return [
        { label: `${node.id}.response.body`, value: `${base}.response.body` },
        { label: `${node.id}.response.status_code`, value: `${base}.response.status_code` },
        { label: `${node.id}.request.url`, value: `${base}.request.url` },
      ];
    case "postgres_query":
      return [
        { label: `${node.id}.rows`, value: `${base}.rows` },
        { label: `${node.id}.row_count`, value: `${base}.row_count` },
      ];
    default:
      return [];
  }
}

const currentFlowDefinition = computed<RouteFlowDefinition>(() => buildDefinitionFromCanvas());
const selectedCanvasNode = computed<CanvasNode | null>(
  () => canvasNodes.value.find((node) => node.id === selectedNodeId.value) ?? null,
);
const flowStateReferenceSnippets = computed(() =>
  currentFlowDefinition.value.nodes
    .filter((node) => node.id !== selectedNodeId.value)
    .filter((node) => !["api_trigger", "set_response", "error_response"].includes(node.type))
    .flatMap(buildStateReferenceSnippets),
);
const transformReferenceSnippets = computed(() => [
  ...BASE_TRANSFORM_REFERENCE_SNIPPETS,
  ...flowStateReferenceSnippets.value,
]);
const responseReferenceSnippets = computed(() => [
  ...flowStateReferenceSnippets.value,
  ...BASE_RESPONSE_REFERENCE_SNIPPETS,
]);
const sortedAvailableConnections = computed(() =>
  [...props.availableConnections].sort((left, right) => {
    const leftPreferred =
      left.project === props.preferredConnectionProject && left.environment === props.preferredConnectionEnvironment;
    const rightPreferred =
      right.project === props.preferredConnectionProject && right.environment === props.preferredConnectionEnvironment;
    if (leftPreferred !== rightPreferred) {
      return leftPreferred ? -1 : 1;
    }
    if (left.is_active !== right.is_active) {
      return left.is_active ? -1 : 1;
    }
    return (
      left.project.localeCompare(right.project) ||
      left.environment.localeCompare(right.environment) ||
      left.name.localeCompare(right.name)
    );
  }),
);
const httpConnectionOptions = computed(() =>
  sortedAvailableConnections.value
    .filter((connection) => connection.connector_type === "http")
    .map((connection) => ({
      title: connectionOptionTitle(connection),
      value: connection.id,
    })),
);
const postgresConnectionOptions = computed(() =>
  sortedAvailableConnections.value
    .filter((connection) => connection.connector_type === "postgres")
    .map((connection) => ({
      title: connectionOptionTitle(connection),
      value: connection.id,
    })),
);
const selectedFlowNodePreset = computed(() => {
  const node = selectedCanvasNode.value;
  return node ? getRouteFlowNodePreset(node.data.runtimeType) : null;
});
const focusCreatablePresets = computed(() =>
  ROUTE_FLOW_NODE_PRESETS.filter((preset) => canAddRouteFlowNode(preset.type, currentFlowDefinition.value.nodes)),
);
const focusReusablePresets = computed(() =>
  ROUTE_FLOW_NODE_PRESETS.filter(
    (preset) => !canAddRouteFlowNode(preset.type, currentFlowDefinition.value.nodes) && canUsePreset(preset.type),
  ),
);
const selectedNodeConnectionSummary = computed(() => {
  if (!selectedCanvasNode.value) {
    return { incoming: 0, outgoing: 0 };
  }

  return {
    incoming: canvasEdges.value.filter((edge) => edge.target === selectedCanvasNode.value?.id).length,
    outgoing: canvasEdges.value.filter((edge) => edge.source === selectedCanvasNode.value?.id).length,
  };
});
const selectedNodeOutgoingConnections = computed(() =>
  selectedCanvasNode.value
    ? canvasEdges.value
        .filter((edge) => edge.source === selectedCanvasNode.value?.id)
        .map((edge) => ({
          id: edge.id,
          sourceId: edge.source,
          sourceLabel: selectedCanvasNode.value?.label ?? edge.source,
          targetId: edge.target,
          targetLabel: canvasNodes.value.find((node) => node.id === edge.target)?.label ?? edge.target,
          branch: typeof edge.data?.extra?.branch === "string" ? edge.data.extra.branch : "",
          caseValue: edge.data?.extra?.case_value,
          label: routeFlowEdgeLabel(toRouteFlowEdge(edge)),
        }))
    : [],
);
const selectedNodeStatusCode = computed({
  get() {
    const rawValue = selectedCanvasNode.value?.data.config?.status_code;
    return rawValue === undefined || rawValue === null ? "" : String(rawValue);
  },
  set(value: string) {
    updateSelectedNode((node) => {
      const normalized = value.trim();
      if (!normalized) {
        const fallback = node.data.runtimeType === "error_response" ? 400 : props.successStatusCode;
        node.data.config = {
          ...node.data.config,
          status_code: fallback,
        };
        return;
      }

      const asNumber = Number(normalized);
      node.data.config = {
        ...node.data.config,
        status_code: Number.isFinite(asNumber) && normalized === String(asNumber) ? asNumber : normalized,
      };
    });
  },
});
const selectedNodeConnectionId = computed<number | null>({
  get() {
    return connectionIdFromValue(selectedCanvasNode.value?.data.config?.connection_id);
  },
  set(value) {
    updateSelectedNode((node) => {
      node.data.config = {
        ...node.data.config,
        connection_id: value,
      };
    });
  },
});
const selectedNodeIfOperator = computed({
  get() {
    return String(selectedCanvasNode.value?.data.config?.operator ?? "equals");
  },
  set(value: string) {
    updateSelectedNode((node) => {
      node.data.config = {
        ...node.data.config,
        operator: String(value || "equals"),
      };
    });
  },
});
const requiresIfRightValue = computed(() => !IF_UNARY_OPERATORS.has(selectedNodeIfOperator.value));
const selectedNodeHttpMethod = computed({
  get() {
    return String(selectedCanvasNode.value?.data.config?.method ?? "GET").toUpperCase();
  },
  set(value: string) {
    updateSelectedNode((node) => {
      node.data.config = {
        ...node.data.config,
        method: String(value || "GET").toUpperCase(),
      };
    });
  },
});
const selectedNodeTimeoutMs = computed({
  get() {
    const rawValue = selectedCanvasNode.value?.data.config?.timeout_ms;
    return rawValue === undefined || rawValue === null ? "" : String(rawValue);
  },
  set(value: string) {
    updateSelectedNode((node) => {
      const normalized = value.trim();
      node.data.config = {
        ...node.data.config,
        timeout_ms: normalized ? Number(normalized) : null,
      };
    });
  },
});
const flowValidationMessages = computed<string[]>(() => validateRouteFlowDefinition(currentFlowDefinition.value));
const localInspectorMessages = computed(() =>
  [
    transformOutputError.value,
    responseBodyError.value,
    errorBodyError.value,
    ifLeftError.value,
    ifRightError.value,
    switchValueError.value,
    httpQueryError.value,
    httpHeadersError.value,
    httpBodyError.value,
    postgresParametersError.value,
  ].filter(
    (value): value is string => Boolean(value),
  ),
);
const allValidationMessages = computed<string[]>(() =>
  Array.from(new Set([...localInspectorMessages.value, ...flowValidationMessages.value])),
);
const connectionSummaries = computed(() =>
  canvasEdges.value.map((edge) => {
    const sourceNode = canvasNodes.value.find((node) => node.id === edge.source);
    const targetNode = canvasNodes.value.find((node) => node.id === edge.target);
    return {
      id: edge.id,
      source: sourceNode?.label || edge.source,
      target: targetNode?.label || edge.target,
      label: routeFlowEdgeLabel(toRouteFlowEdge(edge)),
    };
  }),
);
const nodeCount = computed(() => currentFlowDefinition.value.nodes.length);
const edgeCount = computed(() => currentFlowDefinition.value.edges.length);
const savedConnectionCount = computed(() => props.availableConnections.length);
const flowHealthColor = computed(() => (allValidationMessages.value.length > 0 ? "warning" : "accent"));
const flowHealthLabel = computed(() =>
  allValidationMessages.value.length > 0 ? `${allValidationMessages.value.length} flow issues` : "Flow graph looks coherent",
);
const focusInfoColor = computed(() => (props.errorMessage || allValidationMessages.value.length > 0 ? "warning" : "success"));
const focusInfoLabel = computed(() => {
  if (props.errorMessage) {
    return "Editor issue";
  }

  return allValidationMessages.value.length > 0
    ? `${allValidationMessages.value.length} issue${allValidationMessages.value.length === 1 ? "" : "s"}`
    : "Graph valid";
});
const flowDefinitionPreview = computed(() =>
  JSON.stringify(serializeRouteFlowDefinition(currentFlowDefinition.value), null, 2),
);
const flowInspectionSnapshot = computed(() =>
  buildRouteFlowInspectionSnapshot(
    currentFlowDefinition.value,
    {
      requestSchema: props.requestSchema,
      responseSchema: props.responseSchema,
      routeId: props.routeId,
      routeMethod: props.routeMethod,
      routeName: props.routeName,
      routePath: props.routePath,
      successStatusCode: props.successStatusCode,
    },
    props.availableConnections,
  ),
);
const selectedNodeInspection = computed(() => {
  if (!selectedCanvasNode.value) {
    return null;
  }

  return flowInspectionSnapshot.value.nodesById[selectedCanvasNode.value.id] ?? null;
});
const focusInputSchemaSections = computed<FocusSchemaSection[]>(() => {
  const inspection = selectedNodeInspection.value;
  if (!inspection) {
    return [];
  }

  return inspection.scopeEntries.map((entry) => ({
    label: entry.label,
    refPath: entry.refPath,
    rows: buildFocusSchemaRows(entry.sample, entry.refPath),
    shape: entry.shape,
  }));
});
const focusInputPreviewTableRows = computed<FocusPreviewTableRow[]>(() => {
  const inspection = selectedNodeInspection.value;
  if (!inspection) {
    return [];
  }

  const rows: FocusPreviewTableRow[] = [];
  inspection.scopeEntries.forEach((entry) => {
    flattenPreviewRows(entry.sample, entry.label, entry.refPath, rows);
  });
  return rows;
});
const focusOutputPreviewTableRows = computed<FocusPreviewTableRow[]>(() => {
  const inspection = selectedNodeInspection.value;
  if (!inspection) {
    return [];
  }

  const rows: FocusPreviewTableRow[] = [];
  flattenPreviewRows(inspection.outputSample, inspection.outputTitle, "output", rows);
  return rows;
});
const selectedNodeOnSamplePath = computed(() => {
  const nodeId = selectedCanvasNode.value?.id;
  return nodeId ? flowInspectionSnapshot.value.executedNodeIds.includes(nodeId) : false;
});
const flowResponseComparison = computed(() => {
  const responseNode = currentFlowDefinition.value.nodes.find((node) => node.type === "set_response");
  if (!responseNode) {
    return null;
  }

  return flowInspectionSnapshot.value.nodesById[responseNode.id]?.responseComparison ?? null;
});
const selectedNodePathManagementCopy = computed(() => {
  const node = selectedCanvasNode.value;
  if (!node) {
    return "";
  }

  if (node.data.runtimeType === "if_condition" || node.data.runtimeType === "switch") {
    return "Reconnect branch paths in place and tune branch metadata without leaving this inspector.";
  }

  return "Reconnect or remove outgoing paths directly from this inspector.";
});
const selectedNodeGuidance = computed<{ message: string; tone: InspectorGuidanceTone } | null>(() => {
  const runtimeType = selectedCanvasNode.value?.data.runtimeType;
  if (!runtimeType) {
    return null;
  }

  if (runtimeType === "api_trigger") {
    return {
      message: "API Trigger starts each run from the saved method, path, params, and body shape.",
      tone: "info",
    };
  }

  if (runtimeType === "validate_request") {
    return {
      message: "Validate Request checks the request against the saved contract.",
      tone: "info",
    };
  }

  if (runtimeType === "if_condition") {
    return {
      message: "If checks route data and continues on True or False.",
      tone: "info",
    };
  }

  if (runtimeType === "switch") {
    return {
      message: "Switch routes by case value and should include one default path.",
      tone: "info",
    };
  }

  if (runtimeType === "http_request") {
    return {
      message: "HTTP Request calls an upstream URL through a saved connection.",
      tone: "info",
    };
  }

  if (runtimeType === "postgres_query") {
    return {
      message: "Postgres Query runs one read-only SELECT or WITH statement with named parameters.",
      tone: "info",
    };
  }

  if (runtimeType === "set_response") {
    return {
      message: "Set Response returns the final status and body for live traffic.",
      tone: "info",
    };
  }

  return null;
});
const selectedNodeHasGuidance = computed(() => Boolean(selectedNodeGuidance.value || selectedNodeInspection.value));
const selectedNodeDefaultInspectorSections = computed<string[]>(() => {
  const runtimeType = selectedCanvasNode.value?.data.runtimeType;
  if (!runtimeType) {
    return [];
  }

  const nextSections: string[] = [];
  if (runtimeType === "if_condition" || runtimeType === "switch" || runtimeType === "api_trigger" || runtimeType === "validate_request") {
    nextSections.push("paths");
  }
  if (runtimeType === "api_trigger" || runtimeType === "validate_request") {
    nextSections.push("guidance");
  }
  return nextSections;
});

const reconnectTargetOptionsByEdgeId = computed(() => {
  const selectedNode = selectedCanvasNode.value;
  if (!selectedNode) {
    return new Map<string, Array<{ title: string; value: string }>>();
  }

  const optionsByEdgeId = new Map<string, Array<{ title: string; value: string }>>();

  selectedNodeOutgoingConnections.value.forEach((connection) => {
    const definitionWithoutEdge = definitionWithoutEdgeId(connection.id);
    const options = canvasNodes.value
      .filter((node) => node.id !== connection.sourceId)
      .filter((node) => {
        if (node.id === connection.targetId) {
          return true;
        }
        return !validateRouteFlowConnection(definitionWithoutEdge, connection.sourceId, node.id);
      })
      .map((node) => ({
        title: node.label || node.id,
        value: node.id,
      }));
    optionsByEdgeId.set(connection.id, options);
  });

  return optionsByEdgeId;
});

function existingNodeForType(nodeType: RouteFlowNodeType): CanvasNode | null {
  return canvasNodes.value.find((node) => node.data.runtimeType === nodeType) ?? null;
}

function canUsePreset(nodeType: RouteFlowNodeType): boolean {
  const definition = currentFlowDefinition.value;
  if (canAddRouteFlowNode(nodeType, definition.nodes)) {
    return true;
  }

  const existingNode = existingNodeForType(nodeType);
  if (!existingNode) {
    return false;
  }

  if (!selectedNodeId.value || selectedNodeId.value === existingNode.id) {
    return true;
  }

  return !validateRouteFlowConnection(definition, selectedNodeId.value, existingNode.id);
}

function fitCanvas(): void {
  void flowInstance.value?.fitView({ padding: 0.18, duration: 220 });
}

function focusCanvasNode(nodeId: string | null): void {
  if (!nodeId || !flowInstance.value) {
    return;
  }

  const node = canvasNodes.value.find((candidate) => candidate.id === nodeId);
  if (!node) {
    return;
  }

  void flowInstance.value.setCenter(
    node.position.x + ROUTE_FLOW_NODE_WIDTH / 2,
    node.position.y + ROUTE_FLOW_NODE_HEIGHT / 2,
    {
      zoom: 1,
      duration: 220,
    },
  );
}

function commitFlowDefinition(
  nextDefinition: RouteFlowDefinition,
  options: {
    fitView?: boolean;
    selectedNodeId?: string | null;
  } = {},
): void {
  flowDefinitionState.value = nextDefinition;
  syncCanvasFromDefinition(nextDefinition);

  if (options.selectedNodeId !== undefined) {
    selectedNodeId.value = options.selectedNodeId;
  }

  if (options.fitView) {
    void nextTick(() => {
      fitCanvas();
    });
  }
}

function commitStructuralDefinition(
  nextDefinition: RouteFlowDefinition,
  options: {
    fitView?: boolean;
    forceAutoLayout?: boolean;
    preserveManualLayout?: boolean;
    selectedNodeId?: string | null;
  } = {},
): void {
  const shouldAutoLayout = options.forceAutoLayout || (!options.preserveManualLayout && !hasManualLayout.value);
  const arrangedDefinition = shouldAutoLayout ? autoLayoutRouteFlowDefinition(nextDefinition) : nextDefinition;
  if (options.forceAutoLayout) {
    hasManualLayout.value = false;
  }

  commitFlowDefinition(arrangedDefinition, {
    fitView: options.fitView ?? shouldAutoLayout,
    selectedNodeId: options.selectedNodeId,
  });
}

function setFocusMode(value: boolean): void {
  isFocusMode.value = value;
  isFocusPaletteOpen.value = false;
  isFocusInfoOpen.value = false;
  isFocusInspectorOpen.value = false;

  void nextTick(() => {
    if (value && selectedNodeId.value) {
      focusCanvasNode(selectedNodeId.value);
      return;
    }

    fitCanvas();
  });
}

function toggleFocusMode(): void {
  setFocusMode(!isFocusMode.value);
}

function toggleFocusPalette(): void {
  if (!isFocusPaletteOpen.value) {
    isFocusInfoOpen.value = false;
  }
  isFocusPaletteOpen.value = !isFocusPaletteOpen.value;
}

function toggleFocusInfo(): void {
  if (!isFocusInfoOpen.value) {
    isFocusPaletteOpen.value = false;
  }
  isFocusInfoOpen.value = !isFocusInfoOpen.value;
}

function toggleFocusInspector(): void {
  if (!selectedCanvasNode.value) {
    return;
  }

  if (!isFocusInspectorOpen.value) {
    isFocusPaletteOpen.value = false;
    isFocusInfoOpen.value = false;
  }
  isFocusInspectorOpen.value = !isFocusInspectorOpen.value;
  if (isFocusInspectorOpen.value) {
    focusCanvasNode(selectedCanvasNode.value.id);
  }
}

function zoomCanvasIn(): void {
  void flowInstance.value?.zoomIn({ duration: 180 });
}

function zoomCanvasOut(): void {
  void flowInstance.value?.zoomOut({ duration: 180 });
}

function autoArrangeCanvas(): void {
  commitStructuralDefinition(currentFlowDefinition.value, {
    forceAutoLayout: true,
    fitView: true,
  });
}

function requestSave(): void {
  if (props.saveDisabled || props.saveLoading) {
    return;
  }

  emit("save-requested");
}

function handleFlowInit(instance: VueFlowStore): void {
  flowInstance.value = instance;
}

function handleCanvasMouseDown(event: MouseEvent): void {
  if (event.button === 1) {
    event.preventDefault();
  }
}

function handleCanvasAuxClick(event: MouseEvent): void {
  if (event.button === 1) {
    event.preventDefault();
  }
}

function setPaletteDragState(element: HTMLElement, active: boolean): void {
  element.classList.toggle("schema-drag-source", active);
}

function paletteDragBinding(
  nodeType: RouteFlowNodeType,
  title: string,
): PragmaticDraggableBinding<Record<string, unknown>> {
  return {
    canDrag: canUsePreset(nodeType),
    data: createRouteFlowPaletteDragPayload(nodeType) as unknown as Record<string, unknown>,
    preview: {
      eyebrow: "Flow node",
      label: title,
      tone: "node",
    },
    onDragStart: ({ element }) => {
      setPaletteDragState(element, true);
    },
    onDrop: ({ element }) => {
      setPaletteDragState(element, false);
    },
  };
}

function referenceSnippetDragBinding(label: string, refPath: string): PragmaticDraggableBinding<Record<string, unknown>> {
  return {
    data: createRouteFlowReferenceDragPayload(refPath) as unknown as Record<string, unknown>,
    preview: {
      eyebrow: "Flow ref",
      label,
      tone: "value",
    },
    onDragStart: ({ element }) => {
      setPaletteDragState(element, true);
    },
    onDrop: ({ element }) => {
      setPaletteDragState(element, false);
    },
  };
}

function handleCanvasDrop(sourceData: Record<string, unknown>, clientX: number, clientY: number): void {
  const payload = getRouteFlowPaletteDragPayload(sourceData);
  if (!payload) {
    return;
  }

  const position = flowInstance.value?.screenToFlowCoordinate({
    x: clientX,
    y: clientY,
  });

  addNode(payload.nodeType, {
    position: position
      ? {
          x: position.x,
          y: position.y,
        }
      : undefined,
    preserveManualLayout: true,
  });
}

function handleNodeDragStop(): void {
  hasManualLayout.value = true;
}

const canvasDropBinding = computed<PragmaticDropTargetBinding<Record<string, unknown>>>(() => ({
  canDrop: ({ sourceData }) => getRouteFlowPaletteDragPayload(sourceData) !== null,
  dropEffect: "copy",
  onDrop: ({ clientX, clientY, sourceData }) => {
    handleCanvasDrop(sourceData, clientX, clientY);
  },
}));

function resolveEditorRootElement(element: Element | ComponentPublicInstance | null): HTMLElement | null {
  return element instanceof HTMLElement
    ? element
    : element && "$el" in element && element.$el instanceof HTMLElement
      ? element.$el
      : null;
}

function setJsonEditorRootElement(
  target: JsonConfigTarget,
  element: Element | ComponentPublicInstance | null,
): void {
  const root = resolveEditorRootElement(element);
  if (root) {
    jsonEditorRootElements[target] = root;
    return;
  }

  delete jsonEditorRootElements[target];
  delete jsonEditorSelections[target];
}

function setTextEditorRootElement(
  target: TextConfigTarget,
  element: Element | ComponentPublicInstance | null,
): void {
  const root = resolveEditorRootElement(element);
  if (root) {
    textEditorRootElements[target] = root;
    return;
  }

  delete textEditorRootElements[target];
  delete textEditorSelections[target];
}

function resolveJsonEditorTextarea(target: JsonConfigTarget): HTMLTextAreaElement | null {
  return jsonEditorRootElements[target]?.querySelector("textarea") ?? null;
}

function resolveTextEditorControl(target: TextConfigTarget): HTMLInputElement | HTMLTextAreaElement | null {
  const control = textEditorRootElements[target]?.querySelector("input, textarea");
  return control instanceof HTMLInputElement || control instanceof HTMLTextAreaElement ? control : null;
}

function rememberJsonEditorSelection(target: JsonConfigTarget, event?: Event): void {
  const textarea = event?.target instanceof HTMLTextAreaElement ? event.target : resolveJsonEditorTextarea(target);
  if (!textarea) {
    return;
  }

  const start = textarea.selectionStart ?? textarea.value.length;
  const end = textarea.selectionEnd ?? start;
  jsonEditorSelections[target] = { start, end };
}

function rememberTextEditorSelection(target: TextConfigTarget, event?: Event): void {
  const control =
    event?.target instanceof HTMLInputElement || event?.target instanceof HTMLTextAreaElement
      ? event.target
      : resolveTextEditorControl(target);
  if (!control) {
    return;
  }

  const start = control.selectionStart ?? control.value.length;
  const end = control.selectionEnd ?? start;
  textEditorSelections[target] = { start, end };
}

function refreshInspectorDrafts(): void {
  const selectedNode = selectedCanvasNode.value;

  transformOutputError.value = null;
  responseBodyError.value = null;
  errorBodyError.value = null;
  ifLeftError.value = null;
  ifRightError.value = null;
  switchValueError.value = null;
  httpQueryError.value = null;
  httpHeadersError.value = null;
  httpBodyError.value = null;
  postgresParametersError.value = null;

  if (!selectedNode) {
    transformOutputText.value = "";
    responseBodyText.value = "";
    errorBodyText.value = "";
    ifLeftText.value = "";
    ifRightText.value = "";
    switchValueText.value = "";
    httpPathText.value = "";
    httpQueryText.value = "";
    httpHeadersText.value = "";
    httpBodyText.value = "";
    postgresSqlText.value = "";
    postgresParametersText.value = "";
    return;
  }

  transformOutputText.value = JSON.stringify(selectedNode.data.config.output ?? {}, null, 2);
  responseBodyText.value = JSON.stringify(selectedNode.data.config.body ?? {}, null, 2);
  errorBodyText.value = JSON.stringify(selectedNode.data.config.body ?? {}, null, 2);
  ifLeftText.value = stringifyFlexibleValue(selectedNode.data.config.left);
  ifRightText.value = stringifyFlexibleValue(selectedNode.data.config.right);
  switchValueText.value = stringifyFlexibleValue(selectedNode.data.config.value);
  httpPathText.value = String(selectedNode.data.config.path ?? "");
  httpQueryText.value = JSON.stringify(selectedNode.data.config.query ?? {}, null, 2);
  httpHeadersText.value = JSON.stringify(selectedNode.data.config.headers ?? {}, null, 2);
  httpBodyText.value = JSON.stringify(selectedNode.data.config.body ?? {}, null, 2);
  postgresSqlText.value = String(selectedNode.data.config.sql ?? "");
  postgresParametersText.value = JSON.stringify(selectedNode.data.config.parameters ?? {}, null, 2);
}

function updateSelectedNode(mutator: (node: CanvasNode) => void): void {
  const nodeId = selectedNodeId.value;
  if (!nodeId) {
    return;
  }

  canvasNodes.value = canvasNodes.value.map((node) => {
    if (node.id !== nodeId) {
      return node;
    }

    const nextNode: CanvasNode = {
      ...node,
      position: {
        x: Number(node.position.x ?? 0),
        y: Number(node.position.y ?? 0),
      },
      data: {
        ...node.data,
        config: copyJsonValue(node.data.config),
        extra: { ...node.data.extra },
      },
    };
    mutator(nextNode);
    return nextNode;
  });
}

function updateSelectedNodeName(value: string): void {
  updateSelectedNode((node) => {
    node.label = value.trim() || node.data.title;
  });
}

function parseJsonValue(rawValue: string, label: string): JsonValue | null {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return {};
  }

  try {
    return JSON.parse(trimmed) as JsonValue;
  } catch (error) {
    return {
      __route_flow_error__: error instanceof Error ? `${label} must be valid JSON. ${error.message}` : `${label} must be valid JSON.`,
    };
  }
}

function previewValueType(value: JsonValue): string {
  if (value === null) {
    return "null";
  }
  if (Array.isArray(value)) {
    return "array";
  }
  return typeof value === "object" ? "object" : typeof value;
}

function previewCellValue(value: JsonValue): string {
  if (value === null) {
    return "null";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function schemaPreviewSummary(value: JsonValue): string {
  if (value === null) {
    return "null";
  }
  if (Array.isArray(value)) {
    return value.length === 0 ? "empty list" : `${value.length} item${value.length === 1 ? "" : "s"}`;
  }
  if (typeof value === "object") {
    const keys = Object.keys(value);
    return keys.length === 0 ? "empty object" : `${keys.length} field${keys.length === 1 ? "" : "s"}`;
  }
  return previewCellValue(value);
}

function appendFocusSchemaRows(
  value: JsonValue,
  refPath: string,
  label: string,
  rows: FocusSchemaRow[],
  depth = 0,
): void {
  if (rows.length >= 180 || depth > 4) {
    return;
  }

  rows.push({
    depth,
    label,
    preview: schemaPreviewSummary(value),
    refPath,
    shape: previewValueType(value),
  });

  if (Array.isArray(value)) {
    value.slice(0, 20).forEach((item, index) => {
      appendFocusSchemaRows(item, `${refPath}.${index}`, `[${index}]`, rows, depth + 1);
    });
    return;
  }

  if (value && typeof value === "object") {
    Object.entries(value)
      .slice(0, 25)
      .forEach(([key, child]) => {
        appendFocusSchemaRows(child, `${refPath}.${key}`, key, rows, depth + 1);
      });
  }
}

function buildFocusSchemaRows(value: JsonValue, rootRefPath: string): FocusSchemaRow[] {
  const rows: FocusSchemaRow[] = [];

  if (Array.isArray(value)) {
    value.slice(0, 20).forEach((item, index) => {
      appendFocusSchemaRows(item, `${rootRefPath}.${index}`, `[${index}]`, rows);
    });
    return rows;
  }

  if (value && typeof value === "object") {
    Object.entries(value)
      .slice(0, 25)
      .forEach(([key, child]) => {
        appendFocusSchemaRows(child, `${rootRefPath}.${key}`, key, rows);
      });
    return rows;
  }

  rows.push({
    depth: 0,
    label: rootRefPath.split(".").pop() ?? rootRefPath,
    preview: schemaPreviewSummary(value),
    refPath: rootRefPath,
    shape: previewValueType(value),
  });
  return rows;
}

function flattenPreviewRows(
  value: JsonValue,
  source: string,
  path: string,
  rows: FocusPreviewTableRow[],
  depth = 0,
): void {
  if (rows.length >= 240 || depth > 5) {
    return;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      rows.push({
        source,
        path,
        type: "array",
        value: "[]",
      });
      return;
    }

    value.slice(0, 25).forEach((item, index) => {
      const childPath = `${path}[${index}]`;
      rows.push({
        source,
        path: childPath,
        type: previewValueType(item),
        value: previewCellValue(item),
      });
      if (typeof item === "object" && item !== null) {
        flattenPreviewRows(item, source, childPath, rows, depth + 1);
      }
    });
    return;
  }

  if (value && typeof value === "object") {
    const entries = Object.entries(value).slice(0, 50);
    if (entries.length === 0) {
      rows.push({
        source,
        path,
        type: "object",
        value: "{}",
      });
      return;
    }

    entries.forEach(([key, child]) => {
      const childPath = path ? `${path}.${key}` : key;
      rows.push({
        source,
        path: childPath,
        type: previewValueType(child),
        value: previewCellValue(child),
      });
      if (typeof child === "object" && child !== null) {
        flattenPreviewRows(child, source, childPath, rows, depth + 1);
      }
    });
    return;
  }

  rows.push({
    source,
    path,
    type: previewValueType(value),
    value: previewCellValue(value),
  });
}

function parseFlexibleValue(rawValue: string, label: string): { value: JsonValue | null; error: string | null } {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return { value: null, error: null };
  }

  const looksLikeJson =
    trimmed.startsWith("{") ||
    trimmed.startsWith("[") ||
    trimmed.startsWith("\"") ||
    /^(true|false|null|-?\d+(\.\d+)?)$/i.test(trimmed);
  if (looksLikeJson) {
    try {
      return { value: JSON.parse(trimmed) as JsonValue, error: null };
    } catch (error) {
      return {
        value: null,
        error: error instanceof Error ? `${label} must be valid JSON. ${error.message}` : `${label} must be valid JSON.`,
      };
    }
  }

  return { value: trimmed, error: null };
}

function setJsonTargetError(target: JsonConfigTarget, message: string | null): void {
  switch (target) {
    case "transform":
      transformOutputError.value = message;
      return;
    case "response":
      responseBodyError.value = message;
      return;
    case "error":
      errorBodyError.value = message;
      return;
    case "httpQuery":
      httpQueryError.value = message;
      return;
    case "httpHeaders":
      httpHeadersError.value = message;
      return;
    case "httpBody":
      httpBodyError.value = message;
      return;
    case "postgresParameters":
      postgresParametersError.value = message;
      return;
  }
}

function setFlexibleTargetError(target: FlexibleConfigTarget, message: string | null): void {
  switch (target) {
    case "ifLeft":
      ifLeftError.value = message;
      return;
    case "ifRight":
      ifRightError.value = message;
      return;
    case "switchValue":
      switchValueError.value = message;
      return;
  }
}

function jsonTargetLabel(target: JsonConfigTarget): string {
  switch (target) {
    case "transform":
      return "Transform output";
    case "response":
      return "Response body";
    case "error":
      return "Error body";
    case "httpQuery":
      return "HTTP query";
    case "httpHeaders":
      return "HTTP headers";
    case "httpBody":
      return "HTTP body";
    case "postgresParameters":
      return "Postgres parameters";
  }
}

function flexibleTargetLabel(target: FlexibleConfigTarget): string {
  switch (target) {
    case "ifLeft":
      return "If left value";
    case "ifRight":
      return "If right value";
    case "switchValue":
      return "Switch value";
  }
}

function applyJsonConfigField(
  field: "output" | "body" | "query" | "headers" | "parameters",
  rawValue: string,
  target: JsonConfigTarget,
): void {
  const parsed = parseJsonValue(rawValue, jsonTargetLabel(target));

  if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && "__route_flow_error__" in parsed) {
    const message = typeof parsed.__route_flow_error__ === "string" ? parsed.__route_flow_error__ : "Flow JSON is invalid.";
    setJsonTargetError(target, message);
    return;
  }

  setJsonTargetError(target, null);

  updateSelectedNode((node) => {
    node.data.config = {
      ...node.data.config,
      [field]: parsed ?? {},
    };
  });
}

function applyFlexibleConfigField(
  field: "left" | "right" | "value",
  rawValue: string,
  target: FlexibleConfigTarget,
): void {
  const parsed = parseFlexibleValue(rawValue, flexibleTargetLabel(target));
  setFlexibleTargetError(target, parsed.error);
  if (parsed.error) {
    return;
  }

  updateSelectedNode((node) => {
    const nextConfig = {
      ...node.data.config,
    };

    if (parsed.value === null) {
      delete nextConfig[field];
    } else {
      nextConfig[field] = parsed.value;
    }

    node.data.config = nextConfig;
  });
}

function handleTransformOutputInput(value: string): void {
  transformOutputText.value = value;
  applyJsonConfigField("output", value, "transform");
}

function handleResponseBodyInput(value: string): void {
  responseBodyText.value = value;
  applyJsonConfigField("body", value, "response");
}

function handleErrorBodyInput(value: string): void {
  errorBodyText.value = value;
  applyJsonConfigField("body", value, "error");
}

function handleIfLeftInput(value: string): void {
  ifLeftText.value = value;
  applyFlexibleConfigField("left", value, "ifLeft");
}

function handleIfRightInput(value: string): void {
  ifRightText.value = value;
  applyFlexibleConfigField("right", value, "ifRight");
}

function handleSwitchValueInput(value: string): void {
  switchValueText.value = value;
  applyFlexibleConfigField("value", value, "switchValue");
}

function handleHttpPathInput(value: string): void {
  httpPathText.value = value;
  updateSelectedNode((node) => {
    node.data.config = {
      ...node.data.config,
      path: value,
    };
  });
}

function handleHttpQueryInput(value: string): void {
  httpQueryText.value = value;
  applyJsonConfigField("query", value, "httpQuery");
}

function handleHttpHeadersInput(value: string): void {
  httpHeadersText.value = value;
  applyJsonConfigField("headers", value, "httpHeaders");
}

function handleHttpBodyInput(value: string): void {
  httpBodyText.value = value;
  applyJsonConfigField("body", value, "httpBody");
}

function handlePostgresSqlInput(value: string): void {
  postgresSqlText.value = value;
  updateSelectedNode((node) => {
    node.data.config = {
      ...node.data.config,
      sql: value,
    };
  });
}

function handlePostgresParametersInput(value: string): void {
  postgresParametersText.value = value;
  applyJsonConfigField("parameters", value, "postgresParameters");
}

function buildReferenceSnippet(refPath: string, compact = false): string {
  return compact ? JSON.stringify({ $ref: refPath }) : JSON.stringify({ $ref: refPath }, null, 2);
}

function buildTemplateReferenceSnippet(refPath: string): string {
  return `{{${refPath}}}`;
}

function jsonTargetText(target: JsonConfigTarget): string {
  switch (target) {
    case "transform":
      return transformOutputText.value;
    case "response":
      return responseBodyText.value;
    case "error":
      return errorBodyText.value;
    case "httpQuery":
      return httpQueryText.value;
    case "httpHeaders":
      return httpHeadersText.value;
    case "httpBody":
      return httpBodyText.value;
    case "postgresParameters":
      return postgresParametersText.value;
  }
}

function textTargetText(target: TextConfigTarget): string {
  switch (target) {
    case "httpPath":
      return httpPathText.value;
  }
}

function applyJsonTargetInput(target: JsonConfigTarget, value: string): void {
  switch (target) {
    case "transform":
      handleTransformOutputInput(value);
      return;
    case "response":
      handleResponseBodyInput(value);
      return;
    case "error":
      handleErrorBodyInput(value);
      return;
    case "httpQuery":
      handleHttpQueryInput(value);
      return;
    case "httpHeaders":
      handleHttpHeadersInput(value);
      return;
    case "httpBody":
      handleHttpBodyInput(value);
      return;
    case "postgresParameters":
      handlePostgresParametersInput(value);
      return;
  }
}

function applyTextTargetInput(target: TextConfigTarget, value: string): void {
  switch (target) {
    case "httpPath":
      handleHttpPathInput(value);
      return;
  }
}

async function insertJsonReferenceSnippet(target: JsonConfigTarget, refPath: string): Promise<void> {
  const currentValue = jsonTargetText(target);
  const textarea = resolveJsonEditorTextarea(target);
  const rememberedSelection = jsonEditorSelections[target];
  const selectionStart = rememberedSelection?.start ?? textarea?.selectionStart ?? currentValue.length;
  const selectionEnd = rememberedSelection?.end ?? textarea?.selectionEnd ?? selectionStart;
  const safeStart = Math.max(0, Math.min(selectionStart, currentValue.length));
  const safeEnd = Math.max(safeStart, Math.min(selectionEnd, currentValue.length));
  const snippet = buildReferenceSnippet(refPath, true);
  const nextValue = `${currentValue.slice(0, safeStart)}${snippet}${currentValue.slice(safeEnd)}`;
  let caretPosition = safeStart + snippet.length;

  try {
    const normalizedValue = JSON.stringify(JSON.parse(nextValue) as JsonValue, null, 2);
    const refLine = `"$ref": "${refPath}"`;
    const refLineIndex = normalizedValue.indexOf(refLine, Math.max(0, safeStart - refLine.length));
    if (refLineIndex >= 0) {
      const closingBraceIndex = normalizedValue.indexOf("}", refLineIndex);
      caretPosition = closingBraceIndex >= 0 ? closingBraceIndex + 1 : Math.min(caretPosition, normalizedValue.length);
    } else {
      caretPosition = Math.min(caretPosition, normalizedValue.length);
    }
  } catch {
    caretPosition = Math.min(caretPosition, nextValue.length);
  }

  applyJsonTargetInput(target, nextValue);
  await nextTick();

  const nextTextarea = resolveJsonEditorTextarea(target);
  if (!nextTextarea) {
    return;
  }

  nextTextarea.focus();
  nextTextarea.setSelectionRange(caretPosition, caretPosition);
  jsonEditorSelections[target] = {
    start: caretPosition,
    end: caretPosition,
  };
}

async function insertTextReferenceSnippet(target: TextConfigTarget, refPath: string): Promise<void> {
  const currentValue = textTargetText(target);
  const control = resolveTextEditorControl(target);
  const rememberedSelection = textEditorSelections[target];
  const selectionStart = rememberedSelection?.start ?? control?.selectionStart ?? currentValue.length;
  const selectionEnd = rememberedSelection?.end ?? control?.selectionEnd ?? selectionStart;
  const safeStart = Math.max(0, Math.min(selectionStart, currentValue.length));
  const safeEnd = Math.max(safeStart, Math.min(selectionEnd, currentValue.length));
  const snippet = buildTemplateReferenceSnippet(refPath);
  const nextValue = `${currentValue.slice(0, safeStart)}${snippet}${currentValue.slice(safeEnd)}`;
  const caretPosition = safeStart + snippet.length;

  applyTextTargetInput(target, nextValue);
  await nextTick();

  const nextControl = resolveTextEditorControl(target);
  if (!nextControl) {
    return;
  }

  nextControl.focus();
  nextControl.setSelectionRange(caretPosition, caretPosition);
  textEditorSelections[target] = {
    start: caretPosition,
    end: caretPosition,
  };
}

function createJsonReferenceDropBinding(
  target: JsonConfigTarget,
): PragmaticDropTargetBinding<Record<string, unknown>> {
  return {
    canDrop: ({ sourceData }) => getRouteFlowReferenceDragPayload(sourceData) !== null,
    dropEffect: "copy",
    onDrop: ({ sourceData }) => {
      const payload = getRouteFlowReferenceDragPayload(sourceData);
      if (!payload) {
        return;
      }

      void insertJsonReferenceSnippet(target, payload.refPath);
    },
  };
}

function createTextReferenceDropBinding(
  target: TextConfigTarget,
): PragmaticDropTargetBinding<Record<string, unknown>> {
  return {
    canDrop: ({ sourceData }) => getRouteFlowReferenceDragPayload(sourceData) !== null,
    dropEffect: "copy",
    onDrop: ({ sourceData }) => {
      const payload = getRouteFlowReferenceDragPayload(sourceData);
      if (!payload) {
        return;
      }

      void insertTextReferenceSnippet(target, payload.refPath);
    },
  };
}

const jsonReferenceDropBindings: Record<JsonConfigTarget, PragmaticDropTargetBinding<Record<string, unknown>>> = {
  transform: createJsonReferenceDropBinding("transform"),
  response: createJsonReferenceDropBinding("response"),
  error: createJsonReferenceDropBinding("error"),
  httpQuery: createJsonReferenceDropBinding("httpQuery"),
  httpHeaders: createJsonReferenceDropBinding("httpHeaders"),
  httpBody: createJsonReferenceDropBinding("httpBody"),
  postgresParameters: createJsonReferenceDropBinding("postgresParameters"),
};
const textReferenceDropBindings: Record<TextConfigTarget, PragmaticDropTargetBinding<Record<string, unknown>>> = {
  httpPath: createTextReferenceDropBinding("httpPath"),
};

function applyHttpPathTemplateSnippet(refPath: string): void {
  void insertTextReferenceSnippet("httpPath", refPath);
}

function handleFocusSchemaSnippetClick(refPath: string): void {
  if (selectedCanvasNode.value?.data.runtimeType === "http_request") {
    applyHttpPathTemplateSnippet(refPath);
  }
}

function applyReferenceSnippet(target: ReferenceTarget, refPath: string): void {
  const snippet = buildReferenceSnippet(refPath, false);
  if (target === "transform") {
    handleTransformOutputInput(snippet);
    return;
  }

  if (target === "response") {
    handleResponseBodyInput(snippet);
    return;
  }

  if (target === "error") {
    handleErrorBodyInput(snippet);
    return;
  }

  if (target === "ifLeft") {
    handleIfLeftInput(snippet);
    return;
  }

  if (target === "ifRight") {
    handleIfRightInput(snippet);
    return;
  }

  handleSwitchValueInput(snippet);
}

function handleNodeClick(event: NodeMouseEvent): void {
  selectedNodeId.value = event.node.id;
  if (isFocusMode.value) {
    isFocusPaletteOpen.value = false;
    isFocusInfoOpen.value = false;
  }
}

function clearSelection(): void {
  if (isFocusMode.value) {
    isFocusPaletteOpen.value = false;
    isFocusInfoOpen.value = false;
    return;
  }
  selectedNodeId.value = null;
  isFocusInspectorOpen.value = false;
}

function closeInspector(): void {
  if (isFocusMode.value) {
    isFocusInspectorOpen.value = false;
    return;
  }

  clearSelection();
}

function updateCanvasEdge(edgeId: string, mutator: (edge: CanvasEdge) => void): void {
  canvasEdges.value = canvasEdges.value.map((edge) => {
    if (edge.id !== edgeId) {
      return edge;
    }

    const nextEdge: CanvasEdge = {
      ...edge,
      data: {
        extra: edge.data?.extra ? copyJsonValue(edge.data.extra) : {},
      },
    };
    mutator(nextEdge);
    nextEdge.label = routeFlowEdgeLabel(toRouteFlowEdge(nextEdge)) || undefined;
    return nextEdge;
  });
}

function updateIfBranchForEdge(edgeId: string, branch: string): void {
  updateCanvasEdge(edgeId, (edge) => {
    edge.data = edge.data ?? { extra: {} };
    edge.data.extra = {
      ...edge.data.extra,
      branch,
    };
  });
}

function updateSwitchBranchMode(edgeId: string, branch: string): void {
  updateCanvasEdge(edgeId, (edge) => {
    edge.data = edge.data ?? { extra: {} };
    const nextExtra: JsonObject = {
      ...edge.data.extra,
      branch,
    };

    if (branch !== "case") {
      delete nextExtra.case_value;
    } else if (nextExtra.case_value === undefined) {
      nextExtra.case_value = "case";
    }

    edge.data.extra = nextExtra;
  });
}

function updateSwitchCaseValue(edgeId: string, rawValue: string): void {
  const parsed = parseFlexibleValue(rawValue, "Switch case value");
  updateCanvasEdge(edgeId, (edge) => {
    edge.data = edge.data ?? { extra: {} };
    const nextExtra: JsonObject = {
      ...edge.data.extra,
      branch: "case",
    };
    if (parsed.value === null) {
      delete nextExtra.case_value;
    } else {
      nextExtra.case_value = parsed.value;
    }
    edge.data.extra = nextExtra;
  });
}

function addNode(
  nodeType: RouteFlowNodeType,
  options: {
    position?: { x: number; y: number };
    preserveManualLayout?: boolean;
  } = {},
): void {
  const currentDefinition = currentFlowDefinition.value;
  const existingNode = existingNodeForType(nodeType);
  if (!canAddRouteFlowNode(nodeType, currentDefinition.nodes) && existingNode) {
    const previousSelection = selectedNodeId.value;
    if (previousSelection && previousSelection !== existingNode.id) {
      const connectionError = validateRouteFlowConnection(currentDefinition, previousSelection, existingNode.id);
      if (!connectionError) {
        const nextDefinition: RouteFlowDefinition = {
          schema_version: currentDefinition.schema_version,
          extra: currentDefinition.extra ? copyJsonValue(currentDefinition.extra) : {},
          nodes: currentDefinition.nodes.map((node) => ({
            ...node,
            position: node.position ? { ...node.position } : undefined,
            config: copyJsonValue(node.config),
            extra: node.extra ? copyJsonValue(node.extra) : {},
          })),
          edges: [
            ...currentDefinition.edges.map((edge) => ({
              ...edge,
              extra: edge.extra ? copyJsonValue(edge.extra) : {},
            })),
            {
              id: buildRouteFlowEdgeId(currentDefinition.edges, previousSelection, existingNode.id),
              source: previousSelection,
              target: existingNode.id,
              extra: defaultRouteFlowEdgeExtra(currentDefinition, previousSelection),
            },
          ],
        };
        commitStructuralDefinition(nextDefinition, {
          selectedNodeId: existingNode.id,
          preserveManualLayout: options.preserveManualLayout,
        });
        if (isFocusMode.value) {
          isFocusInspectorOpen.value = true;
          isFocusPaletteOpen.value = false;
          focusCanvasNode(existingNode.id);
        }
        return;
      }
    }

    selectedNodeId.value = existingNode.id;
    if (isFocusMode.value) {
      isFocusInspectorOpen.value = true;
      isFocusPaletteOpen.value = false;
      focusCanvasNode(existingNode.id);
    }
    return;
  }

  const nextNode = createRouteFlowNode(nodeType, currentDefinition.nodes, {
    anchorNodeId: selectedNodeId.value,
    successStatusCode: props.successStatusCode,
  });
  if (options.position) {
    nextNode.position = {
      x: options.position.x,
      y: options.position.y,
    };
  }

  const nextNodes = [...currentDefinition.nodes, nextNode];
  const nextEdges = [...currentDefinition.edges];

  if (selectedNodeId.value) {
    const draftDefinition: RouteFlowDefinition = {
      schema_version: currentDefinition.schema_version,
      extra: currentDefinition.extra ? copyJsonValue(currentDefinition.extra) : {},
      nodes: nextNodes,
      edges: nextEdges,
    };
    const connectionError = validateRouteFlowConnection(draftDefinition, selectedNodeId.value, nextNode.id);
    if (!connectionError) {
      nextEdges.push({
        id: buildRouteFlowEdgeId(nextEdges, selectedNodeId.value, nextNode.id),
        source: selectedNodeId.value,
        target: nextNode.id,
        extra: defaultRouteFlowEdgeExtra(draftDefinition, selectedNodeId.value),
      });
    }
  }

  const nextDefinition: RouteFlowDefinition = {
    schema_version: currentDefinition.schema_version,
    extra: currentDefinition.extra ? copyJsonValue(currentDefinition.extra) : {},
    nodes: nextNodes,
    edges: nextEdges,
  };
  commitStructuralDefinition(nextDefinition, {
    selectedNodeId: nextNode.id,
    preserveManualLayout: options.preserveManualLayout || Boolean(options.position),
  });
  if (isFocusMode.value) {
    isFocusInspectorOpen.value = true;
    isFocusPaletteOpen.value = false;
  }
}

function removeNode(nodeId: string): void {
  if (!nodeId) {
    return;
  }

  const nextDefinition: RouteFlowDefinition = {
    schema_version: currentFlowDefinition.value.schema_version,
    extra: currentFlowDefinition.value.extra ? copyJsonValue(currentFlowDefinition.value.extra) : {},
    nodes: currentFlowDefinition.value.nodes.filter((node) => node.id !== nodeId),
    edges: currentFlowDefinition.value.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
  };
  commitStructuralDefinition(nextDefinition, {
    selectedNodeId: nextDefinition.nodes[0]?.id ?? null,
  });
}

function removeSelectedNode(): void {
  if (!selectedNodeId.value) {
    return;
  }

  removeNode(selectedNodeId.value);
}

function handleNodeToolbarCenter(nodeId: string): void {
  selectedNodeId.value = nodeId;
  if (isFocusMode.value) {
    isFocusInspectorOpen.value = true;
  }
  focusCanvasNode(nodeId);
}

function handleNodeToolbarRemove(nodeId: string): void {
  selectedNodeId.value = nodeId;
  removeNode(nodeId);
}

function removeConnection(edgeId: string): void {
  const nextDefinition: RouteFlowDefinition = {
    schema_version: currentFlowDefinition.value.schema_version,
    extra: currentFlowDefinition.value.extra ? copyJsonValue(currentFlowDefinition.value.extra) : {},
    nodes: currentFlowDefinition.value.nodes.map((node) => ({
      ...node,
      position: node.position ? { ...node.position } : undefined,
      config: copyJsonValue(node.config),
      extra: node.extra ? copyJsonValue(node.extra) : {},
    })),
    edges: currentFlowDefinition.value.edges.filter((edge) => edge.id !== edgeId),
  };
  commitStructuralDefinition(nextDefinition);
}

function edgeBranchFromExtra(extra: JsonObject | undefined): string {
  const rawBranch = typeof extra?.branch === "string" ? extra.branch.trim().toLowerCase() : "";
  return ["true", "false", "case", "default"].includes(rawBranch) ? rawBranch : "";
}

function edgeIdToReplaceForConnection(
  sourceId: string,
  sourceHandle?: string | null,
): string | null {
  const sourceNode = currentFlowDefinition.value.nodes.find((node) => node.id === sourceId);
  if (!sourceNode) {
    return null;
  }

  if (sourceNode.type === "if_condition") {
    const handleBranch = sourceHandle === "true" || sourceHandle === "false" ? sourceHandle : null;
    if (!handleBranch) {
      return null;
    }
    return (
      currentFlowDefinition.value.edges.find(
        (edge) => edge.source === sourceId && edgeBranchFromExtra(edge.extra) === handleBranch,
      )?.id ?? null
    );
  }

  if (sourceNode.type === "switch") {
    if (sourceHandle === "default") {
      return (
        currentFlowDefinition.value.edges.find(
          (edge) => edge.source === sourceId && edgeBranchFromExtra(edge.extra) === "default",
        )?.id ?? null
      );
    }

    if (sourceHandle === "case") {
      return null;
    }

    return null;
  }

  return currentFlowDefinition.value.edges.find((edge) => edge.source === sourceId)?.id ?? null;
}

function replacementEdgeExtra(
  replacedEdge: RouteFlowEdge | null,
  sourceHandle?: string | null,
): JsonObject {
  if (!replacedEdge) {
    return {};
  }

  const nextExtra = replacedEdge.extra ? copyJsonValue(replacedEdge.extra) : {};
  const branch = edgeBranchFromExtra(nextExtra);

  if (sourceHandle === "true" || sourceHandle === "false") {
    nextExtra.branch = sourceHandle;
    return nextExtra;
  }

  if (sourceHandle === "default") {
    nextExtra.branch = "default";
    delete nextExtra.case_value;
    return nextExtra;
  }

  if (sourceHandle === "case") {
    nextExtra.branch = "case";
    if (nextExtra.case_value === undefined) {
      nextExtra.case_value = "case";
    }
    return nextExtra;
  }

  if (branch === "default") {
    delete nextExtra.case_value;
  }

  return nextExtra;
}

function definitionWithoutEdgeId(edgeId: string): RouteFlowDefinition {
  return {
    schema_version: currentFlowDefinition.value.schema_version,
    extra: currentFlowDefinition.value.extra ? copyJsonValue(currentFlowDefinition.value.extra) : {},
    nodes: currentFlowDefinition.value.nodes.map((node) => ({
      ...node,
      position: node.position ? { ...node.position } : undefined,
      config: copyJsonValue(node.config),
      extra: node.extra ? copyJsonValue(node.extra) : {},
    })),
    edges: currentFlowDefinition.value.edges
      .filter((edge) => edge.id !== edgeId)
      .map((edge) => ({
        ...edge,
        extra: edge.extra ? copyJsonValue(edge.extra) : {},
      })),
  };
}

function reconnectConnection(edgeId: string, targetId: string): void {
  const normalizedTargetId = targetId.trim();
  if (!normalizedTargetId) {
    return;
  }

  const currentConnection = currentFlowDefinition.value.edges.find((edge) => edge.id === edgeId);
  if (!currentConnection) {
    return;
  }

  if (currentConnection.target === normalizedTargetId) {
    return;
  }

  const definitionWithoutEdge = definitionWithoutEdgeId(edgeId);
  const reconnectError = validateRouteFlowConnection(
    definitionWithoutEdge,
    currentConnection.source,
    normalizedTargetId,
  );
  if (reconnectError) {
    return;
  }

  const nextDefinition: RouteFlowDefinition = {
    schema_version: definitionWithoutEdge.schema_version,
    extra: definitionWithoutEdge.extra ? copyJsonValue(definitionWithoutEdge.extra) : {},
    nodes: definitionWithoutEdge.nodes.map((node) => ({
      ...node,
      position: node.position ? { ...node.position } : undefined,
      config: copyJsonValue(node.config),
      extra: node.extra ? copyJsonValue(node.extra) : {},
    })),
    edges: [
      ...definitionWithoutEdge.edges.map((edge) => ({
        ...edge,
        extra: edge.extra ? copyJsonValue(edge.extra) : {},
      })),
      {
        id: buildRouteFlowEdgeId(definitionWithoutEdge.edges, currentConnection.source, normalizedTargetId),
        source: currentConnection.source,
        target: normalizedTargetId,
        extra: currentConnection.extra ? copyJsonValue(currentConnection.extra) : {},
      },
    ],
  };

  commitStructuralDefinition(nextDefinition, {
    preserveManualLayout: true,
  });
}

function handleEdgeUpdate(event: { edge: { id: string }; connection: VueFlowConnection }): void {
  const edgeId = event.edge?.id;
  const targetId = event.connection?.target;
  if (!edgeId || !targetId) {
    return;
  }

  reconnectConnection(edgeId, targetId);
}

function handleConnect(connection: VueFlowConnection): void {
  if (!connection.source || !connection.target) {
    return;
  }

  const replacementEdgeId = edgeIdToReplaceForConnection(connection.source, connection.sourceHandle);
  if (replacementEdgeId) {
    const replacedEdge = currentFlowDefinition.value.edges.find((edge) => edge.id === replacementEdgeId) ?? null;
    const definitionWithoutEdge = definitionWithoutEdgeId(replacementEdgeId);
    const replacementError = validateRouteFlowConnection(definitionWithoutEdge, connection.source, connection.target);
    if (replacementError) {
      return;
    }

    const nextDefinition: RouteFlowDefinition = {
      schema_version: definitionWithoutEdge.schema_version,
      extra: definitionWithoutEdge.extra ? copyJsonValue(definitionWithoutEdge.extra) : {},
      nodes: definitionWithoutEdge.nodes.map((node) => ({
        ...node,
        position: node.position ? { ...node.position } : undefined,
        config: copyJsonValue(node.config),
        extra: node.extra ? copyJsonValue(node.extra) : {},
      })),
      edges: [
        ...definitionWithoutEdge.edges.map((edge) => ({
          ...edge,
          extra: edge.extra ? copyJsonValue(edge.extra) : {},
        })),
        {
          id: buildRouteFlowEdgeId(definitionWithoutEdge.edges, connection.source, connection.target),
          source: connection.source,
          target: connection.target,
          extra: replacementEdgeExtra(replacedEdge, connection.sourceHandle),
        },
      ],
    };
    commitStructuralDefinition(nextDefinition, {
      preserveManualLayout: true,
    });
    return;
  }

  const error = validateRouteFlowConnection(currentFlowDefinition.value, connection.source, connection.target);
  if (error) {
    return;
  }

  const nextDefinition: RouteFlowDefinition = {
    schema_version: currentFlowDefinition.value.schema_version,
    extra: currentFlowDefinition.value.extra ? copyJsonValue(currentFlowDefinition.value.extra) : {},
    nodes: currentFlowDefinition.value.nodes.map((node) => ({
      ...node,
      position: node.position ? { ...node.position } : undefined,
      config: copyJsonValue(node.config),
      extra: node.extra ? copyJsonValue(node.extra) : {},
    })),
    edges: [
      ...currentFlowDefinition.value.edges.map((edge) => ({
        ...edge,
        extra: edge.extra ? copyJsonValue(edge.extra) : {},
      })),
      {
        id: buildRouteFlowEdgeId(currentFlowDefinition.value.edges, connection.source, connection.target),
        source: connection.source,
        target: connection.target,
        extra: defaultRouteFlowEdgeExtra(currentFlowDefinition.value, connection.source, connection.sourceHandle),
      },
    ],
  };
  commitStructuralDefinition(nextDefinition);
}

function handleWindowKeydown(event: KeyboardEvent): void {
  if (event.key !== "Escape" || !isFocusMode.value) {
    return;
  }

  if (isFocusPaletteOpen.value) {
    isFocusPaletteOpen.value = false;
    return;
  }
  if (isFocusInfoOpen.value) {
    isFocusInfoOpen.value = false;
    return;
  }
  if (isFocusInspectorOpen.value) {
    isFocusInspectorOpen.value = false;
    return;
  }

  toggleFocusMode();
}

watch(
  () => props.modelValue,
  (value) => {
    const nextDefinition = normalizeRouteFlowDefinition(serializeRouteFlowDefinition(value));
    const nextSerialized = JSON.stringify(serializeRouteFlowDefinition(nextDefinition));
    const currentSerialized = JSON.stringify(serializeRouteFlowDefinition(currentFlowDefinition.value));

    if (nextSerialized === currentSerialized) {
      return;
    }

    hasManualLayout.value = false;
    commitFlowDefinition(nextDefinition);
  },
  { immediate: true, deep: true },
);

watch(
  selectedCanvasNode,
  (node) => {
    refreshInspectorDrafts();

    if (!node) {
      isFocusInspectorOpen.value = false;
      focusEditorTab.value = "parameters";
      focusInputPreviewMode.value = "schema";
      focusOutputPreviewMode.value = "schema";
      inspectorSectionsOpen.value = [];
      return;
    }

    focusEditorTab.value = "parameters";
    inspectorSectionsOpen.value = selectedNodeDefaultInspectorSections.value;
  },
  { immediate: true },
);

watch(
  [canvasNodes, canvasEdges],
  () => {
    const nextDefinition = currentFlowDefinition.value;
    flowDefinitionState.value = nextDefinition;
    emit("update:modelValue", nextDefinition);
  },
  { deep: true },
);

watch(
  allValidationMessages,
  (messages) => {
    emit("validation-change", messages[0] ?? null);
  },
  { immediate: true },
);

watch(isFocusMode, (value) => {
  emit("focus-mode-change", value);

  if (typeof document === "undefined" || typeof window === "undefined") {
    return;
  }

  if (value) {
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleWindowKeydown);
    return;
  }

  window.removeEventListener("keydown", handleWindowKeydown);
  document.body.style.overflow = previousBodyOverflow;
});

onBeforeUnmount(() => {
  if (typeof document !== "undefined") {
    document.body.style.overflow = previousBodyOverflow;
  }
  if (typeof window !== "undefined") {
    window.removeEventListener("keydown", handleWindowKeydown);
  }
});
</script>

<template>
  <Teleport to="body" :disabled="!isFocusMode">
    <div
      class="route-flow-editor"
      :class="{
        'route-flow-editor--focus': isFocusMode,
      }"
    >
      <v-sheet v-if="!isFocusMode" class="route-flow-editor__toolbar pa-4" rounded="xl">
        <div class="route-flow-editor__toolbar-head">
          <div class="route-flow-editor__toolbar-copy">
            <div class="route-flow-editor__panel-eyebrow">
              {{ isFocusMode ? "Command palette" : "Flow designer" }}
            </div>
            <div class="route-flow-editor__toolbar-title">
              {{ isFocusMode ? "Add nodes and shape the route graph." : "Build the route flow on the canvas." }}
            </div>
            <div v-if="!isFocusMode" class="text-body-2 text-medium-emphasis">
              Keep <strong>API Trigger</strong> first, connect logic and connector nodes, then finish with
              <strong>Set Response</strong>.
            </div>
          </div>

          <div class="route-flow-editor__toolbar-status">
            <v-chip :color="flowHealthColor" label size="small" variant="tonal">
              {{ flowHealthLabel }}
            </v-chip>
            <v-chip color="primary" label size="small" variant="tonal">
              {{ nodeCount }} nodes
            </v-chip>
            <v-chip color="secondary" label size="small" variant="tonal">
              {{ edgeCount }} links
            </v-chip>
            <v-chip
              v-if="flowResponseComparison?.matchesContract === false"
              color="warning"
              label
              size="small"
              variant="tonal"
            >
              Preview/live drift
            </v-chip>
            <v-chip
              v-if="savedConnectionCount > 0"
              color="accent"
              label
              size="small"
              variant="tonal"
            >
              {{ savedConnectionCount }} saved connections
            </v-chip>
            <v-btn
              class="route-flow-editor__toolbar-action"
              prepend-icon="mdi-sitemap-outline"
              size="small"
              variant="outlined"
              @click="autoArrangeCanvas"
            >
              Auto arrange
            </v-btn>
            <v-btn
              class="route-flow-editor__toolbar-action"
              :prepend-icon="isFocusMode ? 'mdi-arrow-collapse-all' : 'mdi-arrow-expand-all'"
              color="primary"
              size="small"
              variant="tonal"
              @click="toggleFocusMode"
            >
              {{ isFocusMode ? "Exit full editor" : "Open full editor" }}
            </v-btn>
          </div>
        </div>

        <div class="route-flow-editor__toolbelt">
          <v-btn
            v-for="preset in ROUTE_FLOW_NODE_PRESETS"
            :key="preset.type"
            v-pragmatic-draggable="paletteDragBinding(preset.type, preset.title)"
            class="route-flow-editor__tool-btn"
            :color="preset.color"
            :disabled="!canUsePreset(preset.type)"
            :prepend-icon="preset.icon"
            variant="tonal"
            @click="addNode(preset.type)"
          >
            {{ preset.title }}
          </v-btn>
        </div>

        <div v-if="!isFocusMode" class="route-flow-editor__toolbar-note">
          Drag nodes to the canvas, or click a palette node to append from the selected node.
        </div>
      </v-sheet>

      <div
        v-pragmatic-drop-target="canvasDropBinding"
        class="route-flow-editor__canvas-shell"
        :class="{ 'mt-4': !isFocusMode }"
        @mousedown.capture="handleCanvasMouseDown"
        @auxclick.prevent="handleCanvasAuxClick"
      >
        <VueFlow
          v-model:nodes="canvasNodes"
          v-model:edges="canvasEdges"
          class="route-flow-editor__canvas"
          edges-updatable="target"
          fit-view-on-init
          :min-zoom="0.42"
          :max-zoom="1.75"
          :pan-on-drag="[1]"
          :prevent-scrolling="true"
          @connect="handleConnect"
          @edge-update="handleEdgeUpdate"
          @init="handleFlowInit"
          @node-click="handleNodeClick"
          @node-drag-stop="handleNodeDragStop"
          @pane-click="clearSelection"
        >
          <Background :gap="22" pattern-color="rgba(125, 137, 160, 0.18)" />
          <Panel
            v-if="isFocusMode"
            class="route-flow-editor__focus-floater route-flow-editor__focus-floater--palette"
            position="top-left"
          >
            <v-btn
              class="route-flow-editor__focus-launcher"
              color="primary"
              prepend-icon="mdi-plus-circle-outline"
              rounded="xl"
              variant="tonal"
              @click="toggleFocusPalette"
            >
              {{ isFocusPaletteOpen ? "Hide node tray" : "Add node" }}
            </v-btn>

            <div
              v-if="isFocusPaletteOpen"
              class="route-flow-editor__focus-popover route-flow-editor__focus-popover--palette"
            >
              <div class="route-flow-editor__panel-eyebrow">Command palette</div>
              <div class="route-flow-editor__focus-title">Add or reuse nodes</div>
              <div class="route-flow-editor__focus-copy">
                Drag from here onto the canvas, or click to append from the selected node.
              </div>

              <div v-if="focusCreatablePresets.length > 0" class="mt-4">
                <div class="route-flow-editor__focus-section-title">Create new</div>
                <div class="route-flow-editor__toolbelt route-flow-editor__toolbelt--focus mt-2">
                  <v-btn
                    v-for="preset in focusCreatablePresets"
                    :key="preset.type"
                    v-pragmatic-draggable="paletteDragBinding(preset.type, preset.title)"
                    class="route-flow-editor__tool-btn route-flow-editor__tool-btn--focus"
                    :color="preset.color"
                    :disabled="!canUsePreset(preset.type)"
                    :prepend-icon="preset.icon"
                    variant="tonal"
                    @click="addNode(preset.type)"
                  >
                    {{ preset.title }}
                  </v-btn>
                </div>
              </div>

              <div v-if="focusReusablePresets.length > 0" class="mt-4">
                <div class="route-flow-editor__focus-section-title">Reuse existing</div>
                <div class="route-flow-editor__focus-copy route-flow-editor__focus-copy--compact">
                  Singleton entry and response nodes stay unique. Click one to jump or connect to it.
                </div>
                <div class="route-flow-editor__toolbelt route-flow-editor__toolbelt--focus mt-2">
                  <v-btn
                    v-for="preset in focusReusablePresets"
                    :key="preset.type"
                    v-pragmatic-draggable="paletteDragBinding(preset.type, preset.title)"
                    class="route-flow-editor__tool-btn route-flow-editor__tool-btn--focus"
                    :color="preset.color"
                    :disabled="!canUsePreset(preset.type)"
                    :prepend-icon="preset.icon"
                    variant="tonal"
                    @click="addNode(preset.type)"
                  >
                    {{ preset.title }}
                  </v-btn>
                </div>
              </div>

              <div class="route-flow-editor__focus-help">
                Keep a node selected to append from the palette, or drag straight onto empty canvas space.
              </div>
            </div>
          </Panel>

          <Panel
            v-if="isFocusMode"
            class="route-flow-editor__focus-floater route-flow-editor__focus-floater--utilities"
            position="top-center"
          >
            <div class="route-flow-editor__focus-toolbar">
              <v-btn
                class="route-flow-editor__focus-icon-btn"
                icon="mdi-magnify-minus-outline"
                size="small"
                variant="text"
                @click="zoomCanvasOut"
              />
              <v-btn
                class="route-flow-editor__focus-icon-btn"
                icon="mdi-magnify-plus-outline"
                size="small"
                variant="text"
                @click="zoomCanvasIn"
              />
              <div class="route-flow-editor__focus-divider" />
              <v-btn
                class="route-flow-editor__focus-icon-btn"
                icon="mdi-image-filter-center-focus"
                size="small"
                variant="text"
                @click="fitCanvas"
              />
              <v-btn
                class="route-flow-editor__focus-icon-btn"
                icon="mdi-sitemap-outline"
                size="small"
                variant="text"
                @click="autoArrangeCanvas"
              />
              <v-btn
                aria-label="Save flow"
                class="route-flow-editor__focus-icon-btn"
                :disabled="props.saveDisabled"
                icon="mdi-content-save-outline"
                :loading="props.saveLoading"
                size="small"
                variant="text"
                @click="requestSave"
              />
              <div class="route-flow-editor__focus-divider" />
              <v-btn
                class="route-flow-editor__focus-status-btn"
                :color="focusInfoColor"
                rounded="xl"
                size="small"
                variant="tonal"
                @click="toggleFocusInfo"
              >
                {{ focusInfoLabel }}
              </v-btn>
              <v-btn
                class="route-flow-editor__focus-icon-btn"
                icon="mdi-arrow-collapse-all"
                size="small"
                variant="text"
                @click="toggleFocusMode"
              />
            </div>
          </Panel>

          <Panel
            v-if="isFocusMode && isFocusInfoOpen"
            class="route-flow-editor__focus-floater route-flow-editor__focus-floater--info"
            position="top-center"
          >
            <div class="route-flow-editor__focus-popover route-flow-editor__focus-popover--info">
              <div class="route-flow-editor__focus-signal-bar">
                <div>
                  <div class="route-flow-editor__panel-eyebrow">Flow info</div>
                  <div class="route-flow-editor__focus-title">Route graph status</div>
                </div>
                <v-chip :color="focusInfoColor" label size="small" variant="tonal">
                  {{ focusInfoLabel }}
                </v-chip>
              </div>

              <div class="route-flow-editor__focus-chip-row mt-3">
                <v-chip color="primary" label size="small" variant="tonal">
                  {{ nodeCount }} nodes
                </v-chip>
                <v-chip color="secondary" label size="small" variant="tonal">
                  {{ edgeCount }} links
                </v-chip>
                <v-chip
                  v-if="savedConnectionCount > 0"
                  color="accent"
                  label
                  size="small"
                  variant="tonal"
                >
                  {{ savedConnectionCount }} connections
                </v-chip>
              </div>

              <v-alert
                v-if="errorMessage"
                class="mt-3"
                border="start"
                color="error"
                density="compact"
                variant="tonal"
              >
                {{ errorMessage }}
              </v-alert>

              <v-alert
                v-else-if="allValidationMessages.length > 0"
                class="mt-3"
                border="start"
                color="warning"
                density="compact"
                variant="tonal"
              >
                <div class="font-weight-medium mb-2">Fix these flow issues before saving</div>
                <ul class="route-flow-editor__message-list">
                  <li v-for="message in allValidationMessages" :key="message">{{ message }}</li>
                </ul>
              </v-alert>

              <v-alert
                v-else
                class="mt-3"
                border="start"
                color="success"
                density="compact"
                variant="tonal"
              >
                The current live flow is structurally valid for this runtime slice.
              </v-alert>

              <v-expansion-panels
                v-model="focusSignalsOpen"
                class="route-flow-editor__json-panel route-flow-editor__json-panel--focus mt-3"
                multiple
                variant="accordion"
              >
                <v-expansion-panel :value="0" elevation="0">
                  <v-expansion-panel-title>Route paths</v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <div v-if="connectionSummaries.length === 0" class="text-body-2 text-medium-emphasis">
                      No paths yet. Drag from a port or append a node from the palette.
                    </div>
                    <div v-else class="route-flow-editor__focus-connection-list">
                      <div
                        v-for="connection in connectionSummaries"
                        :key="connection.id"
                        class="route-flow-editor__connection-row"
                      >
                        <div class="text-body-2">
                          <strong>{{ connection.source }}</strong>
                          <span v-if="connection.label" class="text-medium-emphasis"> via {{ connection.label }}</span>
                          <span class="text-medium-emphasis"> to </span>
                          <strong>{{ connection.target }}</strong>
                        </div>
                        <v-btn
                          color="error"
                          icon="mdi-close"
                          size="x-small"
                          variant="text"
                          @click="removeConnection(connection.id)"
                        />
                      </div>
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>

                <v-expansion-panel :value="1" elevation="0">
                  <v-expansion-panel-title>Designer JSON</v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <pre class="route-flow-editor__json-preview">{{ flowDefinitionPreview }}</pre>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </div>
          </Panel>

          <Panel
            v-if="isFocusMode && selectedCanvasNode"
            class="route-flow-editor__focus-floater route-flow-editor__focus-floater--inspector-toggle"
            position="top-right"
          >
            <v-btn
              class="route-flow-editor__focus-node-launcher"
              :color="selectedFlowNodePreset?.color ?? 'primary'"
              prepend-icon="mdi-tune-variant"
              rounded="xl"
              variant="tonal"
              @click="toggleFocusInspector"
            >
              {{ isFocusInspectorOpen ? "Hide" : "Edit" }} {{ selectedCanvasNode.label }}
            </v-btn>
          </Panel>

          <Controls
            v-if="!isFocusMode"
            position="bottom-left"
            :show-fit-view="false"
            :show-interactive="false"
          >
            <ControlButton title="Fit flow to view" @click="fitCanvas">
              <v-icon icon="mdi-image-filter-center-focus" size="18" />
            </ControlButton>
            <ControlButton title="Auto arrange nodes" @click="autoArrangeCanvas">
              <v-icon icon="mdi-sitemap-outline" size="18" />
            </ControlButton>
            <ControlButton
              :title="isFocusMode ? 'Exit full editor' : 'Open full editor'"
              @click="toggleFocusMode"
            >
              <v-icon :icon="isFocusMode ? 'mdi-arrow-collapse-all' : 'mdi-arrow-expand-all'" size="18" />
            </ControlButton>
          </Controls>
          <MiniMap
            v-if="isFocusMode"
            aria-label="Flow minimap"
            class="route-flow-editor__minimap"
            :height="146"
            :width="210"
            mask-color="rgba(15, 23, 42, 0.66)"
            mask-stroke-color="rgba(248, 250, 252, 0.4)"
            :mask-stroke-width="1.5"
            :node-color="miniMapNodeColor"
            :node-stroke-color="miniMapNodeStrokeColor"
            :node-stroke-width="2.2"
            :offset-scale="4"
            pannable
            position="bottom-right"
            zoomable
          />

          <template #node-route="routeNodeProps">
            <RouteFlowCanvasNode
              v-bind="routeNodeProps"
              @center="handleNodeToolbarCenter"
              @remove="handleNodeToolbarRemove"
            />
          </template>
        </VueFlow>
      </div>

      <v-row
        v-if="!isFocusMode || isFocusInspectorOpen"
        class="route-flow-editor__detail-grid"
        :class="{
          'mt-4': !isFocusMode,
          'route-flow-editor__detail-grid--focus': isFocusMode,
        }"
      >
        <v-col
          v-if="selectedCanvasNode"
          class="route-flow-editor__focus-side-column route-flow-editor__focus-side-column--left"
          cols="12"
          md="3"
        >
          <v-sheet class="route-flow-editor__detail-panel route-flow-editor__detail-panel--preview pa-4" rounded="xl">
            <div class="route-flow-editor__detail-head route-flow-editor__detail-head--stacked">
              <div>
                <div class="route-flow-editor__panel-eyebrow">Input payload</div>
                <div class="route-flow-editor__detail-title route-flow-editor__detail-title--sm">Data in scope</div>
              </div>
              <v-chip
                v-if="selectedNodeInspection"
                color="secondary"
                label
                size="small"
                variant="tonal"
              >
                {{ selectedNodeInspection.inputShape }}
              </v-chip>
            </div>

            <v-btn-toggle
              v-model="focusInputPreviewMode"
              class="route-flow-editor__preview-toggle mt-3"
              color="primary"
              mandatory
              variant="outlined"
            >
              <v-btn value="schema">Schema</v-btn>
              <v-btn value="table">Table</v-btn>
              <v-btn value="json">JSON</v-btn>
            </v-btn-toggle>

            <div v-if="selectedNodeInspection" class="route-flow-editor__preview-scroll mt-3" @wheel.stop>
              <template v-if="focusInputPreviewMode === 'schema'">
                <div class="text-caption text-medium-emphasis mb-3">
                  Drag field pills from this payload tree into the center editor.
                </div>

                <div class="d-flex flex-column ga-3">
                  <div
                    v-for="section in focusInputSchemaSections"
                    :key="section.refPath"
                    class="route-flow-editor__schema-section"
                  >
                    <div class="d-flex align-start justify-space-between ga-3">
                      <div>
                        <v-chip
                          v-pragmatic-draggable="referenceSnippetDragBinding(section.label, section.refPath)"
                          class="route-flow-editor__schema-pill"
                          label
                          size="small"
                          variant="outlined"
                          @click="handleFocusSchemaSnippetClick(section.refPath)"
                        >
                          {{ section.label }}
                        </v-chip>
                        <div class="text-caption text-medium-emphasis">{{ section.refPath }}</div>
                      </div>
                      <v-chip label size="x-small" variant="outlined">
                        {{ section.shape }}
                      </v-chip>
                    </div>

                    <div v-if="section.rows.length === 0" class="text-caption text-medium-emphasis mt-3">
                      No visible sample fields for this payload.
                    </div>

                    <div v-else class="route-flow-editor__schema-tree mt-3">
                      <div
                        v-for="row in section.rows"
                        :key="row.refPath"
                        class="route-flow-editor__schema-row"
                        :style="{ '--schema-depth': String(row.depth) }"
                      >
                        <v-chip
                          v-pragmatic-draggable="referenceSnippetDragBinding(row.label, row.refPath)"
                          class="route-flow-editor__schema-pill"
                          label
                          size="small"
                          variant="outlined"
                          @click="handleFocusSchemaSnippetClick(row.refPath)"
                        >
                          {{ row.label }}
                        </v-chip>
                        <span class="text-caption text-medium-emphasis route-flow-editor__schema-row-preview">
                          {{ row.preview }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </template>

              <template v-else-if="focusInputPreviewMode === 'table'">
                <v-table density="compact" hover>
                  <thead>
                    <tr>
                      <th class="text-left">Path</th>
                      <th class="text-left">Type</th>
                      <th class="text-left">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in focusInputPreviewTableRows" :key="`${row.source}:${row.path}`">
                      <td class="text-caption">{{ row.path }}</td>
                      <td class="text-caption">{{ row.type }}</td>
                      <td class="text-caption route-flow-editor__table-value">{{ row.value }}</td>
                    </tr>
                  </tbody>
                </v-table>
              </template>

              <template v-else>
                <div class="d-flex flex-column ga-3">
                  <div
                    v-for="entry in selectedNodeInspection.scopeEntries"
                    :key="entry.refPath"
                    class="route-flow-editor__sample-entry"
                  >
                    <div class="d-flex align-start justify-space-between ga-3">
                      <div>
                        <div class="text-body-2 font-weight-medium">{{ entry.label }}</div>
                        <div class="text-caption text-medium-emphasis">{{ entry.refPath }}</div>
                      </div>
                      <v-chip label size="x-small" variant="outlined">
                        {{ entry.shape }}
                      </v-chip>
                    </div>
                    <pre class="route-flow-editor__json-preview route-flow-editor__json-preview--sample mt-2">{{ entry.json }}</pre>
                  </div>
                </div>
              </template>
            </div>

            <v-alert
              v-else-if="selectedCanvasNode && !selectedNodeOnSamplePath"
              class="mt-3"
              border="start"
              color="info"
              variant="tonal"
            >
              The current generated request sample does not traverse this node path.
            </v-alert>
          </v-sheet>
        </v-col>

        <v-col
          class="route-flow-editor__inspector-column"
          cols="12"
          :md="selectedCanvasNode ? 6 : 12"
          :xl="selectedCanvasNode ? 6 : 12"
        >
          <v-sheet class="route-flow-editor__detail-panel pa-4" rounded="xl">
            <div class="route-flow-editor__detail-head">
              <div>
                <div class="route-flow-editor__panel-eyebrow">Selected node</div>
                <div class="route-flow-editor__detail-title">
                  {{ selectedCanvasNode ? selectedCanvasNode.label : "Choose a node to edit" }}
                </div>
                <div class="text-body-2 text-medium-emphasis">
                  {{
                    selectedCanvasNode
                      ? isFocusMode
                        ? "Edit node parameters here while input/output previews stay pinned."
                        : "Edit node parameters here while input/output previews stay visible."
                      : "Select a node on the canvas to edit it here."
                  }}
                </div>
              </div>

              <div class="d-flex flex-wrap justify-end ga-2">
                <v-btn
                  v-if="selectedCanvasNode"
                  prepend-icon="mdi-close"
                  variant="text"
                  @click="closeInspector"
                >
                  Close
                </v-btn>
                <v-btn
                  v-if="selectedCanvasNode"
                  color="error"
                  prepend-icon="mdi-trash-can-outline"
                  variant="text"
                  @click="removeSelectedNode"
                >
                  Remove
                </v-btn>
              </div>
            </div>

            <v-btn-toggle
              v-if="selectedCanvasNode"
              v-model="focusEditorTab"
              class="route-flow-editor__preview-toggle mt-3"
              color="primary"
              mandatory
              variant="outlined"
            >
              <v-btn value="parameters">Parameters</v-btn>
              <v-btn value="settings">Settings</v-btn>
            </v-btn-toggle>

            <div v-if="selectedCanvasNode" class="route-flow-editor__detail-body d-flex flex-column ga-4 mt-4" @wheel.stop>
              <v-row v-if="focusEditorTab === 'parameters'" class="route-flow-editor__editor-grid">
                <v-col cols="12">
                  <div class="d-flex flex-column ga-4">
                    <v-sheet class="route-flow-editor__subpanel pa-4" rounded="xl">
                      <div class="route-flow-editor__panel-eyebrow">Runtime behavior</div>

                      <template v-if="selectedCanvasNode.data.runtimeType === 'api_trigger'">
                        <div class="text-body-2 text-medium-emphasis mt-3">
                          API Trigger behavior is derived from the saved route contract.
                        </div>
                      </template>

                      <template v-else-if="selectedCanvasNode.data.runtimeType === 'validate_request'">
                        <v-text-field
                          class="mt-3"
                          label="Body mode"
                          :model-value="String(selectedCanvasNode.data.config.body_mode ?? 'contract')"
                          readonly
                        />
                        <v-text-field
                          label="Parameters mode"
                          :model-value="String(selectedCanvasNode.data.config.parameters_mode ?? 'contract')"
                          readonly
                        />
                      </template>

                      <template v-else-if="selectedCanvasNode.data.runtimeType === 'transform'">
                        <div class="route-flow-editor__snippet-row mt-3">
                          <span class="text-caption text-medium-emphasis">Quick refs</span>
                          <div class="d-flex flex-wrap ga-2">
                            <v-chip
                              v-for="snippet in transformReferenceSnippets"
                              :key="snippet.value"
                              v-pragmatic-draggable="referenceSnippetDragBinding(snippet.label, snippet.value)"
                              label
                              size="small"
                              variant="outlined"
                              @click="applyReferenceSnippet('transform', snippet.value)"
                            >
                              {{ snippet.label }}
                            </v-chip>
                          </div>
                        </div>

                        <div
                          :ref="(element) => setJsonEditorRootElement('transform', element)"
                          v-pragmatic-drop-target="jsonReferenceDropBindings.transform"
                          class="route-flow-editor__json-drop-target mt-3"
                          @focusin.capture="rememberJsonEditorSelection('transform', $event)"
                          @keyup.capture="rememberJsonEditorSelection('transform', $event)"
                          @mouseup.capture="rememberJsonEditorSelection('transform', $event)"
                          @select.capture="rememberJsonEditorSelection('transform', $event)"
                        >
                          <v-textarea
                            auto-grow
                            hint="Use JSON with whole-value refs like {&quot;$ref&quot;:&quot;request.body&quot;} and inline string templates like &quot;Hello {{request.path.userId}}&quot;."
                            label="Output template JSON"
                            persistent-hint
                            rows="11"
                            spellcheck="false"
                            :error-messages="transformOutputError ? [transformOutputError] : []"
                            :model-value="transformOutputText"
                            @update:model-value="handleTransformOutputInput(String($event ?? ''))"
                          />
                        </div>
                      </template>

                      <template v-else-if="selectedCanvasNode.data.runtimeType === 'if_condition'">
                        <div class="route-flow-editor__snippet-row mt-3">
                          <span class="text-caption text-medium-emphasis">Quick refs</span>
                          <div class="d-flex flex-wrap ga-2">
                            <v-chip
                              v-for="snippet in transformReferenceSnippets"
                              :key="snippet.value"
                              label
                              size="small"
                              variant="outlined"
                              @click="applyReferenceSnippet('ifLeft', snippet.value)"
                            >
                              {{ snippet.label }}
                            </v-chip>
                          </div>
                        </div>

                        <v-textarea
                          class="mt-3"
                          auto-grow
                          hint="Use a ref like {&quot;$ref&quot;:&quot;request.query.mode&quot;} or a plain string value."
                          label="Left value"
                          persistent-hint
                          rows="3"
                          spellcheck="false"
                          :error-messages="ifLeftError ? [ifLeftError] : []"
                          :model-value="ifLeftText"
                          @update:model-value="handleIfLeftInput(String($event ?? ''))"
                        />
                        <v-select
                          v-model="selectedNodeIfOperator"
                          :items="IF_OPERATOR_OPTIONS"
                          item-title="title"
                          item-value="value"
                          label="Operator"
                          :menu-props="FOCUS_SELECT_MENU_PROPS"
                        />
                        <v-textarea
                          v-if="requiresIfRightValue"
                          auto-grow
                          hint="Use a ref like {&quot;$ref&quot;:&quot;state.http-request-1.response.status_code&quot;} or a plain value."
                          label="Right value"
                          persistent-hint
                          rows="3"
                          spellcheck="false"
                          :error-messages="ifRightError ? [ifRightError] : []"
                          :model-value="ifRightText"
                          @update:model-value="handleIfRightInput(String($event ?? ''))"
                        />
                      </template>

                      <template v-else-if="selectedCanvasNode.data.runtimeType === 'switch'">
                        <div class="route-flow-editor__snippet-row mt-3">
                          <span class="text-caption text-medium-emphasis">Quick refs</span>
                          <div class="d-flex flex-wrap ga-2">
                            <v-chip
                              v-for="snippet in transformReferenceSnippets"
                              :key="snippet.value"
                              label
                              size="small"
                              variant="outlined"
                              @click="applyReferenceSnippet('switchValue', snippet.value)"
                            >
                              {{ snippet.label }}
                            </v-chip>
                          </div>
                        </div>

                        <v-textarea
                          class="mt-3"
                          auto-grow
                          hint="Use a ref like {&quot;$ref&quot;:&quot;request.query.mode&quot;} or a plain string value."
                          label="Switch value"
                          persistent-hint
                          rows="3"
                          spellcheck="false"
                          :error-messages="switchValueError ? [switchValueError] : []"
                          :model-value="switchValueText"
                          @update:model-value="handleSwitchValueInput(String($event ?? ''))"
                        />
                      </template>

                      <template v-else-if="selectedCanvasNode.data.runtimeType === 'http_request'">
                        <v-select
                          v-model="selectedNodeConnectionId"
                          class="mt-3"
                          :items="httpConnectionOptions"
                          clearable
                          label="HTTP connection"
                          :menu-props="FOCUS_SELECT_MENU_PROPS"
                        />

                        <div
                          :ref="(element) => setTextEditorRootElement('httpPath', element)"
                          v-pragmatic-drop-target="textReferenceDropBindings.httpPath"
                          class="route-flow-editor__text-drop-target mt-3"
                          @focusin.capture="rememberTextEditorSelection('httpPath', $event)"
                          @keyup.capture="rememberTextEditorSelection('httpPath', $event)"
                          @mouseup.capture="rememberTextEditorSelection('httpPath', $event)"
                          @select.capture="rememberTextEditorSelection('httpPath', $event)"
                        >
                          <v-text-field
                            hint="Use a relative path such as /devices/{{request.path.deviceId}}, drag in ref pills, or enter a full absolute URL."
                            label="Path or URL template"
                            persistent-hint
                            :model-value="httpPathText"
                            @update:model-value="handleHttpPathInput(String($event ?? ''))"
                          />
                        </div>

                        <v-row class="mt-1">
                          <v-col cols="12" md="6">
                            <v-select
                              v-model="selectedNodeHttpMethod"
                              :items="HTTP_METHOD_OPTIONS"
                              label="Method"
                              :menu-props="FOCUS_SELECT_MENU_PROPS"
                            />
                          </v-col>
                          <v-col cols="12" md="6">
                            <v-text-field
                              v-model="selectedNodeTimeoutMs"
                              label="Timeout (ms)"
                            />
                          </v-col>
                        </v-row>

                        <div
                          :ref="(element) => setJsonEditorRootElement('httpQuery', element)"
                          v-pragmatic-drop-target="jsonReferenceDropBindings.httpQuery"
                          class="route-flow-editor__json-drop-target mt-2"
                          @focusin.capture="rememberJsonEditorSelection('httpQuery', $event)"
                          @keyup.capture="rememberJsonEditorSelection('httpQuery', $event)"
                          @mouseup.capture="rememberJsonEditorSelection('httpQuery', $event)"
                          @select.capture="rememberJsonEditorSelection('httpQuery', $event)"
                        >
                          <v-textarea
                            auto-grow
                            hint="Optional JSON object of query params, for example {&quot;include&quot;:{&quot;$ref&quot;:&quot;request.query.include&quot;}}."
                            label="Query params JSON"
                            persistent-hint
                            rows="5"
                            spellcheck="false"
                            :error-messages="httpQueryError ? [httpQueryError] : []"
                            :model-value="httpQueryText"
                            @update:model-value="handleHttpQueryInput(String($event ?? ''))"
                          />
                        </div>
                        <div
                          :ref="(element) => setJsonEditorRootElement('httpHeaders', element)"
                          v-pragmatic-drop-target="jsonReferenceDropBindings.httpHeaders"
                          class="route-flow-editor__json-drop-target"
                          @focusin.capture="rememberJsonEditorSelection('httpHeaders', $event)"
                          @keyup.capture="rememberJsonEditorSelection('httpHeaders', $event)"
                          @mouseup.capture="rememberJsonEditorSelection('httpHeaders', $event)"
                          @select.capture="rememberJsonEditorSelection('httpHeaders', $event)"
                        >
                          <v-textarea
                            auto-grow
                            hint="Optional JSON object of headers. Connection-level headers still apply automatically."
                            label="Request headers JSON"
                            persistent-hint
                            rows="5"
                            spellcheck="false"
                            :error-messages="httpHeadersError ? [httpHeadersError] : []"
                            :model-value="httpHeadersText"
                            @update:model-value="handleHttpHeadersInput(String($event ?? ''))"
                          />
                        </div>
                        <div
                          :ref="(element) => setJsonEditorRootElement('httpBody', element)"
                          v-pragmatic-drop-target="jsonReferenceDropBindings.httpBody"
                          class="route-flow-editor__json-drop-target"
                          @focusin.capture="rememberJsonEditorSelection('httpBody', $event)"
                          @keyup.capture="rememberJsonEditorSelection('httpBody', $event)"
                          @mouseup.capture="rememberJsonEditorSelection('httpBody', $event)"
                          @select.capture="rememberJsonEditorSelection('httpBody', $event)"
                        >
                          <v-textarea
                            auto-grow
                            hint="Optional JSON body sent to the upstream request."
                            label="Request body JSON"
                            persistent-hint
                            rows="6"
                            spellcheck="false"
                            :error-messages="httpBodyError ? [httpBodyError] : []"
                            :model-value="httpBodyText"
                            @update:model-value="handleHttpBodyInput(String($event ?? ''))"
                          />
                        </div>

                      </template>

                      <template v-else-if="selectedCanvasNode.data.runtimeType === 'postgres_query'">
                        <v-select
                          v-model="selectedNodeConnectionId"
                          class="mt-3"
                          :items="postgresConnectionOptions"
                          clearable
                          label="Postgres connection"
                          :menu-props="FOCUS_SELECT_MENU_PROPS"
                        />
                        <v-textarea
                          auto-grow
                          hint="Use placeholders like %(order_id)s in one read-only statement."
                          label="SQL"
                          persistent-hint
                          rows="7"
                          spellcheck="false"
                          :model-value="postgresSqlText"
                          @update:model-value="handlePostgresSqlInput(String($event ?? ''))"
                        />
                        <div
                          :ref="(element) => setJsonEditorRootElement('postgresParameters', element)"
                          v-pragmatic-drop-target="jsonReferenceDropBindings.postgresParameters"
                          class="route-flow-editor__json-drop-target"
                          @focusin.capture="rememberJsonEditorSelection('postgresParameters', $event)"
                          @keyup.capture="rememberJsonEditorSelection('postgresParameters', $event)"
                          @mouseup.capture="rememberJsonEditorSelection('postgresParameters', $event)"
                          @select.capture="rememberJsonEditorSelection('postgresParameters', $event)"
                        >
                          <v-textarea
                            auto-grow
                            hint="Map placeholders to refs, for example {&quot;order_id&quot;:{&quot;$ref&quot;:&quot;request.path.orderId&quot;}}."
                            label="Parameters JSON"
                            persistent-hint
                            rows="6"
                            spellcheck="false"
                            :error-messages="postgresParametersError ? [postgresParametersError] : []"
                            :model-value="postgresParametersText"
                            @update:model-value="handlePostgresParametersInput(String($event ?? ''))"
                          />
                        </div>
                      </template>

                      <template v-else-if="selectedCanvasNode.data.runtimeType === 'set_response'">
                        <v-text-field v-model="selectedNodeStatusCode" class="mt-3" label="Status code" />

                        <div class="route-flow-editor__snippet-row">
                          <span class="text-caption text-medium-emphasis">Quick refs</span>
                          <div class="d-flex flex-wrap ga-2">
                            <v-chip
                              v-for="snippet in responseReferenceSnippets"
                              :key="snippet.value"
                              v-pragmatic-draggable="referenceSnippetDragBinding(snippet.label, snippet.value)"
                              label
                              size="small"
                              variant="outlined"
                              @click="applyReferenceSnippet('response', snippet.value)"
                            >
                              {{ snippet.label }}
                            </v-chip>
                          </div>
                        </div>

                        <div
                          :ref="(element) => setJsonEditorRootElement('response', element)"
                          v-pragmatic-drop-target="jsonReferenceDropBindings.response"
                          class="route-flow-editor__json-drop-target mt-3"
                          @focusin.capture="rememberJsonEditorSelection('response', $event)"
                          @keyup.capture="rememberJsonEditorSelection('response', $event)"
                          @mouseup.capture="rememberJsonEditorSelection('response', $event)"
                          @select.capture="rememberJsonEditorSelection('response', $event)"
                        >
                          <v-textarea
                            auto-grow
                            hint="Response bodies can mix fixed JSON, whole-value refs like {&quot;$ref&quot;:&quot;state.transform&quot;}, and inline string templates like &quot;order={{request.path.orderId}}&quot;."
                            label="Response body JSON"
                            persistent-hint
                            rows="11"
                            spellcheck="false"
                            :error-messages="responseBodyError ? [responseBodyError] : []"
                            :model-value="responseBodyText"
                            @update:model-value="handleResponseBodyInput(String($event ?? ''))"
                          />
                        </div>
                      </template>

                      <template v-else-if="selectedCanvasNode.data.runtimeType === 'error_response'">
                        <v-text-field v-model="selectedNodeStatusCode" class="mt-3" label="Error response status" />

                        <div class="route-flow-editor__snippet-row">
                          <span class="text-caption text-medium-emphasis">Quick refs</span>
                          <div class="d-flex flex-wrap ga-2">
                            <v-chip
                              v-for="snippet in ERROR_REFERENCE_SNIPPETS"
                              :key="snippet.value"
                              v-pragmatic-draggable="referenceSnippetDragBinding(snippet.label, snippet.value)"
                              label
                              size="small"
                              variant="outlined"
                              @click="applyReferenceSnippet('error', snippet.value)"
                            >
                              {{ snippet.label }}
                            </v-chip>
                          </div>
                        </div>

                        <div
                          :ref="(element) => setJsonEditorRootElement('error', element)"
                          v-pragmatic-drop-target="jsonReferenceDropBindings.error"
                          class="route-flow-editor__json-drop-target mt-3"
                          @focusin.capture="rememberJsonEditorSelection('error', $event)"
                          @keyup.capture="rememberJsonEditorSelection('error', $event)"
                          @mouseup.capture="rememberJsonEditorSelection('error', $event)"
                          @select.capture="rememberJsonEditorSelection('error', $event)"
                        >
                          <v-textarea
                            auto-grow
                            hint="Returned when Validate Request fails or a flow path routes here. Supports whole-value refs and inline string templates such as &quot;reason={{errors.0}}&quot;."
                            label="Error response body JSON"
                            persistent-hint
                            rows="11"
                            spellcheck="false"
                            :error-messages="errorBodyError ? [errorBodyError] : []"
                            :model-value="errorBodyText"
                            @update:model-value="handleErrorBodyInput(String($event ?? ''))"
                          />
                        </div>
                      </template>

                      <v-expansion-panels
                        v-model="inspectorSectionsOpen"
                        class="route-flow-editor__json-panel route-flow-editor__json-panel--focus mt-4"
                        multiple
                        variant="accordion"
                      >
                        <v-expansion-panel v-if="selectedNodeHasGuidance" value="guidance" elevation="0">
                          <v-expansion-panel-title>Flow guidance</v-expansion-panel-title>
                          <v-expansion-panel-text>
                            <v-alert
                              v-if="selectedNodeGuidance"
                              border="start"
                              :color="selectedNodeGuidance.tone"
                              density="comfortable"
                              variant="tonal"
                            >
                              {{ selectedNodeGuidance.message }}
                            </v-alert>

                            <template v-if="selectedNodeInspection">
                              <v-alert
                                class="mt-3"
                                border="start"
                                :color="selectedNodeInspection.boundaryTone"
                                density="comfortable"
                                variant="tonal"
                              >
                                {{ selectedNodeInspection.boundaryMessage }}
                              </v-alert>

                              <v-alert
                                v-if="selectedNodeInspection.unresolvedRefs.length > 0"
                                class="mt-3"
                                border="start"
                                color="warning"
                                density="comfortable"
                                variant="tonal"
                              >
                                Some refs do not resolve in the current sample context yet:
                                {{ selectedNodeInspection.unresolvedRefs.join(", ") }}
                              </v-alert>

                              <v-alert
                                v-for="note in selectedNodeInspection.notes"
                                :key="note"
                                class="mt-3"
                                border="start"
                                color="info"
                                density="comfortable"
                                variant="tonal"
                              >
                                {{ note }}
                              </v-alert>
                            </template>
                          </v-expansion-panel-text>
                        </v-expansion-panel>

                        <v-expansion-panel value="paths" elevation="0">
                          <v-expansion-panel-title>Connected paths</v-expansion-panel-title>
                          <v-expansion-panel-text>
                            <div class="text-caption text-medium-emphasis">
                              {{ selectedNodePathManagementCopy }}
                            </div>
                            <div v-if="selectedNodeOutgoingConnections.length === 0" class="text-caption text-medium-emphasis mt-2">
                              This node currently has no outgoing paths.
                            </div>
                            <div v-else class="d-flex flex-column ga-2 mt-2">
                              <div
                                v-for="connection in selectedNodeOutgoingConnections"
                                :key="`manage-${connection.id}`"
                                class="route-flow-editor__path-card"
                              >
                                <div class="route-flow-editor__path-card-head">
                                  <div class="text-body-2">
                                    <strong>{{ connection.sourceLabel }}</strong>
                                    <span v-if="connection.label" class="text-medium-emphasis"> via {{ connection.label }}</span>
                                    <span class="text-medium-emphasis"> to </span>
                                    <strong>{{ connection.targetLabel }}</strong>
                                  </div>
                                  <v-btn
                                    color="error"
                                    prepend-icon="mdi-link-variant-remove"
                                    size="small"
                                    variant="text"
                                    @click="removeConnection(connection.id)"
                                  >
                                    Remove path
                                  </v-btn>
                                </div>

                                <div class="route-flow-editor__path-targets">
                                  <span class="text-caption text-medium-emphasis">Next node</span>
                                  <v-menu location="bottom start">
                                    <template #activator="{ props: menuProps }">
                                      <v-btn
                                        v-bind="menuProps"
                                        class="route-flow-editor__path-target-button"
                                        variant="outlined"
                                      >
                                        {{ connection.targetLabel }}
                                      </v-btn>
                                    </template>
                                    <v-list density="compact">
                                      <v-list-item
                                        v-for="target in reconnectTargetOptionsByEdgeId.get(connection.id) ?? []"
                                        :key="`${connection.id}-target-${target.value}`"
                                        :active="target.value === connection.targetId"
                                        :title="target.title"
                                        @click="reconnectConnection(connection.id, target.value)"
                                      />
                                    </v-list>
                                  </v-menu>
                                </div>

                                <v-select
                                  v-if="selectedCanvasNode.data.runtimeType === 'if_condition'"
                                  :items="IF_BRANCH_OPTIONS"
                                  item-title="title"
                                  item-value="value"
                                  label="Branch"
                                  :model-value="connection.branch"
                                  :menu-props="FOCUS_SELECT_MENU_PROPS"
                                  @update:model-value="updateIfBranchForEdge(connection.id, String($event ?? ''))"
                                />

                                <template v-else-if="selectedCanvasNode.data.runtimeType === 'switch'">
                                  <v-select
                                    :items="SWITCH_BRANCH_OPTIONS"
                                    item-title="title"
                                    item-value="value"
                                    label="Path type"
                                    :model-value="connection.branch"
                                    :menu-props="FOCUS_SELECT_MENU_PROPS"
                                    @update:model-value="updateSwitchBranchMode(connection.id, String($event ?? ''))"
                                  />
                                  <v-text-field
                                    v-if="connection.branch === 'case'"
                                    label="Case value"
                                    :model-value="stringifyFlexibleValue(connection.caseValue)"
                                    @update:model-value="updateSwitchCaseValue(connection.id, String($event ?? ''))"
                                  />
                                </template>
                              </div>
                            </div>
                          </v-expansion-panel-text>
                        </v-expansion-panel>
                      </v-expansion-panels>
                    </v-sheet>
                  </div>
                </v-col>
              </v-row>

              <v-sheet
                v-else
                class="route-flow-editor__subpanel pa-4"
                rounded="xl"
              >
                <div class="route-flow-editor__panel-eyebrow">Node settings</div>
                <div class="d-flex flex-wrap ga-2 mt-3">
                  <v-chip :color="selectedFlowNodePreset?.color" label size="small" variant="tonal">
                    {{ selectedFlowNodePreset?.title }}
                  </v-chip>
                  <v-chip label size="small" variant="outlined">
                    {{ selectedNodeConnectionSummary.incoming }} in / {{ selectedNodeConnectionSummary.outgoing }} out
                  </v-chip>
                </div>

                <v-text-field
                  class="mt-4"
                  label="Node name"
                  :model-value="selectedCanvasNode.label"
                  @update:model-value="updateSelectedNodeName(String($event ?? ''))"
                />
                <v-text-field
                  label="Node id"
                  :model-value="selectedCanvasNode.id"
                  readonly
                />

                <div class="text-body-2 text-medium-emphasis mt-2">
                  {{ selectedFlowNodePreset?.description }}
                </div>
              </v-sheet>
            </div>

            <div v-else class="route-flow-editor__empty-state mt-4">
              <v-icon icon="mdi-cursor-default-click-outline" size="22" />
              <span>Select a node on the canvas to open its editing dock.</span>
            </div>
          </v-sheet>
        </v-col>

        <v-col
          v-if="selectedCanvasNode"
          class="route-flow-editor__focus-side-column route-flow-editor__focus-side-column--right"
          cols="12"
          md="3"
        >
          <v-sheet class="route-flow-editor__detail-panel route-flow-editor__detail-panel--preview pa-4" rounded="xl">
            <div class="route-flow-editor__detail-head route-flow-editor__detail-head--stacked">
              <div>
                <div class="route-flow-editor__panel-eyebrow">Output payload</div>
                <div class="route-flow-editor__detail-title route-flow-editor__detail-title--sm">
                  {{ selectedNodeInspection?.outputTitle ?? "Node output" }}
                </div>
              </div>
              <v-chip
                v-if="selectedNodeInspection"
                color="primary"
                label
                size="small"
                variant="tonal"
              >
                {{ selectedNodeInspection.outputShape }}
              </v-chip>
            </div>

            <v-btn-toggle
              v-model="focusOutputPreviewMode"
              class="route-flow-editor__preview-toggle mt-3"
              color="primary"
              mandatory
              variant="outlined"
            >
              <v-btn value="schema">Schema</v-btn>
              <v-btn value="table">Table</v-btn>
              <v-btn value="json">JSON</v-btn>
            </v-btn-toggle>

            <div v-if="selectedNodeInspection" class="route-flow-editor__preview-scroll mt-3" @wheel.stop>
              <template v-if="focusOutputPreviewMode === 'schema'">
                <div class="route-flow-editor__sample-entry">
                  <div class="text-body-2 font-weight-medium">{{ selectedNodeInspection.outputTitle }}</div>
                  <div class="text-caption text-medium-emphasis">Live flow output shape</div>
                  <pre class="route-flow-editor__json-preview route-flow-editor__json-preview--sample mt-2">{{ selectedNodeInspection.outputJson }}</pre>
                </div>

                <div v-if="selectedNodeInspection.responseComparison" class="route-flow-editor__sample-entry mt-3">
                  <div class="text-body-2 font-weight-medium">Contract preview sample</div>
                  <div class="text-caption text-medium-emphasis">
                    Test preview still comes from <code>response_schema</code>.
                  </div>
                  <pre class="route-flow-editor__json-preview route-flow-editor__json-preview--sample mt-2">{{ selectedNodeInspection.responseComparison.contractJson ?? "null" }}</pre>
                </div>
              </template>

              <template v-else-if="focusOutputPreviewMode === 'table'">
                <v-table density="compact" hover>
                  <thead>
                    <tr>
                      <th class="text-left">Path</th>
                      <th class="text-left">Type</th>
                      <th class="text-left">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in focusOutputPreviewTableRows" :key="`${row.source}:${row.path}`">
                      <td class="text-caption">{{ row.path }}</td>
                      <td class="text-caption">{{ row.type }}</td>
                      <td class="text-caption route-flow-editor__table-value">{{ row.value }}</td>
                    </tr>
                  </tbody>
                </v-table>
              </template>

              <template v-else>
                <pre class="route-flow-editor__json-preview route-flow-editor__json-preview--sample">{{ selectedNodeInspection.outputJson }}</pre>
              </template>
            </div>
          </v-sheet>
        </v-col>
      </v-row>

      <v-row v-if="!isFocusMode" class="mt-4 route-flow-editor__support-grid">
        <v-col cols="12" lg="5">
          <v-sheet class="route-flow-editor__side-panel pa-4" rounded="xl">
            <div class="route-flow-editor__panel-eyebrow">Flow signals</div>

            <v-alert
              v-if="errorMessage"
              class="mt-3"
              border="start"
              color="error"
              variant="tonal"
            >
              {{ errorMessage }}
            </v-alert>

            <v-alert
              v-if="flowResponseComparison?.matchesContract === false"
              class="mt-3"
              border="start"
              color="warning"
              variant="tonal"
            >
              Current <strong>Set Response</strong> sample differs from <code>response_schema</code>. The Test preview and
              the deployed live response will not match until you align them.
            </v-alert>

            <v-alert
              v-if="allValidationMessages.length > 0"
              class="mt-3"
              border="start"
              color="warning"
              variant="tonal"
            >
              <div class="font-weight-medium mb-2">Fix these flow issues before saving</div>
              <ul class="route-flow-editor__message-list">
                <li v-for="message in allValidationMessages" :key="message">{{ message }}</li>
              </ul>
            </v-alert>

            <v-alert
              v-else
              class="mt-3"
              border="start"
              color="success"
              variant="tonal"
            >
              The current live flow is structurally valid for this runtime slice.
            </v-alert>
          </v-sheet>
        </v-col>

        <v-col cols="12" lg="7">
          <v-sheet class="route-flow-editor__side-panel pa-4" rounded="xl">
            <div class="route-flow-editor__panel-eyebrow mb-3">Route paths</div>

            <div v-if="connectionSummaries.length === 0" class="text-body-2 text-medium-emphasis">
              No paths yet. Select a node, then click or drag a palette node to append it, or draw directly between the
              visible canvas ports.
            </div>

            <div v-else class="d-flex flex-column ga-2">
              <div
                v-for="connection in connectionSummaries"
                :key="connection.id"
                class="route-flow-editor__connection-row"
              >
                <div class="text-body-2">
                  <strong>{{ connection.source }}</strong>
                  <span v-if="connection.label" class="text-medium-emphasis"> via {{ connection.label }}</span>
                  <span class="text-medium-emphasis"> to </span>
                  <strong>{{ connection.target }}</strong>
                </div>
                <v-btn
                  color="error"
                  icon="mdi-close"
                  size="x-small"
                  variant="text"
                  @click="removeConnection(connection.id)"
                />
              </div>
            </div>
          </v-sheet>
        </v-col>

        <v-col cols="12">
          <v-expansion-panels
            v-model="isDesignerJsonOpen"
            class="route-flow-editor__json-panel"
            variant="accordion"
          >
            <v-expansion-panel :value="0" elevation="0">
              <v-expansion-panel-title>Designer JSON</v-expansion-panel-title>
              <v-expansion-panel-text>
                <pre class="route-flow-editor__json-preview">{{ flowDefinitionPreview }}</pre>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
        </v-col>
      </v-row>
    </div>
  </Teleport>
</template>

<style scoped>
.route-flow-editor {
  display: flex;
  flex-direction: column;
}

.route-flow-editor--focus {
  position: fixed;
  inset: calc(var(--v-layout-top, 76px) + 0.65rem) 0.65rem 0.65rem;
  z-index: 3000;
  overflow: hidden;
  padding: 0.7rem;
  border-radius: 28px;
  background:
    radial-gradient(circle at top left, rgba(198, 123, 66, 0.1), transparent 22%),
    radial-gradient(circle at top right, rgba(36, 90, 125, 0.14), transparent 22%),
    linear-gradient(180deg, rgba(10, 16, 28, 0.98), rgba(14, 22, 36, 0.98));
  box-shadow:
    0 28px 60px rgba(15, 23, 42, 0.36),
    inset 0 0 0 1px rgba(148, 163, 184, 0.12);
  backdrop-filter: blur(12px) saturate(120%);
}

.route-flow-editor__toolbar,
.route-flow-editor__detail-panel,
.route-flow-editor__side-panel {
  border: 1px solid rgba(148, 163, 184, 0.16);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent 100%),
    color-mix(in srgb, rgb(var(--v-theme-surface)) 95%, rgb(var(--v-theme-background)) 5%);
  box-shadow: 0 18px 34px rgba(15, 23, 42, 0.08);
}

.route-flow-editor__toolbar {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-top: 1.1rem !important;
}

.route-flow-editor__toolbar-head {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 1.25rem;
}

.route-flow-editor__toolbar-copy {
  max-width: 44rem;
}

.route-flow-editor__panel-eyebrow {
  color: rgb(var(--v-theme-secondary));
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.route-flow-editor__toolbar-title,
.route-flow-editor__detail-title {
  margin-top: 0.35rem;
  color: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 96%, transparent);
  font-size: 1.18rem;
  font-weight: 760;
  line-height: 1.2;
}

.route-flow-editor__toolbar-status {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.45rem;
  max-width: 34rem;
}

.route-flow-editor__toolbelt {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
}

.route-flow-editor__toolbelt--focus {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
}

.route-flow-editor__tool-btn {
  min-height: 2.4rem;
  text-transform: none;
}

.route-flow-editor__tool-btn--focus {
  min-height: 2.15rem;
  justify-content: flex-start;
  font-size: 0.78rem;
}

.route-flow-editor__toolbar-note {
  color: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 58%, transparent);
  font-size: 0.82rem;
  line-height: 1.5;
}

.route-flow-editor__canvas-shell {
  position: relative;
  height: 640px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 30px;
  overflow: hidden;
  overscroll-behavior: contain;
  background:
    radial-gradient(circle at top left, rgba(36, 90, 125, 0.1), transparent 34%),
    linear-gradient(180deg, color-mix(in srgb, rgb(var(--v-theme-surface)) 95%, rgb(var(--v-theme-background)) 5%), color-mix(in srgb, rgb(var(--v-theme-background)) 90%, rgb(var(--v-theme-surface)) 10%));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.route-flow-editor--focus .route-flow-editor__canvas-shell {
  height: 100%;
  border-radius: 24px;
  border-color: rgba(148, 163, 184, 0.12);
}

.route-flow-editor__canvas {
  width: 100%;
  height: 100%;
}

:deep(.route-flow-editor__focus-floater) {
  margin: 0.75rem;
  pointer-events: auto;
}

:deep(.route-flow-editor__focus-floater--palette) {
  width: min(16rem, calc(100vw - 2rem));
}

:deep(.route-flow-editor__focus-floater--info) {
  margin-top: 4.35rem;
  width: min(24rem, calc(100vw - 2rem));
}

:deep(.route-flow-editor__focus-floater--inspector-toggle) {
  margin-top: 0.75rem;
  margin-right: 0.75rem;
}

.route-flow-editor__focus-launcher,
.route-flow-editor__focus-node-launcher {
  min-height: 2.6rem;
  text-transform: none;
  box-shadow:
    0 14px 30px rgba(15, 23, 42, 0.18),
    inset 0 0 0 1px rgba(255, 255, 255, 0.04);
}

.route-flow-editor__focus-popover {
  margin-top: 0.7rem;
  padding: 0.95rem;
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent 100%),
    rgba(18, 27, 42, 0.94);
  box-shadow: 0 22px 40px rgba(15, 23, 42, 0.26);
  backdrop-filter: blur(14px) saturate(125%);
}

.route-flow-editor__focus-popover--palette {
  width: min(19rem, calc(100vw - 2rem));
}

.route-flow-editor__focus-popover--info {
  width: min(24rem, calc(100vw - 2rem));
  max-height: min(58vh, 31rem);
  overflow: auto;
}

.route-flow-editor__focus-title {
  margin-top: 0.35rem;
  color: rgba(248, 250, 252, 0.98);
  font-size: 0.98rem;
  font-weight: 760;
  line-height: 1.2;
}

.route-flow-editor__focus-copy,
.route-flow-editor__focus-help {
  color: rgba(226, 232, 240, 0.76);
  font-size: 0.76rem;
  line-height: 1.45;
}

.route-flow-editor__focus-copy {
  margin-top: 0.6rem;
}

.route-flow-editor__focus-copy--compact {
  margin-top: 0.45rem;
}

.route-flow-editor__focus-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.65rem;
}

.route-flow-editor__focus-help {
  margin-top: 0.85rem;
}

.route-flow-editor__focus-section-title {
  color: rgba(248, 250, 252, 0.9);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.route-flow-editor__focus-connection-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 11rem;
  overflow: auto;
  padding-right: 0.15rem;
}

.route-flow-editor__focus-toolbar {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.38rem;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 18px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), transparent 100%),
    rgba(15, 23, 42, 0.88);
  box-shadow: 0 18px 32px rgba(15, 23, 42, 0.22);
  backdrop-filter: blur(14px) saturate(125%);
}

.route-flow-editor__focus-signal-bar {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 0.75rem;
}

.route-flow-editor__focus-icon-btn {
  color: rgba(248, 250, 252, 0.92);
}

.route-flow-editor__focus-status-btn {
  min-width: 7.75rem;
  text-transform: none;
}

.route-flow-editor__focus-divider {
  width: 1px;
  height: 1.6rem;
  background: rgba(148, 163, 184, 0.22);
}

:deep(.route-flow-editor__select-menu) {
  z-index: 3600 !important;
}

:deep(.route-flow-editor__canvas .vue-flow__pane) {
  cursor: grab;
}

:deep(.route-flow-editor__canvas .vue-flow__pane.dragging) {
  cursor: grabbing;
}

:deep(.route-flow-editor__canvas .vue-flow__controls) {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.35rem;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), transparent 100%),
    rgba(15, 23, 42, 0.84);
  box-shadow: 0 16px 30px rgba(15, 23, 42, 0.16);
}

:deep(.route-flow-editor__canvas .vue-flow__controls-button) {
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 12px;
  background: rgba(30, 41, 59, 0.94);
  color: rgba(248, 250, 252, 0.92);
}

:deep(.route-flow-editor__canvas .vue-flow__edge-path) {
  stroke: color-mix(in srgb, rgb(var(--v-theme-primary)) 58%, rgb(var(--v-theme-secondary)) 42%);
  stroke-width: 2.1;
}

:deep(.route-flow-editor__canvas .vue-flow__edge-textbg) {
  fill: color-mix(in srgb, rgb(var(--v-theme-surface)) 96%, rgb(var(--v-theme-background)) 4%);
  stroke: rgba(148, 163, 184, 0.16);
}

:deep(.route-flow-editor__canvas .vue-flow__edge-text) {
  fill: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 72%, transparent);
  font-size: 11px;
  font-weight: 700;
}

.route-flow-editor__detail-grid--focus {
  position: absolute;
  top: auto;
  right: 0.75rem;
  bottom: 0.75rem;
  left: 0.75rem !important;
  width: auto !important;
  height: min(46vh, 31rem);
  margin: 0 !important;
  display: grid !important;
  grid-template-columns: minmax(16rem, 0.95fr) minmax(0, 1.4fr) minmax(16rem, 0.95fr);
  gap: 0.7rem;
  /* Keep the focus workbench above canvas hit-targets so inspector controls stay reliably clickable. */
  z-index: 3400;
  pointer-events: none;
}

.route-flow-editor__detail-grid--focus > .v-col {
  pointer-events: auto;
  padding: 0;
  min-height: 0;
}

.route-flow-editor__detail-grid--focus .route-flow-editor__inspector-column {
  height: 100%;
  min-width: 0;
  max-width: none;
}

.route-flow-editor__detail-grid--focus .route-flow-editor__inspector-column > * {
  pointer-events: auto;
}

.route-flow-editor__focus-side-column {
  height: 100%;
  min-height: 0;
  min-width: 0;
  max-width: none;
}

.route-flow-editor__detail-head--stacked {
  align-items: flex-start;
}

.route-flow-editor__detail-title--sm {
  font-size: 0.98rem;
}

.route-flow-editor__detail-panel--preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.route-flow-editor__preview-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  padding-right: 0.15rem;
  scrollbar-gutter: stable;
}

.route-flow-editor__preview-toggle {
  display: inline-flex;
}

.route-flow-editor__table-value {
  max-width: 16rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.route-flow-editor__detail-head {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 1rem;
}

.route-flow-editor__editor-grid {
  align-items: start;
}

.route-flow-editor__subpanel {
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 92%, rgb(var(--v-theme-background)) 8%);
}

.route-flow-editor--focus .route-flow-editor__detail-panel {
  height: 100%;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border-radius: 20px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent 100%),
    rgba(20, 29, 44, 0.94);
  backdrop-filter: blur(14px) saturate(125%);
}

.route-flow-editor--focus .route-flow-editor__detail-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  padding-right: 0.15rem;
  scrollbar-gutter: stable;
}

.route-flow-editor--focus .route-flow-editor__subpanel {
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent 100%),
    rgba(30, 41, 59, 0.72);
}

.route-flow-editor--focus .route-flow-editor__editor-grid > .v-col {
  flex: 0 0 100%;
  max-width: 100%;
}

.route-flow-editor__snippet-row {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.route-flow-editor__empty-state {
  display: inline-flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.85rem 1rem;
  border: 1px dashed rgba(148, 163, 184, 0.26);
  border-radius: 18px;
  color: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 68%, transparent);
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 88%, rgb(var(--v-theme-background)) 12%);
}

.route-flow-editor__connection-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.65rem 0.8rem;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 18px;
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 92%, rgb(var(--v-theme-background)) 8%);
}

.route-flow-editor__path-card {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0.62rem 0.72rem;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 16px;
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 93%, rgb(var(--v-theme-background)) 7%);
}

.route-flow-editor__path-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
}

.route-flow-editor__path-targets {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.route-flow-editor__path-target-button {
  justify-content: space-between;
  text-transform: none;
}

.route-flow-editor__sample-entry {
  padding: 0.8rem;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 18px;
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 94%, rgb(var(--v-theme-background)) 6%);
}

.route-flow-editor__support-grid {
  align-items: start;
}

.route-flow-editor__schema-section {
  padding: 0.8rem;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 18px;
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 94%, rgb(var(--v-theme-background)) 6%);
}

.route-flow-editor__schema-tree {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.route-flow-editor__schema-row {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  min-width: 0;
  padding-left: calc(var(--schema-depth, 0) * 0.9rem);
}

.route-flow-editor__schema-pill {
  flex: 0 0 auto;
  text-transform: none;
}

.route-flow-editor__schema-row-preview {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-flow-editor__json-preview {
  overflow-x: auto;
  margin: 0;
  padding: 1rem;
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.82);
  color: #f8fafc;
  font-size: 0.78rem;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.route-flow-editor__json-preview--sample {
  max-height: 14rem;
  overflow: auto;
  padding: 0.85rem 0.95rem;
}

.route-flow-editor__message-list {
  margin: 0;
  padding-left: 1.1rem;
}

:deep(.route-flow-editor__minimap) {
  margin-right: 0.75rem;
  margin-bottom: 0.75rem;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 16px;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.82);
  box-shadow: 0 16px 30px rgba(15, 23, 42, 0.22);
}

@media (max-width: 1279px) {
  .route-flow-editor__canvas-shell {
    height: 520px;
  }

  .route-flow-editor__detail-grid--focus {
    left: 0.55rem !important;
    right: 0.55rem;
    height: min(52vh, 31rem);
    grid-template-columns: minmax(13rem, 0.85fr) minmax(0, 1.35fr) minmax(13rem, 0.85fr);
  }
}

@media (max-width: 959px) {
  .route-flow-editor__toolbar-head,
  .route-flow-editor__detail-head {
    flex-direction: column;
  }

  .route-flow-editor__toolbar-status {
    justify-content: flex-start;
    max-width: none;
  }

  .route-flow-editor--focus {
    inset: calc(var(--v-layout-top, 76px) + 0.35rem) 0.35rem 0.35rem;
    padding: 0;
    border-radius: 22px;
  }

  :deep(.route-flow-editor__focus-floater) {
    margin: 0.5rem;
  }

  .route-flow-editor__focus-toolbar {
    gap: 0.25rem;
    padding: 0.3rem;
  }

  .route-flow-editor__focus-status-btn {
    min-width: auto;
    padding-inline: 0.65rem;
    font-size: 0.74rem;
  }

  .route-flow-editor__focus-popover--palette,
  .route-flow-editor__focus-popover--info {
    width: min(calc(100vw - 1rem), 18rem);
  }

  .route-flow-editor__detail-grid--focus {
    top: auto;
    left: 0.5rem;
    right: 0.5rem;
    bottom: 0.5rem;
    width: auto !important;
    height: min(58vh, 30rem);
    display: grid !important;
    grid-template-columns: 1fr;
  }

  .route-flow-editor__focus-side-column,
  .route-flow-editor__detail-grid--focus .route-flow-editor__inspector-column {
    max-width: 100%;
    margin-bottom: 0.6rem;
  }

  :deep(.route-flow-editor__minimap) {
    display: none;
  }
}
</style>
