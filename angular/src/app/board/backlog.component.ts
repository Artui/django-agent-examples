import { Component } from "@angular/core";
import { BoardService } from "./board.service";
import { parseEventElementId } from "./calendar";
import { readDrag } from "./dragging";
import { EventCardComponent } from "./event-card.component";

/**
 * A drop target twice over: on a card it reorders, on the empty space it takes
 * the event out of the grid.
 */
@Component({
  selector: "app-backlog",
  imports: [EventCardComponent],
  template: `
    <section
      id="backlog"
      class="backlog"
      (dragover)="$event.preventDefault()"
      (drop)="unschedule($event)"
    >
      <h2>Backlog</h2>
      <ol class="backlog-list">
        @for (event of board.backlog(); track event.id) {
          <li (dragover)="$event.preventDefault()" (drop)="reorder(event.id, $event)">
            <app-event-card
              [event]="event"
              [selected]="board.selection() === event.id"
              [compact]="true"
              (select)="board.select($event)"
            />
          </li>
        }
      </ol>
      @if (board.backlog().length === 0) {
        <p class="muted">Nothing waiting.</p>
      }
      <p class="muted backlog-hint">Drop a card here to take it out of the week.</p>
    </section>
  `,
  // Angular wraps every component in a host element, which would sit between the
  // page's grid and its children and break the layout. `display: contents` takes
  // the host out of layout so the children participate in the parent grid as they
  // do in the other apps. This is the one thing about the board that is Angular's
  // rather than the board's.
  styles: [":host { display: contents; }"],
})
export class BacklogComponent {
  constructor(readonly board: BoardService) {}

  private dragged(dropEvent: DragEvent): number | null {
    return parseEventElementId(readDrag(dropEvent.dataTransfer) ?? "");
  }

  unschedule(dropEvent: DragEvent): void {
    dropEvent.preventDefault();
    const eventId = this.dragged(dropEvent);
    if (eventId !== null) {
      void this.board.unschedule(eventId);
    }
  }

  reorder(beforeId: number, dropEvent: DragEvent): void {
    // Stop here: the list's own handler would unschedule instead of reordering.
    dropEvent.stopPropagation();
    dropEvent.preventDefault();
    const eventId = this.dragged(dropEvent);
    if (eventId !== null && eventId !== beforeId) {
      void this.board.reorder(eventId, beforeId);
    }
  }
}
