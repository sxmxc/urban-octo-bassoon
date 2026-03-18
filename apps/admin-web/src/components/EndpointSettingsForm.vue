<script setup lang="ts">
import { computed } from "vue";
import { describeSchema } from "../utils/endpointDrafts";
import type { EndpointDraft } from "../types/endpoints";

const props = withDefaults(
  defineProps<{
    availableCategories?: string[];
    availableTags?: string[];
    createdAt?: string;
    draft: EndpointDraft;
    endpointId?: number;
    errors: Record<string, string>;
    isCreating: boolean;
    isSaving: boolean;
    showContractCard?: boolean;
    updatedAt?: string;
  }>(),
  {
    availableCategories: () => [],
    availableTags: () => [],
    createdAt: undefined,
    endpointId: undefined,
    showContractCard: true,
    updatedAt: undefined,
  },
);

const emit = defineEmits<{
  change: [patch: Partial<EndpointDraft>];
  delete: [];
  duplicate: [];
  openSchema: [];
  preview: [];
  submit: [];
}>();

const methodOptions = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"];
const authOptions = [
  { title: "None", value: "none" },
  { title: "Basic", value: "basic" },
  { title: "API key", value: "api_key" },
  { title: "Bearer", value: "bearer" },
];

const requestSummary = computed(() => describeSchema(props.draft.request_schema, "request"));
const responseSummary = computed(() => describeSchema(props.draft.response_schema, "response"));
const categoryOptions = computed(() =>
  Array.from(
    new Set(
      [...(props.availableCategories ?? []), props.draft.category]
        .map((category) => String(category ?? "").trim())
        .filter(Boolean),
    ),
  ),
);
const tagValues = computed<string[]>({
  get: () =>
    props.draft.tags
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
  set: (value) => {
    const normalized = Array.from(
      new Set(
        (value ?? [])
          .map((tag) => String(tag ?? "").trim())
          .filter(Boolean),
      ),
    );
    patch({ tags: normalized.join(", ") });
  },
});
const tagOptions = computed(() =>
  Array.from(
    new Set(
      [...(props.availableTags ?? []), ...tagValues.value]
        .map((tag) => String(tag ?? "").trim())
        .filter(Boolean),
    ),
  ),
);

function patch(value: Partial<EndpointDraft>): void {
  emit("change", value);
}

function numberPatch(field: keyof EndpointDraft, value: string | number | null): void {
  const nextValue = typeof value === "number" ? value : Number(value ?? 0);
  patch({ [field]: Number.isFinite(nextValue) ? nextValue : 0 } as Partial<EndpointDraft>);
}
</script>

