<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  AdminApiError,
  getExecution,
  getExecutionTelemetryOverview,
  getCurrentRouteImplementation,
  listConnections,
  createEndpoint,
  deleteEndpoint,
  exportEndpointBundle,
  importEndpointBundle,
  listExecutions,
  listEndpoints,
  listRouteDeployments,
  publishRouteImplementation,
  saveCurrentRouteImplementation,
  unpublishRouteDeployment,
  updateEndpoint,
} from "../api/admin";
import EndpointCatalog from "../components/EndpointCatalog.vue";
import EndpointSettingsForm from "../components/EndpointSettingsForm.vue";
import RouteContractEditor from "../components/RouteContractEditor.vue";
import RouteFlowEditor from "../components/RouteFlowEditor.vue";
import { useAuth } from "../composables/useAuth";
import type {
  Connection,
  Endpoint,
  EndpointBundle,
  EndpointDraft,
  EndpointImportMode,
  EndpointImportOperation,
  EndpointImportResponse,
  EndpointImportSummary,
  ExecutionRun,
  ExecutionRunDetail,
  ExecutionTelemetryOverview,
  RouteFlowDefinition,
  RouteDeployment,
  RouteImplementation,
} from "../types/endpoints";
import { normalizeRouteFlowDefinition, serializeRouteFlowDefinition } from "../utils/routeFlow";
import {
  resolveRuntimeRoutePublicationStatus,
  routePublicationColor,
} from "../utils/routePublicationStatus";
import { buildRouteTestState } from "../utils/routeTestState";
import {
  buildPayload,
  createDuplicateDraft,
  createEmptyDraft,
  describeAdminError,
  draftFromEndpoint,
} from "../utils/endpointDrafts";

const CATALOG_BACKGROUND_REFRESH_MS = 30_000;
const CATALOG_STALE_AFTER_MS = 15_000;
const DEFAULT_CONNECTION_PROJECT = "default";
const DEFAULT_CONNECTION_ENVIRONMENT = "production";
type RouteWorkspaceTab = "overview" | "contract" | "flow" | "test" | "deploy";
type ContractSchemaTab = "request" | "response";
type ContractRequestSection = "body" | "path" | "query";
const ROUTE_WORKSPACE_TABS: RouteWorkspaceTab[] = ["overview", "contract", "flow", "test", "deploy"];

const props = defineProps<{
  mode: "browse" | "create" | "edit";
}>();

const route = useRoute();
const router = useRouter();
const auth = useAuth();

const endpoints = ref<Endpoint[]>([]);
const draft = ref<EndpointDraft>(createEmptyDraft());
const fieldErrors = ref<Record<string, string>>({});
const isLoading = ref(false);
const isSaving = ref(false);
const catalogError = ref<string | null>(null);
const pageError = ref<string | null>(null);
const pageSuccess = ref<string | null>(null);
const lastCatalogSyncAt = ref<number | null>(null);
const isExporting = ref(false);
const importDialog = ref(false);
const importMode = ref<EndpointImportMode>("upsert");
const importFile = ref<File | null>(null);
const importText = ref("");
const importPreview = ref<EndpointImportResponse | null>(null);
const importError = ref<string | null>(null);
const isPreviewingImport = ref(false);
const isApplyingImport = ref(false);
const currentImplementation = ref<RouteImplementation | null>(null);
const flowEditorError = ref<string | null>(null);
const flowValidationError = ref<string | null>(null);
const flowDraftDefinition = shallowRef<RouteFlowDefinition>(normalizeRouteFlowDefinition({}));
const isFlowEditorInFocusMode = ref(false);
const isLoadingImplementation = ref(false);
const isSavingImplementation = ref(false);
const deployments = ref<RouteDeployment[]>([]);
const isLoadingDeployments = ref(false);
const isPublishingDeployment = ref(false);
const isUnpublishingDeployment = ref(false);
const executions = ref<ExecutionRun[]>([]);
const isLoadingExecutions = ref(false);
const selectedExecutionId = ref<number | null>(null);
const selectedExecutionDetail = ref<ExecutionRunDetail | null>(null);
const isLoadingExecutionDetail = ref(false);
const executionDetailError = ref<string | null>(null);
const executionTelemetry = ref<ExecutionTelemetryOverview | null>(null);
const isLoadingExecutionTelemetry = ref(false);
const executionTelemetryError = ref<string | null>(null);
const connections = ref<Connection[]>([]);
const isLoadingConnections = ref(false);
const activeContractRequestSection = ref<ContractRequestSection>("body");

let catalogRefreshTimer: number | null = null;
let pendingCatalogRequest: Promise<void> | null = null;
let pendingExecutionTelemetryRequest: Promise<void> | null = null;
let removeFlowNavigationGuard: (() => void) | null = null;
// Ignore out-of-order execution-detail responses when operators switch runs quickly.
let executionDetailRequestToken = 0;
let nextSelectedEndpointDraftOverride: EndpointDraft | null = null;

const importModeOptions: Array<{ title: string; value: EndpointImportMode }> = [
  {
    title: "Upsert existing routes",
    value: "upsert",
  },
  {
    title: "Create only",
    value: "create_only",
  },
  {
    title: "Replace all routes",
    value: "replace_all",
  },
];

const endpointId = computed(() => {
  const rawId = route.params.endpointId;
  return typeof rawId === "string" ? Number(rawId) : null;
});

const duplicateSourceId = computed(() => {
  const rawId = Array.isArray(route.query.duplicateFrom) ? route.query.duplicateFrom[0] : route.query.duplicateFrom;
  if (typeof rawId !== "string") {
    return null;
  }

  const parsed = Number(rawId);
  return Number.isFinite(parsed) ? parsed : null;
});

const selectedEndpoint = computed(() =>
  endpointId.value ? endpoints.value.find((endpoint) => endpoint.id === endpointId.value) ?? null : null,
);
const selectedPublicationStatus = computed(() =>
  selectedEndpoint.value
    ? resolveRuntimeRoutePublicationStatus(selectedEndpoint.value, currentImplementation.value, deployments.value)
    : null,
);
const selectedEndpointSyncKey = computed(() =>
  selectedEndpoint.value ? `${selectedEndpoint.value.id}:${selectedEndpoint.value.updated_at}` : null,
);
const duplicateSource = computed(() =>
  duplicateSourceId.value ? endpoints.value.find((endpoint) => endpoint.id === duplicateSourceId.value) ?? null : null,
);
const duplicateRequestNonce = computed(() => {
  const rawValue = Array.isArray(route.query.duplicateNonce) ? route.query.duplicateNonce[0] : route.query.duplicateNonce;
  return typeof rawValue === "string" ? rawValue : "";
});
const createDraftHydrationKey = computed(() => {
  if (props.mode !== "create") {
    return null;
  }

  if (!duplicateSourceId.value) {
    return `new:${duplicateRequestNonce.value || "fresh"}`;
  }

  return `${duplicateSourceId.value}:${duplicateRequestNonce.value}:${duplicateSource.value ? "ready" : "pending"}`;
});
const savedQueryFlag = computed(() => {
  const rawValue = Array.isArray(route.query.saved) ? route.query.saved[0] : route.query.saved;
  return rawValue === "1";
});
const activeWorkspaceTab = computed<RouteWorkspaceTab>(() => {
  const rawTab = Array.isArray(route.query.tab) ? route.query.tab[0] : route.query.tab;
  if (typeof rawTab === "string" && ROUTE_WORKSPACE_TABS.includes(rawTab as RouteWorkspaceTab)) {
    if (props.mode === "create" && rawTab !== "overview") {
      return "overview";
    }
    return rawTab as RouteWorkspaceTab;
  }

  return "overview";
});

const isInitialCatalogLoad = computed(() => isLoading.value && endpoints.value.length === 0);
const isSelectedEndpointDraftDirty = computed(() => {
  if (props.mode !== "edit" || !selectedEndpoint.value) {
    return false;
  }

  return JSON.stringify(draft.value) !== JSON.stringify(draftFromEndpoint(selectedEndpoint.value));
});
const recordTransitionKey = computed(() =>
  props.mode === "create" ? "create" : selectedEndpoint.value ? `endpoint-${selectedEndpoint.value.id}` : "empty",
);
const duplicateBanner = computed(() => {
  if (props.mode !== "create" || !duplicateSource.value) {
    return null;
  }

  return `Copied settings from ${duplicateSource.value.name}. Review the new name and path before saving.`;
});
const availableCategories = computed(() =>
  Array.from(
    new Set(
      endpoints.value
        .map((endpoint) => endpoint.category?.trim() ?? "")
        .filter(Boolean),
    ),
  ).sort((left, right) => left.localeCompare(right)),
);
const availableTags = computed(() =>
  Array.from(
    new Set(
      endpoints.value
        .flatMap((endpoint) => endpoint.tags)
        .map((tag) => tag.trim())
        .filter(Boolean),
    ),
  ).sort((left, right) => left.localeCompare(right)),
);
const canApplyImport = computed(() =>
  Boolean(importPreview.value) && !importPreview.value?.has_errors && !isPreviewingImport.value && !isApplyingImport.value,
);
const canWriteRoutes = computed(() => auth.canWriteRoutes.value && !auth.mustChangePassword.value);
const canPreviewRoutes = computed(() => auth.canPreviewRoutes.value && !auth.mustChangePassword.value);
const activeContractSchemaTab = computed<ContractSchemaTab>(() => {
  const rawTab = Array.isArray(route.query.contractTab) ? route.query.contractTab[0] : route.query.contractTab;
  if (rawTab === "request") {
    return "request";
  }
  return "response";
});
const contractEditorPath = computed(() => selectedEndpoint.value?.path ?? draft.value.path);

function stripContractFields(source: EndpointDraft): Omit<EndpointDraft, "request_schema" | "response_schema" | "seed_key"> {
  return {
    name: source.name,
    method: source.method,
    path: source.path,
    category: source.category,
    tags: source.tags,
    summary: source.summary,
    description: source.description,
    enabled: source.enabled,
    auth_mode: source.auth_mode,
    success_status_code: source.success_status_code,
    error_rate: source.error_rate,
    latency_min_ms: source.latency_min_ms,
    latency_max_ms: source.latency_max_ms,
  };
}

const isContractDirty = computed(() => {
  if (props.mode !== "edit" || !selectedEndpoint.value) {
    return false;
  }

  return (
    JSON.stringify(draft.value.request_schema) !== JSON.stringify(selectedEndpoint.value.request_schema ?? {}) ||
    JSON.stringify(draft.value.response_schema) !== JSON.stringify(selectedEndpoint.value.response_schema ?? {}) ||
    draft.value.seed_key !== (selectedEndpoint.value.seed_key ?? "")
  );
});
const hasNonContractDraftChanges = computed(() => {
  if (props.mode !== "edit" || !selectedEndpoint.value) {
    return false;
  }

  return JSON.stringify(stripContractFields(draft.value)) !== JSON.stringify(stripContractFields(draftFromEndpoint(selectedEndpoint.value)));
});
const routeTabs = computed(() => [
  {
    title: "Overview",
    value: "overview" as RouteWorkspaceTab,
    disabled: false,
  },
  {
    title: "Contract",
    value: "contract" as RouteWorkspaceTab,
    disabled: props.mode === "create",
  },
  {
    title: "Flow",
    value: "flow" as RouteWorkspaceTab,
    disabled: props.mode === "create",
  },
  {
    title: "Test",
    value: "test" as RouteWorkspaceTab,
    disabled: props.mode === "create",
  },
  {
    title: "Deploy",
    value: "deploy" as RouteWorkspaceTab,
    disabled: props.mode === "create",
  },
]);
const implementationNodeCount = computed(() => {
  return flowDraftDefinition.value.nodes.length;
});
const implementationEdgeCount = computed(() => {
  return flowDraftDefinition.value.edges.length;
});
function serializeFlowDefinitionForComparison(definition: RouteFlowDefinition): string {
  return JSON.stringify(serializeRouteFlowDefinition(definition));
}

