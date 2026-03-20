<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  AdminApiError,
  createConnection,
  deleteConnection,
  listConnections,
  updateConnection,
} from "../api/admin";
import ConnectionManagerCard from "../components/ConnectionManagerCard.vue";
import { useAuth } from "../composables/useAuth";
import type { Connection, ConnectionPayload } from "../types/endpoints";

const DEFAULT_CONNECTION_PROJECT = "default";
const DEFAULT_CONNECTION_ENVIRONMENT = "production";

const auth = useAuth();
const router = useRouter();

const connections = ref<Connection[]>([]);
const isLoading = ref(false);
const isSaving = ref(false);
const pageError = ref<string | null>(null);
const pageSuccess = ref<string | null>(null);

const canManageConnectors = computed(
  () => auth.canWriteRoutes.value && !auth.mustChangePassword.value,
);

function describeError(error: unknown, fallbackMessage: string): string {
  return error instanceof Error ? error.message : fallbackMessage;
}

async function loadConnections(): Promise<void> {
  if (!auth.session.value || !canManageConnectors.value) {
    connections.value = [];
    pageError.value = null;
    return;
  }

  isLoading.value = true;
  pageError.value = null;

  try {
    connections.value = await listConnections(auth.session.value);
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before managing connectors.");
      void router.push({ name: "login" });
      return;
    }
    pageError.value = describeError(error, "Unable to load connectors.");
  } finally {
    isLoading.value = false;
  }
}

watch(
  () => [auth.session.value?.token, canManageConnectors.value],
  () => {
    void loadConnections();
  },
  { immediate: true },
);

async function persistConnection(connectionId: number | null, payload: ConnectionPayload): Promise<void> {
  if (!auth.session.value) {
    pageError.value = "Sign in again before managing connectors.";
    return;
  }

  isSaving.value = true;
  pageError.value = null;
  pageSuccess.value = null;

  try {
    if (connectionId === null) {
      const created = await createConnection(payload, auth.session.value);
      pageSuccess.value = `Saved connector "${created.name}".`;
    } else {
      const updated = await updateConnection(connectionId, payload, auth.session.value);
      pageSuccess.value = `Updated connector "${updated.name}".`;
    }
    await loadConnections();
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before managing connectors.");
      void router.push({ name: "login" });
      return;
    }
    pageError.value = describeError(
      error,
      connectionId === null ? "Unable to create connector." : "Unable to update connector.",
    );
  } finally {
    isSaving.value = false;
  }
}

async function handleCreateConnection(payload: ConnectionPayload): Promise<void> {
  await persistConnection(null, payload);
}

async function handleUpdateConnection(connectionId: number, payload: ConnectionPayload): Promise<void> {
  await persistConnection(connectionId, payload);
}

async function handleDeleteConnection(connectionId: number): Promise<void> {
  if (!auth.session.value) {
    pageError.value = "Sign in again before managing connectors.";
    return;
  }

  isSaving.value = true;
  pageError.value = null;
  pageSuccess.value = null;

  try {
    await deleteConnection(connectionId, auth.session.value);
    pageSuccess.value = "Deleted connector.";
    await loadConnections();
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before managing connectors.");
      void router.push({ name: "login" });
      return;
    }
    pageError.value = describeError(error, "Unable to delete connector.");
  } finally {
    isSaving.value = false;
  }
}
</script>

<template>
  <div class="d-flex flex-column ga-4">
    <v-card class="connections-hero" rounded="xl">
      <v-card-item>
        <template #prepend>
          <v-avatar color="secondary" size="44" variant="tonal">
            <v-icon icon="mdi-connection" />
          </v-avatar>
        </template>
        <v-card-title>Connectors</v-card-title>
        <v-card-subtitle>
          Manage shared HTTP and Postgres connector credentials in one place. Flow nodes can keep binding these records
          by id without re-entering secrets per route.
        </v-card-subtitle>
      </v-card-item>
    </v-card>

    <v-alert
      v-if="pageSuccess"
      border="start"
      color="success"
      variant="tonal"
    >
      {{ pageSuccess }}
    </v-alert>
    <v-alert
      v-if="pageError"
      border="start"
      color="error"
      variant="tonal"
    >
      {{ pageError }}
    </v-alert>
    <v-alert
      v-if="!canManageConnectors"
      border="start"
      color="info"
      variant="tonal"
    >
      Your current role can browse routes but cannot manage connector credentials.
    </v-alert>

    <ConnectionManagerCard
      :can-write="canManageConnectors"
      :connections="connections"
      :error-message="pageError"
      :is-loading="isLoading"
      :is-saving="isSaving"
      :preferred-environment="DEFAULT_CONNECTION_ENVIRONMENT"
      :preferred-project="DEFAULT_CONNECTION_PROJECT"
      @create="handleCreateConnection"
      @delete="handleDeleteConnection"
      @refresh="loadConnections"
      @update="handleUpdateConnection"
    />
  </div>
</template>

<style scoped>
.connections-hero {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background:
    radial-gradient(circle at top left, rgba(36, 90, 125, 0.1), transparent 38%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.06), transparent 100%),
    color-mix(in srgb, rgb(var(--v-theme-surface)) 96%, rgb(var(--v-theme-background)) 4%);
}
</style>
