<script setup lang="ts">
import EventCard from "./EventCard.vue";
import { parseEventElementId } from "./calendar";
import { readDrag } from "./dragging";
import type { BoardState } from "./useBoard";

const props = defineProps<{ board: BoardState }>();

/**
 * A drop target twice over: on a card it reorders, on the empty space it takes
 * the event out of the grid.
 */
function dragged(dropEvent: DragEvent): number | null {
  return parseEventElementId(readDrag(dropEvent.dataTransfer) ?? "");
}

function unschedule(dropEvent: DragEvent): void {
  dropEvent.preventDefault();
  const eventId = dragged(dropEvent);
  if (eventId !== null) {
    void props.board.unschedule(eventId);
  }
}

function reorder(beforeId: number, dropEvent: DragEvent): void {
  // Stop here: the list's own handler would unschedule instead of reordering.
  dropEvent.stopPropagation();
  dropEvent.preventDefault();
  const eventId = dragged(dropEvent);
  if (eventId !== null && eventId !== beforeId) {
    void props.board.reorder(eventId, beforeId);
  }
}
</script>

<template>
  <section id="backlog" class="backlog" @dragover.prevent @drop="unschedule">
    <h2>Backlog</h2>
    <ol class="backlog-list">
      <li
        v-for="event in props.board.backlog.value"
        :key="event.id"
        @dragover.prevent
        @drop="reorder(event.id, $event)"
      >
        <EventCard
          :event="event"
          :selected="props.board.selection.value === event.id"
          compact
          @select="props.board.select"
        />
      </li>
    </ol>
    <p v-if="props.board.backlog.value.length === 0" class="muted">Nothing waiting.</p>
    <p class="muted backlog-hint">Drop a card here to take it out of the week.</p>
  </section>
</template>
