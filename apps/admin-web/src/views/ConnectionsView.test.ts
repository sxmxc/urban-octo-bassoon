import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/vue";
import { flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { defineComponent } from "vue";
import ConnectionsView from "./ConnectionsView.vue";
import { createConnection, deleteConnection, listConnections, updateConnection } from "../api/admin";
import { vuetify } from "../plugins/vuetify";
import type { Connection, ConnectionPayload } from "../types/endpoints";

const authStub = vi.hoisted(() => ({
  canWriteRoutes: { value: true },
  logout: vi.fn(),
  mustChangePassword: { value: false },
  session: {
    value: {
      expires_at: "2026-03-20T00:00:00Z",
      token: "session-token",
      user: {
        id: 1,
        username: "ui-feature-agent",
        full_name: "UI Feature Agent",
        email: "ui-feature-agent@example.com",
        avatar_url: null,
        gravatar_url: "https://www.gravatar.com/avatar/ui-feature-agent?d=identicon&s=160",
        is_active: true,
        role: "editor",
        permissions: ["routes.read", "routes.write", "routes.preview"],
        is_superuser: false,
        must_change_password: false,
        last_login_at: null,
        password_changed_at: "2026-03-20T00:00:00Z",
        created_at: "2026-03-20T00:00:00Z",
        updated_at: "2026-03-20T00:00:00Z",
      },
    },
  },
}));

vi.mock("../composables/useAuth", () => ({
  useAuth: () => authStub,
}));

vi.mock("../api/admin", async () => {
  const actual = await vi.importActual<typeof import("../api/admin")>("../api/admin");
  return {
    ...actual,
    createConnection: vi.fn(),
    deleteConnection: vi.fn(),
    listConnections: vi.fn(),
    updateConnection: vi.fn(),
  };
});

const ConnectionManagerCardStub = defineComponent({
  props: {
    canWrite: {
      type: Boolean,
      default: false,
    },
    connections: {
      type: Array as () => Connection[],
      default: () => [],
    },
    isLoading: {
      type: Boolean,
      default: false,
    },
    isSaving: {
      type: Boolean,
      default: false,
    },
  },
  emits: ["create", "delete", "refresh", "update"],
  template: `
    <div data-testid="connection-manager">
      <div data-testid="manager-can-write">{{ canWrite ? "yes" : "no" }}</div>
      <div data-testid="manager-loading">{{ isLoading ? "loading" : "idle" }}</div>
      <div data-testid="manager-saving">{{ isSaving ? "saving" : "idle" }}</div>
      <div data-testid="manager-count">{{ connections.length }}</div>
      <button
        type="button"
        @click="$emit('create', {
          project: 'default',
          environment: 'production',
          name: 'Connector A',
          connector_type: 'http',
          description: null,
          config: { base_url: 'https://api.example.com' },
          is_active: true,
        })"
      >
        Create connector
      </button>
      <button
        type="button"
        @click="$emit('update', 1, {
          project: 'default',
          environment: 'production',
          name: 'Connector A',
          connector_type: 'http',
          description: 'Updated',
          config: { base_url: 'https://api.example.com' },
          is_active: false,
        })"
      >
        Update connector
      </button>
      <button type="button" @click="$emit('delete', 1)">Delete connector</button>
      <button type="button" @click="$emit('refresh')">Refresh connectors</button>
    </div>
  `,
});

function createRouterInstance() {
  const viewStub = { template: "<div />" };
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/login", name: "login", component: viewStub },
      { path: "/connectors", name: "connectors", component: viewStub },
    ],
  });
}

function createStoredConnection(id: number): Connection {
  return {
    id,
    project: "default",
    environment: "production",
    name: `Connector ${id}`,
    connector_type: "http",
    description: null,
    config: { base_url: "https://api.example.com" },
    is_active: true,
    created_at: "2026-03-20T00:00:00Z",
    updated_at: "2026-03-20T00:00:00Z",
  };
}

async function renderView() {
  const router = createRouterInstance();
  await router.push("/connectors");
  await router.isReady();

  return {
    router,
    ...render(ConnectionsView, {
      global: {
        plugins: [vuetify, router],
        stubs: {
          ConnectionManagerCard: ConnectionManagerCardStub,
        },
      },
    }),
  };
}

describe("ConnectionsView", () => {
  beforeEach(() => {
    vi.mocked(createConnection).mockReset();
    vi.mocked(deleteConnection).mockReset();
    vi.mocked(listConnections).mockReset();
    vi.mocked(updateConnection).mockReset();
    authStub.logout.mockReset();
    authStub.canWriteRoutes.value = true;
    authStub.mustChangePassword.value = false;
    vi.mocked(listConnections).mockResolvedValue([createStoredConnection(1)]);
    vi.mocked(createConnection).mockResolvedValue(createStoredConnection(2));
    vi.mocked(deleteConnection).mockResolvedValue(null);
    vi.mocked(updateConnection).mockResolvedValue(
      {
        ...createStoredConnection(1),
        description: "Updated",
        is_active: false,
      },
    );
  });

  afterEach(() => {
    cleanup();
  });

  it("loads connectors and passes them to the shared manager", async () => {
    await renderView();
    await flushPromises();

    expect(vi.mocked(listConnections)).toHaveBeenCalledWith(authStub.session.value);
    expect(screen.getByTestId("manager-count")).toHaveTextContent("1");
    expect(screen.getByText("Connectors")).toBeInTheDocument();
  });

  it("creates a connector from manager events and refreshes the list", async () => {
    const payload: ConnectionPayload = {
      project: "default",
      environment: "production",
      name: "Connector A",
      connector_type: "http",
      description: null,
      config: { base_url: "https://api.example.com" },
      is_active: true,
    };

    await renderView();
    await flushPromises();

    await fireEvent.click(screen.getByRole("button", { name: "Create connector" }));
    await flushPromises();

    expect(vi.mocked(createConnection)).toHaveBeenCalledWith(payload, authStub.session.value);
    expect(vi.mocked(listConnections)).toHaveBeenCalledTimes(2);
    expect(screen.getByText('Saved connector "Connector 2".')).toBeInTheDocument();
  });

  it("updates a connector from manager events and refreshes the list", async () => {
    const payload: ConnectionPayload = {
      project: "default",
      environment: "production",
      name: "Connector A",
      connector_type: "http",
      description: "Updated",
      config: { base_url: "https://api.example.com" },
      is_active: false,
    };

    await renderView();
    await flushPromises();

    await fireEvent.click(screen.getByRole("button", { name: "Update connector" }));
    await flushPromises();

    expect(vi.mocked(updateConnection)).toHaveBeenCalledWith(1, payload, authStub.session.value);
    expect(vi.mocked(listConnections)).toHaveBeenCalledTimes(2);
    expect(screen.getByText('Updated connector "Connector 1".')).toBeInTheDocument();
  });

  it("deletes a connector from manager events and refreshes the list", async () => {
    await renderView();
    await flushPromises();

    await fireEvent.click(screen.getByRole("button", { name: "Delete connector" }));
    await flushPromises();

    expect(vi.mocked(deleteConnection)).toHaveBeenCalledWith(1, authStub.session.value);
    expect(vi.mocked(listConnections)).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Deleted connector.")).toBeInTheDocument();
  });
});
