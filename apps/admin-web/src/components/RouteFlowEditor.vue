<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
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
import {
  vPragmaticDraggable,
  vPragmaticDropTarget,
  type PragmaticDraggableBinding,
  type PragmaticDropTargetBinding,
} from "../utils/pragmaticDnd";
import {
  createRouteFlowPaletteDragPayload,
  getRouteFlowPaletteDragPayload,
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
type FlexibleConfigTarget = "ifLeft" | "ifRight" | "switchValue";
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

const props = withDefaults(
  defineProps<{
    modelValue: RouteFlowDefinition;
    errorMessage?: string | null;
    availableConnections?: Connection[];
    successStatusCode?: number;
  }>(),
  {
    errorMessage: null,
    availableConnections: () => [],
    successStatusCode: 200,
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: RouteFlowDefinition];
  "validation-change": [value: string | null];
  "focus-mode-change": [value: boolean];
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
const flowInstance = ref<VueFlowStore | null>(null);
const hasManualLayout = ref(false);
const isFocusMode = ref(false);
const isFocusPaletteOpen = ref(false);
const isFocusInfoOpen = ref(false);
const isFocusInspectorOpen = ref(false);
let previousBodyOverflow = "";

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
  return connection.is_active ? connection.name : `${connection.name} (inactive)`;
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
const httpConnectionOptions = computed(() =>
  props.availableConnections
    .filter((connection) => connection.connector_type === "http")
    .map((connection) => ({
      title: connectionOptionTitle(connection),
      value: connection.id,
    })),
);
const postgresConnectionOptions = computed(() =>
  props.availableConnections
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

  if (value) {
    isFocusInspectorOpen.value = false;
  }

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
  isFocusPaletteOpen.value = !isFocusPaletteOpen.value;
}

function toggleFocusInfo(): void {
  isFocusInfoOpen.value = !isFocusInfoOpen.value;
}

function toggleFocusInspector(): void {
  if (!selectedCanvasNode.value) {
    return;
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

function applyReferenceSnippet(target: ReferenceTarget, refPath: string): void {
  const snippet = JSON.stringify({ $ref: refPath }, null, 2);
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
    isFocusInspectorOpen.value = true;
    isFocusPaletteOpen.value = false;
  }
}

function clearSelection(): void {
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

function handleConnect(connection: VueFlowConnection): void {
  if (!connection.source || !connection.target) {
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
    }
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

  if (typeof document === "undefined") {
    return;
  }

  if (value) {
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return;
  }

  document.body.style.overflow = previousBodyOverflow;
});

onBeforeUnmount(() => {
  if (typeof document !== "undefined") {
    document.body.style.overflow = previousBodyOverflow;
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
              {{ isFocusMode ? "Add nodes and shape the route graph." : "Design the live API data flow as a node graph." }}
            </div>
            <div v-if="!isFocusMode" class="text-body-2 text-medium-emphasis">
              Keep the single <strong>API Trigger</strong> fixed, then route request data through logic, transforms,
              connectors, and response nodes. Contract design still lives in the separate <strong>Contract</strong> journey.
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
          Drag nodes from the palette onto the canvas, or click a palette node while another node is selected to append or
          connect it. Use the labeled branch ports on <strong>If</strong> and <strong>Switch</strong> to draw True, False,
          Case, and Default paths directly on the graph.
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
          fit-view-on-init
          :min-zoom="0.42"
          :max-zoom="1.75"
          :pan-on-drag="[1]"
          :prevent-scrolling="true"
          @connect="handleConnect"
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
        <v-col class="route-flow-editor__inspector-column" cols="12" :xl="isFocusMode ? 12 : 8">
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
                        ? "Quick node settings stay docked here."
                        : "Canvas nodes stay stable while the inspector holds the editing detail."
                      : "Nodes stay compact on the canvas; editing opens here once you pick the path you want to tune."
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

            <div v-if="selectedCanvasNode" class="d-flex flex-column ga-4 mt-4">
              <v-row class="route-flow-editor__editor-grid">
                <v-col cols="12" md="5">
                  <v-sheet class="route-flow-editor__subpanel pa-4" rounded="xl">
                    <div class="route-flow-editor__panel-eyebrow">Node basics</div>

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
                </v-col>

                <v-col cols="12" md="7">
                  <v-sheet class="route-flow-editor__subpanel pa-4" rounded="xl">
                    <div class="route-flow-editor__panel-eyebrow">Runtime behavior</div>

                    <template v-if="selectedCanvasNode.data.runtimeType === 'api_trigger'">
                      <v-alert class="mt-3" border="start" color="info" variant="tonal">
                        API Trigger is the only entrypoint in this designer. It always starts with the saved route method, path,
                        and request payload metadata.
                      </v-alert>
                    </template>

                    <template v-else-if="selectedCanvasNode.data.runtimeType === 'validate_request'">
                      <v-alert class="mt-3" border="start" color="info" variant="tonal">
                        Validate Request currently always enforces the saved contract. The future connector/runtime work can make
                        this richer, but today the backend still treats Contract as the source of truth.
                      </v-alert>
                      <v-text-field
                        class="mt-4"
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
                            label
                            size="small"
                            variant="outlined"
                            @click="applyReferenceSnippet('transform', snippet.value)"
                          >
                            {{ snippet.label }}
                          </v-chip>
                        </div>
                      </div>

                      <v-textarea
                        class="mt-3"
                        auto-grow
                        hint="Use JSON plus refs like {&quot;$ref&quot;:&quot;request.body&quot;} or {&quot;$ref&quot;:&quot;state.transform&quot;}."
                        label="Output template JSON"
                        persistent-hint
                        rows="11"
                        spellcheck="false"
                        :error-messages="transformOutputError ? [transformOutputError] : []"
                        :model-value="transformOutputText"
                        @update:model-value="handleTransformOutputInput(String($event ?? ''))"
                      />
                    </template>

                    <template v-else-if="selectedCanvasNode.data.runtimeType === 'if_condition'">
                      <v-alert class="mt-3" border="start" color="info" variant="tonal">
                        If evaluates the current route data and sends execution down a <code>True</code> or <code>False</code>
                        path. Use refs to compare request values or earlier node output.
                      </v-alert>

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

                      <div class="route-flow-editor__snippet-row mt-3">
                        <span class="text-caption text-medium-emphasis">Branch paths</span>
                        <div class="text-caption text-medium-emphasis mt-2">
                          Drag from the <strong>True</strong> and <strong>False</strong> ports on the node, or keep this node
                          selected and click or drop another palette node to create the next step.
                        </div>
                        <div class="d-flex flex-column ga-3 mt-2">
                          <div
                            v-for="connection in selectedNodeOutgoingConnections"
                            :key="connection.id"
                            class="route-flow-editor__branch-row"
                          >
                            <div class="text-body-2 font-weight-medium">{{ connection.targetLabel }}</div>
                            <v-select
                              :items="IF_BRANCH_OPTIONS"
                              item-title="title"
                              item-value="value"
                              label="Branch"
                              :model-value="connection.branch"
                              @update:model-value="updateIfBranchForEdge(connection.id, String($event ?? ''))"
                            />
                          </div>
                        </div>
                      </div>
                    </template>

                    <template v-else-if="selectedCanvasNode.data.runtimeType === 'switch'">
                      <v-alert class="mt-3" border="start" color="info" variant="tonal">
                        Switch picks a case based on the current route data. Give it one or more <code>Case</code> paths and
                        exactly one <code>Default</code> path.
                      </v-alert>

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

                      <div class="route-flow-editor__snippet-row mt-3">
                        <span class="text-caption text-medium-emphasis">Branch paths</span>
                        <div class="text-caption text-medium-emphasis mt-2">
                          Drag from the <strong>Case</strong> or <strong>Default</strong> ports on the node. Keep Switch
                          selected and add another node from the palette whenever you want another case path.
                        </div>
                        <div class="d-flex flex-column ga-3 mt-2">
                          <div
                            v-for="connection in selectedNodeOutgoingConnections"
                            :key="connection.id"
                            class="route-flow-editor__branch-row"
                          >
                            <div class="text-body-2 font-weight-medium">{{ connection.targetLabel }}</div>
                            <v-select
                              :items="SWITCH_BRANCH_OPTIONS"
                              item-title="title"
                              item-value="value"
                              label="Path type"
                              :model-value="connection.branch"
                              @update:model-value="updateSwitchBranchMode(connection.id, String($event ?? ''))"
                            />
                            <v-text-field
                              v-if="connection.branch === 'case'"
                              label="Case value"
                              :model-value="stringifyFlexibleValue(connection.caseValue)"
                              @update:model-value="updateSwitchCaseValue(connection.id, String($event ?? ''))"
                            />
                          </div>
                        </div>
                      </div>
                    </template>

                    <template v-else-if="selectedCanvasNode.data.runtimeType === 'http_request'">
                      <v-alert class="mt-3" border="start" color="info" variant="tonal">
                        HTTP Request calls an upstream URL through a saved shared connection. Path fields support inline tokens
                        like <code v-pre>{{request.path.deviceId}}</code>.
                      </v-alert>

                      <v-select
                        v-model="selectedNodeConnectionId"
                        class="mt-4"
                        :items="httpConnectionOptions"
                        clearable
                        label="HTTP connection"
                      />
                      <v-select
                        v-model="selectedNodeHttpMethod"
                        :items="HTTP_METHOD_OPTIONS"
                        label="Method"
                      />
                      <v-text-field
                        hint="Use a relative path such as /devices/{{request.path.deviceId}} or a full absolute URL."
                        label="Path or URL template"
                        persistent-hint
                        :model-value="httpPathText"
                        @update:model-value="handleHttpPathInput(String($event ?? ''))"
                      />
                      <v-text-field
                        v-model="selectedNodeTimeoutMs"
                        label="Timeout (ms)"
                      />
                      <v-textarea
                        class="mt-2"
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
                    </template>

                    <template v-else-if="selectedCanvasNode.data.runtimeType === 'postgres_query'">
                      <v-alert class="mt-3" border="start" color="info" variant="tonal">
                        Postgres Query is limited to a single read-only <code>SELECT</code> or <code>WITH</code> statement and
                        uses named parameters instead of raw string interpolation.
                      </v-alert>

                      <v-select
                        v-model="selectedNodeConnectionId"
                        class="mt-4"
                        :items="postgresConnectionOptions"
                        clearable
                        label="Postgres connection"
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
                    </template>

                    <template v-else-if="selectedCanvasNode.data.runtimeType === 'set_response'">
                      <v-text-field v-model="selectedNodeStatusCode" class="mt-3" label="Status code" />

                      <div class="route-flow-editor__snippet-row">
                        <span class="text-caption text-medium-emphasis">Quick refs</span>
                        <div class="d-flex flex-wrap ga-2">
                          <v-chip
                            v-for="snippet in responseReferenceSnippets"
                            :key="snippet.value"
                            label
                            size="small"
                            variant="outlined"
                            @click="applyReferenceSnippet('response', snippet.value)"
                          >
                            {{ snippet.label }}
                          </v-chip>
                        </div>
                      </div>

                      <v-textarea
                        class="mt-3"
                        auto-grow
                        hint="Response bodies can be fixed JSON or ref-driven JSON such as {&quot;$ref&quot;:&quot;state.transform&quot;}."
                        label="Response body JSON"
                        persistent-hint
                        rows="11"
                        spellcheck="false"
                        :error-messages="responseBodyError ? [responseBodyError] : []"
                        :model-value="responseBodyText"
                        @update:model-value="handleResponseBodyInput(String($event ?? ''))"
                      />
                    </template>

                    <template v-else-if="selectedCanvasNode.data.runtimeType === 'error_response'">
                      <v-text-field v-model="selectedNodeStatusCode" class="mt-3" label="Error response status" />

                      <div class="route-flow-editor__snippet-row">
                        <span class="text-caption text-medium-emphasis">Quick refs</span>
                        <div class="d-flex flex-wrap ga-2">
                          <v-chip
                            v-for="snippet in ERROR_REFERENCE_SNIPPETS"
                            :key="snippet.value"
                            label
                            size="small"
                            variant="outlined"
                            @click="applyReferenceSnippet('error', snippet.value)"
                          >
                            {{ snippet.label }}
                          </v-chip>
                        </div>
                      </div>

                      <v-textarea
                        class="mt-3"
                        auto-grow
                        hint="Returned when Validate Request fails, or when any other flow path explicitly routes into Error Response."
                        label="Error response body JSON"
                        persistent-hint
                        rows="11"
                        spellcheck="false"
                        :error-messages="errorBodyError ? [errorBodyError] : []"
                        :model-value="errorBodyText"
                        @update:model-value="handleErrorBodyInput(String($event ?? ''))"
                      />
                    </template>
                  </v-sheet>
                </v-col>
              </v-row>
            </div>

            <div v-else class="route-flow-editor__empty-state mt-4">
              <v-icon icon="mdi-cursor-default-click-outline" size="22" />
              <span>Select a node on the canvas to open its editing dock.</span>
            </div>
          </v-sheet>
        </v-col>

        <v-col v-if="!isFocusMode" cols="12" xl="4">
          <div class="d-flex flex-column ga-4">
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
          </div>
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
  top: 4.8rem;
  right: 0.75rem;
  bottom: 0.75rem;
  left: auto !important;
  width: 20.75rem !important;
  margin: 0 !important;
  display: block !important;
  z-index: 4;
  pointer-events: none;
}

.route-flow-editor__detail-grid--focus .route-flow-editor__inspector-column {
  height: 100%;
  padding: 0;
  width: 100%;
  max-width: 100%;
  flex: 0 0 100%;
}

.route-flow-editor__detail-grid--focus .route-flow-editor__inspector-column > * {
  pointer-events: auto;
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
  overflow: auto;
  border-radius: 20px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent 100%),
    rgba(20, 29, 44, 0.94);
  backdrop-filter: blur(14px) saturate(125%);
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
  gap: 0.55rem;
}

.route-flow-editor__branch-row {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  padding: 0.8rem;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 18px;
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 94%, rgb(var(--v-theme-background)) 6%);
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
    width: 19rem;
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
    width: auto;
    height: min(56vh, 34rem);
  }

  :deep(.route-flow-editor__minimap) {
    display: none;
  }
}
</style>
