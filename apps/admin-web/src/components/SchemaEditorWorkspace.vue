<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch, type ComponentPublicInstance } from "vue";
import { useRouter } from "vue-router";
import { AdminApiError, previewResponse } from "../api/admin";
import SchemaNodeCard from "./SchemaNodeCard.vue";
import { copyText } from "../utils/clipboard";
import { useAuth } from "../composables/useAuth";
import { highlightJson } from "../utils/jsonHighlight";
import {
  vPragmaticDraggable,
  type PragmaticDraggableBinding,
} from "../utils/pragmaticDnd";
import {
  createSchemaModePaletteDragPayload,
  createSchemaNodePaletteDragPayload,
  createSchemaPathParameterDragPayload,
  createSchemaValuePaletteDragPayload,
  getSchemaDragPayload,
  type SchemaDragPayload,
} from "../utils/schemaDragDrop";
import {
  buildDefaultParameterValue,
  createRequestParameterDefinition,
  parseOptionalNumberInput,
  type RequestParameterDefinition,
} from "../utils/requestSchema";
import {
  GENERATOR_OPTIONS,
  PALETTE_TYPES,
  addNodeToContainer,
  applyPathParameter,
  applyValueType,
  canAcceptChildren,
  deleteNode,
  duplicateNode,
  findNode,
  insertNewNodeBeforeSibling,
  insertNewNodeAfterSibling,
  isScalarNode,
  moveNodeBeforeSibling,
  moveNodeToContainer,
  nodeLabel,
  resetNodeType,
  schemaToTree,
  treeToSchema,
  updateNode,
  validateTree,
  valueTypeLabel,
  type BuilderNodeType,
  type BuilderScope,
  type GeneratorOption,
  type MockMode,
  type SchemaBuilderNode,
} from "../schemaBuilder";
import type { JsonObject, JsonValue } from "../types/endpoints";
import {
  buildSampleRequestBody,
  collectRequestBodyTemplatePaths,
  validateResponseTemplate,
} from "../utils/responseTemplates";

const props = defineProps<{
  pathParameters?: Array<RequestParameterDefinition | string>;
  queryParameters?: RequestParameterDefinition[];
  requestBodySchema?: JsonObject;
  schema: JsonObject;
  scope: BuilderScope;
  seedKey?: string;
}>();

const emit = defineEmits<{
  "update:schema": [schema: JsonObject];
  "update:seedKey": [seedKey: string];
}>();

const auth = useAuth();
const router = useRouter();

const rootShapeOptions = [
  { title: "Object", value: "object" },
  { title: "Array", value: "array" },
  { title: "String", value: "string" },
  { title: "Enum", value: "enum" },
  { title: "Integer", value: "integer" },
  { title: "Number", value: "number" },
  { title: "Boolean", value: "boolean" },
] as const;

const modeOptions = [
  { title: "True random", value: "generate" },
  { title: "Mocking random", value: "mocking" },
  { title: "Static", value: "fixed" },
];
const behaviorPalette = [
  { value: "generate", label: "Random", icon: "mdi-shuffle-variant" },
  { value: "mocking", label: "Mocking", icon: "mdi-auto-fix" },
  { value: "fixed", label: "Static", icon: "mdi-lock-outline" },
] as const;
const paletteIconByType: Record<BuilderNodeType, string> = {
  array: "mdi-code-brackets",
  boolean: "mdi-toggle-switch-outline",
  enum: "mdi-format-list-bulleted-square",
  integer: "mdi-pound",
  number: "mdi-decimal",
  object: "mdi-code-braces",
  string: "mdi-format-letter-case",
};
const paletteOptions = PALETTE_TYPES.map((item) => ({
  ...item,
  icon: paletteIconByType[item.type],
}));
const valueTypeIconByType: Record<string, string> = {
  text: "mdi-text-box-outline",
  long_text: "mdi-text-long",
  id: "mdi-identifier",
  username: "mdi-account-circle-outline",
  password: "mdi-form-textbox-password",
  keyboard_key: "mdi-keyboard-outline",
  verb: "mdi-console",
  email: "mdi-email-outline",
  url: "mdi-link-variant",
  slug: "mdi-tag-outline",
  file_name: "mdi-file-outline",
  mime_type: "mdi-file-code-outline",
  date: "mdi-calendar-blank-outline",
  datetime: "mdi-calendar-clock-outline",
  time: "mdi-clock-time-four-outline",
  first_name: "mdi-account-outline",
  last_name: "mdi-account-box-outline",
  name: "mdi-badge-account-outline",
  company: "mdi-office-building-outline",
  phone: "mdi-phone-outline",
  street_address: "mdi-home-map-marker",
  city: "mdi-city-variant-outline",
  state: "mdi-map-marker-outline",
  country: "mdi-earth",
  postal_code: "mdi-mailbox-outline",
  avatar_url: "mdi-image-outline",
  integer: "mdi-pound",
  number: "mdi-decimal",
  boolean: "mdi-toggle-switch-outline",
  price: "mdi-cash-multiple",
  enum: "mdi-format-list-bulleted-square",
};

type ValuePaletteSection = { items: Array<GeneratorOption & { icon: string }>; label: string };
type ValuePaletteDefinition = { label: string; values?: string[]; types?: BuilderNodeType[] };

const valuePaletteDefinitions: ValuePaletteDefinition[] = [
  {
    label: "Identity",
    values: ["text", "long_text", "id", "username", "password", "email", "first_name", "last_name", "name", "company", "avatar_url"],
  },
  {
    label: "Web & time",
    values: ["url", "slug", "date", "datetime", "time"],
  },
  {
    label: "Location & contact",
    values: ["phone", "street_address", "city", "state", "country", "postal_code"],
  },
  {
    label: "System",
    values: ["keyboard_key", "verb", "file_name", "mime_type"],
  },
  {
    label: "Numeric",
    types: ["integer", "number"],
  },
  {
    label: "Discrete",
    types: ["boolean", "enum"],
  },
];

const tree = shallowRef<SchemaBuilderNode>(schemaToTree(props.schema, props.scope));
const selectedNodeId = ref(tree.value.id);
const collapsedNodeIds = ref<string[]>([]);
const importDialog = ref(false);
const importError = ref<string | null>(null);
const importText = ref("");
const previewStatus = ref<"idle" | "loading" | "success" | "error">("idle");
const previewBody = ref("");
const previewError = ref<string | null>(null);
const previewPathParameters = ref<Record<string, string>>({});
const previewQueryParameters = ref<Record<string, string>>({});
const previewRequestBodyDraft = ref("");
const fixedJsonDraft = ref("");
const fixedJsonError = ref<string | null>(null);
const responseRailTab = ref<"preview" | "schema">("preview");
const templateTextareaRef = ref<ComponentPublicInstance | null>(null);
let previewTimer: number | null = null;
const schemaCopyState = ref<"idle" | "copied" | "failed">("idle");
const previewCopyState = ref<"idle" | "copied" | "failed">("idle");
let schemaCopyTimer: number | null = null;
let previewCopyTimer: number | null = null;
let lastGeneratedPreviewBody = "";

const serializedIncomingSchema = computed(() => JSON.stringify(props.schema ?? {}));
const normalizedSeedKey = computed(() => {
  const trimmed = props.seedKey?.trim() ?? "";
  return trimmed ? trimmed : null;
});
const schemaJsonText = computed(() => JSON.stringify(liveSchema.value, null, 2));
const previewPaneText = computed(() => responseRailTab.value === "preview" ? (previewBody.value || "{}") : schemaJsonText.value);
const highlightedPreviewBody = computed(() => highlightJson(previewBody.value || "{}"));
const highlightedSchemaBody = computed(() => highlightJson(liveSchema.value));
const schemaCopyLabel = computed(() => {
  if (schemaCopyState.value === "copied") {
    return "Copied";
  }

  if (schemaCopyState.value === "failed") {
    return "Copy failed";
  }

  return "Copy JSON";
});
const previewCopyLabel = computed(() => {
  if (previewCopyState.value === "copied") {
    return "Copied";
  }

  if (previewCopyState.value === "failed") {
    return "Copy failed";
  }

  return responseRailTab.value === "preview" ? "Copy sample" : "Copy schema";
});

