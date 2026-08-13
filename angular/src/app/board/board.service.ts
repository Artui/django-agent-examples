/**
 * The board's state, as an injectable with signals.
 *
 * Same contract as the other apps in the gallery: signals instead of `useState`,
 * `computed` instead of `useMemo`. The agent sees the same seams either way.
 */

import { Injectable, computed, signal } from "@angular/core";
import { type EventRow, listEvents, moveEvent, reorderEvent } from "../api";

@Injectable({ providedIn: "root" })
export class BoardService {
  private readonly all = signal<EventRow[]>([]);

  readonly filter = signal<string>("all");
  readonly selection = signal<number | null>(null);
  readonly error = signal<string | null>(null);
  readonly loading = signal(true);
  /** True while a move is saving; reported in the page map so an agent can wait. */
  readonly saving = signal(false);

  readonly events = computed(() => {
    const room = this.filter();
    return room === "all" ? this.all() : this.all().filter((event) => event.room === room);
  });
  readonly scheduled = computed(() => this.events().filter((event) => event.day !== null));
  readonly backlog = computed(() =>
    this.events()
      .filter((event) => event.day === null)
      .sort((left, right) => left.position - right.position),
  );
  readonly rooms = computed(() =>
    [...new Set(this.all().map((event) => event.room).filter(Boolean))].sort(),
  );

  async reload(): Promise<void> {
    try {
      this.all.set(await listEvents());
      this.error.set(null);
    } catch (cause) {
      this.error.set(cause instanceof Error ? cause.message : String(cause));
    } finally {
      this.loading.set(false);
    }
  }

  private async persist(operation: Promise<EventRow>): Promise<void> {
    let refusal: string | null = null;
    this.saving.set(true);
    try {
      await operation;
    } catch (cause) {
      refusal = cause instanceof Error ? cause.message : String(cause);
    }
    // Reload first, then report: a reload clears the banner on success.
    await this.reload();
    this.error.set(refusal);
    this.saving.set(false);
  }

  select(eventId: number | null): void {
    this.selection.set(eventId);
  }

  setFilter(room: string): void {
    this.filter.set(room);
  }

  schedule(eventId: number, day: string, hour: number): Promise<void> {
    return this.persist(moveEvent(eventId, day, hour));
  }

  unschedule(eventId: number): Promise<void> {
    return this.persist(moveEvent(eventId, null, null));
  }

  reorder(eventId: number, beforeEventId: number | null): Promise<void> {
    return this.persist(reorderEvent(eventId, beforeEventId));
  }

  at(day: string, hour: number): EventRow | undefined {
    return this.scheduled().find((event) => event.day === day && event.start_hour === hour);
  }

  snapshot() {
    return {
      saving: this.saving(),
      filter: this.filter(),
      selection: this.selection(),
      scheduled: this.scheduled(),
      backlog: this.backlog(),
    };
  }
}
