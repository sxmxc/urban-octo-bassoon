<script setup lang="ts">
import { computed, ref, watch } from "vue";

import type { Connection, ConnectionPayload, ConnectionType, JsonObject } from "../types/endpoints";

const DEFAULT_CONNECTION_PROJECT = "default";
const DEFAULT_CONNECTION_ENVIRONMENT = "production";

interface ConnectionFormState {
  project: string;
  environment: string;
  name: string;
  connector_type: ConnectionType;
  description: string;
  is_active: boolean;
  base_url: string;
  timeout_ms: string;
  headers_json: string;
  use_dsn: boolean;
  dsn: string;
  host: string;
  port: string;
  database: string;
  user: string;
  password: string;
  sslmode: string;
}

const props = withDefaults(
  defineProps<{
    connections?: Connection[];
    isLoading?: boolean;
    isSaving?: boolean;
    canWrite?: boolean;
    errorMessage?: string | null;
    preferredProject?: string;
    preferredEnvironment?: string;
  }>(),
  {
    connections: () => [],
    isLoading: false,
    isSaving: false,
    canWrite: false,
    errorMessage: null,
    preferredProject: DEFAULT_CONNECTION_PROJECT,
    preferredEnvironment: DEFAULT_CONNECTION_ENVIRONMENT,
  },
);

const emit = defineEmits<{
  create: [payload: ConnectionPayload];
  update: [connectionId: number, payload: ConnectionPayload];
  refresh: [];
}>();

const CONNECTOR_TYPE_OPTIONS: Array<{ title: string; value: ConnectionType }> = [
  { title: "HTTP Request", value: "http" },
  { title: "Postgres Query", value: "postgres" },
];

function normalizeScopeValue(value: string | null | undefined, fallback: string): string {
  const normalized = String(value ?? "").trim();
  return normalized || fallback;
}

function formatTimestamp(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "Not available yet";
}

function formatJsonObject(value: unknown): string {
  return value && typeof value === "object" && !Array.isArray(value) ? JSON.stringify(value, null, 2) : "";
}

function asJsonObject(value: unknown): JsonObject | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : null;
}

function buildEmptyForm(project: string, environment: string): ConnectionFormState {
  return {
    project,
    environment,
    name: "",
    connector_type: "http",
    description: "",
    is_active: true,
    base_url: "",
    timeout_ms: "",
    headers_json: "",
    use_dsn: false,
    dsn: "",
    host: "",
    port: "",
    database: "",
    user: "",
    password: "",
    sslmode: "",
  };
}

function buildFormFromConnection(
  connection: Connection | null,
  project: string,
  environment: string,
): ConnectionFormState {
  if (!connection) {
    return buildEmptyForm(project, environment);
  }

  const config = asJsonObject(connection.config) ?? {};
  const dsnValue = String(config.dsn ?? config.database_url ?? config.url ?? "").trim();

  return {
    project: normalizeScopeValue(connection.project, project),
    environment: normalizeScopeValue(connection.environment, environment),
    name: connection.name,
    connector_type: connection.connector_type,
    description: connection.description ?? "",
    is_active: connection.is_active,
    base_url: String(config.base_url ?? "").trim(),
    timeout_ms: config.timeout_ms == null ? "" : String(config.timeout_ms),
    headers_json: formatJsonObject(config.headers),
    use_dsn: Boolean(dsnValue),
    dsn: dsnValue,
    host: String(config.host ?? "").trim(),
    port: config.port == null ? "" : String(config.port),
    database: String(config.database ?? config.dbname ?? "").trim(),
    user: String(config.user ?? config.username ?? "").trim(),
    password: String(config.password ?? "").trim(),
    sslmode: String(config.sslmode ?? "").trim(),
  };
}

function parseJsonObjectInput(value: string, label: string): JsonObject | string {
  if (!value.trim()) {
    return {};
  }

  try {
    const parsed = JSON.parse(value);
    const objectValue = asJsonObject(parsed);
    return objectValue ?? `${label} must be a JSON object.`;
  } catch {
    return `${label} must be valid JSON.`;
  }
}

