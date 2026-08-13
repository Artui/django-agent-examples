import type { Day } from "./calendar";
import type { BoardState } from "./useBoard";
import { WeekGrid } from "./WeekGrid";

interface Props {
  day: Day;
  board: BoardState;
}

/** The same grid, one column wide. A route the agent can navigate to. */
export function DayView({ day, board }: Props) {
  return <WeekGrid days={[day]} board={board} />;
}
