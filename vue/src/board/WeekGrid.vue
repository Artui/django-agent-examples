<script setup lang="ts">
import type { EventRow } from "../api";
import EventCard from "./EventCard.vue";
import {
  HOURS,
  type Day,
  dayElementId,
  formatHour,
  parseEventElementId,
  slotElementId,
} from "./calendar";
import { readDrag } from "./dragging";
import type { BoardState } from "./useBoard";

const props = defineProps<{ days: Day[]; board: BoardState }>();

/**
 * Hours down the side, days across, and a container that overflows on both axes —
 * which is what makes the two scrolling interactions real rather than notional.
 */
function at(day: string, hour: number): EventRow | undefined {
  return props.board.scheduled.value.find(
    (event) => event.day === day && event.start_hour === hour,
  );
}

function drop(day: string, hour: number, dropEvent: DragEvent): void {
  dropEvent.preventDefault();
  const eventId = parseEventElementId(readDrag(dropEvent.dataTransfer) ?? "");
  if (eventId !== null) {
    void props.board.schedule(eventId, day, hour);
  }
}
</script>

<template>
  <div class="grid-scroller">
    <div
      class="grid"
      :style="{ gridTemplateColumns: `5rem repeat(${props.days.length}, 14rem)` }"
    >
      <div class="grid-corner" />
      <div
        v-for="day in props.days"
        :key="day.date"
        :id="dayElementId(day.date)"
        class="grid-day-head"
      >
        {{ day.label }}
      </div>
      <template v-for="hour in HOURS" :key="hour">
        <div class="grid-hour">{{ formatHour(hour) }}</div>
        <div
          v-for="day in props.days"
          :key="`${day.date}-${hour}`"
          :id="slotElementId(day.date, hour)"
          class="grid-slot"
          :class="{ 'grid-slot-taken': at(day.date, hour) !== undefined }"
          :aria-label="`${day.label} ${formatHour(hour)}`"
          @dragover.prevent
          @drop="drop(day.date, hour, $event)"
        >
          <EventCard
            v-if="at(day.date, hour) !== undefined"
            :event="at(day.date, hour)!"
            :selected="props.board.selection.value === at(day.date, hour)!.id"
            @select="props.board.select"
          />
        </div>
      </template>
    </div>
  </div>
</template>
