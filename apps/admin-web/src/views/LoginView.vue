<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuth } from "../composables/useAuth";

const auth = useAuth();
const route = useRoute();
const router = useRouter();

const credentials = reactive({
  password: "",
  username: "",
});
const rememberMe = ref(false);
const formError = ref<string | null>(null);

const redirectTarget = computed(() => {
  const rawRedirect = route.query.redirect;
  return typeof rawRedirect === "string" && rawRedirect.startsWith("/") ? rawRedirect : "/endpoints";
});

async function handleSubmit(): Promise<void> {
  formError.value = null;

  if (!credentials.username.trim() || !credentials.password) {
    formError.value = "Enter both username and password.";
    return;
  }

  const result = await auth.login(credentials.username, credentials.password, { rememberMe: rememberMe.value });

  if (!result.ok) {
    formError.value = result.error ?? "We could not sign you in.";
    return;
  }

  void router.replace(redirectTarget.value);
}
</script>

<template>
  <v-row class="fill-height align-center" justify="center">
    <v-col cols="12" md="9" lg="7" xl="6">
      <div class="d-flex flex-column ga-5">
        <v-card class="workspace-card auth-intro-card">
          <v-card-text class="pa-8 pa-sm-9">
            <div class="text-overline text-secondary">Admin access</div>
            <div class="text-h3 font-weight-bold mt-2">Sign in to Artificer Studio</div>
            <div class="text-body-1 text-medium-emphasis mt-4 auth-support-copy">
              Manage routes, edit request and response schemas, and check the live output before you hand the route to someone else.
            </div>
          </v-card-text>
        </v-card>

        <v-card class="workspace-card">
          <v-card-item>
            <template #prepend>
              <v-avatar color="primary" variant="tonal">
                <v-icon icon="mdi-lock-outline" />
              </v-avatar>
            </template>

            <v-card-title>Sign in</v-card-title>
            <v-card-subtitle>Use your admin account. New installs may show a temporary bootstrap password in the API logs.</v-card-subtitle>
          </v-card-item>

          <v-divider />

          <v-card-text class="d-flex flex-column ga-4">
            <v-alert
              v-if="auth.sessionMessage.value"
              border="start"
              color="info"
              variant="tonal"
              @click:close="auth.clearSessionMessage()"
            >
              {{ auth.sessionMessage.value }}
            </v-alert>

            <v-alert v-if="formError" border="start" color="error" variant="tonal">
              {{ formError }}
            </v-alert>

            <v-skeleton-loader
              v-if="auth.status.value === 'restoring'"
              type="article, text, text, button"
            />

            <v-form v-else class="d-flex flex-column ga-4" @submit.prevent="handleSubmit">
              <v-text-field
                v-model="credentials.username"
                autocomplete="username"
                label="Username"
                prepend-inner-icon="mdi-account-outline"
              />

              <v-text-field
                v-model="credentials.password"
                autocomplete="current-password"
                label="Password"
                prepend-inner-icon="mdi-form-textbox-password"
                type="password"
              />

              <v-switch
                v-model="rememberMe"
                color="secondary"
                inset
                label="Remember this browser"
              />

              <div class="text-caption text-medium-emphasis">
                Leave this off on a shared device.
              </div>

              <v-btn
                block
                color="primary"
                :loading="auth.status.value === 'authenticating'"
                prepend-icon="mdi-arrow-right-circle-outline"
                size="large"
                type="submit"
              >
                Sign in
              </v-btn>
            </v-form>
          </v-card-text>
        </v-card>
      </div>
    </v-col>
  </v-row>
</template>
