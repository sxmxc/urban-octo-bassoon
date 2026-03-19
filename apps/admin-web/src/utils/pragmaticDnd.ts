import { draggable, dropTargetForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { unref, type ObjectDirective, type DirectiveBinding } from "vue";
import { setPillDragPreview, type DragGhostOptions } from "./dragGhost";

const cleanupKey = Symbol("pragmatic-dnd-cleanup");

type CleanupElement = HTMLElement & {
  [cleanupKey]?: () => void;
};

export type PragmaticDraggableBinding<TData extends Record<string, unknown> = Record<string, unknown>> = {
  canDrag?: boolean;
  data: TData;
  preview?: DragGhostOptions;
  onDragStart?: (args: { data: TData; element: HTMLElement }) => void;
  onDrop?: (args: { data: TData; element: HTMLElement }) => void;
};

export type PragmaticDropTargetBinding<TData extends Record<string, unknown> = Record<string, unknown>> = {
  canDrop?: (args: { sourceData: TData }) => boolean;
  dropEffect?:
    | Exclude<DataTransfer["dropEffect"], "none">
    | ((args: { sourceData: TData }) => Exclude<DataTransfer["dropEffect"], "none">);
  onDragEnter?: (args: { sourceData: TData; element: HTMLElement }) => void;
  onDragLeave?: (args: { sourceData: TData; element: HTMLElement }) => void;
  onDrop?: (args: { clientX: number; clientY: number; element: HTMLElement; sourceData: TData }) => void;
};

function cleanupBinding(el: CleanupElement): void {
  el[cleanupKey]?.();
  delete el[cleanupKey];
}

function mountDraggable<TData extends Record<string, unknown>>(
  el: CleanupElement,
  binding: DirectiveBinding<PragmaticDraggableBinding<TData>>,
): void {
  cleanupBinding(el);

  const value = unref(binding.value);
  if (!value || value.canDrag === false) {
    return;
  }

  el[cleanupKey] = draggable({
    element: el,
    canDrag: () => value.canDrag !== false,
    getInitialData: () => value.data as Record<string, unknown>,
    onGenerateDragPreview: ({ nativeSetDragImage }) => {
      if (!value.preview) {
        return;
      }

      setPillDragPreview(nativeSetDragImage, value.preview as DragGhostOptions);
    },
    onDragStart: () => {
      value.onDragStart?.({
        data: value.data,
        element: el,
      });
    },
    onDrop: () => {
      value.onDrop?.({
        data: value.data,
        element: el,
      });
    },
  });
}

function mountDropTarget<TData extends Record<string, unknown>>(
  el: CleanupElement,
  binding: DirectiveBinding<PragmaticDropTargetBinding<TData>>,
): void {
  cleanupBinding(el);

  const value = unref(binding.value);
  if (!value) {
    return;
  }

  el[cleanupKey] = dropTargetForElements({
    element: el,
    canDrop: ({ source }) => value.canDrop?.({ sourceData: source.data as TData }) ?? true,
    getDropEffect: ({ source }) => {
      if (typeof value.dropEffect === "function") {
        return value.dropEffect({ sourceData: source.data as TData });
      }

      return value.dropEffect ?? "move";
    },
    onDragEnter: ({ source }) => {
      value.onDragEnter?.({
        sourceData: source.data as TData,
        element: el,
      });
    },
    onDragLeave: ({ source }) => {
      value.onDragLeave?.({
        sourceData: source.data as TData,
        element: el,
      });
    },
    onDrop: ({ location, source }) => {
      value.onDrop?.({
        clientX: location.current.input.clientX,
        clientY: location.current.input.clientY,
        element: el,
        sourceData: source.data as TData,
      });
    },
  });
}

export const vPragmaticDraggable: ObjectDirective<
  HTMLElement,
  PragmaticDraggableBinding<Record<string, unknown>> | null
> = {
  mounted(el, binding) {
    mountDraggable(el as CleanupElement, binding as DirectiveBinding<PragmaticDraggableBinding<Record<string, unknown>>>);
  },
  updated(el, binding) {
    if (unref(binding.value) === unref(binding.oldValue)) {
      return;
    }

    mountDraggable(el as CleanupElement, binding as DirectiveBinding<PragmaticDraggableBinding<Record<string, unknown>>>);
  },
  unmounted(el) {
    cleanupBinding(el as CleanupElement);
  },
};

export const vPragmaticDropTarget: ObjectDirective<
  HTMLElement,
  PragmaticDropTargetBinding<Record<string, unknown>> | null
> = {
  mounted(el, binding) {
    mountDropTarget(el as CleanupElement, binding as DirectiveBinding<PragmaticDropTargetBinding<Record<string, unknown>>>);
  },
  updated(el, binding) {
    if (unref(binding.value) === unref(binding.oldValue)) {
      return;
    }

    mountDropTarget(el as CleanupElement, binding as DirectiveBinding<PragmaticDropTargetBinding<Record<string, unknown>>>);
  },
  unmounted(el) {
    cleanupBinding(el as CleanupElement);
  },
};
