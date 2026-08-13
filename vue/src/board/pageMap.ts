/**
 * What the agent is told the page contains.
 *
 * Ids, labels and coordinates — never values it could get from the API instead.
 * The element recomputes this at the top of every tool round, so after the agent
 * acts the next round already sees the result, and `read_page` returns it on
 * demand within a round.
 *
 * It takes a plain snapshot rather than the composable, so unwrapping Vue's refs
 * stays at the call site and this file is identical in every app in the gallery.
 */

import type { PageMap } from "@artooi/ag-ui-web-component";
import type { EventRow } from "../api";
import {
  HOURS,
  type Day,
  dayElementId,
  eventElementId,
  formatHour,
  slotElementId,
} from "./calendar";

export type ViewName = "week" | "day" | "agenda";

export interface BoardSnapshot {
  saving: boolean;
  filter: string;
  selection: number | null;
  scheduled: EventRow[];
  backlog: EventRow[];
}

export function buildPageMap(view: ViewName, days: Day[], board: BoardSnapshot): PageMap {
  const events = board.scheduled.map((event) => ({
    id: eventElementId(event.id),
    label: event.title,
    day: event.day,
    hour: event.start_hour,
    room: event.room,
  }));
  const taken = new Set(board.scheduled.map((event) => `${event.day}-${event.start_hour}`));

  return {
    view,
    // Whether the page is mid-save. A page action returns as soon as it has
    // dispatched the DOM event, so an agent reading the page straight afterwards
    // can outrun the page's own save; this is what lets it wait instead.
    saving: board.saving,
    filter: { room: board.filter },
    selection: board.selection === null ? null : eventElementId(board.selection),
    days: days.map((day) => ({ id: dayElementId(day.date), label: day.label, date: day.date })),
    hours: HOURS.map(formatHour),
    // Only the visible view's cells: on the agenda there is nothing to drop onto.
    slots:
      view === "agenda"
        ? []
        : days.flatMap((day) =>
            HOURS.map((hour) => ({
              id: slotElementId(day.date, hour),
              label: `${day.label} ${formatHour(hour)}`,
              day: day.date,
              hour,
              taken: taken.has(`${day.date}-${hour}`),
            })),
          ),
    events,
    backlog: board.backlog.map((event) => ({
      id: eventElementId(event.id),
      label: event.title,
      position: event.position,
    })),
  };
}
