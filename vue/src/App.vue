<script setup lang="ts">
import type { RouteMap } from "@artooi/ag-ui-web-component";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import Assistant from "./assistant/Assistant.vue";
import AgendaView from "./board/AgendaView.vue";
import Backlog from "./board/Backlog.vue";
import WeekGrid from "./board/WeekGrid.vue";
import { isoDate, labelForIso, weekDays } from "./board/calendar";
import { buildPageMap, type ViewName } from "./board/pageMap";
import { useBoard } from "./board/useBoard";

/** The routes the agent may navigate to, matching the router below. */
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

const board = useBoard();
const route = useRoute();
const router = useRouter();
const days = weekDays();
const today =
  days.find((day) => day.date === isoDate(new Date())) ??
  days[0] ?? { date: isoDate(new Date()), label: labelForIso(isoDate(new Date())) };

const view = computed<ViewName>(() =>
  route.path.startsWith("/agenda") ? "agenda" : route.path.startsWith("/day") ? "day" : "week",
);
const visibleDays = computed(() => (view.value === "day" ? [today] : days));

function snapshot() {
  return {
    saving: board.saving.value,
    filter: board.filter.value,
    selection: board.selection.value,
    scheduled: board.scheduled.value,
    backlog: board.backlog.value,
  };
}
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <h1>Scheduling board</h1>
      <nav>
        <button
          v-for="entry in ROUTE_MAP"
          :key="entry.id"
          type="button"
          :class="{ 'nav-current': view === entry.id }"
          @click="router.push(entry.path)"
        >
          {{ entry.title }}
        </button>
      </nav>
      <label class="filter">
        Room
        <select :value="board.filter.value" @change="board.setFilter(($event.target as HTMLSelectElement).value)">
          <option value="all">all</option>
          <option v-for="room in board.rooms.value" :key="room" :value="room">{{ room }}</option>
        </select>
      </label>
    </header>

    <p v-if="board.error.value !== null" class="error" role="alert">
      {{ board.error.value }}
    </p>

    <main class="main">
      <div class="board">
        <WeekGrid v-if="view === 'week'" :days="days" :board="board" />
        <WeekGrid v-else-if="view === 'day'" :days="[today]" :board="board" />
        <AgendaView v-else :board="board" />
        <Backlog :board="board" />
      </div>

      <Assistant
        :route-map="ROUTE_MAP"
        :navigate="(path: string) => router.push(path)"
        :get-page-map="() => buildPageMap(view, visibleDays, snapshot())"
        :read-board-state="
          () => ({
            view,
            filter: board.filter.value,
            selection: board.selection.value,
            scheduled: board.scheduled.value.length,
            backlog: board.backlog.value.length,
          })
        "
        :write-board-state="
          (patch: Record<string, unknown>) => {
            if (typeof patch['room'] === 'string') {
              board.setFilter(patch['room']);
            }
            if (patch['selection'] === null || typeof patch['selection'] === 'number') {
              board.select(patch['selection'] as number | null);
            }
            return { ok: true };
          }
        "
      />
    </main>
  </div>
</template>