const liveSchema = ref<JsonObject>({});
const selectedNode = shallowRef<SchemaBuilderNode>(tree.value);
const selectedParent = shallowRef<SchemaBuilderNode | null>(null);
const responsePathParameters = computed<RequestParameterDefinition[]>(() => {
  if (props.scope !== "response") {
    return [];
  }

  const seen = new Set<string>();

  return (props.pathParameters ?? []).reduce<RequestParameterDefinition[]>((accumulator, parameter, index) => {
    const normalized = typeof parameter === "string"
      ? createRequestParameterDefinition("path", {
          hasExplicitSchema: false,
          id: `path-${parameter}-${index}`,
          name: parameter,
          required: true,
        })
      : {
          ...parameter,
          hasExplicitSchema: parameter.hasExplicitSchema ?? true,
          id: parameter.id || `path-${parameter.name}-${index}`,
          required: true,
        };
    const trimmedName = normalized.name.trim();
    if (!trimmedName || seen.has(trimmedName)) {
      return accumulator;
    }

    seen.add(trimmedName);
    accumulator.push({
      ...normalized,
      name: trimmedName,
      required: true,
    });
    return accumulator;
  }, []);
});
const responsePathParameterNames = computed(() => responsePathParameters.value.map((parameter) => parameter.name));
const requestQueryParameters = computed<RequestParameterDefinition[]>(() => props.queryParameters ?? []);
const requestBodyTemplatePaths = computed(() => collectRequestBodyTemplatePaths(props.requestBodySchema));
const hasPreviewRequestBody = computed(() => Boolean(props.requestBodySchema && Object.keys(props.requestBodySchema).length > 0));
const hasPreviewInputs = computed(() =>
  responsePathParameters.value.length > 0 || requestQueryParameters.value.length > 0 || hasPreviewRequestBody.value,
);
const hasRouteValuePalette = computed(() =>
  props.scope === "response" && (responsePathParameters.value.length > 0 || requestQueryParameters.value.length > 0),
);
const previewRequestBodyValidationMessage = computed(() => {
  if (!hasPreviewRequestBody.value || !previewRequestBodyDraft.value.trim()) {
    return null;
  }

  try {
    JSON.parse(previewRequestBodyDraft.value);
    return null;
  } catch {
    return "Use valid JSON to populate request.body.* template tokens.";
  }
});
const selectedIsRoot = computed(() => selectedNode.value.id === tree.value.id);
const selectedShowsQuickAdd = computed(() => selectedNode.value.type === "object");
const selectedShowsItemShape = computed(() => selectedNode.value.type === "array");
const selectedHasValueLane = computed(() => props.scope === "response" && isScalarNode(selectedNode.value));
const selectedUsesPathParameter = computed(() => selectedHasValueLane.value && Boolean(selectedNode.value.parameterSource));
const selectedSupportsTemplate = computed(() => props.scope === "response" && selectedNode.value.type === "string");
const selectedTemplateEnabled = computed(() => selectedSupportsTemplate.value && Boolean(selectedNode.value.template.trim()));
const selectedTemplateError = computed(() => {
  if (!selectedSupportsTemplate.value) {
    return null;
  }

  return validateResponseTemplate(selectedNode.value.template, {
    pathParameterNames: responsePathParameterNames.value,
  });
});
const routeValuesHint = computed(() => {
  if (selectedUsesPathParameter.value) {
    return selectedNode.value.parameterSource;
  }

  if (requestQueryParameters.value.length > 0) {
    return selectedSupportsTemplate.value
      ? "Path values link directly. Query values insert template tokens."
      : "Path values link directly. Select a string field to use query values in a template.";
  }

  return "Link a field to a path parameter";
});
const templateHelperGroups = computed(() => {
  if (!selectedSupportsTemplate.value) {
    return [];
  }

  const groups: Array<{ items: Array<{ label: string; token: string }>; label: string }> = [
    {
      label: "Base value",
      items: [{ label: "value", token: "{{value}}" }],
    },
  ];

  if (responsePathParameters.value.length > 0) {
    groups.push({
      label: "Path params",
      items: responsePathParameters.value.map((parameter) => ({
        label: parameter.name,
        token: `{{request.path.${parameter.name}}}`,
      })),
    });
  }

  if (requestQueryParameters.value.length > 0) {
    groups.push({
      label: "Query params",
      items: requestQueryParameters.value.map((parameter) => ({
        label: parameter.name,
        token: `{{request.query.${parameter.name}}}`,
      })),
    });
  }

  if (requestBodyTemplatePaths.value.length > 0) {
    groups.push({
      label: "Request body",
      items: requestBodyTemplatePaths.value.map((path) => ({
        label: path,
        token: `{{request.body.${path}}}`,
      })),
    });
  }

  return groups;
});
const selectedNodeLabel = computed(() => nodeLabel(selectedNode.value, selectedIsRoot.value));
const selectedPath = computed(() => {
  const path = findNodePath(tree.value, selectedNodeId.value) ?? [tree.value];
  return path.map((node, index) => nodeLabel(node, index === 0)).join(" / ");
});
const totalFieldCount = computed(() => countFields(tree.value, true));
const canvasTitle = computed(() => props.scope === "response" ? "Response schema" : "Request");
const canvasSubtitle = computed(() => props.scope === "response" ? "Add, group, and reorder response fields." : "Define the request JSON body.");
const rootContractLabel = computed(() => {
  if (tree.value.type === "object") {
    const fieldCount = tree.value.children.length;
    return fieldCount === 1 ? "1 top-level field" : `${fieldCount} top-level fields`;
  }

  if (tree.value.type === "array") {
    return "One repeated item shape";
  }

  return "Single value";
});
const showValueTypeSelector = computed(() => {
  if (!selectedHasValueLane.value || selectedNode.value.mode === "fixed" || selectedUsesPathParameter.value) {
    return false;
  }

  return availableGenerators.value.length > 1;
});
const editableSeedKey = computed({
  get: () => props.seedKey ?? "",
  set: (value: string | null) => emit("update:seedKey", String(value ?? "")),
});
const selectedValueType = computed(() => selectedHasValueLane.value ? selectedNode.value.generator : null);
const selectedValueTypeLabel = computed(() => {
  if (!selectedHasValueLane.value) {
    return null;
  }

  if (selectedNode.value.parameterSource) {
    return selectedNode.value.parameterSource;
  }

  return selectedNode.value.mode === "fixed" ? "Fixed value" : valueTypeLabel(selectedNode.value.generator);
});
const availableGenerators = computed(() => {
  const type = selectedNode.value.type;
  return GENERATOR_OPTIONS.filter((option) => option.types.includes(type));
});
const valuePaletteSections = computed<ValuePaletteSection[]>(() => {
  const withIcons = GENERATOR_OPTIONS.map((option) => ({
    ...option,
    icon: valueTypeIconByType[option.value] ?? "mdi-shape-outline",
  }));

  return valuePaletteDefinitions
    .map((section) => {
      const items = section.values
        ? section.values
            .map((value) => withIcons.find((option) => option.value === value) ?? null)
            .filter((option): option is GeneratorOption & { icon: string } => Boolean(option))
        : withIcons.filter((option) => section.types?.some((type) => option.types.includes(type)));

      return {
        label: section.label,
        items,
      };
    })
    .filter((section) => section.items.length > 0);
});

