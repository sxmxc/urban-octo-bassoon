<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useTheme } from "vuetify";
import { ensureAuthBooted, useAuth } from "./composables/useAuth";
import { useStudioTheme } from "./composables/useStudioTheme";
import { getPageTransitionKey } from "./utils/routeTransitions";

const route = useRoute();
const router = useRouter();
const auth = useAuth();
const vuetifyTheme = useTheme();
const studioTheme = useStudioTheme();
const accountMenu = ref(false);

onMounted(async () => {
  vuetifyTheme.change(studioTheme.mode.value);
  await ensureAuthBooted();
});

watch(
  studioTheme.mode,
  (value) => {
    vuetifyTheme.change(value);
  },
  { immediate: true },
);

const pageTransitionKey = computed(() => getPageTransitionKey(route));
const canBrowseRoutes = computed(() => auth.canReadRoutes.value && !auth.mustChangePassword.value);
const canManageConnectors = computed(() => auth.canWriteRoutes.value && !auth.mustChangePassword.value);
const canManageUsers = computed(() => auth.canManageUsers.value && !auth.mustChangePassword.value);
const routesNavActive = computed(() =>
  route.name === "endpoints-browse" ||
  route.name === "endpoints-edit" ||
  route.name === "endpoints-create" ||
  route.name === "schema-editor" ||
  route.name === "endpoint-preview",
);
const connectorsNavActive = computed(() => route.name === "connectors");
const usersNavActive = computed(() => route.name === "users");
const accountAvatarSrc = computed(() => auth.user.value?.avatar_url || auth.user.value?.gravatar_url || "");
const accountDisplayName = computed(() => auth.user.value?.full_name?.trim() || auth.username.value || "Account");
const accountIdentityLine = computed(() => {
  const fullName = auth.user.value?.full_name?.trim();
  const username = auth.username.value;
  const email = auth.user.value?.email;

  if (fullName) {
    if (email && username) {
      return `@${username} · ${email}`;
    }

    return email || (username ? `@${username}` : "");
  }

  return email || "";
});

function toggleTheme(): void {
  studioTheme.toggle();
}

function goToCatalog(): void {
  void router.push({ name: "endpoints-browse" });
}

function goToHome(): void {
  if (canBrowseRoutes.value) {
    goToCatalog();
    return;
  }

  if (auth.isAuthenticated.value) {
    void router.push({ name: "account-profile" });
    return;
  }

  void router.push({ name: "login" });
}

function closeAccountDropdown(): void {
  accountMenu.value = false;
}

function goToProfile(): void {
  closeAccountDropdown();
  void router.push({ name: "account-profile" });
}

function goToUsers(): void {
  void router.push({ name: "users" });
}

function goToConnectors(): void {
  void router.push({ name: "connectors" });
}

async function signOut(): Promise<void> {
  closeAccountDropdown();
  await auth.logout("You signed out.");
  void router.push({ name: "login" });
}
</script>

