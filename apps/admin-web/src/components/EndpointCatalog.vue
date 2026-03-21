<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { Endpoint } from "../types/endpoints";
import { resolveRoutePublicationStatus, routePublicationColor } from "../utils/routePublicationStatus";

const ITEMS_PER_PAGE = 8;

const props = withDefaults(defineProps<{
  activeEndpointId?: number | null;
  allowCreate?: boolean;
  allowDuplicate?: boolean;
  endpoints: Endpoint[];
  error: string | null;
  loading: boolean;
}>(), {
  activeEndpointId: null,
  allowCreate: true,
  allowDuplicate: true,
});

const emit = defineEmits<{
  create: [];
  duplicate: [endpointId: number];
  refresh: [];
  select: [endpointId: number];
}>();

const search = ref("");
const statusFilter = ref<"all" | "live" | "not_live" | "disabled">("all");
const methodFilter = ref("all");
const currentPage = ref(1);

const methodOptions = computed(() => {
  const methods = new Set(props.endpoints.map((endpoint) => endpoint.method));
  return ["all", ...Array.from(methods).sort()];
});

const filteredEndpoints = computed(() =>
  props.endpoints.filter((endpoint) => {
    const matchesSearch =
      !search.value.trim() ||
      [endpoint.name, endpoint.path, endpoint.category ?? "", endpoint.method]
        .join(" ")
        .toLowerCase()
        .includes(search.value.trim().toLowerCase());

    const matchesStatus =
      statusFilter.value === "all" ||
      (statusFilter.value === "live"
        ? resolveRoutePublicationStatus(endpoint).code === "published_live"
        : statusFilter.value === "disabled"
          ? resolveRoutePublicationStatus(endpoint).code === "disabled"
          : ["legacy_mock", "draft_only", "live_disabled"].includes(resolveRoutePublicationStatus(endpoint).code));

    const matchesMethod = methodFilter.value === "all" || endpoint.method === methodFilter.value;

    return matchesSearch && matchesStatus && matchesMethod;
  }),
);

const totalPages = computed(() => Math.max(1, Math.ceil(filteredEndpoints.value.length / ITEMS_PER_PAGE)));
const paginatedEndpoints = computed(() => {
  const start = (currentPage.value - 1) * ITEMS_PER_PAGE;
  return filteredEndpoints.value.slice(start, start + ITEMS_PER_PAGE);
});
const pageSummary = computed(() => {
  if (!filteredEndpoints.value.length) {
    return "No routes in the current result set";
  }

  const start = (currentPage.value - 1) * ITEMS_PER_PAGE + 1;
  const end = Math.min(start + ITEMS_PER_PAGE - 1, filteredEndpoints.value.length);
  return `Showing ${start}-${end} of ${filteredEndpoints.value.length} routes`;
});

watch([search, statusFilter, methodFilter], () => {
  currentPage.value = 1;
});

watch(totalPages, (value) => {
  if (currentPage.value > value) {
    currentPage.value = value;
  }
});

watch(
  [() => props.activeEndpointId, filteredEndpoints],
  ([activeEndpointId, endpoints]) => {
    if (!activeEndpointId) {
      return;
    }

    const activeIndex = endpoints.findIndex((endpoint) => endpoint.id === activeEndpointId);
    if (activeIndex === -1) {
      return;
    }

    const pageForActiveEndpoint = Math.floor(activeIndex / ITEMS_PER_PAGE) + 1;
    if (pageForActiveEndpoint !== currentPage.value) {
      currentPage.value = pageForActiveEndpoint;
    }
  },
  { immediate: true },
);
</script>

