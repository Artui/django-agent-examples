<script setup lang="ts">
import { computed } from "vue";
import { eventElementId, formatHour, labelForIso } from "./calendar";
import type { BoardState } from "./useBoard";

const props = defineProps<{ board: BoardState }>();

/**
 * No drop targets: a third route is worth having only if `read_page` sees a
 * genuinely different surface after the agent navigates.
 */
const days = computed(() => {
  const seen = [...new Set(props.board.scheduled.value.map((event) => event.day))];
  return seen.filter((day): day is string => day !== null).sort();
});

function forDay(day: string) {
  return props.board.scheduled.value
    .filter((event) => event.day === day)
    .sort((left, right) => (left.start_hour ?? 0) - (right.start_hour ?? 0));
}
</script>

<template>
  <div class="agenda">
    <section v-for="day in days" :key="day">
      <h3>{{ labelForIso(day) }}</h3>
      <ul>
        <li
          v-for="event in forDay(day)"
          :key="event.id"
          :id="eventElementId(event.id)"
          :class="{ 'agenda-selected': props.board.selection.value === event.id }"
          @click="props.board.select(event.id)"
        >
          <strong>{{ formatHour(event.start_hour ?? 0) }}</strong> {{ event.title }}
          <span v-if="event.room !== ''" class="muted"> · {{ event.room }}</span>
        </li>
      </ul>
    </section>
    <p v-if="days.length === 0" class="muted">Nothing scheduled.</p>
  </div>
</template>