const formattedCurrentFlowDefinition = computed(() =>
  serializeFlowDefinitionForComparison(normalizeRouteFlowDefinition(currentImplementation.value?.flow_definition ?? {})),
);
const serializedFlowDraftDefinition = computed(() => serializeFlowDefinitionForComparison(flowDraftDefinition.value));
const isFlowDirty = computed(
  () =>
    props.mode === "edit" &&
    Boolean(selectedEndpoint.value) &&
    serializedFlowDraftDefinition.value !== formattedCurrentFlowDefinition.value,
);
const shouldWarnOnUnsavedFlowChanges = computed(
  () => props.mode === "edit" && Boolean(selectedEndpoint.value) && isFlowDirty.value,
);
const activeDeployment = computed(() => deployments.value.find((deployment) => deployment.is_active) ?? null);
const routeConnectionProject = computed(() => DEFAULT_CONNECTION_PROJECT);
const routeConnectionEnvironment = computed(
  () => activeDeployment.value?.environment?.trim() || DEFAULT_CONNECTION_ENVIRONMENT,
);
const routeConnectionScopeLabel = computed(() => `${routeConnectionProject.value} / ${routeConnectionEnvironment.value}`);
const scopedConnectionCount = computed(() =>
  connections.value.filter(
    (connection) =>
      connection.project === routeConnectionProject.value && connection.environment === routeConnectionEnvironment.value,
  ).length,
);
const hasDeploymentHistory = computed(() => deployments.value.length > 0);
const routeTestState = computed(() =>
  selectedEndpoint.value ? buildRouteTestState(selectedEndpoint.value, currentImplementation.value, deployments.value) : null,
);
const deploymentStatusTitle = computed(() => {
  return activeDeployment.value ? "Active deployment" : "Live status";
});
const deploymentHeadline = computed(() => {
  if (activeDeployment.value) {
    return `Implementation ${activeDeployment.value.implementation_id}`;
  }
  return hasDeploymentHistory.value ? "Live disabled" : "Not published";
});
const deploymentSummary = computed(() => {
  if (activeDeployment.value) {
    return `Published ${formatTimestamp(activeDeployment.value.published_at)}`;
  }
  if (hasDeploymentHistory.value) {
    return "This route has deployment history but no active live deployment.";
  }
  return "Publish this route when the draft is ready.";
});
const browseMethodMix = computed(() => {
  const methodCounts = new Map<string, number>();

  for (const endpoint of endpoints.value) {
    const method = endpoint.method.trim().toUpperCase() || "UNKNOWN";
    methodCounts.set(method, (methodCounts.get(method) ?? 0) + 1);
  }

  return Array.from(methodCounts.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
});
const browseCategoryMix = computed(() => {
  const categoryCounts = new Map<string, number>();
  let uncategorizedCount = 0;

  for (const endpoint of endpoints.value) {
    const rawCategory = endpoint.category?.trim() ?? "";
    if (!rawCategory) {
      uncategorizedCount += 1;
      continue;
    }
    categoryCounts.set(rawCategory, (categoryCounts.get(rawCategory) ?? 0) + 1);
  }

  const categories = Array.from(categoryCounts.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));

  if (uncategorizedCount > 0) {
    categories.push({
      label: "Uncategorized",
      count: uncategorizedCount,
    });
  }

  return categories;
});
const browseRouteMetrics = computed(() => {
  const total = endpoints.value.length;
  let publicCount = 0;
  let liveRuntimeCount = 0;
  let legacyMockCount = 0;
  let disabledCount = 0;

  for (const endpoint of endpoints.value) {
    if (endpoint.publication_status.is_public) {
      publicCount += 1;
    }
    if (endpoint.publication_status.is_live) {
      liveRuntimeCount += 1;
    }
    if (endpoint.publication_status.uses_legacy_mock) {
      legacyMockCount += 1;
    }
    if (!endpoint.enabled || endpoint.publication_status.code === "disabled") {
      disabledCount += 1;
    }
  }

  return {
    total,
    publicCount,
    liveRuntimeCount,
    legacyMockCount,
    privateCount: Math.max(total - publicCount, 0),
    disabledCount,
  };
});
const executionTelemetrySnapshot = computed<ExecutionTelemetryOverview>(() => {
  return (
    executionTelemetry.value ?? {
      sample_limit: 200,
      sampled_runs: 0,
      sampled_steps: 0,
      route_count: 0,
      success_runs: 0,
      error_runs: 0,
      success_rate: null,
      average_response_time_ms: null,
      p95_response_time_ms: null,
      average_flow_time_ms: null,
      p95_flow_time_ms: null,
      average_steps_per_run: null,
      latest_completed_at: null,
      precise_step_run_count: 0,
      slow_routes: [],
      slow_flow_steps: [],
    }
  );
});
const hasExecutionTelemetry = computed(() => executionTelemetrySnapshot.value.sampled_runs > 0);
const endpointIndex = computed(() => new Map(endpoints.value.map((endpoint) => [endpoint.id, endpoint])));
const telemetrySlowRoutes = computed(() =>
  executionTelemetrySnapshot.value.slow_routes.map((summary) => ({
    summary,
    endpoint: endpointIndex.value.get(summary.route_id) ?? null,
  })),
);
const telemetrySlowFlowSteps = computed(() =>
  executionTelemetrySnapshot.value.slow_flow_steps.map((summary) => ({
    summary,
    endpoint: endpointIndex.value.get(summary.route_id) ?? null,
  })),
);

function mergeEndpointCatalog(nextEndpoints: Endpoint[]): Endpoint[] {
  const currentEndpointsById = new Map(endpoints.value.map((endpoint) => [endpoint.id, endpoint]));
  const preserveEndpointId =
    isSelectedEndpointDraftDirty.value && selectedEndpoint.value ? selectedEndpoint.value.id : null;

  return nextEndpoints.map((endpoint) => {
    const previous = currentEndpointsById.get(endpoint.id);
    if (!previous) {
      return endpoint;
    }

    if (preserveEndpointId !== null && endpoint.id === preserveEndpointId) {
      return previous;
    }

    return JSON.stringify(previous) === JSON.stringify(endpoint) ? previous : endpoint;
  });
}

function hasStaleCatalog(): boolean {
  return lastCatalogSyncAt.value === null || Date.now() - lastCatalogSyncAt.value >= CATALOG_STALE_AFTER_MS;
}

async function fetchEndpoints(options: { background?: boolean } = {}): Promise<void> {
  if (!auth.session.value) {
    endpoints.value = [];
    catalogError.value = null;
    lastCatalogSyncAt.value = null;
    return;
  }

  if (pendingCatalogRequest) {
    return pendingCatalogRequest;
  }

  isLoading.value = true;
  if (!options.background || endpoints.value.length === 0) {
    catalogError.value = null;
  }

  pendingCatalogRequest = (async () => {
    try {
      const nextEndpoints = await listEndpoints(auth.session.value!);
      endpoints.value = mergeEndpointCatalog(nextEndpoints);
      catalogError.value = null;
      lastCatalogSyncAt.value = Date.now();
      if (props.mode === "browse") {
        void fetchExecutionTelemetry({ background: options.background });
      }
    } catch (error) {
      if (error instanceof AdminApiError && error.status === 401) {
        void auth.logout("Your admin session expired. Sign in again to keep editing.");
        void router.push({ name: "login" });
        return;
      }

      catalogError.value =
        endpoints.value.length > 0
          ? `Showing the last synced catalog. ${describeAdminError(error, "Unable to refresh the route catalog.")}`
          : describeAdminError(error, "Unable to load endpoints.");
    } finally {
      isLoading.value = false;
      pendingCatalogRequest = null;
    }
  })();

  return pendingCatalogRequest;
}

async function fetchExecutionTelemetry(options: { background?: boolean } = {}): Promise<void> {
  if (!auth.session.value || props.mode !== "browse") {
    executionTelemetry.value = null;
    executionTelemetryError.value = null;
    return;
  }

  if (pendingExecutionTelemetryRequest) {
    return pendingExecutionTelemetryRequest;
  }

  isLoadingExecutionTelemetry.value = true;
  if (!options.background || executionTelemetry.value === null) {
    executionTelemetryError.value = null;
  }

  pendingExecutionTelemetryRequest = (async () => {
    try {
      executionTelemetry.value = await getExecutionTelemetryOverview(auth.session.value!, {
        limit: 200,
        top: 5,
      });
      executionTelemetryError.value = null;
    } catch (error) {
      if (error instanceof AdminApiError && error.status === 401) {
        void auth.logout("Your admin session expired. Sign in again to keep editing.");
        void router.push({ name: "login" });
        return;
      }

      executionTelemetryError.value =
        executionTelemetry.value !== null
          ? `Showing the last sampled telemetry. ${describeAdminError(error, "Unable to refresh runtime telemetry.")}`
          : describeAdminError(error, "Unable to load runtime telemetry.");
    } finally {
      isLoadingExecutionTelemetry.value = false;
      pendingExecutionTelemetryRequest = null;
    }
  })();

  return pendingExecutionTelemetryRequest;
}

function refreshCatalogInBackground(force = false): void {
  if (!auth.session.value || pendingCatalogRequest) {
    return;
  }

  if (typeof document !== "undefined" && document.visibilityState === "hidden") {
    return;
  }

  if (!force && !hasStaleCatalog()) {
    return;
  }

  void fetchEndpoints({ background: true });
}

watch(
  () => auth.session.value,
  (session) => {
    if (!session) {
      endpoints.value = [];
      catalogError.value = null;
      lastCatalogSyncAt.value = null;
      executionTelemetry.value = null;
      executionTelemetryError.value = null;
      return;
    }

    void fetchEndpoints();
  },
  { immediate: true },
);

watch(
  () => props.mode,
  (mode) => {
    if (mode === "browse" && auth.session.value) {
      void fetchExecutionTelemetry();
      return;
    }

    executionTelemetryError.value = null;
  },
  { immediate: true },
);

watch(
  createDraftHydrationKey,
  (currentKey, previousKey) => {
    if (props.mode !== "create" || !currentKey || currentKey === previousKey) {
      return;
    }

    fieldErrors.value = {};
    pageError.value = null;
    pageSuccess.value = savedQueryFlag.value ? "Saved endpoint settings." : null;
    draft.value = duplicateSource.value
      ? createDuplicateDraft(duplicateSource.value, endpoints.value)
      : createEmptyDraft();
  },
  { immediate: true },
);

watch(
  [selectedEndpointSyncKey, endpointId],
  ([currentKey, currentEndpointId], previousValues) => {
    const [previousKey, previousEndpointId] = previousValues ?? [null, null];
    if (props.mode !== "edit" || !currentKey || currentKey === previousKey) {
      return;
    }

    fieldErrors.value = {};
    pageError.value = null;

    if (currentEndpointId !== previousEndpointId) {
      pageSuccess.value = savedQueryFlag.value ? "Saved endpoint settings." : null;
      activeContractRequestSection.value = "body";
    }

    if (selectedEndpoint.value) {
      if (nextSelectedEndpointDraftOverride) {
        draft.value = nextSelectedEndpointDraftOverride;
        nextSelectedEndpointDraftOverride = null;
      } else {
        draft.value = draftFromEndpoint(selectedEndpoint.value);
      }
    }
  },
  { immediate: true },
);

watch(
  () => selectedEndpoint.value?.id ?? null,
  (currentEndpointId, previousEndpointId) => {
    if (props.mode !== "edit" || !currentEndpointId || currentEndpointId === previousEndpointId) {
      if (!currentEndpointId) {
        currentImplementation.value = null;
        deployments.value = [];
        executions.value = [];
        flowEditorError.value = null;
        flowValidationError.value = null;
        flowDraftDefinition.value = normalizeRouteFlowDefinition({});
      }
      return;
    }

    void loadRouteRuntimeScaffolding(currentEndpointId);
  },
  { immediate: true },
);

