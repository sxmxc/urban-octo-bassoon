<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { BuilderScope } from "../schemaBuilder";
import type { JsonObject } from "../types/endpoints";
import {
  buildRequestSchemaContract,
  extractRequestBodySchema,
  extractRequestParameterDefinitions,
  syncPathParameterDefinitions,
  type RequestParameterDefinition,
} from "../utils/requestSchema";
import { extractPathParameters } from "../utils/pathParameters";
import RequestParameterEditor from "./RequestParameterEditor.vue";
import SchemaEditorWorkspace from "./SchemaEditorWorkspace.vue";

type RequestSection = "body" | "path" | "query";

const props = withDefaults(defineProps<{
  activeTab?: BuilderScope;
  activeRequestSection?: RequestSection;
  path: string;
  requestSchema: JsonObject;
  responseSchema: JsonObject;
  seedKey: string;
}>(), {
  activeTab: "response",
  activeRequestSection: "body",
});

const emit = defineEmits<{
  "update:activeTab": [value: BuilderScope];
  "update:activeRequestSection": [value: RequestSection];
  "update:requestSchema": [value: JsonObject];
  "update:responseSchema": [value: JsonObject];
  "update:seedKey": [value: string];
}>();

const activeTabModel = computed<BuilderScope>({
  get: () => (props.activeTab === "request" ? "request" : "response"),
  set: (value) => {
    emit("update:activeTab", value);
  },
});
const requestSectionModel = computed<RequestSection>({
  get: () => (props.activeRequestSection === "path" || props.activeRequestSection === "query" ? props.activeRequestSection : "body"),
  set: (value) => {
    emit("update:activeRequestSection", value);
  },
});
const requestBodySchema = ref<JsonObject>({});
const requestPathParameters = ref<RequestParameterDefinition[]>([]);
const requestQueryParameters = ref<RequestParameterDefinition[]>([]);
const responseSchemaModel = ref<JsonObject>({});
const seedKeyModel = ref("");
const isHydrating = ref(false);

const routePathParameters = computed(() => extractPathParameters(props.path));
const requestSchemaContract = computed(() =>
  buildRequestSchemaContract(requestBodySchema.value, {
    path: requestPathParameters.value,
    query: requestQueryParameters.value,
  }),
);

const sourceSyncSignature = computed(() =>
  JSON.stringify({
    path: props.path,
    requestSchema: props.requestSchema ?? {},
    responseSchema: props.responseSchema ?? {},
    seedKey: props.seedKey ?? "",
  }),
);

watch(
  sourceSyncSignature,
  () => {
    isHydrating.value = true;
    requestBodySchema.value = extractRequestBodySchema(props.requestSchema ?? {});
    requestPathParameters.value = syncPathParameterDefinitions(
      props.path,
      extractRequestParameterDefinitions(props.requestSchema ?? {}, "path"),
    );
    requestQueryParameters.value = extractRequestParameterDefinitions(props.requestSchema ?? {}, "query");
    responseSchemaModel.value = JSON.parse(JSON.stringify(props.responseSchema ?? {})) as JsonObject;
    seedKeyModel.value = props.seedKey ?? "";
    if (!routePathParameters.value.length && requestSectionModel.value === "path") {
      requestSectionModel.value = "body";
    }
    isHydrating.value = false;
  },
  { immediate: true },
);

watch(routePathParameters, () => {
  requestPathParameters.value = syncPathParameterDefinitions(props.path, requestPathParameters.value);
  if (!routePathParameters.value.length && requestSectionModel.value === "path") {
    requestSectionModel.value = "body";
  }
});

watch(requestSchemaContract, (value) => {
  if (isHydrating.value) {
    return;
  }
  emit("update:requestSchema", value);
});

watch(responseSchemaModel, (value) => {
  if (isHydrating.value) {
    return;
  }
  emit("update:responseSchema", value);
}, { deep: true });

watch(seedKeyModel, (value) => {
  if (isHydrating.value) {
    return;
  }
  emit("update:seedKey", value);
});
</script>

<template>
  <div class="route-contract-editor d-flex flex-column ga-4">
    <v-card class="workspace-card">
      <v-card-text class="d-flex flex-column flex-xl-row justify-space-between ga-4">
        <div class="d-flex flex-wrap ga-2">
          <v-chip color="primary" label size="small" variant="tonal">
            {{ activeTabModel === "request" ? "Request contract" : "Response contract" }}
          </v-chip>
          <v-chip label size="small" variant="outlined">{{ path }}</v-chip>
        </div>

        <div class="schema-tab-shell">
          <v-tabs
            v-model="activeTabModel"
            align-tabs="start"
            color="secondary"
            density="compact"
          >
            <v-tab value="request">Request schema</v-tab>
            <v-tab value="response">Response schema</v-tab>
          </v-tabs>
        </div>
      </v-card-text>
    </v-card>

    <div v-if="activeTabModel === 'request'" class="schema-workspace-shell d-flex flex-column ga-4">
      <v-card class="workspace-card">
        <v-card-text class="d-flex flex-column flex-xl-row justify-space-between ga-4">
          <div>
            <div class="text-overline text-secondary">Request inputs</div>
            <div class="text-body-1 text-medium-emphasis mt-2">
              Model the JSON body plus any path and query inputs the route accepts.
            </div>
          </div>

          <div class="schema-tab-shell">
            <v-tabs
              v-model="requestSectionModel"
              align-tabs="start"
              color="primary"
              density="compact"
            >
              <v-tab value="body">JSON body</v-tab>
              <v-tab v-if="routePathParameters.length" value="path">Path params</v-tab>
              <v-tab value="query">Query params</v-tab>
            </v-tabs>
          </div>
        </v-card-text>
      </v-card>

      <SchemaEditorWorkspace
        v-if="requestSectionModel === 'body'"
        :schema="requestBodySchema"
        scope="request"
        @update:schema="requestBodySchema = $event"
      />

      <RequestParameterEditor
        v-else-if="requestSectionModel === 'path'"
        :parameters="requestPathParameters"
        location="path"
        subtitle="Path parameters follow the saved route template, so their names stay locked to the URL placeholders."
        title="Path parameters"
        @update:parameters="requestPathParameters = $event"
      />

      <RequestParameterEditor
        v-else
        :parameters="requestQueryParameters"
        location="query"
        subtitle="Add optional query string inputs and describe the scalar values each one accepts."
        title="Query parameters"
        @update:parameters="requestQueryParameters = $event"
      />
    </div>

    <div v-else class="schema-workspace-shell">
      <SchemaEditorWorkspace
        v-model:seed-key="seedKeyModel"
        :path-parameters="requestPathParameters"
        :query-parameters="requestQueryParameters"
        :request-body-schema="requestBodySchema"
        :schema="responseSchemaModel"
        scope="response"
        @update:schema="responseSchemaModel = $event"
      />
    </div>
  </div>
</template>
