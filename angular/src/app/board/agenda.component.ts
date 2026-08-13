import { Component, computed } from "@angular/core";
import type { EventRow } from "../api";
import { BoardService } from "./board.service";
import { eventElementId, formatHour, labelForIso } from "./calendar";

/**
 * No drop targets: a third route is worth having only if `read_page` sees a
 * genuinely different surface after the agent navigates.
 */
@Component({
  selector: "app-agenda",
  template: `
    <div class="agenda">
      @for (day of days(); track day) {
        <section>
          <h3>{{ label(day) }}</h3>
          <ul>
            @for (event of forDay(day); track event.id) {
              <li
                [id]="cardId(event)"
                [class.agenda-selected]="board.selection() === event.id"
                (click)="board.select(event.id)"
              >
                <strong>{{ hour(event) }}</strong> {{ event.title }}
                @if (event.room !== "") {
                  <span class="muted"> · {{ event.room }}</span>
                }
              </li>
            }
          </ul>
        </section>
      }
      @if (days().length === 0) {
        <p class="muted">Nothing scheduled.</p>
      }
    </div>
  `,
  // Angular wraps every component in a host element, which would sit between the
  // page's grid and its children and break the layout. `display: contents` takes
  // the host out of layout so the children participate in the parent grid as they
  // do in the other apps. This is the one thing about the board that is Angular's
  // rather than the board's.
  styles: [":host { display: contents; }"],
})
export class AgendaComponent {
  readonly days = computed(() =>
    [...new Set(this.board.scheduled().map((event) => event.day))]
      .filter((day): day is string => day !== null)
      .sort(),
  );

  constructor(readonly board: BoardService) {}

  forDay(day: string): EventRow[] {
    return this.board
      .scheduled()
      .filter((event) => event.day === day)
      .sort((left, right) => (left.start_hour ?? 0) - (right.start_hour ?? 0));
  }

  label(day: string): string {
    return labelForIso(day);
  }

  cardId(event: EventRow): string {
    return eventElementId(event.id);
  }

  hour(event: EventRow): string {
    return formatHour(event.start_hour ?? 0);
  }
}
