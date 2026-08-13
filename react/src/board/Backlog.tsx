import type { BoardState } from "./useBoard";
import { parseEventElementId } from "./calendar";
import { EventCard } from "./EventCard";
import { readDrag } from "./dragging";

interface Props {
  board: BoardState;
}

/**
 * The unscheduled list: a drop target twice over. Dropping a card *on another
 * card* reorders (the list interaction); dropping it on the empty space below
 * takes it out of the grid and puts it at the end.
 */
export function Backlog({ board }: Props) {
  const dragged = (dropEvent: React.DragEvent): number | null =>
    parseEventElementId(readDrag(dropEvent.dataTransfer) ?? "");

  return (
    <section
      id="backlog"
      className="backlog"
      onDragOver={(dragEvent) => dragEvent.preventDefault()}
      onDrop={(dropEvent) => {
        dropEvent.preventDefault();
        const eventId = dragged(dropEvent);
        if (eventId !== null) {
          void board.unschedule(eventId);
        }
      }}
    >
      <h2>Backlog</h2>
      <ol className="backlog-list">
        {board.backlog.map((event) => (
          <li
            key={event.id}
            onDragOver={(dragEvent) => dragEvent.preventDefault()}
            onDrop={(dropEvent) => {
              // Stop here: the list's own handler would unschedule instead of
              // reordering, and a drop bubbles.
              dropEvent.stopPropagation();
              dropEvent.preventDefault();
              const eventId = dragged(dropEvent);
              if (eventId !== null && eventId !== event.id) {
                void board.reorder(eventId, event.id);
              }
            }}
          >
            <EventCard
              event={event}
              selected={board.selection === event.id}
              onSelect={board.select}
              compact
            />
          </li>
        ))}
      </ol>
      {board.backlog.length === 0 ? <p className="muted">Nothing waiting.</p> : null}
      <p className="muted backlog-hint">Drop a card here to take it out of the week.</p>
    </section>
  );
}