function buildConnectionPayloadFromForm(form: ConnectionFormState): ConnectionPayload | string {
  const project = normalizeScopeValue(form.project, DEFAULT_CONNECTION_PROJECT);
  const environment = normalizeScopeValue(form.environment, DEFAULT_CONNECTION_ENVIRONMENT);
  const name = form.name.trim();
  if (!name) {
    return "Connection name is required.";
  }

  const description = form.description.trim() || null;

  if (form.connector_type === "http") {
    const baseUrl = form.base_url.trim();
    if (!baseUrl) {
      return "HTTP connections require a base URL.";
    }

    const headers = parseJsonObjectInput(form.headers_json, "HTTP headers");
    if (typeof headers === "string") {
      return headers;
    }

    const config: JsonObject = {
      base_url: baseUrl,
    };
    if (Object.keys(headers).length > 0) {
      config.headers = headers;
    }
    if (form.timeout_ms.trim()) {
      const timeout = Number(form.timeout_ms.trim());
      if (!Number.isInteger(timeout) || timeout <= 0) {
        return "HTTP timeout must be a positive integer when provided.";
      }
      config.timeout_ms = timeout;
    }

    return {
      project,
      environment,
      name,
      connector_type: "http",
      description,
      config,
      is_active: form.is_active,
    };
  }

  const config: JsonObject = {};
  if (form.use_dsn) {
    const dsn = form.dsn.trim();
    if (!dsn) {
      return "Postgres connections require a DSN when DSN mode is enabled.";
    }
    config.dsn = dsn;
  } else {
    const host = form.host.trim();
    const database = form.database.trim();
    const user = form.user.trim();
    if (!host || !database || !user) {
      return "Postgres connections require host, database, and user when DSN mode is off.";
    }
    config.host = host;
    config.database = database;
    config.user = user;
    if (form.password.trim()) {
      config.password = form.password.trim();
    }
    if (form.port.trim()) {
      const port = Number(form.port.trim());
      if (!Number.isInteger(port) || port <= 0) {
        return "Postgres port must be a positive integer when provided.";
      }
      config.port = port;
    }
    if (form.sslmode.trim()) {
      config.sslmode = form.sslmode.trim();
    }
  }

  return {
    project,
    environment,
    name,
    connector_type: "postgres",
    description,
    config,
    is_active: form.is_active,
  };
}

function describeConnectionTarget(connection: Connection): string {
  const config = asJsonObject(connection.config) ?? {};
  if (connection.connector_type === "http") {
    const baseUrl = String(config.base_url ?? "").trim();
    const timeout = config.timeout_ms == null ? null : String(config.timeout_ms).trim();
    if (!baseUrl) {
      return "HTTP base URL is missing.";
    }
    return timeout ? `${baseUrl} · timeout ${timeout} ms` : baseUrl;
  }

  const host = String(config.host ?? "").trim();
  const database = String(config.database ?? config.dbname ?? "").trim();
  const dsn = String(config.dsn ?? config.database_url ?? config.url ?? "").trim();
  if (dsn) {
    return "DSN configured";
  }
  if (host && database) {
    return `${host} / ${database}`;
  }
  return "Postgres target is incomplete.";
}

function connectorColor(type: ConnectionType): string {
  return type === "http" ? "primary" : "secondary";
}

const normalizedPreferredProject = computed(() =>
  normalizeScopeValue(props.preferredProject, DEFAULT_CONNECTION_PROJECT),
);
const normalizedPreferredEnvironment = computed(() =>
  normalizeScopeValue(props.preferredEnvironment, DEFAULT_CONNECTION_ENVIRONMENT),
);
const filterProject = ref<string | null>(normalizedPreferredProject.value);
const filterEnvironment = ref<string | null>(normalizedPreferredEnvironment.value);
const editorDialog = ref(false);
const editingConnectionId = ref<number | null>(null);
const formError = ref<string | null>(null);
const pendingSubmit = ref(false);
const formState = ref<ConnectionFormState>(
  buildEmptyForm(normalizedPreferredProject.value, normalizedPreferredEnvironment.value),
);

watch(
  [normalizedPreferredProject, normalizedPreferredEnvironment],
  ([project, environment]) => {
    if (!editorDialog.value) {
      formState.value = buildEmptyForm(project, environment);
    }
  },
  { flush: "post" },
);

watch(
  () => props.isSaving,
  (nextValue, previousValue) => {
    if (!previousValue || nextValue || !pendingSubmit.value) {
      return;
    }

    pendingSubmit.value = false;
    if (!props.errorMessage) {
      closeDialog();
    }
  },
);

