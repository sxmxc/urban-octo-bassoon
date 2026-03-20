<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  AdminApiError,
  getCurrentRouteImplementation,
  getEndpoint,
  listRouteDeployments,
  previewResponse,
} from "../api/admin";
import { useAuth } from "../composables/useAuth";
import type { Endpoint, JsonValue, RouteDeployment, RouteImplementation } from "../types/endpoints";
import { buildRouteTestState } from "../utils/routeTestState";
import {
  buildDefaultParameterValue,
  extractRequestBodySchema,
  extractRequestParameterDefinitions,
  syncPathParameterDefinitions,
  type RequestParameterDefinition,
} from "../utils/requestSchema";
import { buildDefaultPathParameters, resolvePathParameters } from "../utils/pathParameters";
import { buildSampleRequestBody } from "../utils/responseTemplates";

const route = useRoute();
const router = useRouter();
const auth = useAuth();

const endpoint = ref<Endpoint | null>(null);
const pathParameters = ref<Record<string, string>>({});
const queryParameters = ref<Record<string, string>>({});
const requestBody = ref("{}");
const samplePreview = ref<string | null>(null);
const contractPreviewTab = ref<"request" | "response">("response");
const currentImplementation = ref<RouteImplementation | null>(null);
const deployments = ref<RouteDeployment[]>([]);
const previewResult = ref<{
  body: string;
  contentType: string;
  status: number;
  statusText: string;
} | null>(null);
const isLoading = ref(true);
const isLoadingContractPreview = ref(false);
const isRunning = ref(false);
const loadError = ref<string | null>(null);
const contractPreviewError = ref<string | null>(null);
const requestError = ref<string | null>(null);
const runtimeStateError = ref<string | null>(null);
const replayNotice = ref<string | null>(null);

const endpointId = computed(() => {
  const rawId = route.params.endpointId;
  return typeof rawId === "string" ? Number(rawId) : null;
});
const pathParameterDefinitions = computed<RequestParameterDefinition[]>(() =>
  endpoint.value
    ? syncPathParameterDefinitions(
        endpoint.value.path,
        extractRequestParameterDefinitions(endpoint.value.request_schema ?? {}, "path"),
      )
    : [],
);
const queryParameterDefinitions = computed<RequestParameterDefinition[]>(() =>
  endpoint.value ? extractRequestParameterDefinitions(endpoint.value.request_schema ?? {}, "query") : [],
);
const requestBodySchema = computed(() =>
  endpoint.value ? extractRequestBodySchema(endpoint.value.request_schema ?? {}) : {},
);
const contractRequestBodySample = computed<JsonValue | null>(() => buildSampleRequestBody(requestBodySchema.value));
const canWriteRoutes = computed(() => auth.canWriteRoutes.value && !auth.mustChangePassword.value);
const routeTestState = computed(() =>
  endpoint.value ? buildRouteTestState(endpoint.value, currentImplementation.value, deployments.value) : null,
);
const contractRequestPreviewText = computed(() => {
  if (!endpoint.value) {
    return prettyJson({});
  }

  const queryEntries = Object.entries(queryParameters.value)
    .filter(([, value]) => String(value ?? "").trim().length > 0)
    .map(([key, value]) => [key, String(value)]);
  const queryString = new URLSearchParams(queryEntries).toString();

  const previewPayload: Record<string, unknown> = {
    method: endpoint.value.method,
    path_template: endpoint.value.path,
    resolved_path: resolvePathParameters(endpoint.value.path, pathParameters.value),
    path_parameters: pathParameters.value,
    query_parameters: queryParameters.value,
  };

  if (queryString) {
    previewPayload.query_string = queryString;
  }

  if (!["GET", "DELETE"].includes(endpoint.value.method)) {
    previewPayload.request_body = contractRequestBodySample.value;

    const trimmedBody = requestBody.value.trim();
    if (!trimmedBody) {
      if (contractRequestBodySample.value !== null) {
        previewPayload.live_request_body_input = null;
      }
    } else {
      try {
        const parsedBody = JSON.parse(trimmedBody) as JsonValue;
        if (JSON.stringify(parsedBody) !== JSON.stringify(contractRequestBodySample.value)) {
          previewPayload.live_request_body_input = parsedBody;
        }
      } catch {
        previewPayload.live_request_body_raw = requestBody.value;
        previewPayload.live_request_body_error = "Request body must be valid JSON.";
      }
    }
  }

  return prettyJson(previewPayload);
});

function buildDefaultQueryParameterValues(parameters: RequestParameterDefinition[]): Record<string, string> {
  return parameters.reduce<Record<string, string>>((accumulator, parameter) => {
    accumulator[parameter.name] = "";
    return accumulator;
  }, {});
}

