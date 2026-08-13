/**
 * The grid's coordinates, and the element ids that address them.
 *
 * The ids are the contract between the page and the agent: `getPageMap` reports
 * them, `resolvePageTarget` resolves them back to elements, and every tool call
 * the agent makes names one of them. Nothing else in the app needs to know how
 * they are spelled.
 */

export const HOURS: readonly number[] = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18];

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

export interface Day {
  /** ISO date, the value the API speaks. */
  date: string;
  /** What the page calls it, and what the agent matches against. */
  label: string;
}

export function isoDate(value: Date): string {
  const month = `${value.getMonth() + 1}`.padStart(2, "0");
  const day = `${value.getDate()}`.padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}

export function mondayOfThisWeek(today = new Date()): Date {
  const monday = new Date(today);
  // getDay() is Sunday-first; the board is Monday-first.
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7));
  monday.setHours(0, 0, 0, 0);
  return monday;
}

export function weekDays(from = mondayOfThisWeek(), count = 5): Day[] {
  return Array.from({ length: count }, (_, offset) => {
    const date = new Date(from);
    date.setDate(from.getDate() + offset);
    return { date: isoDate(date), label: dayLabel(date) };
  });
}

export function dayLabel(date: Date): string {
  const weekday = WEEKDAY_LABELS[(date.getDay() + 6) % 7] ?? "";
  return `${weekday} ${date.getDate()}`;
}

export function labelForIso(iso: string): string {
  return dayLabel(new Date(`${iso}T00:00:00`));
}

export function eventElementId(eventId: number): string {
  return `event-${eventId}`;
}

export function slotElementId(day: string, hour: number): string {
  return `slot-${day}-${hour}`;
}

export function dayElementId(day: string): string {
  return `day-${day}`;
}

export function parseEventElementId(elementId: string): number | null {
  const match = /^event-(\d+)$/.exec(elementId);
  return match?.[1] === undefined ? null : Number(match[1]);
}

export function parseSlotElementId(elementId: string): { day: string; hour: number } | null {
  const match = /^slot-(\d{4}-\d{2}-\d{2})-(\d{1,2})$/.exec(elementId);
  if (match?.[1] === undefined || match[2] === undefined) {
    return null;
  }
  return { day: match[1], hour: Number(match[2]) };
}

export function formatHour(hour: number): string {
  return `${`${hour}`.padStart(2, "0")}:00`;
}
