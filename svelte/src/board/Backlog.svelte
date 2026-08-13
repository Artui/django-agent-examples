<script lang="ts">
  import type { Board } from "./board.svelte";
  import EventCard from "./EventCard.svelte";
  import { parseEventElementId } from "./calendar";
  import { readDrag } from "./dragging";

  /**
   * A drop target twice over: on a card it reorders, on the empty space it takes
   * the event out of the grid.
   */
  let { board }: { board: Board } = $props();

  function dragged(dropEvent: DragEvent): number | null {
    return parseEventElementId(readDrag(dropEvent.dataTransfer) ?? "");
  }

  function unschedule(dropEvent: DragEvent): void {
    dropEvent.preventDefault();
    const eventId = dragged(dropEvent);
    if (eventId !== null) {
      void board.unschedule(eventId);
    }
  }

  function reorder(beforeId: number, dropEvent: DragEvent): void {
    // Stop here: the list's own handler would unschedule instead of reordering.
    dropEvent.stopPropagation();
    dropEvent.preventDefault();
    const eventId = dragged(dropEvent);
    if (eventId !== null && eventId !== beforeId) {
      void board.reorder(eventId, beforeId);
    }
  }
</script>

<section
  id="backlog"
  class="backlog"
  ondragover={(dragEvent) => dragEvent.preventDefault()}
  ondrop={unschedule}
  role="list"
>
  <h2>Backlog</h2>
  <ol class="backlog-list">
    {#each board.backlog as event (event.id)}
      <li
        ondragover={(dragEvent) => dragEvent.preventDefault()}
        ondrop={(dropEvent) => reorder(event.id, dropEvent)}
      >
        <EventCard
          {event}
          selected={board.selection === event.id}
          compact
          onselect={(id) => board.select(id)}
        />
      </li>
    {/each}
  </ol>
  {#if board.backlog.length === 0}
    <p class="muted">Nothing waiting.</p>
  {/if}
  <p class="muted backlog-hint">Drop a card here to take it out of the week.</p>
</section>
