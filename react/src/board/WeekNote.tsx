/**
 * The week note: one object the page and the agent both edit.
 *
 * Everything else on this board is an *operation* — a move, a reorder, a filter.
 * The agent performs those against the page: `set_board` calls back into this app's
 * own writer, in the browser. The week note is not that. It rides AG-UI shared
 * state, so the page sends it with every run, a **server-side** tool rewrites it,
 * and the snapshot streams back — this app re-renders having executed nothing.
 *
 * The tool call is still visible in the transcript and could still be gated; that
 * is not the difference. The difference is who holds the value and who changes it,
 * which is why this fits a document the two are co-editing and `registerPageState`
 * fits an operation one of them performs.
 */

export interface WeekNoteProps {
  note: string;
  onEdit: (note: string) => void;
}

export function WeekNote({ note, onEdit }: WeekNoteProps) {
  return (
    <section className="week-note" aria-label="Week note">
      <h2 className="week-note-title">Week note</h2>
      <textarea
        id="week-note"
        className="week-note-body"
        value={note}
        placeholder="Yours and the agent's. Try: note: ship the gallery this week"
        onChange={(event) => onEdit(event.target.value)}
      />
      <p className="week-note-hint">
        Shared state, not a tool call — ask the agent to <em>summarise the week into the note</em>.
      </p>
    </section>
  );
}