<template>
  <v-form class="d-flex flex-column ga-5" @submit.prevent="emit('submit')">
    <v-card v-if="showContractCard" class="workspace-card">
      <v-card-item>
        <v-card-title>{{ isCreating ? "Create route" : draft.name || "Untitled route" }}</v-card-title>
        <v-card-subtitle>
          {{ isCreating ? "Set the path, method, and behavior first." : "Edit the route details, runtime behavior, and schema." }}
        </v-card-subtitle>

        <template #append>
          <div class="d-flex flex-wrap justify-end ga-2">
            <v-btn
              v-if="!isCreating"
              color="secondary"
              prepend-icon="mdi-shape-outline"
              variant="tonal"
              @click="emit('openSchema')"
            >
              Edit schema
            </v-btn>
            <v-btn
              v-if="!isCreating"
              prepend-icon="mdi-flask-outline"
              variant="text"
              @click="emit('preview')"
            >
              Test route
            </v-btn>
            <v-btn
              v-if="!isCreating"
              prepend-icon="mdi-content-copy"
              variant="text"
              @click="emit('duplicate')"
            >
              Duplicate
            </v-btn>
            <v-btn
              v-if="!isCreating"
              color="error"
              prepend-icon="mdi-delete-outline"
              variant="text"
              @click="emit('delete')"
            >
              Delete
            </v-btn>
            <v-btn color="primary" :loading="isSaving" prepend-icon="mdi-content-save-outline" type="submit">
              {{ isCreating ? "Create route" : "Save changes" }}
            </v-btn>
          </div>
        </template>
      </v-card-item>

      <v-divider />

      <v-card-text class="d-flex flex-column ga-4">
        <div v-if="!isCreating && endpointId" class="d-flex flex-wrap ga-3 text-caption text-medium-emphasis">
          <span>Endpoint #{{ endpointId }}</span>
          <span v-if="createdAt">Created {{ new Date(createdAt).toLocaleString() }}</span>
          <span v-if="updatedAt">Updated {{ new Date(updatedAt).toLocaleString() }}</span>
        </div>

        <v-row>
          <v-col cols="12" md="6">
            <v-text-field
              :error-messages="errors.name"
              label="Name"
              :model-value="draft.name"
              @update:model-value="patch({ name: String($event ?? '') })"
            />
          </v-col>
          <v-col cols="12" md="4">
            <v-select
              label="Method"
              :items="methodOptions"
              :model-value="draft.method"
              @update:model-value="patch({ method: String($event ?? 'GET') })"
            />
          </v-col>
          <v-col cols="12" md="8">
            <v-text-field
              :error-messages="errors.path"
              label="Path"
              :model-value="draft.path"
              placeholder="/api/widgets/{id}"
              @update:model-value="patch({ path: String($event ?? '') })"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-combobox
              clearable
              :items="categoryOptions"
              label="Category"
              :model-value="draft.category"
              placeholder="Select an existing category or type a new one"
              @update:model-value="patch({ category: String($event ?? '') })"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-combobox
              v-model="tagValues"
              :items="tagOptions"
              chips
              clearable
              closable-chips
              :delimiters="[',']"
              hide-selected
              label="Tags"
              multiple
              placeholder="Select tags or type a new one"
            />
          </v-col>
          <v-col cols="12">
            <v-text-field
              label="Summary"
              :model-value="draft.summary"
              @update:model-value="patch({ summary: String($event ?? '') })"
            />
          </v-col>
          <v-col cols="12">
            <v-textarea
              auto-grow
              label="Description"
              :model-value="draft.description"
              rows="3"
              @update:model-value="patch({ description: String($event ?? '') })"
            />
          </v-col>
          <v-col cols="12">
            <v-switch
              color="accent"
              hide-details
              inset
              label="Serve this endpoint publicly"
              :model-value="draft.enabled"
              @update:model-value="patch({ enabled: Boolean($event) })"
            />
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card class="workspace-card">
      <v-card-item>
        <v-card-title>Runtime behavior</v-card-title>
        <v-card-subtitle>Set auth, status, errors, latency, and sample seeding.</v-card-subtitle>
      </v-card-item>
      <v-divider />
      <v-card-text>
        <v-row>
          <v-col cols="12" md="4">
            <v-select
              :items="authOptions"
              label="Auth mode"
              :model-value="draft.auth_mode"
              @update:model-value="patch({ auth_mode: String($event ?? 'none') })"
            />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field
              :error-messages="errors.success_status_code"
              label="Success status"
              min="100"
              :model-value="draft.success_status_code"
              type="number"
              @update:model-value="numberPatch('success_status_code', $event)"
            />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field
              :error-messages="errors.error_rate"
              label="Error rate"
              max="1"
              min="0"
              :model-value="draft.error_rate"
              step="0.05"
              type="number"
              @update:model-value="numberPatch('error_rate', $event)"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field
              label="Latency min (ms)"
              min="0"
              :model-value="draft.latency_min_ms"
              type="number"
              @update:model-value="numberPatch('latency_min_ms', $event)"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field
              :error-messages="errors.latency_max_ms"
              label="Latency max (ms)"
              min="0"
              :model-value="draft.latency_max_ms"
              type="number"
              @update:model-value="numberPatch('latency_max_ms', $event)"
            />
          </v-col>
          <v-col cols="12">
            <v-text-field
              label="Seed key"
              :model-value="draft.seed_key"
              placeholder="Leave empty for fresh random data each request"
              @update:model-value="patch({ seed_key: String($event ?? '') })"
            />
            <div class="text-caption text-medium-emphasis">
              Use the same seed to get repeatable generated data.
            </div>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card class="workspace-card">
      <v-card-item>
        <template #prepend>
          <v-avatar color="secondary" variant="tonal">
            <v-icon icon="mdi-shape-plus" />
          </v-avatar>
        </template>

        <v-card-title>Request and response</v-card-title>
        <v-card-subtitle>Review the current request and response shape.</v-card-subtitle>
      </v-card-item>

      <v-divider />

      <v-card-text class="d-flex flex-column ga-4">
        <v-row>
          <v-col cols="12" md="6">
            <v-sheet class="schema-summary-card" rounded="xl">
              <div class="text-overline text-medium-emphasis">Request body</div>
              <div class="text-h6">Current schema</div>
              <div class="text-body-2 text-medium-emphasis">{{ requestSummary }}</div>
            </v-sheet>
            <div v-if="errors.request_schema" class="text-caption text-error mt-2">
              {{ errors.request_schema }}
            </div>
          </v-col>
          <v-col cols="12" md="6">
            <v-sheet class="schema-summary-card" rounded="xl">
              <div class="text-overline text-medium-emphasis">Response body</div>
              <div class="text-h6">Current schema</div>
              <div class="text-body-2 text-medium-emphasis">{{ responseSummary }}</div>
            </v-sheet>
            <div v-if="errors.response_schema" class="text-caption text-error mt-2">
              {{ errors.response_schema }}
            </div>
          </v-col>
        </v-row>

        <v-alert
          v-if="isCreating"
          border="start"
          color="info"
          icon="mdi-arrow-right-thin-circle-outline"
          variant="tonal"
        >
          Save the route before editing its request and response schema.
        </v-alert>

        <div v-else class="d-flex flex-wrap ga-3">
          <v-btn color="secondary" prepend-icon="mdi-shape-outline" variant="tonal" @click="emit('openSchema')">
            Edit schema
          </v-btn>
          <v-btn prepend-icon="mdi-flask-outline" variant="text" @click="emit('preview')">
            Test route
          </v-btn>
        </div>
      </v-card-text>
    </v-card>
  </v-form>
</template>
