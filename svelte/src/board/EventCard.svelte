<script lang="ts">
  import type { EventRow } from "../api";
  import { eventElementId, formatHour } from "./calendar";
  import { beginDrag, endDrag } from "./dragging";

  /**
   * The `id` attribute is what the agent addresses: the same string the page map
   * reports and `resolvePageTarget` resolves.
   */
  let {
    event,
    selected,
    compact = false,
    onselect,
  }: {
    event: EventRow;
    selected: boolean;
    compact?: boolean;
    onselect: (eventId: number) => void;
  } = $props();
</script>

<article
  id={eventElementId(event.id)}
  class="card"
  class:card-selected={selected}
  class:card-compact={compact}
  draggable="true"
  aria-label={event.title}
  ondragstart={(dragEvent) => beginDrag(eventElementId(event.id), dragEvent.dataTransfer)}
  ondragend={endDrag}
  onclick={() => onselect(event.id)}
>
  <span class="card-title">{event.title}</span>
  <span class="card-meta">
    {event.start_hour === null ? "unscheduled" : formatHour(event.start_hour)}{event.room === ""
      ? ""
      : ` · ${event.room}`}
  </span>
</article>
