import { pointerOutsideOfPreview } from "@atlaskit/pragmatic-drag-and-drop/element/pointer-outside-of-preview";
import { setCustomNativeDragPreview } from "@atlaskit/pragmatic-drag-and-drop/element/set-custom-native-drag-preview";
import type { ElementEventPayloadMap } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";

export type DragGhostTone = "mode" | "node" | "value";

export type DragGhostOptions = {
  eyebrow?: string;
  label: string;
  tone: DragGhostTone;
};

export function createPillDragGhost(options: DragGhostOptions): HTMLDivElement {
  const ghost = document.createElement("div");
  ghost.className = `schema-drag-ghost schema-drag-ghost-${options.tone}`;

  if (options.eyebrow) {
    const eyebrow = document.createElement("span");
    eyebrow.className = "schema-drag-ghost-eyebrow";
    eyebrow.textContent = options.eyebrow;
    ghost.append(eyebrow);
  }

  const label = document.createElement("span");
  label.className = "schema-drag-ghost-label";
  label.textContent = options.label;
  ghost.append(label);

  return ghost;
}

export function setPillDragPreview(
  nativeSetDragImage: ElementEventPayloadMap["onGenerateDragPreview"]["nativeSetDragImage"],
  options: DragGhostOptions,
): void {
  if (!nativeSetDragImage || typeof document === "undefined") {
    return;
  }

  setCustomNativeDragPreview({
    nativeSetDragImage,
    getOffset: pointerOutsideOfPreview({
      x: "16px",
      y: "12px",
    }),
    render: ({ container }) => {
      const ghost = createPillDragGhost(options);
      container.append(ghost);

      return () => {
        ghost.remove();
      };
    },
  });
}

export function setDragSourceClass(element: Element | null, className: string, active: boolean): void {
  if (!(element instanceof HTMLElement)) {
    return;
  }

  element.classList.toggle(className, active);
}
