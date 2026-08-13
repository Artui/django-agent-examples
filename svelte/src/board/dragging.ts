/**
 * Native HTML5 drag and drop, which is not an implementation detail.
 *
 * The chat element's `drag_and_drop` tool fires the standard sequence —
 * `dragstart` on the source, then `dragenter` / `dragover` / `drop` on the
 * target, then `dragend` — with one shared `DataTransfer`. A board built on a
 * pointer-event drag library (dnd-kit and friends) never sees any of it, so the
 * agent's drag would silently do nothing. Native handlers are the requirement.
 *
 * The dragged id travels two ways on purpose: through the `DataTransfer`, which
 * is what a real user drag carries, and through a module-scoped handle, which is
 * what survives a browser that hands a drop handler an empty `DataTransfer`.
 */

const MIME = "text/plain";

let dragging: string | null = null;

export function beginDrag(elementId: string, transfer: DataTransfer | null): void {
  dragging = elementId;
  transfer?.setData(MIME, elementId);
  if (transfer !== null) {
    transfer.effectAllowed = "move";
  }
}

export function endDrag(): void {
  dragging = null;
}

export function readDrag(transfer: DataTransfer | null): string | null {
  const carried = transfer?.getData(MIME) ?? "";
  return carried === "" ? dragging : carried;
}
