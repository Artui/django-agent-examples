<script lang="ts">
  import type { RouteMap } from "@artooi/ag-ui-web-component";
  import Assistant from "./assistant/Assistant.svelte";
  import AgendaView from "./board/AgendaView.svelte";
  import Backlog from "./board/Backlog.svelte";
  import WeekGrid from "./board/WeekGrid.svelte";
  import { Board } from "./board/board.svelte";
  import { isoDate, labelForIso, weekDays } from "./board/calendar";
  import { buildPageMap, type ViewName } from "./board/pageMap";
  import { router } from "./router.svelte";

  /** The routes the agent may navigate to, matching the router. */
  const ROUTE_MAP: RouteMap = [
    {
      id: "week",
      path: "/week",
      title: "Week grid",
      description: "Five days across, hours down the side. Drop targets for scheduling.",
    },
    {
      id: "day",
      path: "/day",
      title: "Day column",
      description: "One day of the grid, for a close look at a single day.",
    },
    {
      id: "agenda",
      path: "/agenda",
      title: "Agenda list",
      description: "Everything scheduled as a flat list, grouped by day. No drop targets.",
    },
  ];

  const board = new Board();
  void board.reload();

  const days = weekDays();
  const today =
    days.find((day) => day.date === isoDate(new Date())) ??
    days[0] ?? { date: isoDate(new Date()), label: labelForIso(isoDate(new Date())) };

  const view = $derived<ViewName>(
    router.path.startsWith("/agenda") ? "agenda" : router.path.startsWith("/day") ? "day" : "week",
  );
  const visibleDays = $derived(view === "day" ? [today] : days);
</script>

<div class="layout">
  <header class="topbar">
    <h1>Scheduling board</h1>
    <nav>
      {#each ROUTE_MAP as entry (entry.id)}
        <button
          type="button"
          class:nav-current={view === entry.id}
          onclick={() => router.navigate(entry.path)}
        >
          {entry.title}
        </button>
      {/each}
    </nav>
    <label class="filter">
      Room
      <select value={board.filter} onchange={(e) => board.setFilter(e.currentTarget.value)}>
        <option value="all">all</option>
        {#each board.rooms as room (room)}
          <option value={room}>{room}</option>
        {/each}
      </select>
    </label>
  </header>

  {#if board.error !== null}
    <p class="error" role="alert">{board.error}</p>
  {/if}

  <main class="main">
    <div class="board">
      {#if view === "agenda"}
        <AgendaView {board} />
      {:else}
        <WeekGrid days={visibleDays} {board} />
      {/if}
      <Backlog {board} />
    </div>

    <Assistant
      routeMap={ROUTE_MAP}
      navigate={(path) => router.navigate(path)}
      reload={() => void board.reload()}
      getPageMap={() => buildPageMap(view, visibleDays, board.snapshot())}
      skillContext={() => (view === "day" ? { day: today.label } : {})}
      readBoardState={() => ({
        view,
        filter: board.filter,
        selection: board.selection,
        scheduled: board.scheduled.length,
        backlog: board.backlog.length,
      })}
      writeBoardState={(patch) => {
        if (typeof patch["room"] === "string") {
          board.setFilter(patch["room"]);
        }
        if (patch["selection"] === null || typeof patch["selection"] === "number") {
          board.select(patch["selection"] as number | null);
        }
        return { ok: true };
      }}
    />
  </main>
</div>
