/**
 * The board's state as a composable.
 *
 * Same contract as the other apps in the gallery, expressed in Vue's reactivity:
 * refs and computeds instead of `useState` and `useMemo`. The agent cannot tell
 * the difference, which is the point of the comparison.
 */

import { computed, onMounted, ref, type ComputedRef, type Ref } from "vue";
import { type EventRow, listEvents, moveEvent, reorderEvent } from "../api";

export type RoomFilter = "all" | string;

export interface BoardState {
  events: ComputedRef<EventRow[]>;
  scheduled: ComputedRef<EventRow[]>;
  backlog: ComputedRef<EventRow[]>;
  rooms: ComputedRef<string[]>;
  filter: Ref<RoomFilter>;
  selection: Ref<number | null>;
  error: Ref<string | null>;
  loading: Ref<boolean>;
  /** True while a move is saving; reported in the page map so an agent can wait. */
  saving: Ref<boolean>;
  select: (eventId: number | null) => void;
  setFilter: (room: RoomFilter) => void;
  schedule: (eventId: number, day: string, hour: number) => Promise<void>;
  unschedule: (eventId: number) => Promise<void>;
  reorder: (eventId: number, beforeEventId: number | null) => Promise<void>;
  reload: () => Promise<void>;
}

export function useBoard(): BoardState {
  const all = ref<EventRow[]>([]);
  const filter = ref<RoomFilter>("all");
  const selection = ref<number | null>(null);
  const error = ref<string | null>(null);
  const loading = ref(true);
  const saving = ref(false);

  const reload = async (): Promise<void> => {
    try {
      all.value = await listEvents();
      error.value = null;
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause);
    } finally {
      loading.value = false;
    }
  };

  const persist = async (operation: Promise<EventRow>): Promise<void> => {
    let refusal: string | null = null;
    saving.value = true;
    try {
      await operation;
    } catch (cause) {
      refusal = cause instanceof Error ? cause.message : String(cause);
    }
    // Reload first, then report: a reload clears the banner on success.
    await reload();
    error.value = refusal;
    saving.value = false;
  };

  onMounted(reload);

  const events = computed(() =>
    filter.value === "all"
      ? all.value
      : all.value.filter((event) => event.room === filter.value),
  );

  return {
    events,
    scheduled: computed(() => events.value.filter((event) => event.day !== null)),
    backlog: computed(() =>
      events.value
        .filter((event) => event.day === null)
        .sort((left, right) => left.position - right.position),
    ),
    rooms: computed(() =>
      [...new Set(all.value.map((event) => event.room).filter(Boolean))].sort(),
    ),
    filter,
    selection,
    error,
    loading,
    saving,
    select: (eventId) => {
      selection.value = eventId;
    },
    setFilter: (room) => {
      filter.value = room;
    },
    schedule: (eventId, day, hour) => persist(moveEvent(eventId, day, hour)),
    unschedule: (eventId) => persist(moveEvent(eventId, null, null)),
    reorder: (eventId, beforeEventId) => persist(reorderEvent(eventId, beforeEventId)),
    reload,
  };
}