function syncPreviewParameterValues(
  parameters: RequestParameterDefinition[],
  currentValues: Record<string, string>,
  getDefaultValue: (parameter: RequestParameterDefinition) => string,
): Record<string, string> {
  return parameters.reduce<Record<string, string>>((accumulator, parameter) => {
    accumulator[parameter.name] = currentValues[parameter.name] ?? getDefaultValue(parameter);
    return accumulator;
  }, {});
}

function queuePreview(): void {
  if (props.scope !== "response") {
    return;
  }

  if (previewTimer) {
    window.clearTimeout(previewTimer);
  }

  previewTimer = window.setTimeout(() => {
    void runPreview();
  }, 350);
}

function toSchemaSnapshot(nextTree: SchemaBuilderNode): JsonObject {
  return treeToSchema(nextTree, props.scope) as JsonObject;
}

liveSchema.value = toSchemaSnapshot(tree.value);

watch(
  serializedIncomingSchema,
  (serialized) => {
    const current = JSON.stringify(liveSchema.value);
    if (serialized === current) {
      return;
    }

    tree.value = schemaToTree(props.schema, props.scope);
    liveSchema.value = toSchemaSnapshot(tree.value);
    selectedNodeId.value = tree.value.id;
  },
  { immediate: true },
);

watch(
  [tree, selectedNodeId],
  () => {
    selectedNode.value = findNode(tree.value, selectedNodeId.value) ?? tree.value;
    selectedParent.value = findParentNode(tree.value, selectedNodeId.value);
  },
  { immediate: true },
);

watch(
  tree,
  (nextTree) => {
    const validNodeIds = new Set(collectNodeIds(nextTree));
    collapsedNodeIds.value = collapsedNodeIds.value.filter((nodeId) => validNodeIds.has(nodeId));
  },
  { immediate: true },
);

watch(
  selectedNodeId,
  (nodeId) => {
    const path = findNodePath(tree.value, nodeId) ?? [];
    const ancestorIds = new Set(path.slice(0, -1).map((node) => node.id));
    collapsedNodeIds.value = collapsedNodeIds.value.filter((collapsedId) => !ancestorIds.has(collapsedId));
  },
  { immediate: true },
);

watch(
  responsePathParameters,
  (parameters) => {
    previewPathParameters.value = syncPreviewParameterValues(
      parameters,
      previewPathParameters.value,
      buildDefaultParameterValue,
    );
  },
  { immediate: true },
);

watch(
  requestQueryParameters,
  (parameters) => {
    previewQueryParameters.value = syncPreviewParameterValues(
      parameters,
      previewQueryParameters.value,
      () => "",
    );
  },
  { immediate: true },
);

watch(
  () => JSON.stringify(props.requestBodySchema ?? {}),
  () => {
    const sample = buildSampleRequestBody(props.requestBodySchema);
    const nextBodyText = sample == null ? "" : JSON.stringify(sample, null, 2);
    if (!previewRequestBodyDraft.value.trim() || previewRequestBodyDraft.value === lastGeneratedPreviewBody) {
      previewRequestBodyDraft.value = nextBodyText;
    }
    lastGeneratedPreviewBody = nextBodyText;
  },
  { immediate: true },
);

watch(
  () => [selectedNode.value.id, selectedNode.value.mode, selectedNode.value.fixedValue],
  () => {
    if (selectedNode.value.type === "object" || selectedNode.value.type === "array") {
      fixedJsonDraft.value = JSON.stringify(selectedNode.value.fixedValue, null, 2);
    } else {
      fixedJsonDraft.value = "";
    }

    fixedJsonError.value = null;
  },
  { immediate: true, deep: true },
);

watch(
  () => JSON.stringify(liveSchema.value),
  () => queuePreview(),
  { immediate: true },
);

watch(
  () => JSON.stringify({
    body: previewRequestBodyDraft.value,
    path: previewPathParameters.value,
    query: previewQueryParameters.value,
  }),
  () => queuePreview(),
);

watch(normalizedSeedKey, () => queuePreview());

function findParentNode(root: SchemaBuilderNode, targetId: string, parent: SchemaBuilderNode | null = null): SchemaBuilderNode | null {
  if (root.id === targetId) {
    return parent;
  }

  for (const child of root.children) {
    const result = findParentNode(child, targetId, root);
    if (result) {
      return result;
    }
  }

  if (root.item) {
    const result = findParentNode(root.item, targetId, root);
    if (result) {
      return result;
    }
  }

  return null;
}

function findNodePath(
  root: SchemaBuilderNode,
  targetId: string,
  trail: SchemaBuilderNode[] = [],
): SchemaBuilderNode[] | null {
  const nextTrail = [...trail, root];
  if (root.id === targetId) {
    return nextTrail;
  }

  for (const child of root.children) {
    const result = findNodePath(child, targetId, nextTrail);
    if (result) {
      return result;
    }
  }

  if (root.item) {
    const result = findNodePath(root.item, targetId, nextTrail);
    if (result) {
      return result;
    }
  }

  return null;
}

function collectNodeIds(root: SchemaBuilderNode): string[] {
  const ids = [root.id];

  for (const child of root.children) {
    ids.push(...collectNodeIds(child));
  }

  if (root.item) {
    ids.push(...collectNodeIds(root.item));
  }

  return ids;
}

function nodeContains(root: SchemaBuilderNode, targetId: string): boolean {
  return Boolean(findNodePath(root, targetId));
}

function countFields(node: SchemaBuilderNode, root = false): number {
  const selfCount = root ? 0 : 1;
  return selfCount + node.children.reduce((total, child) => total + countFields(child), 0) + (node.item ? countFields(node.item) : 0);
}

function scheduleCopyStateReset(target: "schema" | "preview"): void {
  const timer = target === "schema" ? schemaCopyTimer : previewCopyTimer;
  if (timer) {
    window.clearTimeout(timer);
  }

  const resetTimer = window.setTimeout(() => {
    if (target === "schema") {
      schemaCopyState.value = "idle";
      schemaCopyTimer = null;
    } else {
      previewCopyState.value = "idle";
      previewCopyTimer = null;
    }
  }, 1600);

  if (target === "schema") {
    schemaCopyTimer = resetTimer;
  } else {
    previewCopyTimer = resetTimer;
  }
}

function setCopyState(target: "schema" | "preview", copied: boolean): void {
  if (target === "schema") {
    schemaCopyState.value = copied ? "copied" : "failed";
  } else {
    previewCopyState.value = copied ? "copied" : "failed";
  }

  scheduleCopyStateReset(target);
}

function commitTree(nextTree: SchemaBuilderNode): void {
  tree.value = nextTree;
  liveSchema.value = toSchemaSnapshot(nextTree);

  if (!findNode(nextTree, selectedNodeId.value)) {
    selectedNodeId.value = nextTree.id;
  }

  emit("update:schema", liveSchema.value);
}

function setDragSourceActive(element: HTMLElement, active: boolean): void {
  element.classList.toggle("schema-drag-source", active);
}

function createDragBinding(
  data: SchemaDragPayload,
  preview: {
    eyebrow?: string;
    label: string;
    tone: "mode" | "node" | "value";
  },
): PragmaticDraggableBinding<Record<string, unknown>> {
  return {
    data: data as unknown as Record<string, unknown>,
    preview,
    onDragStart: ({ element }) => {
      setDragSourceActive(element, true);
    },
    onDrop: ({ element }) => {
      setDragSourceActive(element, false);
    },
  };
}

function nodePaletteDragBinding(nodeType: BuilderNodeType): PragmaticDraggableBinding<Record<string, unknown>> {
  return createDragBinding(createSchemaNodePaletteDragPayload(nodeType), {
    eyebrow: "Node",
    label: paletteOptions.find((item) => item.type === nodeType)?.label ?? nodeType,
    tone: "node",
  });
}