watch(
  () => props.mode,
  (mode, previousMode) => {
    if (mode === previousMode) {
      return;
    }

    if (mode === "browse") {
      fieldErrors.value = {};
      pageError.value = null;
      if (!savedQueryFlag.value) {
        pageSuccess.value = null;
      }
    }

    if (mode === "create") {
      setActiveWorkspaceTab("overview");
      currentImplementation.value = null;
      deployments.value = [];
      executions.value = [];
      flowEditorError.value = null;
      flowValidationError.value = null;
      flowDraftDefinition.value = normalizeRouteFlowDefinition({});
      isFlowEditorInFocusMode.value = false;
    }
  },
);

watch([importMode, importText, importFile], () => {
  importPreview.value = null;
  importError.value = null;
});

watch(importDialog, (isOpen) => {
  if (isOpen) {
    return;
  }

  importMode.value = "upsert";
  importFile.value = null;
  importText.value = "";
  importPreview.value = null;
  importError.value = null;
  isPreviewingImport.value = false;
  isApplyingImport.value = false;
});

watch(serializedFlowDraftDefinition, (currentValue, previousValue) => {
  if (previousValue === undefined || currentValue === previousValue) {
    return;
  }

  flowEditorError.value = null;
});

watch(activeWorkspaceTab, (tab) => {
  if (tab !== "flow") {
    isFlowEditorInFocusMode.value = false;
  }
});

function handleWindowFocus(): void {
  refreshCatalogInBackground();
}

function handleWindowOnline(): void {
  refreshCatalogInBackground(true);
}

function handleVisibilityChange(): void {
  if (document.visibilityState === "visible") {
    refreshCatalogInBackground();
  }
}

function parseRouteEndpointId(rawId: unknown): number | null {
  if (typeof rawId === "string" && rawId.trim().length > 0) {
    const parsed = Number(rawId);
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (Array.isArray(rawId) && rawId.length > 0) {
    return parseRouteEndpointId(rawId[0]);
  }
  return null;
}

function shouldConfirmFlowNavigation(nextEndpointId: number | null, nextRouteName: string | symbol | null | undefined): boolean {
  if (!shouldWarnOnUnsavedFlowChanges.value) {
    return false;
  }
  if (nextRouteName === "endpoints-edit" && nextEndpointId === endpointId.value) {
    return false;
  }
  return true;
}

function confirmFlowNavigationLoss(): boolean {
  return window.confirm("You have unsaved Flow changes. Leave this route and discard the current flow draft?");
}

function handleBeforeUnload(event: BeforeUnloadEvent): void {
  if (!shouldWarnOnUnsavedFlowChanges.value) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
}

watch(
  shouldWarnOnUnsavedFlowChanges,
  (value) => {
    if (typeof window === "undefined") {
      return;
    }

    if (value) {
      window.addEventListener("beforeunload", handleBeforeUnload);
      return;
    }

    window.removeEventListener("beforeunload", handleBeforeUnload);
  },
  { immediate: true },
);

onMounted(() => {
  if (typeof window === "undefined") {
    return;
  }

  catalogRefreshTimer = window.setInterval(() => {
    refreshCatalogInBackground();
  }, CATALOG_BACKGROUND_REFRESH_MS);

  window.addEventListener("focus", handleWindowFocus);
  window.addEventListener("online", handleWindowOnline);
  document.addEventListener("visibilitychange", handleVisibilityChange);

  removeFlowNavigationGuard = router.beforeEach((to) => {
    const nextEndpointId = parseRouteEndpointId(to.params?.endpointId);
    if (!shouldConfirmFlowNavigation(nextEndpointId, to.name)) {
      return true;
    }
    return confirmFlowNavigationLoss();
  });
});

onBeforeUnmount(() => {
  if (catalogRefreshTimer !== null && typeof window !== "undefined") {
    window.clearInterval(catalogRefreshTimer);
  }

  if (typeof window !== "undefined") {
    window.removeEventListener("focus", handleWindowFocus);
    window.removeEventListener("online", handleWindowOnline);
    window.removeEventListener("beforeunload", handleBeforeUnload);
  }

  if (typeof document !== "undefined") {
    document.removeEventListener("visibilitychange", handleVisibilityChange);
  }

  removeFlowNavigationGuard?.();
  removeFlowNavigationGuard = null;
});

function applyDraftPatch(patch: Partial<EndpointDraft>): void {
  draft.value = {
    ...draft.value,
    ...patch,
  };
}

function setActiveWorkspaceTab(tab: RouteWorkspaceTab | null): void {
  const nextTab = tab ?? "overview";
  if (!ROUTE_WORKSPACE_TABS.includes(nextTab) || (props.mode === "create" && nextTab !== "overview")) {
    return;
  }

  const nextQuery = { ...route.query };
  if (nextTab === "overview") {
    delete nextQuery.tab;
  } else {
    nextQuery.tab = nextTab;
  }

  void router.replace({
    query: nextQuery,
  });
}

function setActiveContractSchemaTab(tab: ContractSchemaTab): void {
  const nextQuery = { ...route.query };
  if (tab === "response") {
    delete nextQuery.contractTab;
  } else {
    nextQuery.contractTab = tab;
  }

  void router.replace({
    query: nextQuery,
  });
}

function formatTimestamp(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "Not available yet";
}

function formatTelemetryDuration(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "No data";
  }

  if (value >= 1000) {
    return `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)} s`;
  }

  return `${value.toFixed(value >= 100 ? 0 : 1)} ms`;
}

function formatTelemetryPercentage(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "No data";
  }

  return `${value.toFixed(value % 1 === 0 ? 0 : 1)}%`;
}

function deploymentStatusColor(isActive: boolean): string {
  return isActive ? "accent" : "secondary";
}

function executionStatusColor(status: string): string {
  if (status === "success") {
    return "accent";
  }
  if (status === "validation_error") {
    return "warning";
  }
  return "error";
}

function formatJson(value: unknown): string {
  if (value === null || value === undefined) {
    return "n/a";
  }

  return JSON.stringify(value, null, 2);
}

function coerceExecutionParameterMap(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }

  return Object.entries(value as Record<string, unknown>).reduce<Record<string, string>>((accumulator, [key, rawValue]) => {
    if (rawValue === undefined || rawValue === null) {
      return accumulator;
    }
    if (typeof rawValue === "object") {
      return accumulator;
    }

    accumulator[key] = String(rawValue);
    return accumulator;
  }, {});
}

function extractExecutionReplayContext(requestDataRaw: unknown): {
  pathParameters: Record<string, string>;
  queryParameters: Record<string, string>;
  bodyPresent: boolean;
  hasCapturedBody: boolean;
} {
  const requestData =
    requestDataRaw && typeof requestDataRaw === "object" && !Array.isArray(requestDataRaw)
      ? (requestDataRaw as Record<string, unknown>)
      : {};
  const bodyPresent = requestData.body_present === true;
  const hasCapturedBody = Object.prototype.hasOwnProperty.call(requestData, "request_body");

  return {
    pathParameters: coerceExecutionParameterMap(requestData.path_parameters),
    queryParameters: coerceExecutionParameterMap(requestData.query_parameters),
    bodyPresent,
    hasCapturedBody,
  };
}

const selectedExecutionSteps = computed<ExecutionRunDetail["steps"]>(() => {
  if (!selectedExecutionDetail.value) {
    return [];
  }

  return [...selectedExecutionDetail.value.steps].sort((left, right) => left.order_index - right.order_index);
});

const selectedExecutionBodyReplayNote = computed(() => {
  if (!selectedExecutionDetail.value) {
    return null;
  }
  const context = extractExecutionReplayContext(selectedExecutionDetail.value.request_data);

  if (context.hasCapturedBody) {
    return "Replay currently seeds path and query values only. Captured request body data is shown below but is not auto-filled.";
  }
  if (context.bodyPresent) {
    return "This run only recorded request body presence metadata, so request body replay is unavailable for this trace.";
  }

  return "This run did not include a request body.";
});

async function loadRouteRuntimeScaffolding(endpointId: number): Promise<void> {
  if (!auth.session.value) {
    return;
  }

  isLoadingImplementation.value = true;
  isLoadingDeployments.value = true;
  isLoadingExecutions.value = true;
  executionDetailRequestToken += 1;
  isLoadingExecutionDetail.value = false;
  selectedExecutionId.value = null;
  selectedExecutionDetail.value = null;
  executionDetailError.value = null;
  isLoadingConnections.value = true;
  flowEditorError.value = null;
  flowValidationError.value = null;

  try {
    const [implementation, nextDeployments, nextExecutions, nextConnections] = await Promise.all([
      getCurrentRouteImplementation(endpointId, auth.session.value),
      listRouteDeployments(endpointId, auth.session.value),
      listExecutions(auth.session.value, { endpointId, limit: 12 }),
      listConnections(auth.session.value),
    ]);

    currentImplementation.value = implementation;
    flowDraftDefinition.value = normalizeRouteFlowDefinition(implementation.flow_definition ?? {});
    deployments.value = nextDeployments;
    executions.value = nextExecutions;
    connections.value = nextConnections;
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again to keep working on route implementations.");
      void router.push({ name: "login" });
      return;
    }

    pageError.value = describeAdminError(error, "Unable to load route implementation scaffolding.");
  } finally {
    isLoadingImplementation.value = false;
    isLoadingDeployments.value = false;
    isLoadingExecutions.value = false;
    isLoadingConnections.value = false;
  }
}

async function selectExecution(executionId: number): Promise<void> {
  if (!auth.session.value) {
    executionDetailError.value = "Sign in again before inspecting execution details.";
    return;
  }

  if (selectedExecutionId.value === executionId && selectedExecutionDetail.value?.id === executionId) {
    return;
  }

  selectedExecutionId.value = executionId;
  selectedExecutionDetail.value = null;
  executionDetailError.value = null;
  isLoadingExecutionDetail.value = true;
  const requestToken = ++executionDetailRequestToken;

  try {
    const executionDetail = await getExecution(executionId, auth.session.value);

    if (requestToken !== executionDetailRequestToken || selectedExecutionId.value !== executionId) {
      return;
    }

    selectedExecutionDetail.value = executionDetail;
  } catch (error) {
    if (requestToken !== executionDetailRequestToken || selectedExecutionId.value !== executionId) {
      return;
    }

    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again to inspect route execution details.");
      void router.push({ name: "login" });
      return;
    }

    executionDetailError.value = describeAdminError(error, "Unable to load execution details.");
  } finally {
    if (requestToken === executionDetailRequestToken && selectedExecutionId.value === executionId) {
      isLoadingExecutionDetail.value = false;
    }
  }
}

async function refreshConnections(): Promise<void> {
  if (!auth.session.value) {
    return;
  }

  isLoadingConnections.value = true;

  try {
    connections.value = await listConnections(auth.session.value);
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again to keep managing connections.");
      void router.push({ name: "login" });
      return;
    }

    pageError.value = describeAdminError(error, "Unable to refresh connections.");
  } finally {
    isLoadingConnections.value = false;
  }
}

async function refreshRouteRuntimeScaffolding(): Promise<void> {
  if (!selectedEndpoint.value) {
    return;
  }

  await loadRouteRuntimeScaffolding(selectedEndpoint.value.id);
}

async function saveFlowDefinition(): Promise<void> {
  if (!auth.session.value || !selectedEndpoint.value) {
    pageError.value = "Save the route first, then sign in again before editing the flow.";
    return;
  }

  if (flowValidationError.value) {
    flowEditorError.value = flowValidationError.value;
    return;
  }

  isSavingImplementation.value = true;
  pageError.value = null;
  pageSuccess.value = null;

  try {
    const implementation = await saveCurrentRouteImplementation(
      selectedEndpoint.value.id,
      { flow_definition: serializeRouteFlowDefinition(flowDraftDefinition.value) },
      auth.session.value,
    );
    currentImplementation.value = implementation;
    flowDraftDefinition.value = normalizeRouteFlowDefinition(implementation.flow_definition ?? {});
    pageSuccess.value = `Saved live flow draft v${implementation.version}.`;
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before saving the route flow.");
      void router.push({ name: "login" });
      return;
    }

    flowEditorError.value = describeAdminError(error, "Unable to save the route flow.");
  } finally {
    isSavingImplementation.value = false;
  }
}