<template>
  <v-card class="workspace-card catalog-card">
    <v-card-item>
      <template #prepend>
        <v-avatar color="primary" variant="tonal">
          <v-icon icon="mdi-routes" />
        </v-avatar>
      </template>

      <v-card-title>Routes</v-card-title>
      <v-card-subtitle>Search, filter, and jump between routes by publication state.</v-card-subtitle>

      <template #append>
        <div class="d-flex ga-2">
          <v-btn
            :loading="loading && endpoints.length > 0"
            icon="mdi-refresh"
            variant="text"
            @click="emit('refresh')"
          />
          <v-btn v-if="allowCreate !== false" color="primary" prepend-icon="mdi-plus" @click="emit('create')">
            New
          </v-btn>
        </div>
      </template>
    </v-card-item>

    <v-card-text class="catalog-card-body d-flex flex-column ga-4">
      <v-text-field
        v-model="search"
        class="catalog-search"
        hide-details
        placeholder="Search by name, path, method, or category"
        prepend-inner-icon="mdi-magnify"
      />

      <div class="d-flex flex-wrap ga-3">
        <v-chip-group v-model="statusFilter" color="secondary" mandatory selected-class="text-secondary">
          <v-chip value="all" filter variant="outlined">All</v-chip>
          <v-chip value="live" filter variant="outlined">Live</v-chip>
          <v-chip value="not_live" filter variant="outlined">Not live</v-chip>
          <v-chip value="disabled" filter variant="outlined">Disabled</v-chip>
        </v-chip-group>

        <v-chip-group v-model="methodFilter" color="primary" mandatory selected-class="text-primary">
          <v-chip
            v-for="method in methodOptions"
            :key="method"
            :value="method"
            filter
            variant="outlined"
          >
            {{ method === "all" ? "Any method" : method }}
          </v-chip>
        </v-chip-group>
      </div>

      <div class="d-flex align-center justify-space-between flex-wrap ga-3">
        <div class="text-caption text-medium-emphasis">{{ pageSummary }}</div>
        <v-chip label size="small" variant="outlined">
          Page {{ currentPage }} / {{ totalPages }}
        </v-chip>
      </div>

      <div class="catalog-scroll-region">
        <v-alert v-if="error" border="start" class="mb-4" color="error" variant="tonal">
          {{ error }}
        </v-alert>

        <v-skeleton-loader
          v-if="loading && endpoints.length === 0"
          type="list-item-two-line, list-item-two-line, list-item-two-line, list-item-two-line"
        />

        <v-alert v-else-if="!filteredEndpoints.length && endpoints.length === 0 && !error" border="start" color="info" variant="tonal">
          No routes are available yet.
        </v-alert>

        <v-alert v-else-if="!filteredEndpoints.length" border="start" color="info" variant="tonal">
          No routes match the current filters.
        </v-alert>

        <v-list v-else class="catalog-list" rounded="xl">
          <v-list-item
            v-for="endpoint in paginatedEndpoints"
            :key="endpoint.id"
            :active="endpoint.id === activeEndpointId"
            class="catalog-item"
            rounded="xl"
            @click="emit('select', endpoint.id)"
          >
            <div class="catalog-item-shell">
              <span class="catalog-method-badge">{{ endpoint.method }}</span>

              <div class="catalog-item-main">
                <div class="catalog-item-title">{{ endpoint.name }}</div>

                <div class="catalog-item-subline">
                  <span class="catalog-item-path">{{ endpoint.path }}</span>
                  <span class="catalog-item-divider" aria-hidden="true">&bull;</span>
                  <span class="catalog-item-category">{{ endpoint.category || "uncategorized" }}</span>
                </div>
              </div>

              <div class="catalog-item-actions">
                <v-chip
                  class="catalog-status-chip"
                  :color="routePublicationColor(resolveRoutePublicationStatus(endpoint))"
                  density="compact"
                  label
                  size="small"
                  variant="tonal"
                >
                  {{ resolveRoutePublicationStatus(endpoint).label }}
                </v-chip>
                <v-btn
                  v-if="allowDuplicate !== false"
                  class="catalog-duplicate-btn"
                  aria-label="Duplicate route"
                  color="surface-variant"
                  density="compact"
                  icon="mdi-content-copy"
                  size="small"
                  variant="tonal"
                  @click.stop="emit('duplicate', endpoint.id)"
                />
              </div>
            </div>
          </v-list-item>
        </v-list>
      </div>

      <v-pagination
        v-if="filteredEndpoints.length > ITEMS_PER_PAGE"
        v-model="currentPage"
        aria-label="Catalog pagination"
        class="align-self-center"
        :length="totalPages"
        rounded="circle"
        :total-visible="5"
      />
    </v-card-text>
  </v-card>
</template>

<style scoped>
.catalog-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.catalog-card-body {
  flex: 1 1 auto;
  min-height: 0;
}

.catalog-search {
  flex: 0 0 auto;
}

.catalog-scroll-region {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overscroll-behavior: contain;
}

.catalog-item {
  margin-bottom: 0.35rem;
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 95%, rgb(var(--v-theme-background)) 5%);
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background-color 0.18s ease,
    box-shadow 0.18s ease;
}

.catalog-item:hover {
  transform: translateY(-1px);
  border-color: rgba(198, 123, 66, 0.28);
}

.catalog-item.v-list-item--active {
  border-color: rgba(36, 90, 125, 0.42);
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 84%, rgb(var(--v-theme-primary)) 16%);
  box-shadow: 0 0 0 1px rgba(36, 90, 125, 0.16);
}

.catalog-item-shell {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.9rem;
  width: 100%;
  padding: 0.2rem 0;
}

.catalog-item-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.24rem;
}

.catalog-method-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3rem;
  height: 1.8rem;
  padding: 0 0.65rem;
  border: 1px solid rgba(86, 163, 255, 0.28);
  border-radius: 999px;
  background: color-mix(in srgb, rgb(var(--v-theme-primary)) 16%, rgb(var(--v-theme-surface)) 84%);
  color: rgb(var(--v-theme-primary));
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  line-height: 1;
  flex-shrink: 0;
  align-self: center;
}

.catalog-item-title {
  min-width: 0;
  overflow: hidden;
  color: rgba(255, 255, 255, 0.96);
  font-size: 0.98rem;
  font-weight: 700;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.catalog-item-subline {
  display: flex;
  align-items: center;
  gap: 0.32rem;
  min-width: 0;
  color: rgba(203, 213, 225, 0.72);
  font-size: 0.78rem;
  line-height: 1.15;
}

.catalog-item-path,
.catalog-item-category {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.catalog-item-path {
  min-width: 0;
  font-family: var(--font-mono-primary);
}

.catalog-item-category {
  flex-shrink: 0;
  max-width: 7rem;
  color: rgba(148, 163, 184, 0.88);
}

.catalog-item-divider {
  color: rgba(100, 116, 139, 0.8);
  flex-shrink: 0;
}

.catalog-item-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
  min-width: max-content;
}

.catalog-status-chip {
  font-size: 0.7rem;
  letter-spacing: 0.01em;
  font-weight: 600;
}

.catalog-duplicate-btn {
  flex-shrink: 0;
}

.catalog-item :deep(.v-list-item__content) {
  overflow: visible;
}

.catalog-item :deep(.v-list-item__overlay) {
  opacity: 0;
}

@media (min-width: 1280px) {
  .catalog-card {
    height: 100%;
  }

  .catalog-scroll-region {
    flex: 1 1 auto;
    overflow-y: auto;
    padding-right: 0.35rem;
  }
}
</style>