function valuePaletteDragBinding(valueType: string): PragmaticDraggableBinding<Record<string, unknown>> {
  return createDragBinding(createSchemaValuePaletteDragPayload(valueType), {
    eyebrow: "Value",
    label: valueTypeLabel(valueType),
    tone: "value",
  });
}

function pathParameterDragBinding(parameter: RequestParameterDefinition): PragmaticDraggableBinding<Record<string, unknown>> {
  return createDragBinding(createSchemaPathParameterDragPayload(parameter), {
    eyebrow: "Route",
    label: parameter.name,
    tone: "value",
  });
}

function modePaletteDragBinding(mode: MockMode): PragmaticDraggableBinding<Record<string, unknown>> {
  return createDragBinding(createSchemaModePaletteDragPayload(mode), {
    eyebrow: "Behavior",
    label: behaviorPalette.find((item) => item.value === mode)?.label ?? mode,
    tone: "mode",
  });
}

function addNodeFromPalette(nodeType: BuilderNodeType): void {
  const currentNode = selectedNode.value;
  const parentNode = selectedParent.value;

  if (canAcceptChildren(currentNode)) {
    commitTree(addNodeToContainer(tree.value, currentNode.id, nodeType, props.scope));
    return;
  }

  if (parentNode?.type === "object") {
    commitTree(insertNewNodeAfterSibling(tree.value, currentNode.id, nodeType, props.scope));
    return;
  }

  commitTree(addNodeToContainer(tree.value, tree.value.id, nodeType, props.scope));
}

function applyValueTypeFromPalette(valueType: string): void {
  if (!selectedHasValueLane.value) {
    return;
  }

  commitTree(applyValueType(tree.value, selectedNode.value.id, valueType, props.scope));
}

function applyPathParameterFromPalette(parameter: RequestParameterDefinition): void {
  if (!selectedHasValueLane.value) {
    return;
  }

  commitTree(applyPathParameter(tree.value, selectedNode.value.id, parameter, props.scope));
}

function queryParameterToken(parameterName: string): string {
  return `{{request.query.${parameterName}}}`;
}

function queryParameterChipActive(parameterName: string): boolean {
  return selectedSupportsTemplate.value && selectedNode.value.template.includes(queryParameterToken(parameterName));
}

async function insertQueryParameterToken(parameter: RequestParameterDefinition): Promise<void> {
  if (!selectedSupportsTemplate.value) {
    return;
  }

  await insertTemplateToken(queryParameterToken(parameter.name));
}

function applyModeToNode(nodeId: string, mode: MockMode): void {
  if (props.scope !== "response") {
    return;
  }

  commitTree(updateNode(tree.value, nodeId, (node) => ({
    ...node,
    mode,
    parameterSource: null,
  })));
}

function handleDropOnContainer(containerId: string, sourceData: unknown): void {
  const payload = getSchemaDragPayload(sourceData);
  if (!payload) {
    return;
  }

  if (payload.kind === "node-palette") {
    commitTree(addNodeToContainer(tree.value, containerId, payload.nodeType, props.scope));
  } else {
    if (payload.kind === "node") {
      commitTree(moveNodeToContainer(tree.value, payload.nodeId, containerId));
    }
  }
}

function handleDropBeforeRow(nodeId: string, sourceData: unknown): void {
  const payload = getSchemaDragPayload(sourceData);
  if (!payload) {
    return;
  }

  if (payload.kind === "node-palette") {
    commitTree(insertNewNodeBeforeSibling(tree.value, nodeId, payload.nodeType, props.scope));
  } else {
    if (payload.kind === "node") {
      commitTree(moveNodeBeforeSibling(tree.value, payload.nodeId, nodeId));
    }
  }
}

function insertNodeFromMenu(targetId: string, placement: "before" | "container", nodeType: BuilderNodeType): void {
  if (placement === "before") {
    commitTree(insertNewNodeBeforeSibling(tree.value, targetId, nodeType, props.scope));
    return;
  }

  commitTree(addNodeToContainer(tree.value, targetId, nodeType, props.scope));
}

function toggleNodeCollapsed(nodeId: string): void {
  const isCollapsed = collapsedNodeIds.value.includes(nodeId);
  if (isCollapsed) {
    collapsedNodeIds.value = collapsedNodeIds.value.filter((collapsedId) => collapsedId !== nodeId);
    return;
  }

  if (selectedNodeId.value !== nodeId) {
    const node = findNode(tree.value, nodeId);
    if (node && nodeContains(node, selectedNodeId.value)) {
      selectedNodeId.value = nodeId;
    }
  }

  collapsedNodeIds.value = [...collapsedNodeIds.value, nodeId];
}

function handleDropOnValue(nodeId: string, sourceData: unknown): void {
  const payload = getSchemaDragPayload(sourceData);
  if (!payload) {
    return;
  }

  if (payload.kind === "path-parameter") {
    commitTree(applyPathParameter(tree.value, nodeId, payload.parameter, props.scope));
  } else if (payload.kind === "value-palette") {
    commitTree(applyValueType(tree.value, nodeId, payload.valueType, props.scope));
  } else if (payload.kind === "mode-palette") {
    applyModeToNode(nodeId, payload.mode);
  }
}

function updateSelectedNode(
  updater: (node: SchemaBuilderNode, parent: SchemaBuilderNode | null) => SchemaBuilderNode,
): void {
  commitTree(updateNode(tree.value, selectedNode.value.id, updater));
}

function updateStructuredFixedValue(rawValue: string): void {
  fixedJsonDraft.value = rawValue;

  try {
    const parsed = JSON.parse(rawValue) as JsonValue;
    updateSelectedNode((node) => ({
      ...node,
      fixedValue: parsed,
    }));
    fixedJsonError.value = null;
  } catch {
    fixedJsonError.value = "Use valid JSON for fixed object and array values.";
  }
}

function updateEnumValues(rawValue: string): void {
  const enumValues = rawValue
    .split(/\r?\n|,/)
    .map((value) => value.trim())
    .filter(Boolean);

  updateSelectedNode((node) => ({
    ...node,
    enumValues,
  }));
}

function updateSelectedValueType(rawValue: unknown): void {
  const valueType = String(rawValue ?? "").trim() || null;
  if (!valueType) {
    return;
  }

  commitTree(applyValueType(tree.value, selectedNode.value.id, valueType, props.scope));
}

function resolveTemplateTextarea(): HTMLTextAreaElement | null {
  const root = templateTextareaRef.value?.$el;
  if (!(root instanceof HTMLElement)) {
    return null;
  }

  return root.querySelector("textarea");
}

function updateSelectedTemplate(value: string): void {
  updateSelectedNode((node) => ({
    ...node,
    template: value,
  }));
}

function setTemplateEnabled(enabled: boolean): void {
  updateSelectedNode((node) => ({
    ...node,
    template: enabled ? (node.template.trim() || "{{value}}") : "",
  }));
}

async function insertTemplateToken(token: string): Promise<void> {
  if (!selectedSupportsTemplate.value) {
    return;
  }

  const textarea = resolveTemplateTextarea();
  const currentValue = selectedNode.value.template;
  let nextValue: string;
  let caretPosition = currentValue.length + token.length;

  if (textarea) {
    const selectionStart = textarea.selectionStart ?? currentValue.length;
    const selectionEnd = textarea.selectionEnd ?? selectionStart;
    nextValue = `${currentValue.slice(0, selectionStart)}${token}${currentValue.slice(selectionEnd)}`;
    caretPosition = selectionStart + token.length;
  } else {
    nextValue = currentValue ? `${currentValue}${token}` : token;
  }

  updateSelectedTemplate(nextValue);
  await nextTick();

  const nextTextarea = resolveTemplateTextarea();
  if (nextTextarea) {
    nextTextarea.focus();
    nextTextarea.setSelectionRange(caretPosition, caretPosition);
  }
}

