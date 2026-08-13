<script lang="ts">
  import type { EventRow } from "../api";
  import type { Board } from "./board.svelte";
  import EventCard from "./EventCard.svelte";
  import {
    HOURS,
    type Day,
    dayElementId,
    formatHour,
    parseEventElementId,
    slotElementId,
  } from "./calendar";
  import { readDrag } from "./dragging";

  /**
   * Hours down the side, days across, and a container that overflows on both axes,
   * which is what makes the two scrolling interactions real rather than notional.
   */
  let { days, board }: { days: Day[]; board: Board } = $props();

  function at(day: string, hour: number): EventRow | undefined {
    return board.scheduled.find((event) => event.day === day && event.start_hour === hour);
  }

  function drop(day: string, hour: number, dropEvent: DragEvent): void {
    dropEvent.preventDefault();
    const eventId = parseEventElementId(readDrag(dropEvent.dataTransfer) ?? "");
    if (eventId !== null) {
      void board.schedule(eventId, day, hour);
    }
  }
</script>

<div class="grid-scroller">
  <div class="grid" style="grid-template-columns: 5rem repeat({days.length}, 14rem)">
    <div class="grid-corner"></div>
    {#each days as day (day.date)}
      <div id={dayElementId(day.date)} class="grid-day-head">{day.label}</div>
    {/each}
    {#each HOURS as hour (hour)}
      <div class="grid-hour">{formatHour(hour)}</div>
      {#each days as day (day.date)}
        {@const event = at(day.date, hour)}
        <div
          id={slotElementId(day.date, hour)}
          class="grid-slot"
          class:grid-slot-taken={event !== undefined}
          aria-label={`${day.label} ${formatHour(hour)}`}
          ondragover={(dragEvent) => dragEvent.preventDefault()}
          ondrop={(dropEvent) => drop(day.date, hour, dropEvent)}
          role="gridcell"
          tabindex="-1"
        >
          {#if event !== undefined}
            <EventCard
              {event}
              selected={board.selection === event.id}
              onselect={(id) => board.select(id)}
            />
          {/if}
        </div>
      {/each}
    {/each}
  </div>
</div>
