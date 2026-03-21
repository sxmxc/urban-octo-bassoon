import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/vue";
import { flushPromises } from "@vue/test-utils";
import RouteFlowEditor from "./RouteFlowEditor.vue";
import { vuetify } from "../plugins/vuetify";
import type { RouteFlowDefinition } from "../types/endpoints";

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
      data:
        draggableArgs.getInitialData?.({
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

    const canDrop =
      dropTargetArgs.canDrop?.({
        element: targetElement,
        input,
        source,
      }) ?? true;

    if (canDrop) {
      const self = {
        data: {},
        dropEffect: "copy",
        element: targetElement,
        isActiveDueToStickiness: false,
      };

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

const flowStoreStub = vi.hoisted(() => ({
  fitView: vi.fn(),
  setCenter: vi.fn(),
  screenToFlowCoordinate: vi.fn(({ x, y }: { x: number; y: number }) => ({ x, y })),
  zoomIn: vi.fn(),
  zoomOut: vi.fn(),
}));

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

vi.mock("@vue-flow/core", () => ({
  Panel: {
    template: "<div><slot /></div>",
  },
  VueFlow: {
    props: {
      edges: {
        type: Array,
        default: () => [],
      },
      nodes: {
        type: Array,
        default: () => [],
      },
    },
    emits: ["connect", "edge-update", "init", "node-click", "node-drag-stop", "pane-click", "update:edges", "update:nodes"],
    methods: {
      replacementTarget(
        edge: { source: string; target: string },
        nodes: Array<{ id: string; type?: string; data?: { runtimeType?: string } }>,
      ) {
        const candidate = nodes.find(
          (node) =>
            node.id !== edge.source &&
            node.id !== edge.target &&
            node.id !== "trigger" &&
            node.data?.runtimeType !== "api_trigger",
        );
        return candidate?.id ?? edge.target;
      },
      sourceHandle(edge: { sourceHandle?: string | null; data?: { extra?: { branch?: string } } }) {
        return edge.sourceHandle ?? edge.data?.extra?.branch ?? "next";
      },
    },
    mounted(this: { $emit: (event: string, payload: unknown) => void }) {
      this.$emit("init", flowStoreStub);
    },
    template: `
      <div data-testid="vue-flow">
        <button
          v-for="node in nodes"
          :key="node.id"
          :data-testid="'canvas-node-' + node.id"
          type="button"
          @click="$emit('node-click', { node })"
        >
          Select {{ node.label ?? node.id }}
        </button>
        <button
          v-for="edge in edges"
          :key="'emit-connect-' + edge.id"
          :data-testid="'emit-connect-replace-' + edge.id"
          type="button"
          @click="$emit('connect', { source: edge.source, sourceHandle: sourceHandle(edge), target: replacementTarget(edge, nodes) })"
        >
          Connect replace {{ edge.id }}
        </button>
        <button
          v-for="edge in edges"
          :key="'emit-edge-update-' + edge.id"
          :data-testid="'emit-edge-update-' + edge.id"
          type="button"
          @click="$emit('edge-update', { edge, connection: { source: edge.source, sourceHandle: sourceHandle(edge), target: replacementTarget(edge, nodes) } })"
        >
          Edge update {{ edge.id }}
        </button>
        <slot />
      </div>
    `,
  },
}));

vi.mock("@vue-flow/background", () => ({
  Background: {
    template: "<div data-testid='flow-background' />",
  },
}));

vi.mock("@vue-flow/controls", () => ({
  ControlButton: {
    template: "<button type='button'><slot /></button>",
  },
  Controls: {
    template: "<div><slot /></div>",
  },
}));

vi.mock("@vue-flow/minimap", () => ({
  MiniMap: {
    template: "<div data-testid='flow-minimap' />",
  },
}));

const baseFlowDefinition: RouteFlowDefinition = {
  schema_version: 1,
  nodes: [
    {
      id: "trigger",
      type: "api_trigger",
      name: "API Trigger",
      config: {},
      position: { x: 48, y: 56 },
    },
    {
      id: "transform-1",
      type: "transform",
      name: "Transform",
      config: {
        output: {
          greeting: null,
        },
      },
      position: { x: 332, y: 56 },
    },
    {
      id: "response",
      type: "set_response",
      name: "Set Response",
      config: {
        body: {
          status: "ok",
        },
        status_code: 200,
      },
      position: { x: 616, y: 56 },
    },
  ],
  edges: [
    { source: "trigger", target: "transform-1" },
    { source: "transform-1", target: "response" },
  ],
};

const httpFlowDefinition: RouteFlowDefinition = {
  schema_version: 1,
  nodes: [
    {
      id: "trigger",
      type: "api_trigger",
      name: "API Trigger",
      config: {},
      position: { x: 48, y: 56 },
    },
    {
      id: "http-request-1",
      type: "http_request",
      name: "HTTP Request",
      config: {
        headers: {},
        method: "GET",
        path: "/quotes/",
        query: {},
      },
      position: { x: 332, y: 56 },
    },
    {
      id: "response",
      type: "set_response",
      name: "Set Response",
      config: {
        body: {
          status: "ok",
        },
        status_code: 200,
      },
      position: { x: 616, y: 56 },
    },
  ],
  edges: [
    { source: "trigger", target: "http-request-1" },
    { source: "http-request-1", target: "response" },
  ],
};

const branchFlowDefinition: RouteFlowDefinition = {
  schema_version: 1,
  nodes: [
    {
      id: "trigger",
      type: "api_trigger",
      name: "API Trigger",
      config: {},
      position: { x: 48, y: 56 },
    },
    {
      id: "if-1",
      type: "if_condition",
      name: "If",
      config: {
        left: { $ref: "request.query.mode" },
        operator: "equals",
        right: "fast",
      },
      position: { x: 280, y: 56 },
    },
    {
      id: "transform-1",
      type: "transform",
      name: "Transform",
      config: {
        output: {
          mode: "fallback",
        },
      },
      position: { x: 536, y: 56 },
    },
    {
      id: "response",
      type: "set_response",
      name: "Set Response",
      config: {
        body: {
          status: "ok",
        },
        status_code: 200,
      },
      position: { x: 812, y: 8 },
    },
    {
      id: "error",
      type: "error_response",
      name: "Error Response",
      config: {
        body: {
          status: "error",
        },
        status_code: 400,
      },
      position: { x: 812, y: 136 },
    },
  ],
  edges: [
    { source: "trigger", target: "if-1" },
    { source: "if-1", target: "response", extra: { branch: "true" } },
    { source: "if-1", target: "error", extra: { branch: "false" } },
  ],
};

const replaceableSingleOutputFlowDefinition: RouteFlowDefinition = {
  schema_version: 1,
  nodes: [
    {
      id: "trigger",
      type: "api_trigger",
      name: "API Trigger",
      config: {},
      position: { x: 48, y: 56 },
    },
    {
      id: "transform-1",
      type: "transform",
      name: "Transform",
      config: {
        output: {
          greeting: "hello",
        },
      },
      position: { x: 320, y: 56 },
    },
    {
      id: "response",
      type: "set_response",
      name: "Set Response",
      config: {
        body: {
          status: "ok",
        },
        status_code: 200,
      },
      position: { x: 600, y: 24 },
    },
    {
      id: "error",
      type: "error_response",
      name: "Error Response",
      config: {
        body: {
          status: "error",
        },
        status_code: 400,
      },
      position: { x: 600, y: 136 },
    },
  ],
  edges: [
    { source: "trigger", target: "transform-1" },
    { source: "transform-1", target: "response" },
  ],
};

const switchCaseGrowthFlowDefinition: RouteFlowDefinition = {
  schema_version: 1,
  nodes: [
    {
      id: "trigger",
      type: "api_trigger",
      name: "API Trigger",
      config: {},
      position: { x: 48, y: 56 },
    },
    {
      id: "switch-1",
      type: "switch",
      name: "Switch",
      config: {
        value: { $ref: "request.query.tier" },
      },
      position: { x: 280, y: 56 },
    },
    {
      id: "transform-1",
      type: "transform",
      name: "Transform A",
      config: {
        output: {
          bucket: "a",
        },
      },
      position: { x: 536, y: 24 },
    },
    {
      id: "transform-2",
      type: "transform",
      name: "Transform B",
      config: {
        output: {
          bucket: "b",
        },
      },
      position: { x: 536, y: 160 },
    },
    {
      id: "response",
      type: "set_response",
      name: "Set Response",
      config: {
        body: {
          status: "ok",
        },
        status_code: 200,
      },
      position: { x: 812, y: 88 },
    },
  ],
  edges: [
    { source: "trigger", target: "switch-1" },
    { source: "switch-1", target: "transform-1", extra: { branch: "case", case_value: "vip" } },
    { source: "switch-1", target: "response", extra: { branch: "default" } },
  ],
};

function renderEditor(overrideProps: Record<string, unknown> = {}) {
  return render(RouteFlowEditor, {
    props: {
      modelValue: baseFlowDefinition,
      routeMethod: "GET",
      routeName: "Orders",
      routePath: "/api/orders/{orderId}",
      successStatusCode: 200,
      ...overrideProps,
    },
    global: {
      plugins: [vuetify],
    },
  });
}

beforeEach(() => {
  cleanup();
  dndStub.reset();
  flowStoreStub.fitView.mockReset();
  flowStoreStub.setCenter.mockReset();
  flowStoreStub.screenToFlowCoordinate.mockClear();
  flowStoreStub.zoomIn.mockReset();
  flowStoreStub.zoomOut.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("RouteFlowEditor", () => {
  it("uses the same input-config-output workbench outside focus mode", async () => {
    renderEditor();

    await fireEvent.click(screen.getByTestId("canvas-node-transform-1"));
    await flushPromises();

    expect(screen.getByText("Input payload")).toBeInTheDocument();
    expect(screen.getByText("Output payload")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Parameters" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByText("Flow signals")).toBeInTheDocument();
    expect(screen.getByText("Route paths")).toBeInTheDocument();
    expect(screen.queryByText("Flow sample")).not.toBeInTheDocument();
  }, 10_000);

  it("opens the focus workbench on demand so node selection does not trap the canvas", async () => {
    renderEditor();

    await fireEvent.click(screen.getAllByRole("button", { name: "Open full editor" })[0]);
    await fireEvent.click(screen.getByTestId("canvas-node-transform-1"));
    await flushPromises();

    expect(screen.queryByText("Input payload")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Transform" })).toBeInTheDocument();

    await fireEvent.click(screen.getByRole("button", { name: "Edit Transform" }));
    await flushPromises();

    expect(screen.getByText("Input payload")).toBeInTheDocument();
    expect(screen.getByText("Output payload")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Parameters" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByText("Runtime behavior")).toBeInTheDocument();
    expect(screen.queryByText("Flow sample")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Node name")).not.toBeInTheDocument();

    await fireEvent.click(screen.getAllByRole("button", { name: "Table" })[0]);
    expect(screen.getAllByText("Path").length).toBeGreaterThan(0);

    await fireEvent.click(screen.getAllByRole("button", { name: "JSON" })[0]);
    expect(screen.getAllByText("Data in scope").length).toBeGreaterThan(0);

    await fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByLabelText("Node name")).toBeInTheDocument();
  });

  it("emits save-requested from the focus toolbar save icon", async () => {
    const view = renderEditor();

    await fireEvent.click(screen.getAllByRole("button", { name: "Open full editor" })[0]);
    await flushPromises();

    const saveButton = screen.getByRole("button", { name: "Save flow" });
    expect(saveButton).toBeInTheDocument();

    await fireEvent.click(saveButton);
    await flushPromises();

    const emittedEvents = view.emitted() as Record<string, unknown[][]>;
    expect((emittedEvents["save-requested"] ?? []).length).toBe(1);
  });

  it("removes an outgoing path directly from the focus inspector", async () => {
    const view = renderEditor();

    await fireEvent.click(screen.getAllByRole("button", { name: "Open full editor" })[0]);
    await fireEvent.click(screen.getByTestId("canvas-node-transform-1"));
    await fireEvent.click(screen.getByRole("button", { name: "Edit Transform" }));
    await flushPromises();

    const connectedPathsToggle = screen.getByRole("button", { name: "Connected paths" });
    expect(connectedPathsToggle).toBeInTheDocument();
    await fireEvent.click(connectedPathsToggle);
    await flushPromises();

    expect(screen.getByText("Reconnect or remove outgoing paths directly from this inspector.")).toBeInTheDocument();

    await fireEvent.click(screen.getByRole("button", { name: "Remove path" }));
    await flushPromises();

    const emittedEvents = view.emitted() as Record<string, Array<[RouteFlowDefinition]>>;
    const updates = emittedEvents["update:modelValue"] ?? [];
    const lastUpdate = updates.at(-1)?.[0] as RouteFlowDefinition | undefined;
    expect(lastUpdate?.edges).toHaveLength(1);
    expect(lastUpdate?.edges[0]).toEqual(expect.objectContaining({ source: "trigger", target: "transform-1" }));
  });

  it("keeps editable controls visible first and moves guidance into a collapsible section", async () => {
    renderEditor({
      modelValue: branchFlowDefinition,
    });

    await fireEvent.click(screen.getAllByRole("button", { name: "Open full editor" })[0]);
    await fireEvent.click(screen.getByTestId("canvas-node-if-1"));
    await fireEvent.click(screen.getByRole("button", { name: "Edit If" }));
    await flushPromises();

    expect(screen.getByLabelText("Left value")).toBeInTheDocument();
    expect(screen.queryByText("If checks route data and continues on True or False.")).not.toBeInTheDocument();

    await fireEvent.click(screen.getByRole("button", { name: "Flow guidance" }));
    await flushPromises();

    expect(screen.getByText("If checks route data and continues on True or False.")).toBeInTheDocument();
  });

  it("reconnects an outgoing branch path from the shared connected-path cards", async () => {
    const view = renderEditor({
      modelValue: branchFlowDefinition,
    });

    await fireEvent.click(screen.getAllByRole("button", { name: "Open full editor" })[0]);
    await fireEvent.click(screen.getByTestId("canvas-node-if-1"));
    await fireEvent.click(screen.getByRole("button", { name: "Edit If" }));
    await flushPromises();

    expect(screen.getAllByText("Connected paths").length).toBeGreaterThan(0);

    await fireEvent.click(screen.getAllByRole("button", { name: "Set Response" })[0]);
    await flushPromises();

    await fireEvent.click(await screen.findByText("Transform"));
    await flushPromises();

    const emittedEvents = view.emitted() as Record<string, Array<[RouteFlowDefinition]>>;
    const updates = emittedEvents["update:modelValue"] ?? [];
    const lastUpdate = updates.at(-1)?.[0] as RouteFlowDefinition | undefined;
    expect(lastUpdate?.edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: "if-1", target: "transform-1", extra: { branch: "true" } }),
      ]),
    );
  });

  it("replaces an occupied single-output path when connecting from the same output handle", async () => {
    const view = renderEditor({
      modelValue: replaceableSingleOutputFlowDefinition,
    });

    const replaceButton = view.container.querySelector(
      '[data-testid^="emit-connect-replace-edge-transform-1-response"]',
    );
    expect(replaceButton).toBeTruthy();
    await fireEvent.click(replaceButton as Element);
    await flushPromises();

    const emittedEvents = view.emitted() as Record<string, Array<[RouteFlowDefinition]>>;
    const updates = emittedEvents["update:modelValue"] ?? [];
    const lastUpdate = updates.at(-1)?.[0] as RouteFlowDefinition | undefined;
    expect(lastUpdate?.edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: "transform-1", target: "error" }),
      ]),
    );
    expect(lastUpdate?.edges).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: "transform-1", target: "response" }),
      ]),
    );
  });

  it("appends a second switch case branch when connecting from the shared case handle", async () => {
    const view = renderEditor({
      modelValue: switchCaseGrowthFlowDefinition,
    });

    const replaceButton = view.container.querySelector(
      '[data-testid^="emit-connect-replace-edge-switch-1-transform-1"]',
    );
    expect(replaceButton).toBeTruthy();
    await fireEvent.click(replaceButton as Element);
    await flushPromises();

    const emittedEvents = view.emitted() as Record<string, Array<[RouteFlowDefinition]>>;
    const updates = emittedEvents["update:modelValue"] ?? [];
    const lastUpdate = updates.at(-1)?.[0] as RouteFlowDefinition | undefined;
    const switchCaseEdges = (lastUpdate?.edges ?? []).filter(
      (edge) => edge.source === "switch-1" && edge.extra?.branch === "case",
    );

    expect(lastUpdate?.edges).toHaveLength(4);
    expect(switchCaseEdges).toHaveLength(2);
    expect(switchCaseEdges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ target: "transform-1", extra: { branch: "case", case_value: "vip" } }),
        expect.objectContaining({ target: "transform-2", extra: { branch: "case", case_value: "case-2" } }),
      ]),
    );
  });

  it("rewires an existing edge target via edge-update", async () => {
    const view = renderEditor({
      modelValue: replaceableSingleOutputFlowDefinition,
    });

    const edgeUpdateButton = view.container.querySelector(
      '[data-testid^="emit-edge-update-edge-transform-1-response"]',
    );
    expect(edgeUpdateButton).toBeTruthy();
    await fireEvent.click(edgeUpdateButton as Element);
    await flushPromises();

    const emittedEvents = view.emitted() as Record<string, Array<[RouteFlowDefinition]>>;
    const updates = emittedEvents["update:modelValue"] ?? [];
    const lastUpdate = updates.at(-1)?.[0] as RouteFlowDefinition | undefined;
    expect(lastUpdate?.edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: "transform-1", target: "error" }),
      ]),
    );
    expect(lastUpdate?.edges).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: "transform-1", target: "response" }),
      ]),
    );
  });

  it("disables the focus toolbar save icon when save is unavailable", async () => {
    const view = renderEditor({
      saveDisabled: true,
    });

    await fireEvent.click(screen.getAllByRole("button", { name: "Open full editor" })[0]);
    await flushPromises();

    const saveButton = screen.getByRole("button", { name: "Save flow" });
    expect(saveButton).toBeDisabled();

    await fireEvent.click(saveButton);
    await flushPromises();

    const emittedEvents = view.emitted() as Record<string, unknown[][]>;
    expect(emittedEvents["save-requested"]).toBeUndefined();
  });

  it("lets focus-mode ref pills target the HTTP path template field", async () => {
    const view = renderEditor({
      modelValue: httpFlowDefinition,
    });

    await fireEvent.click(screen.getAllByRole("button", { name: "Open full editor" })[0]);
    await fireEvent.click(screen.getByTestId("canvas-node-http-request-1"));
    await fireEvent.click(screen.getByRole("button", { name: "Edit HTTP Request" }));
    await flushPromises();

    const pathInput = screen.getByLabelText("Path or URL template") as HTMLInputElement;
    pathInput.focus();
    pathInput.setSelectionRange(pathInput.value.length, pathInput.value.length);
    await fireEvent.focusIn(pathInput);
    await fireEvent.select(pathInput);

    const sourceElement = Array.from(dndStub.draggables.keys()).find(
      (element) =>
        element.textContent?.trim() === "orderId"
        && element.closest(".route-flow-editor__focus-side-column--left"),
    );
    expect(sourceElement).toBeTruthy();

    const targetElement = Array.from(dndStub.dropTargets.keys()).find(
      (element) =>
        element.classList.contains("route-flow-editor__text-drop-target") && element.querySelector("input") === pathInput,
    );
    expect(targetElement).toBeTruthy();

    dndStub.simulateDrop(sourceElement as Element, targetElement as Element);
    await flushPromises();

    expect(pathInput.value).toBe("/quotes/{{request.path.orderId}}");

    const emittedEvents = view.emitted() as Record<string, Array<[RouteFlowDefinition]>>;
    const updates = emittedEvents["update:modelValue"] ?? [];
    const lastUpdate = updates.at(-1)?.[0] as RouteFlowDefinition | undefined;
    expect(lastUpdate?.nodes.find((node) => node.id === "http-request-1")?.config.path).toBe(
      "/quotes/{{request.path.orderId}}",
    );
  });

  it("lets clicking a left-pane schema pill insert into the HTTP path template", async () => {
    renderEditor({
      modelValue: httpFlowDefinition,
    });

    await fireEvent.click(screen.getAllByRole("button", { name: "Open full editor" })[0]);
    await fireEvent.click(screen.getByTestId("canvas-node-http-request-1"));
    await fireEvent.click(screen.getByRole("button", { name: "Edit HTTP Request" }));
    await flushPromises();

    const pathInput = screen.getByLabelText("Path or URL template") as HTMLInputElement;
    pathInput.focus();
    pathInput.setSelectionRange(pathInput.value.length, pathInput.value.length);
    await fireEvent.focusIn(pathInput);
    await fireEvent.select(pathInput);

    const leftPaneChip = Array.from(document.querySelectorAll(".route-flow-editor__focus-side-column--left .v-chip")).find(
      (element) => element.textContent?.trim() === "orderId",
    );
    expect(leftPaneChip).toBeTruthy();

    await fireEvent.click(leftPaneChip as Element);
    await flushPromises();

    expect(pathInput.value).toBe("/quotes/{{request.path.orderId}}");
  });

  it("drops a ref snippet into the current JSON selection instead of replacing the whole payload", async () => {
    const view = renderEditor();

    await fireEvent.click(screen.getByTestId("canvas-node-transform-1"));
    await flushPromises();

    const textarea = screen.getByLabelText("Output template JSON") as HTMLTextAreaElement;
    const nullStart = textarea.value.indexOf("null");
    expect(nullStart).toBeGreaterThan(-1);

    textarea.focus();
    textarea.setSelectionRange(nullStart, nullStart + 4);
    await fireEvent.focusIn(textarea);
    await fireEvent.select(textarea);

    const sourceElement = Array.from(dndStub.draggables.keys()).find((element) => element.textContent?.includes("request.body"));
    expect(sourceElement).toBeTruthy();

    const targetElement = Array.from(dndStub.dropTargets.keys()).find(
      (element) =>
        element.classList.contains("route-flow-editor__json-drop-target") && element.querySelector("textarea") === textarea,
    );
    expect(targetElement).toBeTruthy();

    dndStub.simulateDrop(sourceElement as Element, targetElement as Element);
    await flushPromises();

    expect(JSON.parse(textarea.value)).toEqual({
      greeting: {
        $ref: "request.body",
      },
    });
    expect(textarea.value.trim()).not.toBe('{\n  "$ref": "request.body"\n}');

    const emittedEvents = view.emitted() as Record<string, Array<[RouteFlowDefinition]>>;
    const updates = emittedEvents["update:modelValue"] ?? [];
    const lastUpdate = updates.at(-1)?.[0] as RouteFlowDefinition | undefined;
    expect(lastUpdate?.nodes.find((node) => node.id === "transform-1")?.config.output).toEqual({
      greeting: {
        $ref: "request.body",
      },
    });

    const refLineIndex = textarea.value.indexOf('"$ref": "request.body"');
    const caretPosition = textarea.value.indexOf("}", refLineIndex) + 1;
    expect(textarea.selectionStart).toBe(caretPosition);
    expect(textarea.selectionEnd).toBe(caretPosition);
  });
});