const projectOptions = computed(() =>
  Array.from(new Set([normalizedPreferredProject.value, ...props.connections.map((connection) => connection.project)])).sort(
    (left, right) => left.localeCompare(right),
  ),
);
const environmentOptions = computed(() =>
  Array.from(
    new Set([normalizedPreferredEnvironment.value, ...props.connections.map((connection) => connection.environment)]),
  ).sort((left, right) => left.localeCompare(right)),
);
const currentScopeLabel = computed(
  () => `${normalizedPreferredProject.value} / ${normalizedPreferredEnvironment.value}`,
);
const currentScopeConnectionCount = computed(
  () =>
    props.connections.filter(
      (connection) =>
        connection.project === normalizedPreferredProject.value &&
        connection.environment === normalizedPreferredEnvironment.value,
    ).length,
);
const filteredConnections = computed(() =>
  [...props.connections]
    .filter((connection) => (filterProject.value ? connection.project === filterProject.value : true))
    .filter((connection) => (filterEnvironment.value ? connection.environment === filterEnvironment.value : true))
    .sort((left, right) => {
      const leftPreferred =
        left.project === normalizedPreferredProject.value && left.environment === normalizedPreferredEnvironment.value;
      const rightPreferred =
        right.project === normalizedPreferredProject.value && right.environment === normalizedPreferredEnvironment.value;
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
const dialogTitle = computed(() => (editingConnectionId.value === null ? "New connection" : "Edit connection"));
const dialogError = computed(() => formError.value || (pendingSubmit.value ? props.errorMessage : null));

function isConnectionInPreferredScope(connection: Connection): boolean {
  return (
    connection.project === normalizedPreferredProject.value &&
    connection.environment === normalizedPreferredEnvironment.value
  );
}

function resetScopeFilters(): void {
  filterProject.value = normalizedPreferredProject.value;
  filterEnvironment.value = normalizedPreferredEnvironment.value;
}

function openCreateDialog(): void {
  editingConnectionId.value = null;
  formError.value = null;
  pendingSubmit.value = false;
  formState.value = buildEmptyForm(normalizedPreferredProject.value, normalizedPreferredEnvironment.value);
  editorDialog.value = true;
}

function openEditDialog(connection: Connection): void {
  editingConnectionId.value = connection.id;
  formError.value = null;
  pendingSubmit.value = false;
  formState.value = buildFormFromConnection(
    connection,
    normalizedPreferredProject.value,
    normalizedPreferredEnvironment.value,
  );
  editorDialog.value = true;
}

function closeDialog(): void {
  editorDialog.value = false;
  editingConnectionId.value = null;
  formError.value = null;
  pendingSubmit.value = false;
  formState.value = buildEmptyForm(normalizedPreferredProject.value, normalizedPreferredEnvironment.value);
}

function submitConnectionForm(): void {
  formError.value = null;
  const payload = buildConnectionPayloadFromForm(formState.value);
  if (typeof payload === "string") {
    formError.value = payload;
    return;
  }

  pendingSubmit.value = true;
  if (editingConnectionId.value === null) {
    emit("create", payload);
    return;
  }
  emit("update", editingConnectionId.value, payload);
}

function toggleConnectionActive(connection: Connection): void {
  emit("update", connection.id, {
    project: connection.project,
    environment: connection.environment,
    name: connection.name,
    connector_type: connection.connector_type,
    description: connection.description,
    config: connection.config,
    is_active: !connection.is_active,
  });
}
</script>

<template>
  <v-card class="workspace-card">
    <v-card-item>
      <template #prepend>
        <v-avatar color="secondary" variant="tonal">
          <v-icon icon="mdi-connection" />
        </v-avatar>
      </template>
      <v-card-title>Connections</v-card-title>
      <v-card-subtitle>
        Manage shared HTTP and Postgres connection records by project and environment. Flow nodes still bind a saved
        connection by id.
      </v-card-subtitle>

      <template #append>
        <div class="d-flex flex-wrap justify-end ga-2">
          <v-btn prepend-icon="mdi-refresh" variant="text" @click="emit('refresh')">Refresh</v-btn>
          <v-btn
            v-if="canWrite"
            color="primary"
            prepend-icon="mdi-plus-circle-outline"
            variant="tonal"
            @click="openCreateDialog"
          >
            New connection
          </v-btn>
        </div>
      </template>
    </v-card-item>

    <v-divider />

    <v-card-text class="d-flex flex-column ga-4">
      <div class="d-flex flex-wrap ga-2">
        <v-chip color="primary" label size="small" variant="tonal">Current scope · {{ currentScopeLabel }}</v-chip>
        <v-chip color="accent" label size="small" variant="tonal">
          {{ currentScopeConnectionCount }} in current route scope
        </v-chip>
        <v-chip color="secondary" label size="small" variant="outlined">{{ connections.length }} total saved</v-chip>
      </div>

      <v-alert v-if="errorMessage" border="start" color="error" density="compact" variant="tonal">
        {{ errorMessage }}
      </v-alert>

      <v-alert
        v-else-if="!isLoading && currentScopeConnectionCount === 0"
        border="start"
        color="warning"
        density="compact"
        variant="tonal"
      >
        No connections currently match the route's default scope. Create one for {{ currentScopeLabel }} or clear the
        filters below to inspect other scopes.
      </v-alert>

      <v-row dense>
        <v-col cols="12" md="5">
          <v-select
            v-model="filterProject"
            clearable
            density="compact"
            :items="projectOptions"
            label="Filter project"
            variant="outlined"
          />
        </v-col>
        <v-col cols="12" md="5">
          <v-select
            v-model="filterEnvironment"
            clearable
            density="compact"
            :items="environmentOptions"
            label="Filter environment"
            variant="outlined"
          />
        </v-col>
        <v-col cols="12" md="2" class="d-flex align-center justify-md-end">
          <v-btn block prepend-icon="mdi-target" variant="text" @click="resetScopeFilters">Current scope</v-btn>
        </v-col>
      </v-row>

      <v-skeleton-loader
        v-if="isLoading"
        type="table-row-divider, table-row-divider, table-row-divider"
      />
      <div v-else-if="filteredConnections.length === 0" class="text-body-2 text-medium-emphasis">
        No connections match the current filters.
      </div>
      <div v-else class="connection-manager__list">
        <v-sheet
          v-for="connection in filteredConnections"
          :key="connection.id"
          class="connection-manager__record pa-4"
          rounded="xl"
        >
          <div class="d-flex flex-column flex-lg-row justify-space-between ga-4">
            <div class="d-flex flex-column ga-2">
              <div class="d-flex flex-wrap align-center ga-2">
                <div class="text-subtitle-1 font-weight-medium">{{ connection.name }}</div>
                <v-chip :color="connectorColor(connection.connector_type)" label size="small" variant="tonal">
                  {{ connection.connector_type === "http" ? "HTTP" : "Postgres" }}
                </v-chip>
                <v-chip color="secondary" label size="small" variant="outlined">{{ connection.project }}</v-chip>
                <v-chip color="secondary" label size="small" variant="outlined">{{ connection.environment }}</v-chip>
                <v-chip
                  :color="connection.is_active ? 'accent' : 'error'"
                  label
                  size="small"
                  variant="tonal"
                >
                  {{ connection.is_active ? "Active" : "Inactive" }}
                </v-chip>
                <v-chip
                  v-if="isConnectionInPreferredScope(connection)"
                  color="primary"
                  label
                  size="small"
                  variant="outlined"
                >
                  Current route scope
                </v-chip>
              </div>

              <div class="text-body-2 text-medium-emphasis">{{ describeConnectionTarget(connection) }}</div>
              <div v-if="connection.description" class="text-body-2">{{ connection.description }}</div>
              <div class="text-caption text-medium-emphasis">Updated {{ formatTimestamp(connection.updated_at) }}</div>
            </div>

            <div v-if="canWrite" class="d-flex flex-wrap justify-end ga-2">
              <v-btn
                :disabled="isSaving"
                prepend-icon="mdi-pencil-outline"
                variant="outlined"
                @click="openEditDialog(connection)"
              >
                Edit
              </v-btn>
              <v-btn
                :color="connection.is_active ? 'error' : 'accent'"
                :disabled="isSaving"
                :prepend-icon="connection.is_active ? 'mdi-pause-circle-outline' : 'mdi-check-circle-outline'"
                variant="tonal"
                @click="toggleConnectionActive(connection)"
              >
                {{ connection.is_active ? "Retire" : "Reactivate" }}
              </v-btn>
            </div>
          </div>
        </v-sheet>
      </div>
    </v-card-text>

    <v-dialog v-model="editorDialog" max-width="900">
      <v-card>
        <v-card-item>
          <v-card-title>{{ dialogTitle }}</v-card-title>
          <v-card-subtitle>
            Scope connection records to the route's current project and deployment environment so operators can rotate
            credentials without losing context.
          </v-card-subtitle>
        </v-card-item>

        <v-divider />

        <v-card-text class="d-flex flex-column ga-4">
          <v-alert v-if="dialogError" border="start" color="error" density="compact" variant="tonal">
            {{ dialogError }}
          </v-alert>

          <v-row dense>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="formState.project"
                density="compact"
                label="Project"
                placeholder="default"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="formState.environment"
                density="compact"
                label="Environment"
                placeholder="production"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="formState.name" density="compact" label="Connection name" variant="outlined" />
            </v-col>
            <v-col cols="12" md="6">
              <v-select
                v-model="formState.connector_type"
                :disabled="editingConnectionId !== null"
                density="compact"
                :items="CONNECTOR_TYPE_OPTIONS"
                label="Connector type"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12">
              <v-text-field
                v-model="formState.description"
                density="compact"
                label="Description"
                placeholder="Optional operator note"
                variant="outlined"
              />
            </v-col>
          </v-row>

          <v-switch
            v-model="formState.is_active"
            color="accent"
            density="compact"
            inset
            label="Connection is active"
          />

          <template v-if="formState.connector_type === 'http'">
            <div class="text-subtitle-2">HTTP configuration</div>
            <v-row dense>
              <v-col cols="12" md="8">
                <v-text-field
                  v-model="formState.base_url"
                  density="compact"
                  label="Base URL"
                  placeholder="https://api.example.com"
                  variant="outlined"
                />
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model="formState.timeout_ms"
                  density="compact"
                  label="Timeout (ms)"
                  placeholder="2500"
                  variant="outlined"
                />
              </v-col>
              <v-col cols="12">
                <v-textarea
                  v-model="formState.headers_json"
                  auto-grow
                  class="connection-manager__json-input"
                  label="Shared headers JSON"
                  rows="5"
                  variant="outlined"
                />
              </v-col>
            </v-row>
          </template>

          <template v-else>
            <div class="text-subtitle-2">Postgres configuration</div>
            <v-switch
              v-model="formState.use_dsn"
              color="secondary"
              density="compact"
              inset
              label="Use DSN instead of individual fields"
            />

            <template v-if="formState.use_dsn">
              <v-textarea
                v-model="formState.dsn"
                auto-grow
                class="connection-manager__json-input"
                label="DSN"
                rows="4"
                variant="outlined"
              />
            </template>

            <v-row v-else dense>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="formState.host"
                  density="compact"
                  label="Host"
                  placeholder="db.internal"
                  variant="outlined"
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="formState.database"
                  density="compact"
                  label="Database"
                  placeholder="mockingbird"
                  variant="outlined"
                />
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model="formState.user"
                  density="compact"
                  label="User"
                  placeholder="readonly"
                  variant="outlined"
                />
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model="formState.password"
                  density="compact"
                  label="Password"
                  placeholder="Optional"
                  type="password"
                  variant="outlined"
                />
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model="formState.port"
                  density="compact"
                  label="Port"
                  placeholder="5432"
                  variant="outlined"
                />
              </v-col>
              <v-col cols="12">
                <v-text-field
                  v-model="formState.sslmode"
                  density="compact"
                  label="SSL mode"
                  placeholder="require"
                  variant="outlined"
                />
              </v-col>
            </v-row>
          </template>
        </v-card-text>

        <v-divider />

        <v-card-actions class="justify-end">
          <v-btn :disabled="isSaving" variant="text" @click="closeDialog">Cancel</v-btn>
          <v-btn
            color="primary"
            :loading="isSaving && pendingSubmit"
            prepend-icon="mdi-content-save-outline"
            variant="tonal"
            @click="submitConnectionForm"
          >
            Save connection
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<style scoped>
.connection-manager__list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.connection-manager__record {
  border: 1px solid rgba(99, 115, 129, 0.18);
  background:
    linear-gradient(135deg, rgba(9, 30, 66, 0.04), transparent 50%),
    rgba(255, 255, 255, 0.78);
}

.connection-manager__json-input :deep(textarea) {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}
</style>
