import { Component, computed, signal } from "@angular/core";
import { Router } from "@angular/router";
import type { RouteMap } from "@artooi/ag-ui-web-component";
import { AssistantComponent } from "./assistant/assistant.component";
import { AgendaComponent } from "./board/agenda.component";
import { BacklogComponent } from "./board/backlog.component";
import { BoardService } from "./board/board.service";
import { isoDate, labelForIso, weekDays } from "./board/calendar";
import { buildPageMap, type ViewName } from "./board/pageMap";
import { WeekGridComponent } from "./board/week-grid.component";

/** The routes the agent may navigate to, matching `app.routes.ts`. */
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

@Component({
  selector: "app-root",
  imports: [WeekGridComponent, BacklogComponent, AgendaComponent, AssistantComponent],
  template: `
    <div class="layout">
      <header class="topbar">
        <h1>Scheduling board</h1>
        <nav>
          @for (entry of routeMap; track entry.id) {
            <button
              type="button"
              [class.nav-current]="view() === entry.id"
              (click)="go(entry.path)"
            >
              {{ entry.title }}
            </button>
          }
        </nav>
        <label class="filter">
          Room
          <select [value]="board.filter()" (change)="onFilter($event)">
            <option value="all">all</option>
            @for (room of board.rooms(); track room) {
              <option [value]="room">{{ room }}</option>
            }
          </select>
        </label>
      </header>

      @if (board.error() !== null) {
        <p class="error" role="alert">{{ board.error() }}</p>
      }

      <main class="main">
        <div class="board">
          @if (view() === "agenda") {
            <app-agenda />
          } @else {
            <app-week-grid [days]="visibleDays()" />
          }
          <app-backlog />
        </div>

        <app-assistant
          [routeMap]="routeMap"
          [navigate]="navigate"
          [reload]="reloadBoard"
          [getPageMap]="pageMap"
          [skillContext]="skillContext"
          [readBoardState]="readBoardState"
          [writeBoardState]="writeBoardState"
        />
      </main>
    </div>
  `,
})
export class App {
  readonly routeMap = ROUTE_MAP;
  private readonly path = signal(window.location.pathname);

  readonly view = computed<ViewName>(() => {
    const path = this.path();
    return path.startsWith("/agenda") ? "agenda" : path.startsWith("/day") ? "day" : "week";
  });

  private readonly days = weekDays();
  private readonly today =
    this.days.find((day) => day.date === isoDate(new Date())) ??
    this.days[0] ?? { date: isoDate(new Date()), label: labelForIso(isoDate(new Date())) };

  readonly visibleDays = computed(() => (this.view() === "day" ? [this.today] : this.days));

  constructor(
    readonly board: BoardService,
    private readonly router: Router,
  ) {
    void this.board.reload();
    // The URL is the source of truth for the view; the agent changes it through
    // `navigate`, exactly as the buttons do.
    this.router.events.subscribe(() => {
      this.path.set(window.location.pathname);
    });
  }

  /** Passed to the assistant: the single seam that makes this host a single-page app. */
  readonly reloadBoard = (): void => {
    void this.board.reload();
  };

  readonly navigate = (path: string): void => {
    void this.router.navigateByUrl(path);
  };

  readonly pageMap = () => buildPageMap(this.view(), this.visibleDays(), this.board.snapshot());

  // What a templated skill's placeholders are filled from: the day view has a day
  // and the week view does not, so the component blocks rather than sending a
  // question with a hole in it.
  readonly skillContext = () => (this.view() === "day" ? { day: this.today.label } : {});

  readonly readBoardState = () => ({
    view: this.view(),
    filter: this.board.filter(),
    selection: this.board.selection(),
    scheduled: this.board.scheduled().length,
    backlog: this.board.backlog().length,
  });

  readonly writeBoardState = (patch: Record<string, unknown>) => {
    if (typeof patch["room"] === "string") {
      this.board.setFilter(patch["room"]);
    }
    if (patch["selection"] === null || typeof patch["selection"] === "number") {
      this.board.select(patch["selection"] as number | null);
    }
    return { ok: true };
  };

  go(path: string): void {
    this.navigate(path);
  }

  onFilter(changeEvent: Event): void {
    this.board.setFilter((changeEvent.target as HTMLSelectElement).value);
  }
}
