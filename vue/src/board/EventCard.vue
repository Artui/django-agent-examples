<script setup lang="ts">
import type { EventRow } from "../api";
import { eventElementId, formatHour } from "./calendar";
import { beginDrag, endDrag } from "./dragging";

const props = defineProps<{
  event: EventRow;
  selected: boolean;
  compact?: boolean;
}>();

const emit = defineEmits<{ select: [eventId: number] }>();

/**
 * The `id` attribute is what the agent addresses: the same string the page map
 * reports and `resolvePageTarget` resolves.
 */
</script>

<template>
  <article
    :id="eventElementId(props.event.id)"
    class="card"
    :class="{ 'card-selected': props.selected, 'card-compact': props.compact }"
    draggable="true"
    :aria-label="props.event.title"
    @dragstart="beginDrag(eventElementId(props.event.id), $event.dataTransfer)"
    @dragend="endDrag()"
    @click="emit('select', props.event.id)"
  >
    <span class="card-title">{{ props.event.title }}</span>
    <span class="card-meta">
      {{ props.event.start_hour === null ? "unscheduled" : formatHour(props.event.start_hour) }}
      {{ props.event.room === "" ? "" : ` · ${props.event.room}` }}
    </span>
  </article>
</template>