watch(
  endpointId,
  () => {
    void loadEndpoint();
  },
  { immediate: true },
);

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function parseReplayMap(prefix: "replay_path_" | "replay_query_"): Record<string, string> {
  const replayMap: Record<string, string> = {};

  for (const [key, rawValue] of Object.entries(route.query)) {
    if (!key.startsWith(prefix)) {
      continue;
    }

    const normalizedKey = key.slice(prefix.length);
    if (!normalizedKey) {
      continue;
    }

    const value = Array.isArray(rawValue) ? rawValue[0] : rawValue;
    if (typeof value !== "string") {
      continue;
    }

    replayMap[normalizedKey] = value;
  }

  return replayMap;
}

function buildReplayNotice(options: {
  replayRunId: string;
  replayPathParameters: Record<string, string>;
  replayQueryParameters: Record<string, string>;
  replayBodyCaptured: string | null | undefined;
}): string {
  const replayInputCount =
    Object.keys(options.replayPathParameters).length + Object.keys(options.replayQueryParameters).length;

  if (replayInputCount === 0) {
    if (options.replayBodyCaptured === "0") {
      return `Replaying run #${options.replayRunId}: this trace had no path/query inputs to prefill, and request body replay is unavailable because only body-presence metadata was captured.`;
    }

    return `Replaying run #${options.replayRunId}: this trace had no path or query inputs to prefill.`;
  }

  if (options.replayBodyCaptured === "0") {
    return `Replaying run #${options.replayRunId}: path/query inputs were prefilled, but request body replay is unavailable because only body-presence metadata was captured for this trace.`;
  }

  return `Replaying run #${options.replayRunId}: path/query inputs were prefilled from the selected execution trace.`;
}

async function loadEndpoint(): Promise<void> {
  if (!endpointId.value || !auth.session.value) {
    isLoading.value = false;
    loadError.value = "Missing endpoint id.";
    return;
  }

  isLoading.value = true;
  loadError.value = null;
  contractPreviewError.value = null;
  requestError.value = null;
  runtimeStateError.value = null;
  replayNotice.value = null;

  try {
    const loadedEndpoint = await getEndpoint(endpointId.value, auth.session.value);
    endpoint.value = loadedEndpoint;
    pathParameters.value = pathParameterDefinitions.value.reduce<Record<string, string>>((accumulator, parameter) => {
      accumulator[parameter.name] = buildDefaultParameterValue(parameter);
      return accumulator;
    }, buildDefaultPathParameters(loadedEndpoint.path));
    queryParameters.value = buildDefaultQueryParameterValues(queryParameterDefinitions.value);

    const replayPathParameters = parseReplayMap("replay_path_");
    const replayQueryParameters = parseReplayMap("replay_query_");
    if (Object.keys(replayPathParameters).length > 0) {
      pathParameters.value = {
        ...pathParameters.value,
        ...replayPathParameters,
      };
    }
    if (Object.keys(replayQueryParameters).length > 0) {
      queryParameters.value = {
        ...queryParameters.value,
        ...replayQueryParameters,
      };
    }

    const replayRunIdRaw = Array.isArray(route.query.replayRunId) ? route.query.replayRunId[0] : route.query.replayRunId;
    const replayRunId = typeof replayRunIdRaw === "string" && replayRunIdRaw.trim() ? replayRunIdRaw.trim() : null;
    const replayBodyCapturedRaw = Array.isArray(route.query.replayBodyCaptured)
      ? route.query.replayBodyCaptured[0]
      : route.query.replayBodyCaptured;
    if (replayRunId) {
      replayNotice.value = buildReplayNotice({
        replayRunId,
        replayPathParameters,
        replayQueryParameters,
        replayBodyCaptured: typeof replayBodyCapturedRaw === "string" ? replayBodyCapturedRaw : null,
      });
    }

    if (["GET", "DELETE"].includes(loadedEndpoint.method)) {
      requestBody.value = "{}";
    } else {
      const requestBodySample = buildSampleRequestBody(extractRequestBodySchema(loadedEndpoint.request_schema ?? {}));
      requestBody.value = requestBodySample === null ? "" : prettyJson(requestBodySample);
    }
    previewResult.value = null;
    samplePreview.value = null;

    const [implementationResult, deploymentsResult] = await Promise.allSettled([
      getCurrentRouteImplementation(endpointId.value, auth.session.value),
      listRouteDeployments(endpointId.value, auth.session.value),
    ]);

    const runtimeErrors = [implementationResult, deploymentsResult].filter(
      (result): result is PromiseRejectedResult => result.status === "rejected",
    );
    const unauthorizedRuntimeError = runtimeErrors.find(
      (result) => result.reason instanceof AdminApiError && result.reason.status === 401,
    );

    if (unauthorizedRuntimeError) {
      void auth.logout("Your admin session expired. Sign in again before previewing endpoints.");
      void router.push({ name: "login" });
      return;
    }

    currentImplementation.value = implementationResult.status === "fulfilled" ? implementationResult.value : null;
    deployments.value = deploymentsResult.status === "fulfilled" ? deploymentsResult.value : [];

    if (runtimeErrors.length > 0) {
      runtimeStateError.value =
        "Live deployment status is temporarily unavailable. You can still generate contract previews and send public requests from this page.";
    }

    await refreshContractPreview();
  } catch (error) {
    if (error instanceof AdminApiError && error.status === 401) {
      void auth.logout("Your admin session expired. Sign in again before previewing endpoints.");
      void router.push({ name: "login" });
      return;
    }

    loadError.value = error instanceof Error ? error.message : "Unable to load the endpoint preview.";
  } finally {
    isLoading.value = false;
  }
}

