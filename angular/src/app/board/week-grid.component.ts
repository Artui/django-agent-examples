import { Component, input } from "@angular/core";
import { BoardService } from "./board.service";
import {
  HOURS,
  type Day,
  dayElementId,
  formatHour,
  parseEventElementId,
  slotElementId,
} from "./calendar";
import { readDrag } from "./dragging";
import { EventCardComponent } from "./event-card.component";

/**
 * Hours down the side, days across, and a container that overflows on both axes,
 * which is what makes the two scrolling interactions real rather than notional.
 */
@Component({
  selector: "app-week-grid",
  imports: [EventCardComponent],
  template: `
    <div class="grid-scroller">
      <div class="grid" [style.gridTemplateColumns]="columns()">
        <div class="grid-corner"></div>
        @for (day of days(); track day.date) {
          <div [id]="dayId(day)" class="grid-day-head">{{ day.label }}</div>
        }
        @for (hour of hours; track hour) {
          <div class="grid-hour">{{ label(hour) }}</div>
          @for (day of days(); track day.date) {
            <div
              [id]="slotId(day, hour)"
              class="grid-slot"
              [class.grid-slot-taken]="board.at(day.date, hour) !== undefined"
              [attr.aria-label]="day.label + ' ' + label(hour)"
              (dragover)="$event.preventDefault()"
              (drop)="drop(day.date, hour, $event)"
            >
              @if (board.at(day.date, hour); as event) {
                <app-event-card
                  [event]="event"
                  [selected]="board.selection() === event.id"
                  (select)="board.select($event)"
                />
              }
            </div>
          }
        }
      </div>
    </div>
  `,
  // Angular wraps every component in a host element, which would sit between the
  // page's grid and its children and break the layout. `display: contents` takes
  // the host out of layout so the children participate in the parent grid as they
  // do in the other apps. This is the one thing about the board that is Angular's
  // rather than the board's.
  styles: [":host { display: contents; }"],
})
export class WeekGridComponent {
  readonly days = input.required<Day[]>();
  readonly hours = HOURS;

  constructor(readonly board: BoardService) {}

  columns(): string {
    return `5rem repeat(${this.days().length}, 14rem)`;
  }

  dayId(day: Day): string {
    return dayElementId(day.date);
  }

  slotId(day: Day, hour: number): string {
    return slotElementId(day.date, hour);
  }

  label(hour: number): string {
    return formatHour(hour);
  }

  drop(day: string, hour: number, dropEvent: DragEvent): void {
    dropEvent.preventDefault();
    const eventId = parseEventElementId(readDrag(dropEvent.dataTransfer) ?? "");
    if (eventId !== null) {
      void this.board.schedule(eventId, day, hour);
    }
  }
}
