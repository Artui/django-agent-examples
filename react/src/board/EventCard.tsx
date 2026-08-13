import type { EventRow } from "../api";
import { eventElementId, formatHour } from "./calendar";
import { beginDrag, endDrag } from "./dragging";

interface Props {
  event: EventRow;
  selected: boolean;
  onSelect: (eventId: number) => void;
  compact?: boolean;
}

/**
 * One draggable card. The `id` attribute is what the agent addresses: it is the
 * same string `getPageMap` reports and `resolvePageTarget` resolves.
 */
export function EventCard({ event, selected, onSelect, compact = false }: Props) {
  return (
    <article
      id={eventElementId(event.id)}
      className={`card${selected ? " card-selected" : ""}${compact ? " card-compact" : ""}`}
      draggable
      onDragStart={(dragEvent) => beginDrag(eventElementId(event.id), dragEvent.dataTransfer)}
      onDragEnd={endDrag}
      onClick={() => onSelect(event.id)}
      aria-label={event.title}
    >
      <span className="card-title">{event.title}</span>
      <span className="card-meta">
        {event.start_hour === null ? "unscheduled" : formatHour(event.start_hour)}
        {event.room === "" ? "" : ` · ${event.room}`}
      </span>
    </article>
  );
}