async function publishFlowDeployment(): Promise<void> {
  if (!auth.session.value || !selectedEndpoint.value) {
    pageError.value = "Save the route first, then sign in again before publishing.";
    return;
  }

  isPublishingDeployment.value = true;
  pageError.value = null;
  pageSuccess.value = null;

  try {
    const deployment = await publishRouteImplementation(
      selectedEndpoint.value.id,
      { environment: "production" },
      auth.session.value,
    );
    pageSuccess.value = `Published implementation ${deployment.implementation_id} to ${deployment.environment}.`;
    await loadRouteRuntimeScaffolding(selectedEndpoint.value.id);
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before publishing.");
      void router.push({ name: "login" });
      return;
    }

    pageError.value = describeAdminError(error, "Unable to publish the current route implementation.");
  } finally {
    isPublishingDeployment.value = false;
  }
}

async function unpublishFlowDeployment(): Promise<void> {
  if (!auth.session.value || !selectedEndpoint.value) {
    pageError.value = "Save the route first, then sign in again before changing the live deployment state.";
    return;
  }
  if (!activeDeployment.value) {
    pageError.value = "This route does not have an active live deployment to disable.";
    return;
  }

  const confirmed = window.confirm(
    `Disable the live ${activeDeployment.value.environment} deployment for ${selectedEndpoint.value.name}? Public traffic and published docs will stop using this route until it is published again.`,
  );
  if (!confirmed) {
    return;
  }

  isUnpublishingDeployment.value = true;
  pageError.value = null;
  pageSuccess.value = null;

  try {
    const deployment = await unpublishRouteDeployment(
      selectedEndpoint.value.id,
      { environment: activeDeployment.value.environment },
      auth.session.value,
    );
    pageSuccess.value = `Disabled the live ${deployment.environment} deployment. The route definition and flow implementation remain saved.`;
    await loadRouteRuntimeScaffolding(selectedEndpoint.value.id);
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before disabling the live route.");
      void router.push({ name: "login" });
      return;
    }

    pageError.value = describeAdminError(error, "Unable to disable the live route.");
  } finally {
    isUnpublishingDeployment.value = false;
  }
}

function openCreateView(): void {
  if (!canWriteRoutes.value) {
    return;
  }

  void router.push({ name: "endpoints-create" });
}

function openImportDialog(): void {
  if (!canWriteRoutes.value) {
    return;
  }

  importDialog.value = true;
}

function duplicateEndpoint(endpointId: number): void {
  if (!canWriteRoutes.value) {
    return;
  }

  void router.push({
    name: "endpoints-create",
    query: {
      duplicateFrom: String(endpointId),
      duplicateNonce: String(Date.now()),
    },
  });
}

async function handleSave(): Promise<void> {
  if (!auth.session.value) {
    pageError.value = "Sign in again before saving endpoints.";
    return;
  }

  pageError.value = null;
  pageSuccess.value = null;

  const { errors, payload } = buildPayload(draft.value);
  fieldErrors.value = errors;

  if (!payload || Object.keys(errors).length > 0) {
    if (activeWorkspaceTab.value === "contract") {
      if (typeof errors.request_schema === "string") {
        pageError.value = errors.request_schema;
        setActiveContractSchemaTab("request");
      } else if (typeof errors.response_schema === "string") {
        pageError.value = errors.response_schema;
        setActiveContractSchemaTab("response");
      } else {
        pageError.value = Object.values(errors)[0] ?? "Fix the highlighted route fields before saving.";
      }
    }
    return;
  }

  isSaving.value = true;

  try {
    if (props.mode === "create") {
      const createdEndpoint = await createEndpoint(payload, auth.session.value);
      endpoints.value = [createdEndpoint, ...endpoints.value];
      lastCatalogSyncAt.value = Date.now();
      void router.push({ name: "endpoints-edit", params: { endpointId: createdEndpoint.id }, query: { saved: "1" } });
      return;
    }

    if (!selectedEndpoint.value) {
      pageError.value = "Select an endpoint before saving.";
      return;
    }

    const updatedEndpoint = await updateEndpoint(selectedEndpoint.value.id, payload, auth.session.value);
    endpoints.value = endpoints.value.map((endpoint) => (endpoint.id === updatedEndpoint.id ? updatedEndpoint : endpoint));
    lastCatalogSyncAt.value = Date.now();
    pageSuccess.value = `Saved ${updatedEndpoint.name}.`;
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before saving more changes.");
      void router.push({ name: "login" });
      return;
    }

    pageError.value = describeAdminError(error, "Unable to save the endpoint.");
  } finally {
    isSaving.value = false;
  }
}

async function handleDelete(): Promise<void> {
  if (!selectedEndpoint.value || !auth.session.value) {
    return;
  }

  const shouldDelete = window.confirm(`Delete "${selectedEndpoint.value.name}" from the catalog?`);
  if (!shouldDelete) {
    return;
  }

  isSaving.value = true;
  pageError.value = null;
  pageSuccess.value = null;

  try {
    await deleteEndpoint(selectedEndpoint.value.id, auth.session.value);
    endpoints.value = endpoints.value.filter((endpoint) => endpoint.id !== selectedEndpoint.value?.id);
    lastCatalogSyncAt.value = Date.now();
    void router.push({ name: "endpoints-browse" });
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before deleting endpoints.");
      void router.push({ name: "login" });
      return;
    }

    pageError.value = describeAdminError(error, "Unable to delete the endpoint.");
  } finally {
    isSaving.value = false;
  }
}

function openSchemaStudio(): void {
  if (!selectedEndpoint.value || !canWriteRoutes.value) {
    return;
  }

  void router.push({ name: "endpoints-edit", params: { endpointId: selectedEndpoint.value.id }, query: { tab: "contract" } });
}

function openPreview(): void {
  if (!selectedEndpoint.value || !canPreviewRoutes.value) {
    return;
  }

  void router.push({ name: "endpoint-preview", params: { endpointId: selectedEndpoint.value.id } });
}

function openConnectorsPage(): void {
  void router.push({ name: "connectors" });
}

function resetContractDraft(): void {
  if (!selectedEndpoint.value) {
    return;
  }

  draft.value = {
    ...draft.value,
    request_schema: JSON.parse(JSON.stringify(selectedEndpoint.value.request_schema ?? {})),
    response_schema: JSON.parse(JSON.stringify(selectedEndpoint.value.response_schema ?? {})),
    seed_key: selectedEndpoint.value.seed_key ?? "",
  };
  activeContractRequestSection.value = "body";
  pageError.value = null;
  pageSuccess.value = null;
}

function resolveContractRequestSectionFromError(message: string): ContractRequestSection {
  if (message.includes("query parameter")) {
    return "query";
  }
  if (message.includes("path parameter")) {
    return "path";
  }
  return "body";
}

async function handleContractSave(): Promise<void> {
  if (!auth.session.value) {
    pageError.value = "Sign in again before saving contract changes.";
    return;
  }

  if (!selectedEndpoint.value) {
    pageError.value = "Select an endpoint before saving.";
    return;
  }

  pageError.value = null;
  pageSuccess.value = null;

  const contractDraft: EndpointDraft = {
    ...draftFromEndpoint(selectedEndpoint.value),
    request_schema: draft.value.request_schema,
    response_schema: draft.value.response_schema,
    seed_key: draft.value.seed_key,
  };
  const { errors, payload } = buildPayload(contractDraft);
  fieldErrors.value = errors;

  if (!payload || Object.keys(errors).length > 0) {
    if (typeof errors.request_schema === "string") {
      pageError.value = errors.request_schema;
      activeContractRequestSection.value = resolveContractRequestSectionFromError(errors.request_schema);
      setActiveContractSchemaTab("request");
    } else if (typeof errors.response_schema === "string") {
      pageError.value = errors.response_schema;
      setActiveContractSchemaTab("response");
    } else {
      pageError.value = Object.values(errors)[0] ?? "Fix the highlighted contract fields before saving.";
    }
    return;
  }

  isSaving.value = true;

  try {
    const updatedEndpoint = await updateEndpoint(selectedEndpoint.value.id, payload, auth.session.value);
    nextSelectedEndpointDraftOverride = {
      ...draft.value,
      request_schema: updatedEndpoint.request_schema ?? {},
      response_schema: updatedEndpoint.response_schema ?? {},
      seed_key: updatedEndpoint.seed_key ?? "",
    };
    endpoints.value = endpoints.value.map((endpoint) => (endpoint.id === updatedEndpoint.id ? updatedEndpoint : endpoint));
    lastCatalogSyncAt.value = Date.now();
    pageSuccess.value = `Saved contract changes for ${updatedEndpoint.name}.`;
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before saving contract changes.");
      void router.push({ name: "login" });
      return;
    }

    pageError.value = describeAdminError(error, "Unable to save the route contract.");
  } finally {
    isSaving.value = false;
  }
}

function replayExecutionInTester(): void {
  if (!selectedEndpoint.value || !selectedExecutionDetail.value) {
    return;
  }

  const replayContext = extractExecutionReplayContext(selectedExecutionDetail.value.request_data);
  const replayQuery: Record<string, string> = {
    replayRunId: String(selectedExecutionDetail.value.id),
    replayBodyCaptured: replayContext.hasCapturedBody ? "1" : replayContext.bodyPresent ? "0" : "none",
  };

  for (const [key, value] of Object.entries(replayContext.pathParameters)) {
    replayQuery[`replay_path_${key}`] = value;
  }
  for (const [key, value] of Object.entries(replayContext.queryParameters)) {
    replayQuery[`replay_query_${key}`] = value;
  }

  void router.push({
    name: "endpoint-preview",
    params: { endpointId: selectedEndpoint.value.id },
    query: replayQuery,
  });
}

function duplicateSelectedEndpoint(): void {
  if (!selectedEndpoint.value) {
    return;
  }

  duplicateEndpoint(selectedEndpoint.value.id);
}

function openEndpointFromCatalog(endpointId: number): void {
  if (!canWriteRoutes.value && canPreviewRoutes.value) {
    void router.push({ name: "endpoint-preview", params: { endpointId } });
    return;
  }

  void router.push({ name: "endpoints-edit", params: { endpointId } });
}

function handleImportFileChange(value: File | File[] | null): void {
  importFile.value = Array.isArray(value) ? value[0] ?? null : value;
}

function importOperationColor(action: EndpointImportOperation["action"]): string {
  if (action === "create") {
    return "accent";
  }

  if (action === "update") {
    return "primary";
  }

  if (action === "delete" || action === "error") {
    return "error";
  }

  return "secondary";
}

function importOperationLabel(action: EndpointImportOperation["action"]): string {
  return action.replace(/_/g, " ");
}

function formatImportSummary(prefix: string, summary: EndpointImportSummary): string {
  const parts = [
    summary.create_count ? `${summary.create_count} created` : null,
    summary.update_count ? `${summary.update_count} updated` : null,
    summary.delete_count ? `${summary.delete_count} deleted` : null,
    summary.skip_count ? `${summary.skip_count} skipped` : null,
    summary.error_count ? `${summary.error_count} errors` : null,
  ].filter(Boolean);

  return parts.length > 0
    ? `${prefix}: ${parts.join(", ")}.`
    : `${prefix}: no route changes were needed.`;
}

async function resolveImportBundle(): Promise<EndpointBundle> {
  const rawText = importText.value.trim()
    ? importText.value.trim()
    : importFile.value
      ? (await importFile.value.text()).trim()
      : "";

  if (!rawText) {
    throw new Error("Choose a JSON bundle file or paste a bundle before previewing the import.");
  }

  try {
    return JSON.parse(rawText) as EndpointBundle;
  } catch {
    throw new Error("The import bundle must be valid JSON.");
  }
}

