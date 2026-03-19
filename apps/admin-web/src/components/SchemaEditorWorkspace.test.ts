import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/vue";
import { flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import SchemaEditorWorkspace from "./SchemaEditorWorkspace.vue";
import { AdminApiError, previewResponse } from "../api/admin";
import { vuetify } from "../plugins/vuetify";
import { createRequestParameterDefinition } from "../utils/requestSchema";
import type { BuilderScope } from "../schemaBuilder";
import type { JsonObject } from "../types/endpoints";

type StubInput = {
  altKey: boolean;
  button: number;
  buttons: number;
  clientX: number;
  clientY: number;
  ctrlKey: boolean;
  metaKey: boolean;
  pageX: number;
  pageY: number;
  shiftKey: boolean;
};

type StubSource = {
  data: Record<string, unknown>;
  dragHandle: Element;
  element: Element;
};

type StubLocation = {
  current: {
    dropTargets: never[];
    input: StubInput;
  };
  initial: {
    dropTargets: never[];
    input: StubInput;
  };
  previous: {
    dropTargets: never[];
  };
};

type RegisteredDraggable = {
  element: Element;
  getInitialData?: (args: { dragHandle: Element; element: Element; input: StubInput }) => Record<string, unknown>;
  onGenerateDragPreview?: (args: { location: StubLocation; nativeSetDragImage: ReturnType<typeof vi.fn>; source: StubSource }) => void;
  onDragStart?: (args: { location: StubLocation; source: StubSource }) => void;
  onDrop?: (args: { location: StubLocation; source: StubSource }) => void;
};

type DropTargetSelf = {
  data: Record<string, unknown>;
  dropEffect: string;
  element: Element;
  isActiveDueToStickiness: boolean;
};

type RegisteredDropTarget = {
  element: Element;
  canDrop?: (args: { element: Element; input: StubInput; source: StubSource }) => boolean;
  onDragEnter?: (args: { location: StubLocation; self: DropTargetSelf; source: StubSource }) => void;
  onDrop?: (args: { location: StubLocation; self: DropTargetSelf; source: StubSource }) => void;
};

const dndStub = vi.hoisted(() => {
  const draggables = new Map<Element, RegisteredDraggable>();
  const dropTargets = new Map<Element, RegisteredDropTarget>();

  function reset() {
    draggables.clear();
    dropTargets.clear();
  }

  function simulateDrop(sourceElement: Element, targetElement: Element) {
    const draggableArgs = draggables.get(sourceElement);
    const dropTargetArgs = dropTargets.get(targetElement);

    if (!draggableArgs) {
      throw new Error("Missing draggable registration for source element.");
    }

    if (!dropTargetArgs) {
      throw new Error("Missing drop target registration for target element.");
    }

    const input = {
      altKey: false,
      button: 0,
      buttons: 1,
      clientX: 320,
      clientY: 180,
      ctrlKey: false,
      metaKey: false,
      pageX: 320,
      pageY: 180,
      shiftKey: false,
    };
    const location = {
      current: {
        dropTargets: [],
        input,
      },
      initial: {
        dropTargets: [],
        input,
      },
      previous: {
        dropTargets: [],
      },
    };
    const source = {
      data: draggableArgs.getInitialData?.({
        dragHandle: sourceElement,
        element: sourceElement,
        input,
      }) ?? {},
      dragHandle: sourceElement,
      element: sourceElement,
    };

    draggableArgs.onGenerateDragPreview?.({
      location,
      nativeSetDragImage: vi.fn(),
      source,
    });
    draggableArgs.onDragStart?.({
      location,
      source,
    });

    const canDrop = dropTargetArgs.canDrop?.({
      element: targetElement,
      input,
      source,
    }) ?? true;

    if (canDrop) {
      const self = {
        data: {},
        dropEffect: "move",
        element: targetElement,
        isActiveDueToStickiness: false,
      };

      dropTargetArgs.onDragEnter?.({
        location,
        self,
        source,
      });
      dropTargetArgs.onDrop?.({
        location,
        self,
        source,
      });
    }

    draggableArgs.onDrop?.({
      location,
      source,
    });
  }

  return {
    draggables,
    dropTargets,
    reset,
    simulateDrop,
  };
});

const authStub = vi.hoisted(() => ({
  logout: vi.fn(),
  session: {
    value: {
      expires_at: "2026-03-15T00:00:00Z",
      token: "session-token",
      user: {
        id: 1,
        username: "admin",
        full_name: "Admin User",
        email: "admin@example.com",
        avatar_url: null,
        gravatar_url: "https://www.gravatar.com/avatar/admin?d=identicon&s=160",
        is_active: true,
        role: "superuser",
        permissions: ["routes.read", "routes.write", "routes.preview", "users.manage"],
        is_superuser: true,
        must_change_password: false,
        last_login_at: null,
        password_changed_at: "2026-03-15T00:00:00Z",
        created_at: "2026-03-15T00:00:00Z",
        updated_at: "2026-03-15T00:00:00Z",
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
    previewResponse: vi.fn(),
  };
});

vi.mock("@atlaskit/pragmatic-drag-and-drop/element/adapter", () => ({
  draggable: vi.fn((args: RegisteredDraggable) => {
    dndStub.draggables.set(args.element, args);
    return () => {
      dndStub.draggables.delete(args.element);
    };
  }),
  dropTargetForElements: vi.fn((args: RegisteredDropTarget) => {
    dndStub.dropTargets.set(args.element, args);
    return () => {
      dndStub.dropTargets.delete(args.element);
    };
  }),
}));

vi.mock("@atlaskit/pragmatic-drag-and-drop/element/set-custom-native-drag-preview", () => ({
  setCustomNativeDragPreview: vi.fn(({ render }: { render: ({ container }: { container: HTMLElement }) => (() => void) | void }) => {
    const container = document.createElement("div");
    const cleanup = render({ container });
    cleanup?.();
  }),
}));

function createRouterInstance() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "editor", component: { template: "<div>editor</div>" } },
      { path: "/login", name: "login", component: { template: "<div>login</div>" } },
    ],
  });
}