function parsePreviewRequestBody(): JsonValue | null {
  const trimmed = previewRequestBodyDraft.value.trim();
  if (!trimmed) {
    return null;
  }

  return JSON.parse(trimmed) as JsonValue;
}

async function copySchema(): Promise<void> {
  const copied = await copyText(schemaJsonText.value);
  setCopyState("schema", copied);
}

async function copyPreviewPane(): Promise<void> {
  const copied = await copyText(previewPaneText.value);
  setCopyState("preview", copied);
}

function importSchema(): void {
  importError.value = null;

  try {
    const parsed = JSON.parse(importText.value) as JsonValue;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      importError.value = "Import a JSON Schema object.";
      return;
    }

    tree.value = schemaToTree(parsed as JsonObject, props.scope);
    liveSchema.value = toSchemaSnapshot(tree.value);
    selectedNodeId.value = tree.value.id;
    emit("update:schema", liveSchema.value);
    importDialog.value = false;
  } catch {
    importError.value = "That JSON could not be parsed.";
  }
}

function removeSelectedNode(): void {
  if (selectedIsRoot.value) {
    return;
  }

  const fallbackSelection = selectedParent.value?.id ?? tree.value.id;
  commitTree(deleteNode(tree.value, selectedNode.value.id));
  selectedNodeId.value = fallbackSelection;
}

function duplicateSelectedNode(): void {
  if (selectedIsRoot.value) {
    return;
  }

  commitTree(duplicateNode(tree.value, selectedNode.value.id));
}

async function runPreview(force = false): Promise<void> {
  if (props.scope !== "response" || !auth.session.value) {
    return;
  }

  if (!force && previewStatus.value === "loading") {
    return;
  }

  previewStatus.value = "loading";
  previewError.value = null;

  try {
    const schemaError = validateTree(tree.value, {
      pathParameterNames: responsePathParameterNames.value,
    });
    if (schemaError) {
      previewStatus.value = "error";
      previewError.value = schemaError;
      return;
    }

    if (previewRequestBodyValidationMessage.value) {
      previewStatus.value = "error";
      previewError.value = previewRequestBodyValidationMessage.value;
      return;
    }

    const response = await previewResponse(
      liveSchema.value,
      normalizedSeedKey.value,
      previewPathParameters.value,
      auth.session.value,
      {
        queryParameters: previewQueryParameters.value,
        requestBody: parsePreviewRequestBody(),
      },
    );
    previewBody.value = JSON.stringify(response.preview, null, 2);
    previewStatus.value = "success";
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before previewing response schemas.");
      void router.push({ name: "login" });
      return;
    }

    previewStatus.value = "error";
    previewError.value = error instanceof Error ? error.message : "Unable to generate a schema preview.";
  }
}

function previewModeLabel(mode: MockMode): string {
  if (mode === "fixed") {
    return "static";
  }

  if (mode === "mocking") {
    return "mocking";
  }

  return "random";
}

function nodeValueBadge(node: SchemaBuilderNode): string | null {
  if (!isScalarNode(node)) {
    return null;
  }

  if (node.parameterSource) {
    return node.parameterSource;
  }

  return node.mode === "fixed" ? "Fixed value" : valueTypeLabel(node.generator);
}

function nodeBehaviorLabel(node: SchemaBuilderNode): string {
  if (node.parameterSource) {
    return "route value";
  }

  return previewModeLabel(node.mode);
}

onBeforeUnmount(() => {
  if (previewTimer) {
    window.clearTimeout(previewTimer);
  }

  if (schemaCopyTimer) {
    window.clearTimeout(schemaCopyTimer);
  }

  if (previewCopyTimer) {
    window.clearTimeout(previewCopyTimer);
  }
});
</script>

