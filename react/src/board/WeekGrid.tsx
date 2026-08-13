import type { EventRow } from "../api";
import type { BoardState } from "./useBoard";
import {
  HOURS,
  type Day,
  dayElementId,
  formatHour,
  slotElementId,
} from "./calendar";
import { EventCard } from "./EventCard";
import { parseEventElementId } from "./calendar";
import { readDrag } from "./dragging";

interface Props {
  days: Day[];
  board: BoardState;
}

/**
 * The grid: hours down the side, days across, and a scroll container that
 * overflows on both axes. That is what makes the two scrolling interactions
 * (`scroll_to` vertically down the hours, horizontally across the days) real
 * rather than notional.
 */
export function WeekGrid({ days, board }: Props) {
  const at = (day: string, hour: number): EventRow | undefined =>
    board.scheduled.find((event) => event.day === day && event.start_hour === hour);

  const drop = (day: string, hour: number) => (dropEvent: React.DragEvent) => {
    dropEvent.preventDefault();
    const eventId = parseEventElementId(readDrag(dropEvent.dataTransfer) ?? "");
    if (eventId !== null) {
      void board.schedule(eventId, day, hour);
    }
  };

  return (
    <div className="grid-scroller" data-testid="grid-scroller">
      <div className="grid" style={{ gridTemplateColumns: `5rem repeat(${days.length}, 14rem)` }}>
        <div className="grid-corner" />
        {days.map((day) => (
          <div key={day.date} id={dayElementId(day.date)} className="grid-day-head">
            {day.label}
          </div>
        ))}
        {HOURS.map((hour) => (
          <div className="grid-row" key={hour} style={{ display: "contents" }}>
            <div className="grid-hour">{formatHour(hour)}</div>
            {days.map((day) => {
              const event = at(day.date, hour);
              return (
                <div
                  key={`${day.date}-${hour}`}
                  id={slotElementId(day.date, hour)}
                  className={`grid-slot${event === undefined ? "" : " grid-slot-taken"}`}
                  onDragOver={(dragEvent) => dragEvent.preventDefault()}
                  onDrop={drop(day.date, hour)}
                  aria-label={`${day.label} ${formatHour(hour)}`}
                >
                  {event === undefined ? null : (
                    <EventCard
                      event={event}
                      selected={board.selection === event.id}
                      onSelect={board.select}
                    />
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