async function renderWorkspace(
  props: {
    pathParameters?: Array<ReturnType<typeof createRequestParameterDefinition> | string>;
    queryParameters?: Array<ReturnType<typeof createRequestParameterDefinition>>;
    requestBodySchema?: JsonObject;
    schema: JsonObject;
    scope: BuilderScope;
    seedKey?: string;
  },
): Promise<ReturnType<typeof render> & { router: ReturnType<typeof createRouterInstance> }> {
  const router = createRouterInstance();
  await router.push("/");
  await router.isReady();

  return {
    router,
    ...render(SchemaEditorWorkspace, {
      props,
      global: {
        plugins: [vuetify, router],
      },
    }),
  };
}

function createObjectSchema(propertyName = "quote") {
  return {
    type: "object",
    properties: {
      [propertyName]: {
        type: "string",
      },
    },
    required: [],
    "x-builder": {
      order: [propertyName],
    },
  };
}

function findSchemaNodeByLabel(label: string): HTMLElement | null {
  return Array.from(document.querySelectorAll<HTMLElement>("[data-node-id]")).find(
    (element) => element.querySelector(".schema-node-pill-label")?.textContent?.trim() === label,
  ) ?? null;
}

function findNodeDragHandleByLabel(label: string): HTMLElement | null {
  const node = findSchemaNodeByLabel(label);
  const nodeId = node?.getAttribute("data-node-id");
  if (!nodeId) {
    return null;
  }

  return document.querySelector<HTMLElement>(`[data-node-drag-handle="${nodeId}"]`);
}

function findNodeCollapseToggleByLabel(label: string): HTMLElement | null {
  const node = findSchemaNodeByLabel(label);
  const nodeId = node?.getAttribute("data-node-id");
  if (!nodeId) {
    return null;
  }

  return document.querySelector<HTMLElement>(`[data-collapse-toggle="${nodeId}"]`);
}