<template>
  <v-app class="studio-app">
    <v-app-bar class="studio-topbar" flat height="76">
      <v-container class="studio-topbar-inner fill-height px-3 px-sm-5" fluid>
        <v-btn class="studio-brand-button px-0" variant="text" @click="goToHome">
          <span class="brand-mark">
            <img alt="Artificer icon" class="brand-mark-image" src="/icon.svg">
          </span>
          <span class="studio-brand-copy">
            <span class="studio-brand-name">Artificer</span>
            <span class="studio-brand-kicker">Studio</span>
          </span>
        </v-btn>

        <div class="studio-topbar-center">
          <div
            v-if="auth.isAuthenticated.value && (canBrowseRoutes || canManageConnectors || canManageUsers)"
            class="studio-primary-nav"
          >
            <v-btn
              v-if="canBrowseRoutes"
              :aria-current="routesNavActive ? 'page' : undefined"
              :class="{ 'studio-primary-nav__button--active': routesNavActive }"
              class="studio-primary-nav__button"
              prepend-icon="mdi-view-dashboard-outline"
              rounded="xl"
              variant="text"
              @click="goToCatalog"
            >
              Routes
            </v-btn>
            <v-btn
              v-if="canManageConnectors"
              :aria-current="connectorsNavActive ? 'page' : undefined"
              :class="{ 'studio-primary-nav__button--active': connectorsNavActive }"
              class="studio-primary-nav__button"
              prepend-icon="mdi-connection"
              rounded="xl"
              variant="text"
              @click="goToConnectors"
            >
              Connectors
            </v-btn>
            <v-btn
              v-if="canManageUsers"
              :aria-current="usersNavActive ? 'page' : undefined"
              :class="{ 'studio-primary-nav__button--active': usersNavActive }"
              class="studio-primary-nav__button"
              prepend-icon="mdi-account-group-outline"
              rounded="xl"
              variant="text"
              @click="goToUsers"
            >
              Users
            </v-btn>
          </div>
        </div>

        <div class="studio-topbar-actions">
          <v-chip
            v-if="auth.status.value === 'restoring'"
            color="info"
            label
            prepend-icon="mdi-cloud-sync-outline"
            variant="tonal"
          >
            Reconnecting
          </v-chip>

          <template v-else-if="auth.isAuthenticated.value">
            <v-chip
              v-if="auth.mustChangePassword.value"
              color="warning"
              label
              prepend-icon="mdi-lock-reset"
              variant="tonal"
            >
              Password reset required
            </v-chip>

            <v-menu v-model="accountMenu" location="bottom end">
              <template #activator="{ props: menuProps }">
                <v-btn
                  append-icon="mdi-chevron-down"
                  color="secondary"
                  rounded="xl"
                  variant="text"
                  v-bind="menuProps"
                >
                  <template #prepend>
                    <v-avatar size="30">
                      <v-img v-if="accountAvatarSrc" :src="accountAvatarSrc" cover />
                      <v-icon v-else icon="mdi-account-circle-outline" />
                    </v-avatar>
                  </template>
                  <span class="studio-account-label">{{ auth.username.value }}</span>
                </v-btn>
              </template>

              <v-card class="studio-account-menu" min-width="296">
                <v-card-text class="d-flex flex-column ga-3">
                  <div class="d-flex align-center ga-3">
                    <v-avatar size="44">
                      <v-img v-if="accountAvatarSrc" :src="accountAvatarSrc" cover />
                      <v-icon v-else icon="mdi-account-circle-outline" />
                    </v-avatar>
                    <div>
                      <div class="text-overline text-medium-emphasis">Account</div>
                      <div class="text-subtitle-1 font-weight-bold">{{ accountDisplayName }}</div>
                      <div v-if="accountIdentityLine" class="text-body-2 text-medium-emphasis mt-1">
                        {{ accountIdentityLine }}
                      </div>
                      <div class="text-body-2 text-medium-emphasis mt-1">{{ auth.roleLabel.value }}</div>
                    </div>
                  </div>

                  <v-divider />

                  <v-list class="pa-0" density="comfortable" nav>
                    <v-list-item
                      prepend-icon="mdi-account-cog-outline"
                      rounded="lg"
                      title="Profile"
                      @click="goToProfile"
                    />
                    <v-list-item prepend-icon="mdi-logout" rounded="lg" title="Sign out" @click="void signOut()" />
                  </v-list>
                </v-card-text>
              </v-card>
            </v-menu>
          </template>

          <v-btn
            :icon="studioTheme.isDark.value ? 'mdi-weather-sunny' : 'mdi-weather-night'"
            class="studio-theme-toggle"
            variant="text"
            @click="toggleTheme"
          />
        </div>
      </v-container>
    </v-app-bar>

    <v-main class="studio-main">
      <v-container class="studio-shell fill-height px-3 px-sm-6 py-6" fluid>
        <router-view v-slot="{ Component }">
          <v-fade-transition mode="out-in">
            <component :is="Component" :key="pageTransitionKey" />
          </v-fade-transition>
        </router-view>
      </v-container>
    </v-main>
  </v-app>
</template>
