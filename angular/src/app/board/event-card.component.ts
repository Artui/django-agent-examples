import { Component, input, output } from "@angular/core";
import type { EventRow } from "../api";
import { eventElementId, formatHour } from "./calendar";
import { beginDrag, endDrag } from "./dragging";

/**
 * One draggable card. The `id` attribute is what the agent addresses: the same
 * string the page map reports and `resolvePageTarget` resolves.
 */
@Component({
  selector: "app-event-card",
  template: `
    <article
      [id]="elementId()"
      class="card"
      [class.card-selected]="selected()"
      [class.card-compact]="compact()"
      draggable="true"
      [attr.aria-label]="event().title"
      (dragstart)="onDragStart($event)"
      (dragend)="endDrag()"
      (click)="select.emit(event().id)"
    >
      <span class="card-title">{{ event().title }}</span>
      <span class="card-meta">{{ meta() }}</span>
    </article>
  `,
})
export class EventCardComponent {
  readonly event = input.required<EventRow>();
  readonly selected = input(false);
  readonly compact = input(false);
  readonly select = output<number>();

  readonly endDrag = endDrag;

  elementId(): string {
    return eventElementId(this.event().id);
  }

  meta(): string {
    const row = this.event();
    const when = row.start_hour === null ? "unscheduled" : formatHour(row.start_hour);
    return row.room === "" ? when : `${when} · ${row.room}`;
  }

  onDragStart(dragEvent: DragEvent): void {
    beginDrag(this.elementId(), dragEvent.dataTransfer);
  }
}