describe("SchemaEditorWorkspace", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(previewResponse).mockReset();
    authStub.logout.mockReset();
    dndStub.reset();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("adds a request field through palette drag and drop", async () => {
    const { emitted } = await renderWorkspace({
      schema: {
        type: "object",
        properties: {},
        required: [],
        "x-builder": {
          order: [],
        },
      },
      scope: "request",
    });

    const paletteChip = document.querySelector('[data-palette-type="string"]');
    const rootDropZone = document.querySelector('[data-drop-zone="container"][data-drop-target="builder-root"]');

    expect(paletteChip).not.toBeNull();
    expect(rootDropZone).not.toBeNull();

    dndStub.simulateDrop(paletteChip as Element, rootDropZone as Element);

    const schemaUpdates = emitted()["update:schema"] as Array<[JsonObject]> | undefined;

    expect(schemaUpdates?.at(-1)?.[0]).toMatchObject({
      type: "object",
      properties: {
        field: {
          type: "string",
        },
      },
      required: [],
    });
  }, 30_000);

  it("adds a request field through the plus-button insert menu", async () => {
    const { emitted } = await renderWorkspace({
      schema: {
        type: "object",
        properties: {},
        required: [],
        "x-builder": {
          order: [],
        },
      },
      scope: "request",
    });

    const rootInsertButton = document.querySelector('[data-insert-menu="container"][data-insert-target="builder-root"]');
    expect(rootInsertButton).not.toBeNull();

    await fireEvent.click(rootInsertButton as Element);
    await flushPromises();

    const insertStringOption = document.querySelector('[data-insert-placement="container"][data-insert-type="string"]');
    expect(insertStringOption).not.toBeNull();
    await fireEvent.click(insertStringOption as Element);

    const schemaUpdates = emitted()["update:schema"] as Array<[JsonObject]> | undefined;
    expect(schemaUpdates?.at(-1)?.[0]).toMatchObject({
      type: "object",
      properties: {
        field: {
          type: "string",
        },
      },
      required: [],
    });
  }, 30_000);

  it("reorders object siblings through the row insertion anchor", async () => {
    const { emitted } = await renderWorkspace({
      schema: {
        type: "object",
        properties: {
          id: {
            type: "string",
          },
          value: {
            type: "string",
          },
        },
        required: [],
        "x-builder": {
          order: ["id", "value"],
        },
      },
      scope: "request",
    });

    const idNode = findSchemaNodeByLabel("id");
    const valueNode = findNodeDragHandleByLabel("value");

    expect(idNode).not.toBeNull();
    expect(valueNode).not.toBeNull();

    const idAnchor = document.querySelector(
      `[data-drop-zone="row"][data-drop-target="${idNode?.getAttribute("data-node-id")}"]`,
    );
    expect(idAnchor).not.toBeNull();

    dndStub.simulateDrop(valueNode as Element, idAnchor as Element);

    const schemaUpdates = emitted()["update:schema"] as Array<[JsonObject]> | undefined;
    expect(schemaUpdates?.at(-1)?.[0]).toMatchObject({
      "x-builder": {
        order: ["value", "id"],
      },
    });
  }, 30_000);

  it("adds a request field at the end of the current object level", async () => {
    const { emitted } = await renderWorkspace({
      schema: {
        type: "object",
        properties: {
          id: {
            type: "string",
          },
          value: {
            type: "string",
          },
        },
        required: [],
        "x-builder": {
          order: ["id", "value"],
        },
      },
      scope: "request",
    });

    const paletteChip = document.querySelector('[data-palette-type="string"]');
    const endAnchor = document.querySelector('[data-drop-zone="container"][data-drop-target="builder-root"]');
    expect(paletteChip).not.toBeNull();
    expect(endAnchor).not.toBeNull();

    dndStub.simulateDrop(paletteChip as Element, endAnchor as Element);

    const schemaUpdates = emitted()["update:schema"] as Array<[JsonObject]> | undefined;
    expect(schemaUpdates?.at(-1)?.[0]).toMatchObject({
      properties: {
        field: {
          type: "string",
        },
      },
      "x-builder": {
        order: ["id", "value", "field"],
      },
    });
  }, 15_000);

  it("links a response field to a route parameter through the value lane", async () => {
    const { emitted } = await renderWorkspace({
      pathParameters: ["userId", "deviceId"],
      schema: {
        type: "object",
        properties: {
          id: {
            type: "string",
          },
        },
        required: [],
        "x-builder": {
          order: ["id"],
        },
      },
      scope: "response",
    });

    const idNode = findSchemaNodeByLabel("id");
    expect(idNode).not.toBeNull();

    const valueSlot = document.querySelector(
      `[data-drop-zone="value"][data-drop-target="${idNode?.getAttribute("data-node-id")}"]`,
    );
    const parameterPill = document.querySelector('[data-path-parameter="userId"]');

    expect(valueSlot).not.toBeNull();
    expect(parameterPill).not.toBeNull();

    dndStub.simulateDrop(parameterPill as Element, valueSlot as Element);

    const schemaUpdates = emitted()["update:schema"] as Array<[JsonObject]> | undefined;
    expect(schemaUpdates?.at(-1)?.[0]).toMatchObject({
      properties: {
        id: {
          type: "string",
          "x-mock": {
            mode: "generate",
            type: "path_parameter",
            generator: "path_parameter",
            parameter: "userId",
            options: {
              parameter: "userId",
            },
          },
        },
      },
    });
  });

  it("preserves numeric field constraints when linking a route parameter through the value lane", async () => {
    const { emitted } = await renderWorkspace({
      pathParameters: ["deviceId"],
      schema: {
        type: "object",
        properties: {
          deviceId: {
            type: "integer",
            minimum: 10,
            maximum: 99,
          },
        },
        required: [],
        "x-builder": {
          order: ["deviceId"],
        },
      },
      scope: "response",
    });

    const deviceIdNode = findSchemaNodeByLabel("deviceId");
    expect(deviceIdNode).not.toBeNull();

    const valueSlot = document.querySelector(
      `[data-drop-zone="value"][data-drop-target="${deviceIdNode?.getAttribute("data-node-id")}"]`,
    );
    const parameterPill = document.querySelector('[data-path-parameter="deviceId"]');

    expect(valueSlot).not.toBeNull();
    expect(parameterPill).not.toBeNull();

    dndStub.simulateDrop(parameterPill as Element, valueSlot as Element);

    const schemaUpdates = emitted()["update:schema"] as Array<[JsonObject]> | undefined;
    expect(schemaUpdates?.at(-1)?.[0]).toMatchObject({
      properties: {
        deviceId: {
          type: "integer",
          minimum: 10,
          maximum: 99,
          "x-mock": {
            mode: "generate",
            type: "path_parameter",
            generator: "path_parameter",
            parameter: "deviceId",
            options: {
              parameter: "deviceId",
            },
          },
        },
      },
    });
  });

  it("adopts the request path parameter type and format when linking a generic response field", async () => {
    const { emitted } = await renderWorkspace({
      pathParameters: [
        createRequestParameterDefinition("path", {
          name: "deviceId",
          type: "string",
          format: "uuid",
        }),
      ],
      schema: {
        type: "object",
        properties: {
          linkedValue: {
            type: "string",
          },
        },
        required: [],
        "x-builder": {
          order: ["linkedValue"],
        },
      },
      scope: "response",
    });

    const linkedValueNode = findSchemaNodeByLabel("linkedValue");
    expect(linkedValueNode).not.toBeNull();

    const valueSlot = document.querySelector(
      `[data-drop-zone="value"][data-drop-target="${linkedValueNode?.getAttribute("data-node-id")}"]`,
    );
    const parameterPill = document.querySelector('[data-path-parameter="deviceId"]');

    expect(valueSlot).not.toBeNull();
    expect(parameterPill).not.toBeNull();

    dndStub.simulateDrop(parameterPill as Element, valueSlot as Element);

    const schemaUpdates = emitted()["update:schema"] as Array<[JsonObject]> | undefined;
    expect(schemaUpdates?.at(-1)?.[0]).toMatchObject({
      properties: {
        linkedValue: {
          type: "string",
          format: "uuid",
          "x-mock": {
            mode: "generate",
            type: "path_parameter",
            generator: "path_parameter",
            parameter: "deviceId",
            options: {
              parameter: "deviceId",
            },
          },
        },
      },
    });

    expect(screen.queryByLabelText("Min length")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Max length")).not.toBeInTheDocument();
  });

  it("assigns value types and behaviors through the scalar value lane", async () => {
    const { emitted } = await renderWorkspace({
      schema: {
        type: "object",
        properties: {
          quote: {
            type: "string",
          },
        },
        required: [],
        "x-builder": {
          order: ["quote"],
        },
      },
      scope: "response",
    });

    const quoteNode = findSchemaNodeByLabel("quote");
    expect(quoteNode).not.toBeNull();

    const valueSlot = document.querySelector(
      `[data-drop-zone="value"][data-drop-target="${quoteNode?.getAttribute("data-node-id")}"]`,
    );
    const keyboardKeyPill = document.querySelector('[data-value-type="keyboard_key"]');
    const verbPill = document.querySelector('[data-value-type="verb"]');
    const pricePill = document.querySelector('[data-value-type="price"]');
    const mockingPill = document.querySelector('[data-value-mode="mocking"]');

    expect(valueSlot).not.toBeNull();
    expect(keyboardKeyPill).not.toBeNull();
    expect(verbPill).not.toBeNull();
    expect(pricePill).not.toBeNull();
    expect(mockingPill).not.toBeNull();

    dndStub.simulateDrop(pricePill as Element, valueSlot as Element);

    dndStub.simulateDrop(mockingPill as Element, valueSlot as Element);

    const schemaUpdates = emitted()["update:schema"] as Array<[JsonObject]> | undefined;
    expect(schemaUpdates?.at(-1)?.[0]).toMatchObject({
      properties: {
        quote: {
          type: "number",
          "x-mock": {
            mode: "mocking",
            type: "price",
            generator: "price",
          },
        },
      },
    });
  }, 15_000);

  it("marks the selected canvas row with a dedicated selected indicator", async () => {
    await renderWorkspace({
      schema: createObjectSchema(),
      scope: "response",
    });

    const quoteNode = findSchemaNodeByLabel("quote");
    expect(quoteNode).not.toBeNull();

    await fireEvent.click(quoteNode as Element);

    const selectedRow = (quoteNode as HTMLElement).closest(".schema-tree-row");
    expect(selectedRow).not.toBeNull();
    expect(selectedRow).toHaveClass("schema-tree-row-selected");
    expect(selectedRow?.querySelector(".schema-node-selected-pill")?.textContent).toContain("selected");
  });

  it("collapses and expands object branches from the canvas", async () => {
    await renderWorkspace({
      schema: {
        type: "object",
        properties: {
          meta: {
            type: "object",
            properties: {
              count: {
                type: "integer",
              },
            },
            required: [],
            "x-builder": {
              order: ["count"],
            },
          },
        },
        required: [],
        "x-builder": {
          order: ["meta"],
        },
      },
      scope: "request",
    });

    expect(findSchemaNodeByLabel("count")).not.toBeNull();

    const collapseToggle = findNodeCollapseToggleByLabel("meta");
    expect(collapseToggle).not.toBeNull();

    await fireEvent.click(collapseToggle as Element);
    expect(findSchemaNodeByLabel("count")).toBeNull();
    expect(screen.getByText("1 field hidden")).toBeInTheDocument();

    await fireEvent.click(collapseToggle as Element);
    expect(findSchemaNodeByLabel("count")).not.toBeNull();
  });

  it("adds response templates through helper chips and persists them in x-mock metadata", async () => {
    vi.mocked(previewResponse).mockResolvedValue({
      preview: {
        quote: "templated preview",
      },
    });

    const { emitted } = await renderWorkspace({
      pathParameters: ["orderId"],
      queryParameters: [
        createRequestParameterDefinition("query", {
          name: "status",
        }),
      ],
      requestBodySchema: {
        type: "object",
        properties: {
          customer: {
            type: "object",
            properties: {
              email: {
                type: "string",
                format: "email",
              },
            },
            required: ["email"],
            "x-builder": {
              order: ["email"],
            },
          },
        },
        required: ["customer"],
        "x-builder": {
          order: ["customer"],
        },
      },
      schema: createObjectSchema(),
      scope: "response",
    });

    const quoteNode = findSchemaNodeByLabel("quote");
    expect(quoteNode).not.toBeNull();
    await fireEvent.click(quoteNode as Element);

    expect(document.querySelector('[data-path-parameter="orderId"]')).not.toBeNull();
    expect(document.querySelector('[data-query-parameter="status"]')).not.toBeNull();
    expect(document.querySelector('[data-query-parameter="status"]')?.getAttribute("draggable")).toBe("false");

    await fireEvent.click(screen.getByLabelText("Use template"));
    await fireEvent.click(document.querySelector('[data-template-token="{{request.path.orderId}}"]') as Element);
    await fireEvent.click(document.querySelector('[data-query-parameter="status"]') as Element);
    await fireEvent.click(document.querySelector('[data-template-token="{{request.body.customer.email}}"]') as Element);

    const schemaUpdates = emitted()["update:schema"] as Array<[JsonObject]> | undefined;
    expect(schemaUpdates?.at(-1)?.[0]).toMatchObject({
      properties: {
        quote: {
          type: "string",
          "x-mock": {
            template: "{{value}}{{request.path.orderId}}{{request.query.status}}{{request.body.customer.email}}",
          },
        },
      },
    });

    expect(document.querySelector('[data-query-parameter="status"]')).toHaveClass("schema-value-pill-active");
  });

  it("renders generated response previews and emits seed updates from the preview rail", async () => {
    vi.mocked(previewResponse).mockResolvedValue({
      preview: {
        quote: "hello from preview",
      },
    });

    const { emitted } = await renderWorkspace({
      schema: createObjectSchema(),
      scope: "response",
      seedKey: "seed-123",
    });

    await vi.advanceTimersByTimeAsync(400);
    await flushPromises();

    expect(previewResponse).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "object",
      }),
      "seed-123",
      {},
      expect.objectContaining({
        token: "session-token",
      }),
      {
        queryParameters: {},
        requestBody: null,
      },
    );

    expect(await screen.findByText(/hello from preview/)).toBeInTheDocument();
    expect(document.querySelector(".code-block--json-editor .json-token--key")).not.toBeNull();
    expect(document.querySelector(".code-block--json-editor .json-token--string")).not.toBeNull();

    await fireEvent.update(screen.getByLabelText("Seed key"), "seed-456");

    expect(emitted()["update:seedKey"]?.at(-1)).toEqual(["seed-456"]);
  });

  it("uses typed request path parameter defaults when seeding response previews", async () => {
    vi.mocked(previewResponse).mockResolvedValue({
      preview: {
        id: "11111111-1111-4111-8111-111111111111",
      },
    });

    await renderWorkspace({
      pathParameters: [
        createRequestParameterDefinition("path", {
          name: "deviceId",
          type: "string",
          format: "uuid",
        }),
      ],
      schema: createObjectSchema("id"),
      scope: "response",
    });

    await vi.advanceTimersByTimeAsync(400);
    await flushPromises();

    expect(previewResponse).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "object",
      }),
      null,
      {
        deviceId: "11111111-1111-4111-8111-111111111111",
      },
      expect.objectContaining({
        token: "session-token",
      }),
      {
        queryParameters: {},
        requestBody: null,
      },
    );
  });

  it("clips generated path-parameter preview samples to the configured max length", async () => {
    vi.mocked(previewResponse).mockResolvedValue({
      preview: {
        slug: "sample",
      },
    });

    await renderWorkspace({
      pathParameters: [
        createRequestParameterDefinition("path", {
          name: "slug",
          type: "string",
          maxLength: 6,
        }),
      ],
      schema: createObjectSchema("slug"),
      scope: "response",
    });

    await vi.advanceTimersByTimeAsync(400);
    await flushPromises();

    expect(previewResponse).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "object",
      }),
      null,
      {
        slug: "sample",
      },
      expect.objectContaining({
        token: "session-token",
      }),
      {
        queryParameters: {},
        requestBody: null,
      },
    );
  });

  it("passes preview query parameters and request body context to the preview API", async () => {
    vi.mocked(previewResponse).mockResolvedValue({
      preview: {
        quote: "hello from preview",
      },
    });

    await renderWorkspace({
      pathParameters: ["orderId"],
      queryParameters: [
        createRequestParameterDefinition("query", {
          name: "status",
        }),
      ],
      requestBodySchema: {
        type: "object",
        properties: {
          customer: {
            type: "object",
            properties: {
              email: {
                type: "string",
                format: "email",
              },
            },
            required: ["email"],
            "x-builder": {
              order: ["email"],
            },
          },
        },
        required: ["customer"],
        "x-builder": {
          order: ["customer"],
        },
      },
      schema: createObjectSchema(),
      scope: "response",
    });

    expect(screen.getAllByLabelText("Path: orderId")).toHaveLength(1);
    expect(screen.getAllByLabelText("Query: status")).toHaveLength(1);
    expect(screen.getAllByLabelText("Request body JSON")).toHaveLength(1);

    await fireEvent.update(screen.getByLabelText("Path: orderId"), "ord-42");
    await fireEvent.update(screen.getByLabelText("Query: status"), "queued");
    await fireEvent.update(screen.getByLabelText("Request body JSON"), '{"customer":{"email":"ops@example.com"}}');

    await vi.advanceTimersByTimeAsync(400);
    await flushPromises();

    expect(previewResponse).toHaveBeenLastCalledWith(
      expect.objectContaining({
        type: "object",
      }),
      null,
      {
        orderId: "ord-42",
      },
      expect.objectContaining({
        token: "session-token",
      }),
      {
        queryParameters: {
          status: "queued",
        },
        requestBody: {
          customer: {
            email: "ops@example.com",
          },
        },
      },
    );
  });

  it("copies schema and preview json through the schema actions", async () => {
    const clipboardWriteText = vi.mocked(navigator.clipboard.writeText);
    vi.mocked(previewResponse).mockResolvedValue({
      preview: {
        quote: "hello from preview",
      },
    });

    await renderWorkspace({
      schema: createObjectSchema(),
      scope: "response",
    });

    await vi.advanceTimersByTimeAsync(400);
    await flushPromises();

    await fireEvent.click(screen.getByRole("button", { name: "Copy JSON" }));
    const copiedSchema = JSON.parse(String(clipboardWriteText.mock.calls[0]?.[0]));
    expect(copiedSchema).toMatchObject({
      type: "object",
      properties: {
        quote: {
          type: "string",
        },
      },
    });

    await fireEvent.click(screen.getByRole("button", { name: "Copy sample" }));
    expect(JSON.parse(String(clipboardWriteText.mock.calls.at(-1)?.[0]))).toEqual({ quote: "hello from preview" });
  }, 30_000);

  it("logs out and redirects to login when preview auth expires", async () => {
    vi.mocked(previewResponse).mockRejectedValue(new AdminApiError("Unauthorized", 401));

    const { router } = await renderWorkspace({
      schema: createObjectSchema("message"),
      scope: "response",
    });

    await vi.advanceTimersByTimeAsync(400);
    await flushPromises();

    expect(authStub.logout).toHaveBeenCalledWith("Your admin session expired. Sign in again before previewing response schemas.");
    expect(router.currentRoute.value.name).toBe("login");
  });
});
