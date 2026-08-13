/**
 * The board's state, and the two mutations the page can perform.
 *
 * A drop persists immediately — which is what makes the agent's `drag_and_drop`
 * a durable action rather than a cosmetic one, and why the chat element gates it
 * behind a confirmation card.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { type EventRow, listEvents, moveEvent, reorderEvent } from "../api";

export type RoomFilter = "all" | string;

export interface BoardState {
  events: EventRow[];
  scheduled: EventRow[];
  backlog: EventRow[];
  rooms: string[];
  filter: RoomFilter;
  selection: number | null;
  error: string | null;
  loading: boolean;
  /**
   * True while a move is being saved. It is reported in the page map on purpose:
   * a page action returns as soon as it has dispatched the DOM event, so an
   * agent that reads the page straight afterwards can outrun the page's own
   * save and conclude that nothing happened. A page that says when it is busy is
   * a page an agent can wait for.
   */
  saving: boolean;
  setFilter: (room: RoomFilter) => void;
  select: (eventId: number | null) => void;
  schedule: (eventId: number, day: string, hour: number) => Promise<void>;
  unschedule: (eventId: number) => Promise<void>;
  reorder: (eventId: number, beforeEventId: number | null) => Promise<void>;
  reload: () => Promise<void>;
}

export function useBoard(): BoardState {
  const [events, setEvents] = useState<EventRow[]>([]);
  const [filter, setFilter] = useState<RoomFilter>("all");
  const [selection, select] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const reload = useCallback(async () => {
    try {
      setEvents(await listEvents());
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const persist = useCallback(
    async (operation: Promise<EventRow>) => {
      let refusal: string | null = null;
      setSaving(true);
      try {
        await operation;
      } catch (cause) {
        // The move was refused — a slot already taken, most likely. The page has
        // to say so itself: the agent's drag tool reports only that it dispatched
        // the drag, so this banner is how the refusal becomes visible.
        refusal = cause instanceof Error ? cause.message : String(cause);
      }
      // Reload first, then report: a reload clears the banner on success, so
      // setting the message before it would wipe out the very thing we want to
      // show.
      await reload();
      setError(refusal);
      setSaving(false);
    },
    [reload],
  );

  const filtered = useMemo(
    () => (filter === "all" ? events : events.filter((event) => event.room === filter)),
    [events, filter],
  );

  return {
    events: filtered,
    scheduled: filtered.filter((event) => event.day !== null),
    backlog: filtered
      .filter((event) => event.day === null)
      .sort((left, right) => left.position - right.position),
    rooms: [...new Set(events.map((event) => event.room).filter(Boolean))].sort(),
    filter,
    selection,
    error,
    loading,
    saving,
    setFilter,
    select,
    schedule: (eventId, day, hour) => persist(moveEvent(eventId, day, hour)),
    unschedule: (eventId) => persist(moveEvent(eventId, null, null)),
    reorder: (eventId, beforeEventId) => persist(reorderEvent(eventId, beforeEventId)),
    reload,
  };
}
