import type { RouteMap } from "@artooi/ag-ui-web-component";
import { useMemo, useState } from "react";
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { Assistant } from "./assistant/Assistant";
import { WeekNote } from "./board/WeekNote";
import { AgendaView } from "./board/AgendaView";
import { Backlog } from "./board/Backlog";
import { DayView } from "./board/DayView";
import { WeekGrid } from "./board/WeekGrid";
import { isoDate, labelForIso, weekDays } from "./board/calendar";
import { buildPageMap, type ViewName } from "./board/pageMap";
import { useBoard } from "./board/useBoard";

/**
 * The routes the agent may navigate to. Ids are what it addresses; paths are the
 * app's own. Because `navigate` is wired to the router below, switching views
 * never reloads the page and the run loop simply continues.
 */
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

export function App() {
  const board = useBoard();
  // The one piece of page state that is *not* exposed as a tool: it rides AG-UI
  // shared state instead, so the agent and the page hold the same object. See
  // `board/WeekNote.tsx` for why that distinction is the point.
  const [note, setNote] = useState("");
  const location = useLocation();
  const navigate = useNavigate();
  const days = useMemo(() => weekDays(), []);
  const today = useMemo(() => {
    const iso = isoDate(new Date());
    return days.find((day) => day.date === iso) ?? days[0] ?? { date: iso, label: labelForIso(iso) };
  }, [days]);

  const view: ViewName = location.pathname.startsWith("/agenda")
    ? "agenda"
    : location.pathname.startsWith("/day")
      ? "day"
      : "week";
  const visibleDays = view === "day" ? [today] : days;

  return (
    <div className="layout">
      <header className="topbar">
        <h1>Scheduling board</h1>
        <nav>
          {ROUTE_MAP.map((route) => (
            <button
              key={route.id}
              type="button"
              className={view === route.id ? "nav-current" : undefined}
              onClick={() => navigate(route.path)}
            >
              {route.title}
            </button>
          ))}
        </nav>
        <label className="filter">
          Room
          <select value={board.filter} onChange={(event) => board.setFilter(event.target.value)}>
            <option value="all">all</option>
            {board.rooms.map((room) => (
              <option key={room} value={room}>
                {room}
              </option>
            ))}
          </select>
        </label>
      </header>

      {board.error === null ? null : (
        <p className="error" role="alert">
          {board.error}
        </p>
      )}

      <main className="main">
        <div className="board">
          <Routes>
            <Route path="/" element={<Navigate to="/week" replace />} />
            <Route path="/week" element={<WeekGrid days={days} board={board} />} />
            <Route path="/day" element={<DayView day={today} board={board} />} />
            <Route path="/agenda" element={<AgendaView board={board} />} />
          </Routes>
          <Backlog board={board} />
          <WeekNote note={note} onEdit={setNote} />
        </div>

        <Assistant
          routeMap={ROUTE_MAP}
          navigate={(path) => navigate(path)}
          reload={() => void board.reload()}
          note={note}
          onNoteChanged={setNote}
          getPageMap={() =>
            buildPageMap(view, visibleDays, {
              saving: board.saving,
              filter: board.filter,
              selection: board.selection,
              scheduled: board.scheduled,
              backlog: board.backlog,
            })
          }
          // What a templated skill's `{placeholder}`s are filled from. The day
          // view is looking at one day and the week view is not, so the value
          // exists in one and is absent in the other -- and the component
          // refuses to send a prompt with an unfilled hole rather than sending a
          // question about nothing.
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
  );
}