async function previewImportRoutes(): Promise<void> {
  if (!auth.session.value) {
    pageError.value = "Sign in again before importing routes.";
    importDialog.value = false;
    return;
  }

  isPreviewingImport.value = true;
  importError.value = null;

  try {
    const bundle = await resolveImportBundle();
    importPreview.value = await importEndpointBundle(
      {
        bundle,
        mode: importMode.value,
        dry_run: true,
        confirm_replace_all: false,
      },
      auth.session.value,
    );
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before importing routes.");
      void router.push({ name: "login" });
      return;
    }

    importPreview.value = null;
    importError.value = describeAdminError(error, "Unable to preview the route import.");
  } finally {
    isPreviewingImport.value = false;
  }
}

async function applyImportedRoutes(): Promise<void> {
  if (!auth.session.value) {
    pageError.value = "Sign in again before importing routes.";
    importDialog.value = false;
    return;
  }

  if (importMode.value === "replace_all") {
    const confirmed = window.confirm(
      "Replace the full route catalog with this bundle? Routes not present in the bundle will be deleted.",
    );
    if (!confirmed) {
      return;
    }
  }

  isApplyingImport.value = true;
  importError.value = null;

  try {
    const bundle = await resolveImportBundle();
    const result = await importEndpointBundle(
      {
        bundle,
        mode: importMode.value,
        dry_run: false,
        confirm_replace_all: importMode.value === "replace_all",
      },
      auth.session.value,
    );
    importPreview.value = result;

    if (!result.applied) {
      importError.value = result.has_errors
        ? "Fix the bundle issues below before importing routes."
        : "The import preview did not produce any route changes.";
      return;
    }

    await fetchEndpoints();
    pageError.value = null;
    pageSuccess.value = formatImportSummary("Import complete", result.summary);
    importDialog.value = false;
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before importing routes.");
      void router.push({ name: "login" });
      return;
    }

    importError.value = describeAdminError(error, "Unable to import routes.");
  } finally {
    isApplyingImport.value = false;
  }
}

