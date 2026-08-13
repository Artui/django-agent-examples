import { eventElementId, formatHour, labelForIso } from "./calendar";
import type { BoardState } from "./useBoard";

interface Props {
  board: BoardState;
}

/**
 * A flat list, grouped by day. No drop targets: the point of a third route is
 * that the agent's `read_page` sees a genuinely different surface after it
 * navigates, not the same one relabelled.
 */
export function AgendaView({ board }: Props) {
  const days = [...new Set(board.scheduled.map((event) => event.day))].filter(
    (day): day is string => day !== null,
  );
  days.sort();

  return (
    <div className="agenda">
      {days.map((day) => (
        <section key={day}>
          <h3>{labelForIso(day)}</h3>
          <ul>
            {board.scheduled
              .filter((event) => event.day === day)
              .sort((left, right) => (left.start_hour ?? 0) - (right.start_hour ?? 0))
              .map((event) => (
                <li
                  key={event.id}
                  id={eventElementId(event.id)}
                  className={board.selection === event.id ? "agenda-selected" : undefined}
                  onClick={() => board.select(event.id)}
                >
                  <strong>{formatHour(event.start_hour ?? 0)}</strong> {event.title}
                  {event.room === "" ? null : <span className="muted"> · {event.room}</span>}
                </li>
              ))}
          </ul>
        </section>
      ))}
      {days.length === 0 ? <p className="muted">Nothing scheduled.</p> : null}
    </div>
  );
}