<template>
  <v-row class="schema-studio-grid">
    <v-col class="schema-sidebar-col" cols="12" xl="3" lg="3">
      <div class="schema-sidebar d-flex flex-column ga-4">
        <v-card class="workspace-card">
          <v-card-item>
            <template #prepend>
              <v-avatar color="secondary" variant="tonal">
                <v-icon icon="mdi-toy-brick-plus-outline" />
              </v-avatar>
            </template>

            <v-card-title>Add fields</v-card-title>
            <v-card-subtitle>Click or drag a field into the schema.</v-card-subtitle>
          </v-card-item>
          <v-divider />
          <v-card-text class="d-flex flex-column ga-4">
            <div class="d-flex flex-column ga-3">
              <div class="schema-section-label">Field types</div>
              <div class="schema-palette-grid">
                <v-chip
                  v-for="item in paletteOptions"
                  :key="item.type"
                  v-pragmatic-draggable="nodePaletteDragBinding(item.type)"
                  :data-palette-type="item.type"
                  class="schema-pill"
                  :class="{ 'schema-pill-active': selectedNode.type === item.type }"
                  label
                  size="small"
                  variant="elevated"
                  @click="addNodeFromPalette(item.type)"
                >
                  <template #prepend>
                    <v-icon :icon="item.icon" size="18" />
                  </template>
                  {{ item.label }}
                </v-chip>
              </div>
            </div>

            <div v-if="hasRouteValuePalette" class="d-flex flex-column ga-3">
              <div class="d-flex flex-wrap align-center justify-space-between ga-2">
                <div class="schema-section-label">Route values</div>
                <div class="text-caption text-medium-emphasis">
                  {{ routeValuesHint }}
                </div>
              </div>

              <div v-if="responsePathParameters.length" class="d-flex flex-column ga-2">
                <div class="schema-mini-label">Path params</div>
                <div class="schema-value-palette-wrap">
                  <v-chip
                    v-for="parameter in responsePathParameters"
                    :key="parameter.name"
                    v-pragmatic-draggable="pathParameterDragBinding(parameter)"
                    :data-path-parameter="parameter.name"
                    class="schema-value-pill schema-value-pill-parameter"
                    :class="{ 'schema-value-pill-active': selectedUsesPathParameter && selectedNode.parameterSource === parameter.name }"
                    label
                    size="small"
                    variant="elevated"
                    @click="applyPathParameterFromPalette(parameter)"
                  >
                    <template #prepend>
                      <v-icon icon="mdi-variable" size="18" />
                    </template>
                    {{ parameter.name }}
                  </v-chip>
                </div>
              </div>

              <div v-if="requestQueryParameters.length" class="d-flex flex-column ga-2">
                <div class="schema-mini-label">Query params</div>
                <div class="schema-value-palette-wrap">
                  <v-chip
                    v-for="parameter in requestQueryParameters"
                    :key="parameter.name"
                    :data-query-parameter="parameter.name"
                    class="schema-value-pill schema-value-pill-parameter"
                    :class="{ 'schema-value-pill-active': queryParameterChipActive(parameter.name) }"
                    :draggable="false"
                    label
                    size="small"
                    variant="elevated"
                    @click="insertQueryParameterToken(parameter)"
                  >
                    <template #prepend>
                      <v-icon icon="mdi-tune-variant" size="18" />
                    </template>
                    {{ parameter.name }}
                  </v-chip>
                </div>
              </div>
            </div>

            <div v-if="scope === 'response'" class="d-flex flex-column ga-3">
              <div class="schema-section-label">Value mode</div>
              <div class="schema-value-palette-wrap">
                <v-chip
                  v-for="item in behaviorPalette"
                  :key="item.value"
                  v-pragmatic-draggable="modePaletteDragBinding(item.value)"
                  :data-value-mode="item.value"
                  class="schema-mode-pill"
                  :class="{ 'schema-mode-pill-active': selectedHasValueLane && selectedNode.mode === item.value }"
                  label
                  size="small"
                  variant="elevated"
                  @click="selectedHasValueLane && applyModeToNode(selectedNode.id, item.value)"
                >
                  <template #prepend>
                    <v-icon :icon="item.icon" size="16" />
                  </template>
                  {{ item.label }}
                </v-chip>
              </div>
            </div>

            <div v-if="scope === 'response'" class="d-flex flex-column ga-3">
              <div class="d-flex flex-wrap align-center justify-space-between ga-2">
                <div class="schema-section-label">Value type</div>
                <div class="text-caption text-medium-emphasis">
                  {{ selectedHasValueLane ? selectedValueTypeLabel : "Select a value field" }}
                </div>
              </div>

              <div class="schema-value-palette">
                <div v-for="section in valuePaletteSections" :key="section.label" class="schema-value-group">
                  <div class="schema-mini-label">{{ section.label }}</div>
                  <div class="schema-value-palette-wrap">
                    <v-chip
                      v-for="item in section.items"
                      :key="item.value"
                      v-pragmatic-draggable="valuePaletteDragBinding(item.value)"
                      :data-value-type="item.value"
                      class="schema-value-pill"
                      :class="{ 'schema-value-pill-active': selectedHasValueLane && selectedValueType === item.value }"
                      label
                      size="small"
                      variant="elevated"
                      @click="applyValueTypeFromPalette(item.value)"
                    >
                      <template #prepend>
                        <v-icon :icon="item.icon" size="16" />
                      </template>
                      {{ item.label }}
                    </v-chip>
                  </div>
                </div>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </div>
    </v-col>

    <v-col cols="12" xl="6" lg="6">
      <div class="schema-main-stack d-flex flex-column ga-4">
        <v-card class="workspace-card">
          <v-card-item>
            <template #prepend>
              <v-avatar color="primary" variant="tonal">
                <v-icon icon="mdi-vector-polyline-plus" />
              </v-avatar>
            </template>

            <v-card-title>{{ canvasTitle }}</v-card-title>
            <v-card-subtitle>{{ canvasSubtitle }}</v-card-subtitle>

            <template #append>
              <div class="d-flex flex-wrap ga-2">
                <v-btn prepend-icon="mdi-upload-outline" variant="text" @click="importDialog = true">
                  Import
                </v-btn>
                <v-btn prepend-icon="mdi-content-copy" variant="text" @click="copySchema">
                  {{ schemaCopyLabel }}
                </v-btn>
              </div>
            </template>
          </v-card-item>

          <v-divider />

          <v-card-text class="schema-canvas">
            <div class="schema-canvas-toolbar">
              <div class="schema-canvas-context">
                <div class="schema-section-label">Selected field</div>
                <div class="schema-canvas-heading">
                  <div class="text-subtitle-1 font-weight-medium">
                    {{ selectedNodeLabel }}
                  </div>
                  <v-chip color="primary" label size="small" variant="tonal">
                    {{ selectedNode.type }}
                  </v-chip>
                </div>
                <div class="schema-canvas-path text-body-2 text-medium-emphasis">
                  {{ selectedPath }}
                </div>
              </div>

              <div class="schema-canvas-meta">
                <v-chip color="primary" label size="small" variant="tonal">
                  {{ totalFieldCount }} {{ totalFieldCount === 1 ? "field" : "fields" }}
                </v-chip>
                <v-chip label size="small" variant="outlined">
                  {{ tree.type }} root
                </v-chip>
                <v-chip
                  v-if="selectedHasValueLane"
                  :color="selectedUsesPathParameter ? 'primary' : 'success'"
                  label
                  size="small"
                  variant="tonal"
                >
                  {{ nodeValueBadge(selectedNode) }}
                </v-chip>
              </div>
            </div>

            <SchemaNodeCard
              :active-node-id="selectedNodeId"
              :collapsed-node-ids="collapsedNodeIds"
              :node="tree"
              :parent-id="null"
              :parent-type="null"
              root
              :scope="scope"
              @drop-container="handleDropOnContainer"
              @drop-row="handleDropBeforeRow"
              @drop-value="handleDropOnValue"
              @insert-node="insertNodeFromMenu"
              @select="selectedNodeId = $event"
              @toggle-collapse="toggleNodeCollapsed"
            />
          </v-card-text>
        </v-card>

        <div class="schema-detail-grid" :class="{ 'schema-detail-grid--split': scope === 'response' && hasPreviewInputs }">
          <v-card class="workspace-card">
            <v-card-item>
              <template #prepend>
                <v-avatar color="accent" variant="tonal">
                  <v-icon icon="mdi-tune-variant" />
                </v-avatar>
              </template>

              <v-card-title>Field settings</v-card-title>
              <v-card-subtitle>Edit the selected field.</v-card-subtitle>

              <template #append>
                <div class="d-flex ga-2">
                  <v-btn
                    :disabled="selectedIsRoot"
                    icon="mdi-content-copy"
                    size="small"
                    variant="text"
                    @click="duplicateSelectedNode"
                  />
                  <v-btn
                    :disabled="selectedIsRoot"
                    color="error"
                    icon="mdi-delete-outline"
                    size="small"
                    variant="text"
                    @click="removeSelectedNode"
                  />
                </div>
              </template>
            </v-card-item>

            <v-divider />

            <v-card-text class="d-flex flex-column ga-4">
              <div class="d-flex flex-wrap ga-2">
                <v-chip color="primary" label size="small" variant="tonal">
                  {{ selectedNode.type }}
                </v-chip>
                <v-chip
                  v-if="scope === 'response'"
                  color="secondary"
                  label
                  size="small"
                  variant="tonal"
                >
                  {{ nodeBehaviorLabel(selectedNode) }}
                </v-chip>
                <v-chip v-if="!selectedIsRoot && selectedNode.required" color="accent" label size="small" variant="tonal">
                  required
                </v-chip>
                <v-chip
                  v-if="selectedHasValueLane"
                  :color="selectedUsesPathParameter ? 'primary' : 'success'"
                  label
                  size="small"
                  variant="tonal"
                >
                  {{ nodeValueBadge(selectedNode) }}
                </v-chip>
              </div>

              <section class="schema-detail-section d-flex flex-column ga-3">
                <div class="schema-detail-section__title">Basics</div>

                <v-text-field
                  :disabled="selectedIsRoot"
                  label="Field name"
                  :model-value="selectedNode.name"
                  @update:model-value="updateSelectedNode((node) => ({ ...node, name: String($event ?? '') }))"
                />

                <v-select
                  :items="rootShapeOptions"
                  item-title="title"
                  item-value="value"
                  label="Field type"
                  :model-value="selectedNode.type"
                  @update:model-value="(value) => value && commitTree(resetNodeType(tree, selectedNode.id, value, scope))"
                />

                <v-textarea
                  auto-grow
                  label="Description"
                  :model-value="selectedNode.description"
                  rows="2"
                  @update:model-value="updateSelectedNode((node) => ({ ...node, description: String($event ?? '') }))"
                />

                <v-switch
                  v-if="!selectedIsRoot && selectedParent?.type === 'object'"
                  color="accent"
                  inset
                  label="Required field"
                  :model-value="selectedNode.required"
                  @update:model-value="updateSelectedNode((node) => ({ ...node, required: Boolean($event) }))"
                />
              </section>

              <section
                v-if="scope === 'response' && (selectedHasValueLane || selectedUsesPathParameter)"
                class="schema-detail-section d-flex flex-column ga-3"
              >
                <div class="schema-detail-section__title">Behavior</div>

                <v-select
                  v-if="scope === 'response' && !selectedUsesPathParameter"
                  :items="modeOptions"
                  item-title="title"
                  item-value="value"
                  label="Value mode"
                  :model-value="selectedNode.mode"
                  @update:model-value="updateSelectedNode((node) => ({ ...node, mode: String($event ?? 'generate') as MockMode }))"
                />

                <v-text-field
                  v-else-if="selectedUsesPathParameter"
                  label="Route parameter"
                  :model-value="selectedNode.parameterSource"
                  readonly
                />

                <v-select
                  v-if="showValueTypeSelector"
                  :items="availableGenerators"
                  item-title="label"
                  item-value="value"
                  label="Value type"
                  :model-value="selectedNode.generator"
                  @update:model-value="updateSelectedValueType"
                />

                <template v-if="scope === 'response' && selectedNode.mode === 'fixed'">
                  <v-switch
                    v-if="selectedNode.type === 'boolean'"
                    color="accent"
                    inset
                    label="Fixed boolean value"
                    :model-value="Boolean(selectedNode.fixedValue)"
                    @update:model-value="updateSelectedNode((node) => ({ ...node, fixedValue: Boolean($event) }))"
                  />

                  <v-text-field
                    v-else-if="selectedNode.type === 'integer' || selectedNode.type === 'number'"
                    label="Fixed value"
                    :model-value="selectedNode.fixedValue"
                    type="number"
                    @update:model-value="updateSelectedNode((node) => ({ ...node, fixedValue: Number($event ?? 0) }))"
                  />

                  <v-textarea
                    v-else-if="selectedNode.type === 'string' || selectedNode.type === 'enum'"
                    auto-grow
                    label="Fixed value"
                    :model-value="String(selectedNode.fixedValue ?? '')"
                    rows="3"
                    @update:model-value="updateSelectedNode((node) => ({ ...node, fixedValue: String($event ?? '') }))"
                  />

                  <v-textarea
                    v-else
                    auto-grow
                    :error-messages="fixedJsonError ?? undefined"
                    label="Fixed JSON value"
                    :model-value="fixedJsonDraft"
                    rows="6"
                    @update:model-value="updateStructuredFixedValue(String($event ?? ''))"
                  />
                </template>
              </section>

              <section
                v-if="selectedNode.type === 'string' || selectedNode.type === 'integer' || selectedNode.type === 'number' || selectedNode.type === 'array' || selectedNode.type === 'enum'"
                class="schema-detail-section d-flex flex-column ga-3"
              >
                <div class="schema-detail-section__title">Constraints</div>

                <v-row v-if="selectedNode.type === 'string' && !selectedUsesPathParameter">
                  <v-col cols="6">
                    <v-text-field
                      label="Min length"
                      :model-value="selectedNode.minLength ?? ''"
                      type="number"
                      @update:model-value="updateSelectedNode((node) => ({ ...node, minLength: parseOptionalNumberInput($event) }))"
                    />
                  </v-col>
                  <v-col cols="6">
                    <v-text-field
                      label="Max length"
                      :model-value="selectedNode.maxLength ?? ''"
                      type="number"
                      @update:model-value="updateSelectedNode((node) => ({ ...node, maxLength: parseOptionalNumberInput($event) }))"
                    />
                  </v-col>
                </v-row>

                <v-row v-if="selectedNode.type === 'integer' || selectedNode.type === 'number'">
                  <v-col cols="6">
                    <v-text-field
                      label="Minimum"
                      :model-value="selectedNode.minimum ?? ''"
                      type="number"
                      @update:model-value="updateSelectedNode((node) => ({ ...node, minimum: parseOptionalNumberInput($event) }))"
                    />
                  </v-col>
                  <v-col cols="6">
                    <v-text-field
                      label="Maximum"
                      :model-value="selectedNode.maximum ?? ''"
                      type="number"
                      @update:model-value="updateSelectedNode((node) => ({ ...node, maximum: parseOptionalNumberInput($event) }))"
                    />
                  </v-col>
                </v-row>

                <v-row v-if="selectedNode.type === 'array'">
                  <v-col cols="6">
                    <v-text-field
                      label="Min items"
                      :model-value="selectedNode.minItems ?? ''"
                      type="number"
                      @update:model-value="updateSelectedNode((node) => ({ ...node, minItems: $event ? Number($event) : null }))"
                    />
                  </v-col>
                  <v-col cols="6">
                    <v-text-field
                      label="Max items"
                      :model-value="selectedNode.maxItems ?? ''"
                      type="number"
                      @update:model-value="updateSelectedNode((node) => ({ ...node, maxItems: $event ? Number($event) : null }))"
                    />
                  </v-col>
                </v-row>

                <v-textarea
                  v-if="selectedNode.type === 'enum'"
                  auto-grow
                  label="Enum options"
                  :model-value="selectedNode.enumValues.join('\n')"
                  rows="4"
                  @update:model-value="updateEnumValues(String($event ?? ''))"
                />
              </section>

              <section v-if="selectedSupportsTemplate" class="schema-detail-section d-flex flex-column ga-3">
                <div class="schema-detail-section__title">Template</div>

                <v-switch
                  color="secondary"
                  inset
                  label="Use template"
                  :model-value="selectedTemplateEnabled"
                  @update:model-value="setTemplateEnabled(Boolean($event))"
                />

                <div v-if="selectedTemplateEnabled" class="d-flex flex-column ga-3">
                  <v-textarea
                    ref="templateTextareaRef"
                    auto-grow
                    :error-messages="selectedTemplateError ?? undefined"
                    hint="Use {{value}} plus request.path.*, request.query.*, and request.body.* tokens."
                    label="Template"
                    :model-value="selectedNode.template"
                    persistent-hint
                    rows="4"
                    @update:model-value="updateSelectedTemplate(String($event ?? ''))"
                  />

                  <div class="d-flex flex-column ga-3">
                    <div class="d-flex flex-wrap align-center justify-space-between ga-2">
                      <div class="schema-mini-label">Helper tokens</div>
                      <div class="text-caption text-medium-emphasis">
                        Click to insert at the cursor.
                      </div>
                    </div>

                    <div
                      v-for="group in templateHelperGroups"
                      :key="group.label"
                      class="d-flex flex-column ga-2"
                    >
                      <div class="schema-mini-label">{{ group.label }}</div>
                      <div class="schema-value-palette-wrap">
                        <v-chip
                          v-for="item in group.items"
                          :key="item.token"
                          :data-template-token="item.token"
                          class="schema-value-pill"
                          label
                          size="small"
                          variant="elevated"
                          @click="insertTemplateToken(item.token)"
                        >
                          {{ item.label }}
                        </v-chip>
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              <section
                v-if="selectedShowsQuickAdd || selectedShowsItemShape"
                class="schema-detail-section d-flex flex-column ga-3"
              >
                <div class="schema-detail-section__title">Structure</div>

                <div v-if="selectedShowsQuickAdd" class="d-flex flex-column ga-3">
                  <div class="text-overline text-medium-emphasis">Add inside this object</div>
                  <div class="d-flex flex-wrap ga-2">
                    <v-chip
                      v-for="item in PALETTE_TYPES"
                      :key="`quick-${item.type}`"
                      color="secondary"
                      label
                      variant="tonal"
                      @click="commitTree(addNodeToContainer(tree, selectedNode.id, item.type, scope))"
                    >
                      {{ item.label }}
                    </v-chip>
                  </div>
                </div>

                <div v-else-if="selectedShowsItemShape" class="d-flex flex-column ga-3">
                  <div class="text-overline text-medium-emphasis">Item shape</div>
                  <div class="d-flex flex-wrap ga-2">
                    <v-chip
                      v-for="item in PALETTE_TYPES"
                      :key="`array-item-${item.type}`"
                      color="secondary"
                      label
                      variant="tonal"
                      @click="commitTree(addNodeToContainer(tree, selectedNode.id, item.type, scope))"
                    >
                      {{ item.label }}
                    </v-chip>
                  </div>
                </div>
              </section>
            </v-card-text>
          </v-card>

          <v-card v-if="scope === 'response' && hasPreviewInputs" class="workspace-card">
            <v-card-item>
              <template #prepend>
                <v-avatar color="primary" variant="tonal">
                  <v-icon icon="mdi-tune-variant" />
                </v-avatar>
              </template>

              <v-card-title>Preview inputs</v-card-title>
              <v-card-subtitle>Feed request tokens without squeezing the preview rail.</v-card-subtitle>
            </v-card-item>

            <v-divider />

            <v-card-text class="d-flex flex-column ga-4">
              <v-text-field
                v-for="parameter in responsePathParameters"
                :key="`preview-path-${parameter.name}`"
                v-model="previewPathParameters[parameter.name]"
                :label="`Path: ${parameter.name}`"
              />

              <v-text-field
                v-for="parameter in requestQueryParameters"
                :key="`preview-query-${parameter.name}`"
                v-model="previewQueryParameters[parameter.name]"
                clearable
                :label="`Query: ${parameter.name}`"
              />

              <v-textarea
                v-if="hasPreviewRequestBody"
                v-model="previewRequestBodyDraft"
                auto-grow
                :error-messages="previewRequestBodyValidationMessage ?? undefined"
                hint="Optional JSON body used for request.body.* template tokens."
                label="Request body JSON"
                persistent-hint
                rows="5"
              />
            </v-card-text>
          </v-card>
        </div>
      </div>
    </v-col>

    <v-col class="schema-preview-col" cols="12" xl="3" lg="3">
      <div class="schema-preview-stack d-flex flex-column ga-4">
        <v-card v-if="scope === 'response'" class="workspace-card">
          <v-card-item>
            <template #prepend>
              <v-avatar color="primary" variant="tonal">
                <v-icon icon="mdi-lightning-bolt-outline" />
              </v-avatar>
            </template>

            <v-card-title>Live preview</v-card-title>
            <v-card-subtitle>
              {{ normalizedSeedKey ? "Seeded output stays deterministic." : "Leave the seed blank for fresh samples." }}
            </v-card-subtitle>

            <template #append>
              <v-btn
                v-if="!normalizedSeedKey && responseRailTab === 'preview'"
                prepend-icon="mdi-refresh"
                variant="text"
                @click="runPreview(true)"
              >
                Regenerate
              </v-btn>
            </template>
          </v-card-item>

          <v-divider />

          <v-card-text class="d-flex flex-column ga-4">
            <div class="d-flex flex-wrap ga-2">
              <v-chip color="secondary" label size="small" variant="tonal">
                {{ nodeBehaviorLabel(selectedNode) }}
              </v-chip>
              <v-chip color="primary" label size="small" variant="tonal">
                {{ totalFieldCount }} {{ totalFieldCount === 1 ? "field" : "fields" }}
              </v-chip>
              <v-chip label size="small" variant="outlined">
                {{ selectedNode.type }}
              </v-chip>
            </div>

            <v-text-field
              v-model="editableSeedKey"
              clearable
              hint="Optional deterministic seed for preview and runtime output."
              label="Seed key"
              persistent-hint
              placeholder="Optional deterministic seed"
            />

            <v-tabs v-model="responseRailTab" color="secondary" density="compact">
              <v-tab value="preview">Sample response</v-tab>
              <v-tab value="schema">JSON Schema</v-tab>
            </v-tabs>

            <v-skeleton-loader v-if="responseRailTab === 'preview' && previewStatus === 'loading'" type="paragraph, paragraph, paragraph" />

            <v-alert
              v-else-if="responseRailTab === 'preview' && previewStatus === 'error' && previewError"
              border="start"
              color="error"
              closable
              variant="tonal"
              @click:close="previewError = null"
            >
              {{ previewError }}
            </v-alert>

            <div v-else class="schema-code-pane">
              <v-btn
                class="schema-code-pane__copy"
                color="primary"
                density="compact"
                prepend-icon="mdi-content-copy"
                size="small"
                variant="tonal"
                @click="copyPreviewPane"
              >
                {{ previewCopyLabel }}
              </v-btn>

              <!-- eslint-disable vue/no-v-html -->
              <pre
                v-if="responseRailTab === 'preview'"
                class="code-block code-block--json-editor"
              ><code class="code-block__code" v-html="highlightedPreviewBody" /></pre>

              <pre
                v-else
                class="code-block code-block--json-editor"
              ><code class="code-block__code" v-html="highlightedSchemaBody" /></pre>
              <!-- eslint-enable vue/no-v-html -->
            </div>
          </v-card-text>
        </v-card>

        <v-card v-else class="workspace-card">
          <v-card-item>
            <template #prepend>
              <v-avatar color="primary" variant="tonal">
                <v-icon icon="mdi-code-json" />
              </v-avatar>
            </template>

            <v-card-title>Request body</v-card-title>
            <v-card-subtitle>Current JSON body schema.</v-card-subtitle>
            <template #append>
              <v-chip color="primary" label size="small" variant="tonal">
                {{ totalFieldCount }} {{ totalFieldCount === 1 ? "field" : "fields" }}
              </v-chip>
            </template>
          </v-card-item>
          <v-divider />
          <v-card-text class="d-flex flex-column ga-4">
            <div class="d-flex flex-wrap ga-2">
              <v-chip label size="small" variant="outlined">
                {{ selectedNode.type }}
              </v-chip>
              <v-chip color="secondary" label size="small" variant="tonal">
                {{ rootContractLabel }}
              </v-chip>
            </div>

            <pre class="code-block">{{ JSON.stringify(liveSchema, null, 2) }}</pre>
          </v-card-text>
        </v-card>
      </div>
    </v-col>
  </v-row>

  <v-dialog v-model="importDialog" max-width="720">
    <v-card class="workspace-card">
      <v-card-item>
        <v-card-title>Import schema</v-card-title>
        <v-card-subtitle>Paste a JSON Schema object.</v-card-subtitle>
      </v-card-item>
      <v-divider />
      <v-card-text class="d-flex flex-column ga-4">
        <v-alert
          v-if="importError"
          border="start"
          closable
          color="error"
          variant="tonal"
          @click:close="importError = null"
        >
          {{ importError }}
        </v-alert>
        <v-textarea v-model="importText" auto-grow label="Schema JSON" rows="12" />
      </v-card-text>
      <v-card-actions class="px-6 pb-6">
        <v-spacer />
        <v-btn variant="text" @click="importDialog = false">Cancel</v-btn>
        <v-btn color="primary" prepend-icon="mdi-upload-outline" @click="importSchema">
          Import schema
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.schema-main-stack {
  width: 100%;
  min-height: 0;
}