function parseRequestBody(
  errorMessage: string,
): {
  error: string | null;
  parsed: JsonValue | null;
  raw: string | null;
} {
  if (!endpoint.value || ["GET", "DELETE"].includes(endpoint.value.method) || !requestBody.value.trim()) {
    return {
      error: null,
      parsed: null,
      raw: null,
    };
  }

  try {
    return {
      error: null,
      parsed: JSON.parse(requestBody.value) as JsonValue,
      raw: requestBody.value,
    };
  } catch {
    return {
      error: errorMessage,
      parsed: null,
      raw: null,
    };
  }
}

async function refreshContractPreview(): Promise<void> {
  if (!endpoint.value || !auth.session.value) {
    return;
  }

  contractPreviewError.value = null;
  requestError.value = null;
  isLoadingContractPreview.value = true;

  const requestBodyState = parseRequestBody("Request body must be valid JSON before generating the contract preview.");
  if (requestBodyState.error) {
    contractPreviewError.value = requestBodyState.error;
    isLoadingContractPreview.value = false;
    return;
  }

  try {
    const response = await previewResponse(
      endpoint.value.response_schema ?? {},
      endpoint.value.seed_key ?? null,
      pathParameters.value,
      auth.session.value,
      {
        queryParameters: queryParameters.value,
        requestBody: requestBodyState.parsed,
      },
    );
    samplePreview.value = prettyJson(response.preview);
  } catch (error) {
    samplePreview.value = null;
    contractPreviewError.value =
      error instanceof Error ? error.message : "Unable to generate the contract preview.";
  } finally {
    isLoadingContractPreview.value = false;
  }
}

async function runLiveRequest(): Promise<void> {
  if (!endpoint.value) {
    return;
  }

  requestError.value = null;
  previewResult.value = null;
  isRunning.value = true;

  try {
    const requestBodyState = parseRequestBody("Request body must be valid JSON before sending the live request.");
    if (requestBodyState.error) {
      requestError.value = requestBodyState.error;
      isRunning.value = false;
      return;
    }

    const contractPreviewRefresh = refreshContractPreview();

    const queryString = new URLSearchParams(
      Object.entries(queryParameters.value).filter(([, value]) => String(value ?? "").trim()),
    ).toString();

    const requestPath = resolvePathParameters(endpoint.value.path, pathParameters.value);
    const response = await fetch(queryString ? `${requestPath}?${queryString}` : requestPath, {
      method: endpoint.value.method,
      headers: requestBodyState.raw ? { "Content-Type": "application/json" } : undefined,
      body: requestBodyState.raw ?? undefined,
    });
    const responseText = await response.text();

    let renderedBody = responseText;
    try {
      renderedBody = prettyJson(JSON.parse(responseText));
    } catch {
      if (!responseText) {
        renderedBody = "(empty response)";
      }
    }

    previewResult.value = {
      status: response.status,
      statusText: response.statusText,
      contentType: response.headers.get("content-type") ?? "unknown",
      body: renderedBody,
    };
    await contractPreviewRefresh;
  } catch (error) {
    requestError.value = error instanceof Error ? error.message : "Unable to send the live request.";
  } finally {
    isRunning.value = false;
  }
}
</script>

