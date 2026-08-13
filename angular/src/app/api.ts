/**
 * The board API, as the browser sees it.
 *
 * One token in one header, on every request — the same header the chat element
 * is given, so the board and the agent act as the same principal. The dev server
 * proxies `/api` and `/agent` to Django, so nothing here is cross-origin.
 */

export interface EventRow {
  id: number;
  title: string;
  room: string;
  day: string | null;
  start_hour: number | null;
  duration_hours: number;
  position: number;
  updated_at: string;
}

/** The demo token seeded by `manage.py seed_board`. Not a secret, by design. */
export const DEMO_TOKEN = readToken();

function readToken(): string {
  // Vite exposes build-time env on `import.meta.env`; the Angular CLI does not.
  // Written to compile under both so this file stays identical in every app.
  const meta = import.meta as ImportMeta & { env?: Record<string, string | undefined> };
  return meta.env?.["VITE_DEMO_TOKEN"] ?? "demo-token-not-a-secret";
}

export function authHeaders(): Record<string, string> {
  return { Authorization: `Token ${DEMO_TOKEN}` };
}

export class ApiError extends Error {}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    // A business-rule failure arrives as 422 with the service's own message,
    // which is worth showing verbatim: it is the same sentence the agent gets
    // when it calls the operation as a tool.
    throw new ApiError(readDetail(payload) ?? `${path} failed (${response.status})`);
  }
  return payload as T;
}

function readDetail(payload: unknown): string | null {
  if (payload === null || typeof payload !== "object") {
    return null;
  }
  const record = payload as Record<string, unknown>;
  if (typeof record["detail"] === "string") {
    return record["detail"];
  }
  const first = Object.values(record)[0];
  if (Array.isArray(first) && typeof first[0] === "string") {
    return first[0];
  }
  return typeof first === "string" ? first : null;
}

export async function listEvents(): Promise<EventRow[]> {
  const response = await fetch("/api/events/", { headers: authHeaders() });
  if (!response.ok) {
    throw new ApiError(`Could not load the board (${response.status})`);
  }
  return (await response.json()) as EventRow[];
}

export function moveEvent(
  eventId: number,
  day: string | null,
  startHour: number | null,
): Promise<EventRow> {
  return post<EventRow>("/api/events/move/", {
    event_id: eventId,
    day,
    start_hour: startHour,
  });
}

export function reorderEvent(eventId: number, beforeEventId: number | null): Promise<EventRow> {
  return post<EventRow>("/api/events/reorder/", {
    event_id: eventId,
    before_event_id: beforeEventId,
  });
}
