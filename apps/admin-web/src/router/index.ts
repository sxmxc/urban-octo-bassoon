import { createRouter, createWebHistory, type RouteLocationGeneric } from "vue-router";
import EndpointsView from "../views/EndpointsView.vue";
import EndpointPreviewView from "../views/EndpointPreviewView.vue";
import ConnectionsView from "../views/ConnectionsView.vue";
import LoginView from "../views/LoginView.vue";
import ProfileView from "../views/ProfileView.vue";
import UsersView from "../views/UsersView.vue";
import { ensureAuthBooted, hasPermissionValue, isAuthenticated, mustChangePassword } from "../composables/useAuth";
import type { AdminPermission } from "../types/endpoints";

export function mapLegacySchemaEditorRedirect(to: RouteLocationGeneric) {
  const legacyTab = Array.isArray(to.query.tab) ? to.query.tab[0] : to.query.tab;
  const contractTab = legacyTab === "request" || legacyTab === "response" ? legacyTab : undefined;
  const nextQuery = {
    ...to.query,
    tab: "contract",
    ...(contractTab ? { contractTab } : {}),
  };

  return {
    name: "endpoints-edit",
    params: {
      endpointId: to.params.endpointId,
    },
    query: nextQuery,
  };
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: "/endpoints",
    },
    {
      path: "/login",
      name: "login",
      component: LoginView,
      meta: {
        title: "Sign in",
      },
    },
    {
      path: "/account",
      redirect: {
        name: "account-profile",
      },
    },
    {
      path: "/account/profile",
      name: "account-profile",
      component: ProfileView,
      meta: {
        requiresAuth: true,
        title: "Profile",
      },
    },
    {
      path: "/security",
      name: "security",
      redirect: {
        name: "account-profile",
      },
      meta: {
        requiresAuth: true,
      },
    },
    {
      path: "/connectors",
      name: "connectors",
      component: ConnectionsView,
      meta: {
        requiresAuth: true,
        permission: "routes.write",
        title: "Connectors",
      },
    },
    {
      path: "/users",
      name: "users",
      component: UsersView,
      meta: {
        requiresAuth: true,
        permission: "users.manage",
        title: "Users",
      },
    },
    {
      path: "/endpoints",
      name: "endpoints-browse",
      component: EndpointsView,
      props: {
        mode: "browse",
      },
      meta: {
        requiresAuth: true,
        permission: "routes.read",
        title: "Routes",
        transitionShell: "endpoint-workspace",
      },
    },
    {
      path: "/endpoints/new",
      name: "endpoints-create",
      component: EndpointsView,
      props: {
        mode: "create",
      },
      meta: {
        requiresAuth: true,
        permission: "routes.write",
        title: "Create route",
        transitionShell: "endpoint-workspace",
      },
    },
    {
      path: "/endpoints/:endpointId",
      name: "endpoints-edit",
      component: EndpointsView,
      props: {
        mode: "edit",
      },
      meta: {
        requiresAuth: true,
        permission: "routes.write",
        title: "Route",
        transitionShell: "endpoint-workspace",
      },
    },
    {
      path: "/endpoints/:endpointId/schema",
      name: "schema-editor",
      redirect: mapLegacySchemaEditorRedirect,
      meta: {
        requiresAuth: true,
        permission: "routes.write",
        title: "Schema",
      },
    },
    {
      path: "/endpoints/:endpointId/preview",
      name: "endpoint-preview",
      component: EndpointPreviewView,
      meta: {
        requiresAuth: true,
        permission: "routes.preview",
        title: "Test route",
      },
    },
  ],
});

router.beforeEach(async (to) => {
  await ensureAuthBooted();

  if (to.meta.requiresAuth && !isAuthenticated.value) {
    return {
      name: "login",
      query: {
        redirect: to.fullPath,
      },
    };
  }

  if (isAuthenticated.value && mustChangePassword.value && to.name !== "account-profile" && to.name !== "security") {
    return {
      name: "account-profile",
    };
  }

  if (typeof to.meta.permission === "string" && !hasPermissionValue(to.meta.permission as AdminPermission)) {
    return {
      name: "endpoints-browse",
    };
  }

  if (to.name === "login" && isAuthenticated.value) {
    return {
      name: mustChangePassword.value ? "account-profile" : "endpoints-browse",
    };
  }

  return true;
});

router.afterEach((to, from) => {
  if (typeof document !== "undefined") {
    const pageTitle = typeof to.meta.title === "string" ? to.meta.title : "Artificer Studio";
    document.title = `Artificer Studio | ${pageTitle}`;

    const nextShell = typeof to.meta.transitionShell === "string" ? to.meta.transitionShell : "";
    const previousShell = typeof from.meta.transitionShell === "string" ? from.meta.transitionShell : "";
    const shouldResetShellScroll = to.name !== from.name || nextShell !== previousShell;

    if (shouldResetShellScroll) {
      requestAnimationFrame(() => {
        document.querySelector<HTMLElement>(".studio-shell")?.scrollTo({ top: 0, left: 0 });
      });
    }
  }
});
