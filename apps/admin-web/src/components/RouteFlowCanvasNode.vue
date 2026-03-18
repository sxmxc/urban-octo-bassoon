<script setup lang="ts">
import { computed } from "vue";
import { Handle, Position, type NodeProps } from "@vue-flow/core";
import { NodeToolbar } from "@vue-flow/node-toolbar";
import type { JsonObject, JsonValue, RouteFlowNodeType } from "../types/endpoints";

interface RouteFlowCanvasNodeData {
  title: string;
  description: string;
  icon: string;
  color: string;
  runtimeType: RouteFlowNodeType;
  hasIncoming: boolean;
  hasOutgoing: boolean;
  config: JsonObject;
}

interface SourceHandleDescriptor {
  id: string;
  label?: string;
  top: string;
}

const props = defineProps<NodeProps<RouteFlowCanvasNodeData>>();
const emit = defineEmits<{
  center: [nodeId: string];
  remove: [nodeId: string];
}>();

function centerNode(): void {
  emit("center", props.id);
}

function removeNode(): void {
  emit("remove", props.id);
}

function isJsonObject(value: JsonValue | undefined): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function previewJsonShape(value: JsonValue | undefined): string {
  if (isJsonObject(value)) {
    const keys = Object.keys(value);
    if (keys.length === 0) {
      return "empty object";
    }
    if (keys.length <= 2) {
      return keys.join(" + ");
    }
    return `${keys.length} keys`;
  }

  if (Array.isArray(value)) {
    return `${value.length} items`;
  }

  if (typeof value === "string") {
    return value.length > 18 ? `${value.slice(0, 18)}...` : value;
  }

  if (value === null || value === undefined) {
    return "empty";
  }

  return String(value);
}

const nodeLabel = computed(() => (typeof props.label === "string" && props.label.trim() ? props.label : props.data.title));
const summaryLine = computed(() => {
  switch (props.data.runtimeType) {
    case "api_trigger":
      return "Route entry";
    case "validate_request":
      return "Contract gate";
    case "transform":
      return `Output: ${previewJsonShape(props.data.config.output)}`;
    case "if_condition":
      return `If ${String(props.data.config.operator ?? "equals")}`;
    case "switch":
      return `Switch on ${previewJsonShape(props.data.config.value)}`;
    case "http_request":
      return `${String(props.data.config.method ?? "GET")} ${previewJsonShape(props.data.config.path)}`;
    case "postgres_query":
      return `Query: ${previewJsonShape(props.data.config.sql)}`;
    case "set_response":
      return `Returns ${String(props.data.config.status_code ?? 200)}`;
    case "error_response":
      return `Fails with ${String(props.data.config.status_code ?? 400)}`;
    default:
      return props.data.title;
  }
});
const detailLine = computed(() => {
  switch (props.data.runtimeType) {
    case "api_trigger":
      return "Method, path, and request context";
    case "validate_request":
      return "Body and params from Contract";
    case "transform":
      return props.data.description;
    case "if_condition":
      return `Compare: ${previewJsonShape(props.data.config.left)}`;
    case "switch":
      return `Value: ${previewJsonShape(props.data.config.value)}`;
    case "http_request":
      return `Connection #${String(props.data.config.connection_id ?? "pending")}`;
    case "postgres_query":
      return `Connection #${String(props.data.config.connection_id ?? "pending")}`;
    case "set_response":
      return `Body: ${previewJsonShape(props.data.config.body)}`;
    case "error_response":
      return `Body: ${previewJsonShape(props.data.config.body)}`;
    default:
      return props.data.description;
  }
});
const typeBadge = computed(() => props.data.runtimeType.replaceAll("_", " "));
const sourceHandles = computed<SourceHandleDescriptor[]>(() => {
  switch (props.data.runtimeType) {
    case "if_condition":
      return [
        { id: "true", label: "True", top: "38%" },
        { id: "false", label: "False", top: "70%" },
      ];
    case "switch":
      return [
        { id: "case", label: "Case", top: "38%" },
        { id: "default", label: "Default", top: "70%" },
      ];
    default:
      return props.data.hasOutgoing ? [{ id: "next", top: "50%" }] : [];
  }
});
</script>

