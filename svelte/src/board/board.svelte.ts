/**
 * The board's state, in runes.
 *
 * A class with `$state` fields is Svelte 5's answer to a store, and it reads
 * closest to the plain object the other apps in this gallery pass around. The
 * agent cannot tell the difference: the seams it sees are the same functions.
 */

import { type EventRow, listEvents, moveEvent, reorderEvent } from "../api";

export class Board {
  all = $state<EventRow[]>([]);
  filter = $state<string>("all");
  selection = $state<number | null>(null);
  error = $state<string | null>(null);
  loading = $state(true);
  /** True while a move is saving; reported in the page map so an agent can wait. */
  saving = $state(false);

  events = $derived(
    this.filter === "all" ? this.all : this.all.filter((event) => event.room === this.filter),
  );
  scheduled = $derived(this.events.filter((event) => event.day !== null));
  backlog = $derived(
    this.events
      .filter((event) => event.day === null)
      .toSorted((left, right) => left.position - right.position),
  );
  rooms = $derived([...new Set(this.all.map((event) => event.room).filter(Boolean))].toSorted());

  async reload(): Promise<void> {
    try {
      this.all = await listEvents();
      this.error = null;
    } catch (cause) {
      this.error = cause instanceof Error ? cause.message : String(cause);
    } finally {
      this.loading = false;
    }
  }

  async #persist(operation: Promise<EventRow>): Promise<void> {
    let refusal: string | null = null;
    this.saving = true;
    try {
      await operation;
    } catch (cause) {
      refusal = cause instanceof Error ? cause.message : String(cause);
    }
    // Reload first, then report: a reload clears the banner on success.
    await this.reload();
    this.error = refusal;
    this.saving = false;
  }

  select(eventId: number | null): void {
    this.selection = eventId;
  }

  setFilter(room: string): void {
    this.filter = room;
  }

  schedule(eventId: number, day: string, hour: number): Promise<void> {
    return this.#persist(moveEvent(eventId, day, hour));
  }

  unschedule(eventId: number): Promise<void> {
    return this.#persist(moveEvent(eventId, null, null));
  }

  reorder(eventId: number, beforeEventId: number | null): Promise<void> {
    return this.#persist(reorderEvent(eventId, beforeEventId));
  }

  snapshot() {
    return {
      saving: this.saving,
      filter: this.filter,
      selection: this.selection,
      scheduled: this.scheduled,
      backlog: this.backlog,
    };
  }
}
