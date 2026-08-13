/**
 * This app is the gallery's localized one, in German.
 *
 * Two halves, and the point is that they are separate. `BOARD` is this app's own
 * chrome, translated the way any app translates itself. `CHAT` is the component's
 * `UiStrings` — its buttons, its placeholders, the sentence it uses when a tool
 * call is declined — which no host CSS or slot can reach, because they are text
 * the component composes at runtime. It takes them from the `strings` property (or
 * a `data-strings` JSON attribute), merged over its English defaults.
 *
 * Only the keys that appear are overridden, so a partial map is legitimate: the
 * rest stay English rather than becoming blank, which is what a missing key in a
 * component's own catalogue usually costs. That also makes this file safe to leave
 * behind when the component adds a string.
 *
 * Not an i18n framework, deliberately. A real app reaches for its framework's
 * own — `@angular/localize`, `vue-i18n`, `svelte-i18n` — and the only thing that
 * changes is where these values come from. What the gallery has to show is the
 * seam into the shadow DOM, and that seam is one object either way.
 */

/** The board's own visible text. */
export const BOARD = {
  title: "Terminplan",
  week: "Wochenraster",
  day: "Tagesspalte",
  agenda: "Terminliste",
  room: "Raum",
  allRooms: "alle",
  backlog: "Sammlung",
  backlogHint: "Karte hier ablegen, um sie aus der Woche zu nehmen.",
  unscheduled: "ohne Termin",
  assistant: "Terminassistent",
} as const;

/**
 * The component's own strings. Keys are `UiStrings`; anything omitted keeps the
 * English default.
 */
export const CHAT: Record<string, string> = {
  inputPlaceholder: "Frag mich etwas...",
  answerPlaceholder: "Antwort...",
  send: "Senden",
  stop: "Anhalten",
  newChat: "Neues Gespräch",
  chatHistory: "Verlauf",
  checkpoints: "Lauf fortsetzen",
  noCheckpoints: "Noch nichts fortzusetzen.",
  resumeRun: "Fortsetzen",
  forkRun: "Verzweigen",
  forkedRun: "verzweigt",
  justNow: "gerade eben",
  minutesAgo: "vor {n} Min.",
  hoursAgo: "vor {n} Std.",
  daysAgo: "vor {n} Tagen",
  collapse: "Einklappen",
  expand: "Ausklappen",
  confirmRun: "Auf dem Plan verschieben? Die Änderung wird sofort gespeichert.",
  confirm: "Verschieben",
  cancel: "Abbrechen",
  declinedAction: "Vom Benutzer abgelehnt.",
  approvalPrompt: "Diese Aktion ausführen?",
  approve: "Genehmigen",
  deny: "Ablehnen",
  askUserAction: "Frage",
  submit: "Absenden",
  otherOption: "Andere...",
  attachFiles: "Datei anhängen",
  recordVoice: "Sprachaufnahme",
  resizePanel: "Größe ändern",
  details: "Details",
  thinking: "Denkt nach",
  toolRunning: "läuft...",
  connectionLost: "Verbindung verloren.",
  skillNeeds: "„{title}“ braucht {fields} — unten ausfüllen und senden.",
};