<template>
  <div class="d-flex flex-column ga-4">
    <div class="d-flex flex-column flex-lg-row justify-space-between ga-4">
      <div>
        <div class="text-overline text-secondary">Test route</div>
        <div class="text-h3 font-weight-bold mt-2">{{ endpoint?.name || "Loading route" }}</div>
        <div class="text-body-1 text-medium-emphasis mt-3">
          Compare admin-only contract previews with live/public request results for this route.
        </div>
      </div>

      <div class="d-flex flex-wrap align-start justify-end ga-2">
        <v-btn
          prepend-icon="mdi-arrow-left"
          variant="text"
          @click="router.push({ name: canWriteRoutes ? (endpoint ? 'endpoints-edit' : 'endpoints-browse') : 'endpoints-browse', params: canWriteRoutes && endpoint ? { endpointId: endpoint.id } : undefined })"
        >
          {{ canWriteRoutes ? "Back to route" : "Back to routes" }}
        </v-btn>
        <v-btn
          v-if="endpoint && canWriteRoutes"
          prepend-icon="mdi-shape-outline"
          variant="text"
          @click="router.push({ name: 'endpoints-edit', params: { endpointId: endpoint.id }, query: { tab: 'contract' } })"
        >
          Edit contract
        </v-btn>
      </div>
    </div>

    <v-skeleton-loader
      v-if="isLoading"
      class="workspace-card"
      type="heading, paragraph, paragraph, table-heading, table-row-divider, paragraph"
    />

    <v-card v-else-if="!endpoint" class="workspace-card">
      <v-card-text class="pa-8">
        <div class="text-overline text-error">Preview unavailable</div>
        <div class="text-h4 font-weight-bold mt-2">We could not load that endpoint.</div>
        <div class="text-body-1 text-medium-emphasis mt-4">
          {{ loadError ?? "The endpoint is missing or your session changed while loading the preview." }}
        </div>
      </v-card-text>
    </v-card>

    <template v-else>
      <v-card class="workspace-card">
        <v-card-text class="d-flex flex-wrap justify-space-between ga-3">
          <div class="d-flex flex-wrap ga-2">
            <v-chip color="primary" label size="small" variant="tonal">{{ endpoint.method }}</v-chip>
            <v-chip
              v-if="runtimeStateError"
              color="warning"
              label
              size="small"
              variant="tonal"
            >
              Runtime state unavailable
            </v-chip>
            <v-chip
              v-else-if="routeTestState"
              :color="routeTestState.liveStatusColor"
              label
              size="small"
              variant="tonal"
            >
              {{ routeTestState.liveStatusLabel }}
            </v-chip>
            <v-chip label size="small" variant="outlined">{{ endpoint.path }}</v-chip>
          </div>
        </v-card-text>
      </v-card>

      <v-row>
        <v-col cols="12" md="4">
          <v-card class="workspace-card fill-height">
            <v-card-text class="d-flex flex-column ga-2">
              <div class="text-overline text-medium-emphasis">Contract preview</div>
              <div class="text-h6">{{ routeTestState?.previewHeadline }}</div>
              <div class="text-body-2 text-medium-emphasis">{{ routeTestState?.previewSummary }}</div>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" md="4">
          <v-card class="workspace-card fill-height">
            <v-card-text class="d-flex flex-column ga-2">
              <div class="d-flex flex-wrap align-center justify-space-between ga-2">
                <div class="text-overline text-medium-emphasis">Live request path</div>
                <v-chip
                  v-if="runtimeStateError"
                  color="warning"
                  label
                  size="small"
                  variant="tonal"
                >
                  Unavailable
                </v-chip>
                <v-chip
                  v-else-if="routeTestState"
                  :color="routeTestState.liveStatusColor"
                  label
                  size="small"
                  variant="tonal"
                >
                  {{ routeTestState.liveStatusLabel }}
                </v-chip>
              </div>
              <div class="text-h6">{{ runtimeStateError ? "Live status unavailable" : routeTestState?.liveHeadline }}</div>
              <div class="text-body-2 text-medium-emphasis">
                {{
                  runtimeStateError
                    ? "The live/public route can still be exercised here, but deployment metadata could not be loaded."
                    : routeTestState?.liveSummary
                }}
              </div>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" md="4">
          <v-card class="workspace-card fill-height">
            <v-card-text class="d-flex flex-column ga-2">
              <div class="text-overline text-medium-emphasis">Draft vs live</div>
              <div class="d-flex flex-wrap align-center ga-2">
                <v-chip
                  v-if="runtimeStateError"
                  color="warning"
                  label
                  size="small"
                  variant="tonal"
                >
                  Unavailable
                </v-chip>
                <v-chip
                  v-else-if="routeTestState"
                  :color="routeTestState.currentDraftBadgeColor"
                  label
                  size="small"
                  variant="tonal"
                >
                  {{ routeTestState.currentDraftBadgeLabel }}
                </v-chip>
              </div>
              <div class="text-h6">{{ runtimeStateError ? "Draft status unavailable" : routeTestState?.draftHeadline }}</div>
              <div class="text-body-2 text-medium-emphasis">
                {{
                  runtimeStateError
                    ? "The flow draft and deployment relationship could not be loaded for this route."
                    : routeTestState?.draftSummary
                }}
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <v-alert border="start" color="info" variant="tonal">
        Contract preview uses the admin preview endpoint and never executes live connectors. Send live request hits the public route path and follows the live state shown above.
      </v-alert>

      <v-alert v-if="replayNotice" border="start" color="secondary" variant="tonal">
        {{ replayNotice }}
      </v-alert>

      <v-alert v-if="runtimeStateError" border="start" color="warning" variant="tonal">
        {{ runtimeStateError }}
      </v-alert>

      <v-alert v-if="contractPreviewError" border="start" color="error" variant="tonal">
        {{ contractPreviewError }}
      </v-alert>

      <v-alert v-if="requestError" border="start" color="error" variant="tonal">
        {{ requestError }}
      </v-alert>

      <v-card class="workspace-card">
        <v-card-item>
          <v-card-title>Shared inputs</v-card-title>
          <v-card-subtitle>
            Use the same path, query, and body values to compare contract preview output with a live/public request.
          </v-card-subtitle>
        </v-card-item>
        <v-divider />
        <v-card-text class="d-flex flex-column ga-4">
          <v-text-field
            v-for="parameter in pathParameterDefinitions"
            :key="parameter.name"
            v-model="pathParameters[parameter.name]"
            :hint="parameter.description || undefined"
            :label="`Path parameter: ${parameter.name}`"
            persistent-hint
          />

          <v-text-field
            v-for="parameter in queryParameterDefinitions"
            :key="parameter.name"
            v-model="queryParameters[parameter.name]"
            :hint="parameter.description || undefined"
            :label="`Query parameter: ${parameter.name}`"
            persistent-hint
          />

          <v-textarea
            v-if="!['GET', 'DELETE'].includes(endpoint.method)"
            v-model="requestBody"
            auto-grow
            label="Request body"
            rows="10"
          />
        </v-card-text>
      </v-card>

      <v-row density="comfortable">
        <v-col cols="12" lg="6">
          <v-card class="workspace-card fill-height">
            <v-card-item>
              <v-card-title>Contract preview sample</v-card-title>
              <v-card-subtitle>
                {{
                  contractPreviewTab === "request"
                    ? "Generated from the saved request contract. Current shared body input is shown only when it differs from the contract sample."
                    : "Generated from the saved response schema plus the shared preview inputs. This stays inside the admin preview engine."
                }}
              </v-card-subtitle>

              <template #append>
                <div class="d-flex flex-wrap align-center justify-end ga-2">
                  <v-btn-toggle
                    v-model="contractPreviewTab"
                    color="primary"
                    density="compact"
                    mandatory
                    variant="outlined"
                  >
                    <v-btn value="request">Request preview</v-btn>
                    <v-btn value="response">Response preview</v-btn>
                  </v-btn-toggle>
                  <v-btn
                    color="secondary"
                    :loading="isLoadingContractPreview"
                    prepend-icon="mdi-flask-outline"
                    variant="tonal"
                    @click="refreshContractPreview"
                  >
                    Generate contract preview
                  </v-btn>
                </div>
              </template>
            </v-card-item>
            <v-divider />
            <v-card-text>
              <pre v-if="contractPreviewTab === 'request'" class="code-block">{{ contractRequestPreviewText }}</pre>
              <pre v-else class="code-block">{{ samplePreview ?? "(generate the contract preview to see sample output)" }}</pre>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" lg="6">
          <v-card class="workspace-card fill-height">
            <v-card-item>
              <v-card-title>Live request result</v-card-title>
              <v-card-subtitle>
                {{
                  previewResult
                    ? `${previewResult.status} ${previewResult.statusText} • ${previewResult.contentType}`
                    : runtimeStateError
                      ? "Send the live request to inspect the public response. Deployment metadata is temporarily unavailable."
                      : routeTestState?.liveSummary ?? "Send the live request to inspect the public response."
                }}
              </v-card-subtitle>

              <template #append>
                <v-btn color="primary" :loading="isRunning" prepend-icon="mdi-play-circle-outline" @click="runLiveRequest">
                  Send live request
                </v-btn>
              </template>
            </v-card-item>
            <v-divider />
            <v-card-text>
              <pre class="code-block">{{ previewResult?.body ?? "(send the live request to see the public response body)" }}</pre>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </template>
  </div>
</template>