async function exportRoutes(): Promise<void> {
  if (!auth.session.value) {
    pageError.value = "Sign in again before exporting routes.";
    return;
  }

  isExporting.value = true;
  pageError.value = null;

  try {
    const bundle = await exportEndpointBundle(auth.session.value);
    const serialized = JSON.stringify(bundle, null, 2);

    if (typeof window !== "undefined") {
      const blob = new Blob([serialized], { type: "application/json" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      const exportDate = bundle.exported_at ? bundle.exported_at.slice(0, 10) : new Date().toISOString().slice(0, 10);
      link.href = url;
      link.download = `artificer-endpoints-${exportDate}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    }

    pageSuccess.value = `Exported ${bundle.endpoints.length} routes.`;
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before exporting routes.");
      void router.push({ name: "login" });
      return;
    }

    pageError.value = describeAdminError(error, "Unable to export routes.");
  } finally {
    isExporting.value = false;
  }
}

const activeTitle = computed(() => {
  if (props.mode === "create") {
    return "Start a new route";
  }

  if (!selectedEndpoint.value) {
    return "Choose a route";
  }

  return selectedEndpoint.value.name;
});
</script>

<template>
  <div class="d-flex flex-column ga-4">
    <v-row class="workspace-grid endpoint-workspace-grid">
      <v-col class="endpoint-sidebar-col" cols="12" xl="3" lg="4">
        <div class="endpoint-sidebar">
          <EndpointCatalog
            :active-endpoint-id="selectedEndpoint?.id"
            :allow-create="canWriteRoutes"
            :allow-duplicate="canWriteRoutes"
            :endpoints="endpoints"
            :error="catalogError"
            :loading="isLoading"
            @create="openCreateView"
            @duplicate="duplicateEndpoint"
            @refresh="fetchEndpoints"
            @select="openEndpointFromCatalog"
          />
        </div>
      </v-col>

      <v-col class="endpoint-detail-col" cols="12" xl="9" lg="8">
        <div class="endpoint-detail-shell">
          <v-alert v-if="pageSuccess" border="start" color="success" variant="tonal">
            {{ pageSuccess }}
          </v-alert>

          <v-alert v-if="pageError" border="start" color="error" variant="tonal">
            {{ pageError }}
          </v-alert>

          <v-alert v-if="duplicateBanner" border="start" color="info" variant="tonal">
            {{ duplicateBanner }}
          </v-alert>

          <div class="endpoint-detail-scroll">
            <v-skeleton-loader
              v-if="isInitialCatalogLoad"
              class="workspace-card"
              type="heading, paragraph, paragraph, paragraph, table-heading, table-row-divider, table-row-divider"
            />

            <v-card v-else-if="props.mode === 'browse'" class="workspace-card browse-card">
              <v-card-text class="pa-8">
                <div class="text-overline text-secondary">Routes</div>
                <div class="text-h3 font-weight-bold mt-2">Choose a route or create a new one.</div>
                <div class="text-body-1 text-medium-emphasis mt-4">
                  {{
                    canWriteRoutes
                      ? "Select a route to edit its details, request and response schema, and live test flow."
                      : "Select a route to preview its live behavior and inspect the catalog."
                  }}
                </div>
                <div class="d-flex flex-wrap ga-3 mt-6">
                  <v-btn v-if="canWriteRoutes" color="primary" prepend-icon="mdi-plus" @click="router.push({ name: 'endpoints-create' })">
                    Create route
                  </v-btn>
                  <v-btn prepend-icon="mdi-refresh" variant="text" @click="fetchEndpoints">
                    Refresh routes
                  </v-btn>
                  <v-btn :loading="isExporting" prepend-icon="mdi-download" variant="text" @click="exportRoutes">
                    Export routes
                  </v-btn>
                  <v-btn v-if="canWriteRoutes" prepend-icon="mdi-upload" variant="text" @click="openImportDialog">
                    Import routes
                  </v-btn>
                </div>

                <v-divider class="my-6" />

                <v-row class="browse-metrics-grid" density="comfortable">
                  <v-col cols="12" md="6" xl="3">
                    <v-sheet class="browse-metric-card pa-4" rounded="lg">
                      <div class="text-overline text-medium-emphasis">Total routes</div>
                      <div class="text-h5 font-weight-bold" data-testid="browse-metric-total-routes">
                        {{ browseRouteMetrics.total }}
                      </div>
                      <div class="text-caption text-medium-emphasis">Catalog records available for editing or preview.</div>
                    </v-sheet>
                  </v-col>
                  <v-col cols="12" md="6" xl="3">
                    <v-sheet class="browse-metric-card pa-4" rounded="lg">
                      <div class="text-overline text-medium-emphasis">Public routes</div>
                      <div class="text-h5 font-weight-bold" data-testid="browse-metric-public-routes">
                        {{ browseRouteMetrics.publicCount }}
                      </div>
                      <div class="text-caption text-medium-emphasis">
                        Live runtime {{ browseRouteMetrics.liveRuntimeCount }} · Legacy mock {{ browseRouteMetrics.legacyMockCount }}
                      </div>
                    </v-sheet>
                  </v-col>
                  <v-col cols="12" md="6" xl="3">
                    <v-sheet class="browse-metric-card pa-4" rounded="lg">
                      <div class="text-overline text-medium-emphasis">Private or draft</div>
                      <div class="text-h5 font-weight-bold" data-testid="browse-metric-private-routes">
                        {{ browseRouteMetrics.privateCount }}
                      </div>
                      <div class="text-caption text-medium-emphasis">Not currently available on public API surfaces.</div>
                    </v-sheet>
                  </v-col>
                  <v-col cols="12" md="6" xl="3">
                    <v-sheet class="browse-metric-card pa-4" rounded="lg">
                      <div class="text-overline text-medium-emphasis">Disabled routes</div>
                      <div class="text-h5 font-weight-bold" data-testid="browse-metric-disabled-routes">
                        {{ browseRouteMetrics.disabledCount }}
                      </div>
                      <div class="text-caption text-medium-emphasis">Route-level kill switch is enabled for these routes.</div>
                    </v-sheet>
                  </v-col>
                </v-row>

                <v-row class="browse-mix-grid" density="comfortable">
                  <v-col cols="12" md="6">
                    <v-sheet class="browse-metric-card pa-4" rounded="lg">
                      <div class="text-overline text-medium-emphasis mb-2">Method mix</div>
                      <div class="d-flex flex-wrap ga-2" data-testid="browse-method-mix">
                        <v-chip
                          v-for="entry in browseMethodMix"
                          :key="entry.label"
                          color="primary"
                          label
                          size="small"
                          variant="tonal"
                        >
                          {{ entry.label }} · {{ entry.count }}
                        </v-chip>
                      </div>
                    </v-sheet>
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-sheet class="browse-metric-card pa-4" rounded="lg">
                      <div class="text-overline text-medium-emphasis mb-2">Category mix</div>
                      <div class="d-flex flex-wrap ga-2" data-testid="browse-category-mix">
                        <v-chip
                          v-for="entry in browseCategoryMix"
                          :key="entry.label"
                          color="secondary"
                          label
                          size="small"
                          variant="tonal"
                        >
                          {{ entry.label }} · {{ entry.count }}
                        </v-chip>
                      </div>
                    </v-sheet>
                  </v-col>
                </v-row>

                <v-divider class="my-6" />

                <div class="d-flex flex-wrap align-center justify-space-between ga-3 mb-4">
                  <div>
                    <div class="text-overline text-secondary">Live telemetry</div>
                    <div class="text-body-2 text-medium-emphasis">
                      Based on the latest {{ executionTelemetrySnapshot.sampled_runs }} live runs stored in runtime history.
                    </div>
                  </div>
                  <div class="text-caption text-medium-emphasis">
                    Last sampled {{ formatTimestamp(executionTelemetrySnapshot.latest_completed_at) }}
                  </div>
                </div>

                <v-alert
                  v-if="executionTelemetryError"
                  class="mb-4"
                  border="start"
                  color="warning"
                  variant="tonal"
                >
                  {{ executionTelemetryError }}
                </v-alert>

                <v-row class="browse-telemetry-grid" density="comfortable">
                  <v-col cols="12" md="6" xl="3">
                    <v-sheet class="browse-metric-card pa-4" rounded="lg">
                      <div class="text-overline text-medium-emphasis">Recent live runs</div>
                      <div class="text-h5 font-weight-bold" data-testid="browse-telemetry-runs">
                        {{ executionTelemetrySnapshot.sampled_runs }}
                      </div>
                      <div class="text-caption text-medium-emphasis">
                        {{ formatTelemetryPercentage(executionTelemetrySnapshot.success_rate) }} success ·
                        {{ executionTelemetrySnapshot.route_count }} routes observed
                      </div>
                    </v-sheet>
                  </v-col>
                  <v-col cols="12" md="6" xl="3">
                    <v-sheet class="browse-metric-card pa-4" rounded="lg">
                      <div class="text-overline text-medium-emphasis">Average response</div>
                      <div class="text-h5 font-weight-bold" data-testid="browse-telemetry-avg-response">
                        {{ formatTelemetryDuration(executionTelemetrySnapshot.average_response_time_ms) }}
                      </div>
                      <div class="text-caption text-medium-emphasis">Route wall-clock time across sampled runs.</div>
                    </v-sheet>
                  </v-col>
                  <v-col cols="12" md="6" xl="3">
                    <v-sheet class="browse-metric-card pa-4" rounded="lg">
                      <div class="text-overline text-medium-emphasis">P95 response</div>
                      <div class="text-h5 font-weight-bold" data-testid="browse-telemetry-p95-response">
                        {{ formatTelemetryDuration(executionTelemetrySnapshot.p95_response_time_ms) }}
                      </div>
                      <div class="text-caption text-medium-emphasis">Tail latency to help surface slow outliers.</div>
                    </v-sheet>
                  </v-col>
                  <v-col cols="12" md="6" xl="3">
                    <v-sheet class="browse-metric-card pa-4" rounded="lg">
                      <div class="text-overline text-medium-emphasis">Average flow time</div>
                      <div class="text-h5 font-weight-bold" data-testid="browse-telemetry-avg-flow">
                        {{ formatTelemetryDuration(executionTelemetrySnapshot.average_flow_time_ms) }}
                      </div>
                      <div class="text-caption text-medium-emphasis">
                        {{ formatTelemetryDuration(executionTelemetrySnapshot.p95_flow_time_ms) }} p95 ·
                        {{ executionTelemetrySnapshot.average_steps_per_run ?? 0 }} steps/run
                      </div>
                    </v-sheet>
                  </v-col>
                </v-row>

                <v-row class="browse-telemetry-detail-grid" density="comfortable">
                  <v-col cols="12" lg="7">
                    <v-sheet class="browse-metric-card pa-4" rounded="lg">
                      <div class="d-flex flex-wrap align-center justify-space-between ga-3 mb-3">
                        <div class="text-overline text-medium-emphasis">Slow routes</div>
                        <div class="text-caption text-medium-emphasis">
                          Ranked by average response time from the sampled live traffic.
                        </div>
                      </div>

                      <div
                        v-if="telemetrySlowRoutes.length === 0 && !isLoadingExecutionTelemetry"
                        class="text-body-2 text-medium-emphasis"
                      >
                        No live route telemetry yet.
                      </div>
                      <v-skeleton-loader
                        v-else-if="isLoadingExecutionTelemetry && !hasExecutionTelemetry"
                        type="list-item-two-line, list-item-two-line, list-item-two-line"
                      />
                      <div v-else class="d-flex flex-column ga-3" data-testid="browse-telemetry-slow-routes">
                        <v-sheet
                          v-for="{ summary, endpoint } in telemetrySlowRoutes"
                          :key="`slow-route-${summary.route_id}`"
                          class="telemetry-row pa-3"
                          rounded="lg"
                        >
                          <div class="d-flex flex-wrap align-center justify-space-between ga-3">
                            <div>
                              <div class="font-weight-medium">
                                {{ endpoint?.name ?? `Route #${summary.route_id}` }}
                              </div>
                              <div class="text-caption text-medium-emphasis">
                                {{ endpoint?.method ?? "ROUTE" }} {{ endpoint?.path ?? `#${summary.route_id}` }}
                              </div>
                            </div>
                            <div class="text-caption text-medium-emphasis">
                              {{ summary.total_runs }} runs · {{ formatTelemetryPercentage(summary.success_rate) }} success
                            </div>
                          </div>
                          <div class="d-flex flex-wrap ga-2 mt-3">
                            <v-chip color="primary" label size="small" variant="tonal">
                              Avg {{ formatTelemetryDuration(summary.average_response_time_ms) }}
                            </v-chip>
                            <v-chip color="secondary" label size="small" variant="tonal">
                              P95 {{ formatTelemetryDuration(summary.p95_response_time_ms) }}
                            </v-chip>
                            <v-chip color="info" label size="small" variant="tonal">
                              Flow {{ formatTelemetryDuration(summary.average_flow_time_ms) }}
                            </v-chip>
                          </div>
                        </v-sheet>
                      </div>
                    </v-sheet>
                  </v-col>

                  <v-col cols="12" lg="5">
                    <v-sheet class="browse-metric-card pa-4" rounded="lg">
                      <div class="d-flex flex-wrap align-center justify-space-between ga-3 mb-3">
                        <div class="text-overline text-medium-emphasis">Slow flow hotspots</div>
                        <div class="text-caption text-medium-emphasis">
                          {{ executionTelemetrySnapshot.precise_step_run_count }} runs with per-node timing
                        </div>
                      </div>

                      <div
                        v-if="telemetrySlowFlowSteps.length === 0 && !isLoadingExecutionTelemetry"
                        class="text-body-2 text-medium-emphasis"
                      >
                        No node-level flow telemetry yet.
                      </div>
                      <v-skeleton-loader
                        v-else-if="isLoadingExecutionTelemetry && !hasExecutionTelemetry"
                        type="list-item-two-line, list-item-two-line, list-item-two-line"
                      />
                      <div v-else class="d-flex flex-column ga-3" data-testid="browse-telemetry-slow-steps">
                        <v-sheet
                          v-for="{ summary, endpoint } in telemetrySlowFlowSteps"
                          :key="`slow-step-${summary.route_id}-${summary.node_type}`"
                          class="telemetry-row pa-3"
                          rounded="lg"
                        >
                          <div class="font-weight-medium">
                            {{ endpoint?.name ?? `Route #${summary.route_id}` }}
                          </div>
                          <div class="text-caption text-medium-emphasis mt-1">
                            {{ summary.node_type }} · {{ summary.total_steps }} samples
                          </div>
                          <div class="d-flex flex-wrap ga-2 mt-3">
                            <v-chip color="primary" label size="small" variant="tonal">
                              Avg {{ formatTelemetryDuration(summary.average_duration_ms) }}
                            </v-chip>
                            <v-chip color="secondary" label size="small" variant="tonal">
                              P95 {{ formatTelemetryDuration(summary.p95_duration_ms) }}
                            </v-chip>
                          </div>
                        </v-sheet>
                      </div>
                    </v-sheet>
                  </v-col>
                </v-row>
              </v-card-text>
            </v-card>

            <v-card
              v-else-if="props.mode === 'edit' && !selectedEndpoint"
              class="workspace-card browse-card"
            >
              <v-card-text class="pa-8">
                <div class="text-overline text-error">Missing endpoint</div>
                <div class="text-h4 font-weight-bold mt-2">That route is no longer in the catalog.</div>
                <div class="text-body-1 text-medium-emphasis mt-4">
                  Refresh the list, pick another route, or create a new one.
                </div>
              </v-card-text>
            </v-card>

            <template v-else>
              <v-slide-y-transition mode="out-in">
                <div :key="recordTransitionKey" class="d-flex flex-column ga-4">
                  <v-card class="workspace-card record-hero">
                    <v-card-text class="d-flex flex-column flex-md-row justify-space-between ga-4">
                      <div>
                        <div class="text-overline text-secondary">
                          {{ props.mode === "create" ? "New route" : "Route details" }}
                        </div>
                        <div class="text-h4 font-weight-bold mt-2">{{ activeTitle }}</div>
                        <div class="text-body-1 text-medium-emphasis mt-3">
                          {{
                            props.mode === "create"
                              ? "Set the path, method, and behavior first."
                              : selectedEndpoint?.path
                          }}
                        </div>
                      </div>

                      <div class="d-flex flex-wrap align-start justify-end ga-2">
                        <v-chip v-if="selectedEndpoint" color="primary" label size="small" variant="tonal">
                          {{ selectedEndpoint.method }}
                        </v-chip>
                        <v-chip
                          v-if="selectedEndpoint"
                          :color="selectedPublicationStatus ? routePublicationColor(selectedPublicationStatus) : 'secondary'"
                          label
                          size="small"
                          variant="tonal"
                        >
                          {{ selectedPublicationStatus?.label ?? "Unknown" }}
                        </v-chip>
                        <v-chip v-if="selectedEndpoint?.category" color="secondary" label size="small" variant="tonal">
                          {{ selectedEndpoint.category }}
                        </v-chip>
                      </div>
                    </v-card-text>
                  </v-card>

                  <v-card class="workspace-card workspace-tabs-card">
                    <v-tabs
                      color="primary"
                      :model-value="activeWorkspaceTab"
                      slider-color="primary"
                      @update:model-value="setActiveWorkspaceTab($event as RouteWorkspaceTab | null)"
                    >
                      <v-tab
                        v-for="tab in routeTabs"
                        :key="tab.value"
                        :disabled="tab.disabled"
                        :value="tab.value"
                      >
                        {{ tab.title }}
                      </v-tab>
                    </v-tabs>
                  </v-card>

                  <EndpointSettingsForm
                    v-if="activeWorkspaceTab === 'overview'"
                    :available-categories="availableCategories"
                    :available-tags="availableTags"
                    :created-at="selectedEndpoint?.created_at"
                    :draft="draft"
                    :endpoint-id="selectedEndpoint?.id"
                    :errors="fieldErrors"
                    :is-creating="props.mode === 'create'"
                    :is-saving="isSaving"
                    :updated-at="selectedEndpoint?.updated_at"
                    @change="applyDraftPatch"
                    @delete="handleDelete"
                    @duplicate="duplicateSelectedEndpoint"
                    @open-schema="openSchemaStudio"
                    @preview="openPreview"
                    @submit="handleSave"
                  />

                  <template v-else-if="activeWorkspaceTab === 'contract'">
                    <v-card class="workspace-card">
                      <v-card-item>
                        <template #prepend>
                          <v-avatar color="secondary" variant="tonal">
                            <v-icon icon="mdi-file-document-outline" />
                          </v-avatar>
                        </template>
                        <v-card-title>Contract</v-card-title>
                        <v-card-subtitle>
                          Define the request and response contract for this route.
                        </v-card-subtitle>

                        <template #append>
                          <div class="d-flex flex-wrap justify-end ga-2">
                            <v-btn v-if="isContractDirty" prepend-icon="mdi-restore" variant="text" @click="resetContractDraft">
                              Reset
                            </v-btn>
                            <v-btn
                              color="primary"
                              :disabled="!isContractDirty"
                              :loading="isSaving"
                              prepend-icon="mdi-content-save-outline"
                              @click="handleContractSave"
                            >
                              Save contract
                            </v-btn>
                            <v-btn
                              v-if="canPreviewRoutes"
                              prepend-icon="mdi-flask-outline"
                              variant="text"
                              @click="openPreview"
                            >
                              Test route
                            </v-btn>
                          </div>
                        </template>
                      </v-card-item>

                      <v-divider />

                      <v-card-text class="d-flex flex-column ga-4">
                        <v-alert
                          v-if="hasNonContractDraftChanges"
                          border="start"
                          color="info"
                          variant="tonal"
                        >
                          Unsaved <strong>Overview</strong> edits are not applied here yet. Save or reset them first to refresh method/path values in Contract.
                        </v-alert>

                        <RouteContractEditor
                          :active-tab="activeContractSchemaTab"
                          :active-request-section="activeContractRequestSection"
                          :path="contractEditorPath"
                          :request-schema="draft.request_schema"
                          :response-schema="draft.response_schema"
                          :seed-key="draft.seed_key"
                          @update:active-tab="setActiveContractSchemaTab"
                          @update:active-request-section="activeContractRequestSection = $event"
                          @update:request-schema="applyDraftPatch({ request_schema: $event })"
                          @update:response-schema="applyDraftPatch({ response_schema: $event })"
                          @update:seed-key="applyDraftPatch({ seed_key: $event })"
                        />
                      </v-card-text>
                    </v-card>
                  </template>

                  <template v-else-if="activeWorkspaceTab === 'flow'">
                    <v-card class="workspace-card">
                      <v-card-item>
                        <template #prepend>
                          <v-avatar color="accent" variant="tonal">
                            <v-icon icon="mdi-graph-outline" />
                          </v-avatar>
                        </template>
                        <v-card-title>Flow</v-card-title>
                        <v-card-subtitle>
                          Build the live route logic with nodes, paths, and connector calls.
                        </v-card-subtitle>

                        <template #append>
                          <div class="d-flex flex-wrap justify-end ga-2">
                            <v-btn prepend-icon="mdi-refresh" variant="text" @click="refreshRouteRuntimeScaffolding">
                              Refresh
                            </v-btn>
                            <v-btn
                              color="primary"
                              :disabled="!isFlowDirty || Boolean(flowValidationError)"
                              :loading="isSavingImplementation"
                              prepend-icon="mdi-content-save-outline"
                              @click="saveFlowDefinition"
                            >
                              Save flow
                            </v-btn>
                          </div>
                        </template>
                      </v-card-item>

                      <v-divider />

                      <v-card-text class="d-flex flex-column ga-4">
                        <div class="d-flex flex-wrap align-center justify-space-between ga-3">
                          <div class="d-flex flex-wrap ga-2">
                            <v-chip color="primary" label size="small" variant="tonal">
                              v{{ currentImplementation?.version ?? 1 }}
                            </v-chip>
                            <v-chip
                              :color="currentImplementation?.is_draft === false ? 'accent' : 'warning'"
                              label
                              size="small"
                              variant="tonal"
                            >
                              {{ currentImplementation?.is_draft === false ? "Published base" : "Draft" }}
                            </v-chip>
                            <v-chip label size="small" variant="outlined">{{ implementationNodeCount }} nodes</v-chip>
                            <v-chip label size="small" variant="outlined">{{ implementationEdgeCount }} edges</v-chip>
                          </div>

                          <div
                            v-if="!isFlowEditorInFocusMode"
                            class="d-flex flex-wrap align-center justify-end ga-2 flow-connection-context-row"
                            data-testid="flow-connection-context"
                          >
                            <v-chip color="primary" label size="small" variant="tonal">
                              Scope · {{ routeConnectionScopeLabel }}
                            </v-chip>
                            <v-chip label size="small" variant="outlined">
                              {{ scopedConnectionCount }} in scope
                            </v-chip>
                            <v-chip label size="small" variant="outlined">
                              {{ connections.length }} total
                            </v-chip>
                            <v-chip v-if="isLoadingConnections" color="secondary" label size="small" variant="tonal">
                              Syncing…
                            </v-chip>
                            <v-btn prepend-icon="mdi-refresh" size="small" variant="text" @click="refreshConnections">
                              Refresh
                            </v-btn>
                            <v-btn color="primary" prepend-icon="mdi-open-in-new" size="small" variant="tonal" @click="openConnectorsPage">
                              Open Connectors
                            </v-btn>
                          </div>
                        </div>

                        <v-skeleton-loader
                          v-if="isLoadingImplementation"
                          type="paragraph, paragraph, paragraph"
                        />

                        <RouteFlowEditor
                          v-else
                          v-model="flowDraftDefinition"
                          :available-connections="connections"
                          :error-message="flowEditorError"
                          :preferred-connection-environment="routeConnectionEnvironment"
                          :preferred-connection-project="routeConnectionProject"
                          :request-schema="draft.request_schema"
                          :response-schema="draft.response_schema"
                          :route-id="selectedEndpoint?.id ?? null"
                          :route-method="draft.method"
                          :route-name="draft.name"
                          :route-path="draft.path"
                          :save-disabled="!isFlowDirty || Boolean(flowValidationError)"
                          :save-loading="isSavingImplementation"
                          :success-status-code="draft.success_status_code"
                          @focus-mode-change="isFlowEditorInFocusMode = $event"
                          @save-requested="saveFlowDefinition"
                          @validation-change="flowValidationError = $event"
                        />
                      </v-card-text>
                    </v-card>

                  </template>

                  <template v-else-if="activeWorkspaceTab === 'test'">
                    <v-card class="workspace-card">
                      <v-card-item>
                        <template #prepend>
                          <v-avatar color="primary" variant="tonal">
                            <v-icon icon="mdi-flask-outline" />
                          </v-avatar>
                        </template>
                        <v-card-title>Test</v-card-title>
                        <v-card-subtitle>
                          Compare contract output with live route behavior and recent runs.
                        </v-card-subtitle>

                        <template #append>
                          <div class="d-flex flex-wrap justify-end ga-2">
                            <v-btn
                              v-if="canPreviewRoutes"
                              color="secondary"
                              prepend-icon="mdi-flask-outline"
                              variant="tonal"
                              @click="openPreview"
                            >
                              Open route tester
                            </v-btn>
                            <v-btn prepend-icon="mdi-refresh" variant="text" @click="refreshRouteRuntimeScaffolding">
                              Refresh
                            </v-btn>
                          </div>
                        </template>
                      </v-card-item>

                      <v-divider />

                      <v-card-text class="d-flex flex-column ga-4">
                        <v-sheet class="schema-summary-card pa-4" rounded="xl">
                          <div class="d-flex flex-wrap align-center justify-space-between ga-2">
                            <div class="text-overline text-medium-emphasis">Route status</div>
                            <v-chip
                              v-if="routeTestState"
                              :color="routeTestState.liveStatusColor"
                              label
                              size="small"
                              variant="tonal"
                            >
                              {{ routeTestState.liveStatusLabel }}
                            </v-chip>
                          </div>
                          <div class="text-h6">{{ routeTestState?.liveHeadline ?? "Live route state" }}</div>
                          <div class="text-body-2 text-medium-emphasis">{{ routeTestState?.liveSummary }}</div>

                          <v-divider class="my-3" />

                          <div class="d-flex flex-wrap align-start ga-5">
                            <div>
                              <div class="text-caption text-medium-emphasis">Contract preview</div>
                              <div class="text-body-1">{{ routeTestState?.previewHeadline ?? "Contract preview" }}</div>
                              <div class="text-body-2 text-medium-emphasis">{{ routeTestState?.previewSummary }}</div>
                            </div>
                            <div>
                              <div class="text-caption text-medium-emphasis">Draft status</div>
                              <div class="d-flex flex-wrap align-center ga-2">
                                <v-chip
                                  v-if="routeTestState"
                                  :color="routeTestState.currentDraftBadgeColor"
                                  label
                                  size="small"
                                  variant="tonal"
                                >
                                  {{ routeTestState.currentDraftBadgeLabel }}
                                </v-chip>
                                <span class="text-body-1">{{ routeTestState?.draftHeadline ?? "Current draft" }}</span>
                              </div>
                              <div class="text-body-2 text-medium-emphasis mt-1">{{ routeTestState?.draftSummary }}</div>
                            </div>
                          </div>
                        </v-sheet>

                        <v-skeleton-loader
                          v-if="isLoadingExecutions"
                          type="table-heading, table-row-divider, table-row-divider"
                        />

                        <div v-else-if="executions.length === 0" class="text-body-2 text-medium-emphasis">
                          {{ routeTestState?.executionsEmptyState ?? "No live executions yet." }}
                        </div>

                        <div v-else class="d-flex flex-column ga-3">
                          <v-sheet
                            v-for="execution in executions"
                            :key="execution.id"
                            class="runtime-row pa-4"
                            :class="{
                              'runtime-row--selectable': true,
                              'runtime-row--selected': selectedExecutionId === execution.id,
                            }"
                            :aria-label="`Inspect run ${execution.id}`"
                            rounded="lg"
                            role="button"
                            tabindex="0"
                            @click="selectExecution(execution.id)"
                            @keydown.enter.prevent="selectExecution(execution.id)"
                            @keydown.space.prevent="selectExecution(execution.id)"
                          >
                            <div class="d-flex flex-wrap align-center justify-space-between ga-3">
                              <div class="d-flex flex-wrap align-center ga-2">
                                <v-chip
                                  :color="executionStatusColor(execution.status)"
                                  label
                                  size="small"
                                  variant="tonal"
                                >
                                  {{ execution.status }}
                                </v-chip>
                                <v-chip label size="small" variant="outlined">{{ execution.method }}</v-chip>
                                <span class="font-weight-medium">{{ execution.path }}</span>
                              </div>
                              <div class="text-caption text-medium-emphasis">
                                {{ formatTimestamp(execution.started_at) }}
                              </div>
                            </div>

                            <div class="d-flex flex-wrap align-center justify-space-between ga-3 mt-3 text-body-2 text-medium-emphasis">
                              <div class="d-flex flex-wrap ga-3">
                                <span>Status code: {{ execution.response_status_code ?? "n/a" }}</span>
                                <span>Environment: {{ execution.environment }}</span>
                                <span>Published implementation: {{ execution.implementation_id ?? "n/a" }}</span>
                              </div>
                              <v-chip
                                :color="selectedExecutionId === execution.id ? 'primary' : 'secondary'"
                                label
                                size="small"
                                variant="tonal"
                              >
                                {{ selectedExecutionId === execution.id ? "Selected" : "Inspect run" }}
                              </v-chip>
                            </div>
                          </v-sheet>

                          <v-skeleton-loader
                            v-if="isLoadingExecutionDetail"
                            type="heading, paragraph, paragraph, paragraph"
                          />

                          <v-alert v-else-if="executionDetailError" border="start" color="error" variant="tonal">
                            {{ executionDetailError }}
                          </v-alert>

                          <v-sheet
                            v-else-if="selectedExecutionDetail"
                            class="runtime-row pa-4 d-flex flex-column ga-4"
                            rounded="lg"
                          >
                            <div class="d-flex flex-wrap align-start justify-space-between ga-3">
                              <div>
                                <div class="text-overline text-medium-emphasis">Execution details</div>
                                <div class="text-h6">
                                  Run #{{ selectedExecutionDetail.id }} · {{ selectedExecutionDetail.method }}
                                  {{ selectedExecutionDetail.path }}
                                </div>
                                <div class="text-body-2 text-medium-emphasis">
                                  Started {{ formatTimestamp(selectedExecutionDetail.started_at) }} · Completed
                                  {{ formatTimestamp(selectedExecutionDetail.completed_at) }}
                                </div>
                              </div>
                              <v-btn
                                color="secondary"
                                prepend-icon="mdi-flask-outline"
                                variant="tonal"
                                @click="replayExecutionInTester"
                              >
                                Replay in tester
                              </v-btn>
                            </div>

                            <v-alert border="start" color="info" variant="tonal">
                              {{ selectedExecutionBodyReplayNote }}
                            </v-alert>

                            <div class="d-flex flex-wrap ga-3 text-body-2 text-medium-emphasis">
                              <span>Status code: {{ selectedExecutionDetail.response_status_code ?? "n/a" }}</span>
                              <span>Environment: {{ selectedExecutionDetail.environment }}</span>
                              <span>Deployment: {{ selectedExecutionDetail.deployment_id ?? "n/a" }}</span>
                              <span>Implementation: {{ selectedExecutionDetail.implementation_id ?? "n/a" }}</span>
                            </div>

                            <v-row density="comfortable">
                              <v-col cols="12" md="4">
                                <v-sheet class="schema-summary-card pa-3" rounded="lg">
                                  <div class="text-overline text-medium-emphasis">Request metadata</div>
                                  <pre class="execution-json mt-2">{{ formatJson(selectedExecutionDetail.request_data) }}</pre>
                                </v-sheet>
                              </v-col>
                              <v-col cols="12" md="4">
                                <v-sheet class="schema-summary-card pa-3" rounded="lg">
                                  <div class="text-overline text-medium-emphasis">Response body</div>
                                  <pre class="execution-json mt-2">{{ formatJson(selectedExecutionDetail.response_body) }}</pre>
                                </v-sheet>
                              </v-col>
                              <v-col cols="12" md="4">
                                <v-sheet class="schema-summary-card pa-3" rounded="lg">
                                  <div class="text-overline text-medium-emphasis">Runtime error</div>
                                  <pre class="execution-json mt-2">{{ selectedExecutionDetail.error_message ?? "n/a" }}</pre>
                                </v-sheet>
                              </v-col>
                            </v-row>

                            <div class="d-flex flex-column ga-3">
                              <div class="text-overline text-medium-emphasis">Execution steps</div>
                              <div
                                v-if="selectedExecutionSteps.length === 0"
                                class="text-body-2 text-medium-emphasis"
                              >
                                No step traces were recorded for this run.
                              </div>
                              <v-sheet
                                v-for="step in selectedExecutionSteps"
                                :key="step.id"
                                class="runtime-row pa-3"
                                rounded="lg"
                              >
                                <div class="d-flex flex-wrap align-center justify-space-between ga-3">
                                  <div class="d-flex flex-wrap align-center ga-2">
                                    <v-chip :color="executionStatusColor(step.status)" label size="small" variant="tonal">
                                      {{ step.status }}
                                    </v-chip>
                                    <v-chip label size="small" variant="outlined">
                                      #{{ step.order_index }} · {{ step.node_type }}
                                    </v-chip>
                                    <span class="font-weight-medium">{{ step.node_id }}</span>
                                  </div>
                                  <div class="text-caption text-medium-emphasis">
                                    {{ formatTimestamp(step.started_at) }}
                                  </div>
                                </div>
                                <div class="mt-3 d-flex flex-column ga-2">
                                  <v-sheet class="schema-summary-card pa-2" rounded="lg">
                                    <div class="text-caption text-medium-emphasis">Input</div>
                                    <pre class="execution-json mt-1">{{ formatJson(step.input_data) }}</pre>
                                  </v-sheet>
                                  <v-sheet class="schema-summary-card pa-2" rounded="lg">
                                    <div class="text-caption text-medium-emphasis">Output</div>
                                    <pre class="execution-json mt-1">{{ formatJson(step.output_data) }}</pre>
                                  </v-sheet>
                                  <v-sheet class="schema-summary-card pa-2" rounded="lg">
                                    <div class="text-caption text-medium-emphasis">Error</div>
                                    <pre class="execution-json mt-1">{{ step.error_message ?? "n/a" }}</pre>
                                  </v-sheet>
                                </div>
                              </v-sheet>
                            </div>
                          </v-sheet>
                        </div>
                      </v-card-text>
                    </v-card>
                  </template>

                  <template v-else-if="activeWorkspaceTab === 'deploy'">
                    <v-card class="workspace-card">
                      <v-card-item>
                        <template #prepend>
                          <v-avatar color="secondary" variant="tonal">
                            <v-icon icon="mdi-rocket-launch-outline" />
                          </v-avatar>
                        </template>
                        <v-card-title>Deploy</v-card-title>
                        <v-card-subtitle>
                          Publish the saved flow to live traffic or turn live traffic off.
                        </v-card-subtitle>

                        <template #append>
                          <div class="d-flex flex-wrap justify-end ga-2">
                            <v-btn prepend-icon="mdi-refresh" variant="text" @click="refreshRouteRuntimeScaffolding">
                              Refresh
                            </v-btn>
                            <v-btn
                              v-if="activeDeployment"
                              color="warning"
                              :loading="isUnpublishingDeployment"
                              prepend-icon="mdi-power-plug-off-outline"
                              variant="tonal"
                              @click="unpublishFlowDeployment"
                            >
                              Disable live route
                            </v-btn>
                            <v-btn
                              color="primary"
                              :loading="isPublishingDeployment"
                              prepend-icon="mdi-rocket-launch-outline"
                              @click="publishFlowDeployment"
                            >
                              Publish live route
                            </v-btn>
                          </div>
                        </template>
                      </v-card-item>

                      <v-divider />

                      <v-card-text class="d-flex flex-column ga-4">
                        <v-sheet class="deployment-summary-card pa-4" rounded="xl">
                          <div class="d-flex flex-wrap align-center justify-space-between ga-2">
                            <div class="text-overline text-medium-emphasis">{{ deploymentStatusTitle }}</div>
                            <v-chip
                              :color="activeDeployment ? 'accent' : hasDeploymentHistory ? 'warning' : 'secondary'"
                              label
                              size="small"
                              variant="tonal"
                            >
                              {{ activeDeployment ? "Live" : hasDeploymentHistory ? "Inactive" : "Not published" }}
                            </v-chip>
                          </div>
                          <div class="text-h6">{{ deploymentHeadline }}</div>
                          <div class="text-body-2 text-medium-emphasis">{{ deploymentSummary }}</div>

                          <v-divider class="my-3" />

                          <div class="text-caption text-medium-emphasis">Current draft</div>
                          <div class="d-flex flex-wrap align-center ga-2">
                            <v-chip
                              :color="currentImplementation?.is_draft === false ? 'accent' : 'warning'"
                              label
                              size="small"
                              variant="tonal"
                            >
                              {{ currentImplementation?.is_draft === false ? "Published base" : "Draft" }}
                            </v-chip>
                            <span class="text-body-1">v{{ currentImplementation?.version ?? 1 }}</span>
                          </div>
                        </v-sheet>

                        <v-skeleton-loader
                          v-if="isLoadingDeployments"
                          type="table-heading, table-row-divider, table-row-divider"
                        />

                        <div v-else-if="deployments.length === 0" class="text-body-2 text-medium-emphasis">
                          No deployment history yet. Publish once to make this route live.
                        </div>

                        <div v-else class="d-flex flex-column ga-3">
                          <v-sheet
                            v-for="deployment in deployments"
                            :key="deployment.id"
                            class="runtime-row pa-4"
                            rounded="lg"
                          >
                            <div class="d-flex flex-wrap align-center justify-space-between ga-3">
                              <div class="d-flex flex-wrap align-center ga-2">
                                <v-chip
                                  :color="deploymentStatusColor(deployment.is_active)"
                                  label
                                  size="small"
                                  variant="tonal"
                                >
                                  {{ deployment.is_active ? "Active" : "Inactive" }}
                                </v-chip>
                                <span class="font-weight-medium">
                                  {{ deployment.environment }} · implementation {{ deployment.implementation_id }}
                                </span>
                              </div>
                              <div class="text-caption text-medium-emphasis">
                                {{ formatTimestamp(deployment.published_at) }}
                              </div>
                            </div>
                          </v-sheet>
                        </div>
                      </v-card-text>
                    </v-card>
                  </template>
                </div>
              </v-slide-y-transition>
            </template>
          </div>
        </div>
      </v-col>
    </v-row>

    <v-dialog v-model="importDialog" max-width="960">
      <v-card class="workspace-card">
        <v-card-item>
          <v-card-title>Import routes</v-card-title>
          <v-card-subtitle>Preview a native Artificer bundle before applying it to this catalog.</v-card-subtitle>
        </v-card-item>

        <v-divider />

        <v-card-text class="d-flex flex-column ga-4">
          <v-alert v-if="importError" border="start" color="error" variant="tonal">
            {{ importError }}
          </v-alert>

          <v-alert
            v-else-if="importPreview?.has_errors"
            border="start"
            color="warning"
            variant="tonal"
          >
            Review the bundle errors below before importing routes.
          </v-alert>

          <v-select
            :disabled="isPreviewingImport || isApplyingImport"
            :items="importModeOptions"
            item-title="title"
            item-value="value"
            label="Import mode"
            :model-value="importMode"
            @update:model-value="importMode = ($event as EndpointImportMode | null) ?? 'upsert'"
          />

          <v-file-input
            accept=".json,application/json"
            clearable
            :disabled="isPreviewingImport || isApplyingImport"
            label="Bundle file"
            :model-value="importFile"
            prepend-icon="mdi-file-import-outline"
            show-size
            @update:model-value="handleImportFileChange"
          />

          <div class="text-caption text-medium-emphasis">Or paste the bundle JSON directly.</div>

          <v-textarea
            auto-grow
            :disabled="isPreviewingImport || isApplyingImport"
            label="Bundle JSON"
            :model-value="importText"
            rows="8"
            @update:model-value="importText = String($event ?? '')"
          />

          <div v-if="importPreview" class="d-flex flex-column ga-3">
            <div class="d-flex flex-wrap ga-2">
              <v-chip color="primary" label size="small" variant="tonal">
                {{ importPreview.summary.endpoint_count }} bundled
              </v-chip>
              <v-chip v-if="importPreview.summary.create_count" color="accent" label size="small" variant="tonal">
                {{ importPreview.summary.create_count }} create
              </v-chip>
              <v-chip v-if="importPreview.summary.update_count" color="primary" label size="small" variant="tonal">
                {{ importPreview.summary.update_count }} update
              </v-chip>
              <v-chip v-if="importPreview.summary.delete_count" color="error" label size="small" variant="tonal">
                {{ importPreview.summary.delete_count }} delete
              </v-chip>
              <v-chip v-if="importPreview.summary.skip_count" color="secondary" label size="small" variant="tonal">
                {{ importPreview.summary.skip_count }} skip
              </v-chip>
              <v-chip v-if="importPreview.summary.error_count" color="warning" label size="small" variant="tonal">
                {{ importPreview.summary.error_count }} error
              </v-chip>
            </div>

            <div class="import-operation-list d-flex flex-column ga-2">
              <v-sheet
                v-for="operation in importPreview.operations"
                :key="`${operation.action}:${operation.method}:${operation.path}:${operation.name}`"
                class="import-operation-row pa-3"
                rounded="lg"
              >
                <div class="d-flex flex-wrap align-center justify-space-between ga-3">
                  <div class="d-flex flex-wrap align-center ga-2">
                    <v-chip
                      :color="importOperationColor(operation.action)"
                      label
                      size="small"
                      variant="tonal"
                    >
                      {{ importOperationLabel(operation.action) }}
                    </v-chip>
                    <v-chip label size="small" variant="outlined">{{ operation.method }}</v-chip>
                    <span class="font-weight-medium">{{ operation.name }}</span>
                  </div>
                  <code>{{ operation.path }}</code>
                </div>

                <div v-if="operation.detail" class="text-body-2 text-medium-emphasis mt-2">
                  {{ operation.detail }}
                </div>
              </v-sheet>
            </div>
          </div>
        </v-card-text>

        <v-divider />

        <v-card-actions class="justify-end">
          <v-btn variant="text" @click="importDialog = false">Close</v-btn>
          <v-btn
            :loading="isPreviewingImport"
            prepend-icon="mdi-clipboard-search-outline"
            variant="text"
            @click="previewImportRoutes"
          >
            Preview import
          </v-btn>
          <v-btn
            color="primary"
            :disabled="!canApplyImport"
            :loading="isApplyingImport"
            prepend-icon="mdi-upload"
            @click="applyImportedRoutes"
          >
            Import routes
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.endpoint-sidebar,
.endpoint-detail-shell {
  width: 100%;
}

.endpoint-detail-shell {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.endpoint-detail-scroll {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 1rem;
  min-height: 0;
}

.workspace-tabs-card {
  overflow: hidden;
}

.flow-connection-context-row {
  min-height: 2rem;
}

.deployment-summary-card,
.schema-summary-card,
.runtime-row,
.browse-metric-card,
.telemetry-row {
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 94%, rgb(var(--v-theme-background)) 6%);
}

.browse-metrics-grid,
.browse-mix-grid,
.browse-telemetry-grid,
.browse-telemetry-detail-grid {
  margin: 0;
}

.runtime-row--selectable {
  cursor: pointer;
  transition: border-color 160ms ease, background-color 160ms ease;
}

.runtime-row--selectable:hover {
  border-color: rgba(var(--v-theme-primary), 0.42);
}

.runtime-row--selected {
  border-color: rgba(var(--v-theme-primary), 0.62);
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 90%, rgb(var(--v-theme-primary)) 10%);
}

.deployment-summary-card {
  min-width: min(100%, 18rem);
}

.flow-json-editor :deep(textarea) {
  font-family: "JetBrains Mono", "Fira Code", "Source Code Pro", monospace;
  line-height: 1.45;
}

.execution-json {
  margin: 0;
  overflow-x: auto;
  white-space: pre;
  font-family: "JetBrains Mono", "Fira Code", "Source Code Pro", monospace;
  font-size: 0.75rem;
  line-height: 1.4;
}

.import-operation-list {
  max-height: 18rem;
  overflow-y: auto;
}

.import-operation-row {
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: color-mix(in srgb, rgb(var(--v-theme-surface)) 94%, rgb(var(--v-theme-background)) 6%);
}

@media (min-width: 1280px) {
  .endpoint-workspace-grid {
    min-height: calc(100vh - var(--v-layout-top, 88px) - 3rem);
  }

  .endpoint-detail-col {
    display: flex;
  }

  .endpoint-sidebar-col {
    display: flex;
    position: sticky;
    top: 0;
    align-self: flex-start;
  }

  .endpoint-sidebar {
    height: calc(100vh - var(--v-layout-top, 88px) - 3rem);
    max-height: calc(100vh - var(--v-layout-top, 88px) - 3rem);
  }
}
</style>