<template>
  <div
    class="route-flow-node"
    :class="{
      'route-flow-node--selected': selected,
      'route-flow-node--dimmed': dragging,
    }"
    :style="{ '--route-flow-node-accent': `rgb(var(--v-theme-${data.color}))` }"
  >
    <NodeToolbar
      :is-visible="selected"
      :offset="14"
      align="center"
      :position="Position.Top"
    >
      <div class="route-flow-node__toolbar">
        <v-btn
          class="route-flow-node__toolbar-btn"
          icon="mdi-crosshairs-gps"
          size="x-small"
          variant="text"
          @click.stop="centerNode"
        />
        <v-btn
          class="route-flow-node__toolbar-btn"
          color="error"
          icon="mdi-trash-can-outline"
          size="x-small"
          variant="text"
          @click.stop="removeNode"
        />
      </div>
    </NodeToolbar>

    <Handle
      v-if="data.hasIncoming"
      class="route-flow-node__handle route-flow-node__handle--target"
      type="target"
      :position="Position.Left"
    />

    <div class="route-flow-node__chrome">
      <div class="route-flow-node__header">
        <div class="route-flow-node__icon-shell">
          <v-icon :icon="data.icon" size="16" />
        </div>

        <div class="route-flow-node__copy">
          <div class="route-flow-node__title">{{ nodeLabel }}</div>
          <div class="route-flow-node__summary">{{ summaryLine }}</div>
        </div>

        <div class="route-flow-node__badge">{{ typeBadge }}</div>
      </div>

      <div class="route-flow-node__details">
        <div class="route-flow-node__body">{{ detailLine }}</div>
        <div v-if="selected" class="route-flow-node__selected-pill">editing</div>
      </div>
    </div>

    <template v-for="handle in sourceHandles" :key="handle.id">
      <div
        v-if="handle.label"
        class="route-flow-node__source-label"
        :style="{ top: handle.top }"
      >
        {{ handle.label }}
      </div>
      <Handle
        :id="handle.id"
        class="route-flow-node__handle route-flow-node__handle--source"
        :position="Position.Right"
        type="source"
        :style="{ top: handle.top }"
      />
    </template>
  </div>
</template>

<style scoped>
.route-flow-node {
  position: relative;
  width: 236px;
}

.route-flow-node__toolbar {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.28rem;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), transparent 100%),
    rgba(15, 23, 42, 0.92);
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.28);
}

.route-flow-node__toolbar-btn {
  color: rgba(248, 250, 252, 0.92);
}

.route-flow-node__chrome {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  min-height: 104px;
  padding: 0.72rem 0.84rem;
  border: 1px solid color-mix(in srgb, var(--route-flow-node-accent) 18%, rgba(148, 163, 184, 0.28));
  border-radius: 18px;
  background:
    linear-gradient(155deg, color-mix(in srgb, var(--route-flow-node-accent) 10%, rgba(255, 255, 255, 0.08)), transparent 70%),
    color-mix(in srgb, rgb(var(--v-theme-surface)) 95%, rgb(var(--v-theme-background)) 5%);
  box-shadow: 0 14px 24px rgba(15, 23, 42, 0.11);
  transition:
    transform 0.16s ease,
    box-shadow 0.16s ease,
    border-color 0.16s ease;
}

.route-flow-node--selected .route-flow-node__chrome {
  border-color: color-mix(in srgb, var(--route-flow-node-accent) 58%, rgba(255, 255, 255, 0.14));
  box-shadow:
    0 18px 34px rgba(15, 23, 42, 0.16),
    0 0 0 2px color-mix(in srgb, var(--route-flow-node-accent) 20%, transparent);
  transform: translateY(-1px);
}

.route-flow-node--dimmed .route-flow-node__chrome {
  box-shadow: 0 10px 18px rgba(15, 23, 42, 0.08);
}

.route-flow-node__header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.55rem;
}

.route-flow-node__icon-shell {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--route-flow-node-accent) 14%, rgb(var(--v-theme-surface)) 86%);
  color: color-mix(in srgb, var(--route-flow-node-accent) 84%, rgb(var(--v-theme-on-surface)) 16%);
}

.route-flow-node__copy {
  min-width: 0;
}

.route-flow-node__title {
  overflow: hidden;
  color: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 96%, transparent);
  font-size: 0.88rem;
  font-weight: 720;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-flow-node__summary {
  overflow: hidden;
  color: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 60%, transparent);
  font-size: 0.73rem;
  font-weight: 560;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-flow-node__badge {
  max-width: 5.5rem;
  overflow: hidden;
  padding: 0.22rem 0.48rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--route-flow-node-accent) 12%, rgba(255, 255, 255, 0.06));
  color: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 74%, transparent);
  font-size: 0.63rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}

.route-flow-node__details {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  padding-top: 0.15rem;
}

.route-flow-node__body {
  color: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 70%, transparent);
  font-size: 0.76rem;
  line-height: 1.45;
  min-width: 0;
}

.route-flow-node__selected-pill {
  padding: 0.16rem 0.48rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--route-flow-node-accent) 18%, rgba(255, 255, 255, 0.06));
  color: color-mix(in srgb, var(--route-flow-node-accent) 84%, rgb(var(--v-theme-on-surface)) 16%);
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.route-flow-node__handle {
  width: 10px;
  height: 10px;
  border: 2px solid rgb(var(--v-theme-surface));
  background: color-mix(in srgb, var(--route-flow-node-accent) 88%, rgb(var(--v-theme-surface)) 12%);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--route-flow-node-accent) 24%, transparent);
}

.route-flow-node__handle--target {
  left: -6px;
}

.route-flow-node__handle--source {
  right: -6px;
}

.route-flow-node__source-label {
  position: absolute;
  right: 18px;
  z-index: 4;
  padding: 0.12rem 0.38rem;
  border: 1px solid color-mix(in srgb, var(--route-flow-node-accent) 18%, rgba(148, 163, 184, 0.24));
  border-radius: 999px;
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 94%, rgb(var(--v-theme-background)) 6%);
  color: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 72%, transparent);
  font-size: 0.61rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  line-height: 1.1;
  transform: translateY(-50%);
}
</style>
