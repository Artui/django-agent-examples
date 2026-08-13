<script lang="ts">
  import type { Board } from "./board.svelte";
  import { eventElementId, formatHour, labelForIso } from "./calendar";

  /**
   * No drop targets: a third route is worth having only if `read_page` sees a
   * genuinely different surface after the agent navigates.
   */
  let { board }: { board: Board } = $props();

  const days = $derived(
    [...new Set(board.scheduled.map((event) => event.day))]
      .filter((day): day is string => day !== null)
      .toSorted(),
  );
</script>

<div class="agenda">
  {#each days as day (day)}
    <section>
      <h3>{labelForIso(day)}</h3>
      <ul>
        {#each board.scheduled
          .filter((event) => event.day === day)
          .toSorted((left, right) => (left.start_hour ?? 0) - (right.start_hour ?? 0)) as event (event.id)}
          <li
            id={eventElementId(event.id)}
            class:agenda-selected={board.selection === event.id}
            onclick={() => board.select(event.id)}
          >
            <strong>{formatHour(event.start_hour ?? 0)}</strong>
            {event.title}
            {#if event.room !== ""}<span class="muted"> · {event.room}</span>{/if}
          </li>
        {/each}
      </ul>
    </section>
  {/each}
  {#if days.length === 0}
    <p class="muted">Nothing scheduled.</p>
  {/if}
</div>