.schema-detail-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
}

.schema-detail-grid > * {
  min-width: 0;
}

.schema-detail-section {
  padding: 0.9rem 1rem;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 18px;
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 95%, rgb(var(--v-theme-primary)) 5%);
}

.schema-detail-section__title {
  color: rgba(148, 163, 184, 0.92);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.schema-sidebar {
  width: 100%;
  min-height: 0;
  overscroll-behavior: contain;
}

.schema-sidebar > * {
  flex: 0 0 auto;
}

@media (min-width: 1280px) {
  .schema-detail-grid--split {
    grid-template-columns: minmax(0, 1.22fr) minmax(0, 0.9fr);
  }

  .schema-sidebar-col {
    display: flex;
    position: sticky;
    top: 0;
    align-self: flex-start;
  }

  .schema-sidebar {
    height: calc(100vh - var(--v-layout-top, 88px) - 3rem);
    max-height: calc(100vh - var(--v-layout-top, 88px) - 3rem);
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 0.35rem;
    padding-bottom: 0.35rem;
    scrollbar-gutter: stable;
  }

  .schema-preview-col {
    display: flex;
    position: sticky;
    top: 0;
    align-self: flex-start;
  }

  .schema-preview-stack {
    width: 100%;
    height: calc(100vh - var(--v-layout-top, 88px) - 3rem);
    max-height: calc(100vh - var(--v-layout-top, 88px) - 3rem);
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 0.35rem;
    padding-bottom: 0.35rem;
    scrollbar-gutter: stable;
  }
}
</style>
