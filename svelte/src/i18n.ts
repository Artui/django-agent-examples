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

import type { UiStrings } from "@artooi/agents-web-components";

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
export const CHAT: Partial<UiStrings> = {
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
  // The row a run's consecutive tool calls fold into, which is the component's
  // default display, so it labels every run that calls a tool. `toolStepRepeat`
  // is left out: its "({n})" reads the same in German.
  toolGroupSteps: "{count} Schritte",
  toolGroupWorking: "Arbeitet {count} Schritte ab",
  toolGroupWorked: "{count} Schritte abgearbeitet",
  toolGroupWaiting: "{count} offen",
  toolGroupFailed: "{count} fehlgeschlagen",
  toolGroupDeclined: "{count} abgelehnt",
  // The planner sub-agent's row, on a run that delegates to it.
  subAgentWorking: "Arbeitet...",
  subAgentDelegatedTo: "An {agent} übergeben",
  subAgentFinished: "{agent} ist fertig",
  subAgentFailed: "Der Unteragent ist fehlgeschlagen",
  subAgentSteps: "Schritte des Unteragenten",
  // A delegated task's own conversation: the parent's card from it, and the links between them.
  childReport: "Bericht von {agent}",
  childQuestion: "Frage von {agent}",
  childSessionOpen: "Aufgabe von {agent} öffnen",
  childSessionNeedsYou: "Die Aufgabe von {agent} braucht dich",
  parentThread: "Aus {title}",
  parentThreadUnlisted: "Aus dem Gespräch, das dieses begonnen hat",
  connectionLost: "Verbindung verloren.",
  skillNeeds: "„{title}“ braucht {fields} — unten ausfüllen und senden.",
  // The place chip in the composer, which every app gets from its `routeMap`.
  placeShared: "Der Assistent erfährt, dass du auf {label} bist",
  placeWithheld: "{label} wird mit deiner nächsten Nachricht nicht gesendet",
  placeStopSharing: "Diese Seite nicht mehr teilen",
  placeShareAgain: "Diese Seite wieder teilen",
  // The conversation list's date headings.
  threadsToday: "Heute",
  threadsPreviousWeek: "Letzte 7 Tage",
  threadsOlder: "Älter",
  // Only drawn by a placement that can maximise; this app is `embedded`.
  maximize: "Maximieren",
  restore: "Wiederherstellen",
  thoughtFor: "{seconds} s nachgedacht",
  // A failed run, by the code django-ag-ui sends.
  runErrorTimedOut: "Die Antwort hat zu lange gedauert und wurde abgebrochen.",
  runErrorInterrupted: "Die Antwort wurde unterbrochen, bevor sie fertig war.",
  runErrorFailed: "Die Antwort ist fehlgeschlagen. Versuch es gleich noch einmal.",
  runErrorNewChat: "Neues Gespräch beginnen",
  // The token line under a turn, drawn only where `show-usage` is set.
  usageBoth: "{input} ein · {output} aus (Tokens)",
  usageInput: "{input} ein (Tokens)",
  usageOutput: "{output} aus (Tokens)",
  // The conversation list: its panel, search and rows.
  chats: "Gespräche",
  conversation: "Gespräch",
  closeHistory: "Verlauf schließen",
  backToConversation: "Zurück zum Gespräch",
  searchConversations: "Gespräche durchsuchen",
  noConversations: "Noch keine Gespräche.",
  noMatches: "Kein Gespräch passt dazu.",
  weeksAgo: "vor {n} Wo.",
  rename: "Umbenennen",
  renameConversation: "Gespräch umbenennen",
  delete: "Löschen",
  deleteConversation: "Gespräch löschen",
  deletePrompt: "Löschen?",
  create: "Erstellen",
  save: "Speichern",
  remove: "Entfernen",
  undo: "Rückgängig",
  pause: "Pausieren",
  resume: "Fortsetzen",
  turnOn: "Einschalten",
  turnOff: "Ausschalten",
  moreControls: "Mehr",
  expandUnread: "Ausklappen – {count} ungelesen",
  // The transcript and the message actions this app keeps at their default.
  message: "Nachricht",
  messageActions: "Aktionen zur Nachricht",
  copyMessage: "Nachricht kopieren",
  copyCode: "Kopieren",
  copied: "Kopiert",
  copyFailed: "Kopieren fehlgeschlagen",
  retry: "Wiederholen",
  retryMessage: "Noch einmal versuchen",
  quoteSelection: "Zitieren",
  jumpToLatest: "Zum Neuesten springen",
  suggestions: "Vorgeschlagene Anschlussfragen",
  thoughts: "Gedanken",
  navigating: "Navigiert…",
  stopped: "Angehalten",
  enqueuedMessages: "Während des Laufs hinzugefügt",
  queued: "Wartet auf das Senden",
  removeQueued: "„{text}“ nicht senden",
  usingSkill: "Verwendet den Skill {name}",
  historyCompacted:
    "Frühere Beiträge wurden gekürzt, damit sie ins Kontextfenster passen ({count} entfernt)",
  historyReplaced:
    "Der Server hat den Verlauf dieses Gesprächs ersetzt. Neu laden, um ihn zu sehen.",
  runInterrupted: "Die letzte Antwort ist nicht fertig geworden – die Seite hat sich vorher geändert.",
  notConnected: "Dieser Chat ist mit keinem Agenten verbunden, die Nachricht wurde nicht gesendet.",
  pageMoved:
    "Die Seite hat sich seit dem letzten Lesen geändert. Rufe read_page auf, um die aktuelle Seite zu sehen, und versuche es dann noch einmal.",
  chartUndrawable: "Aus den gesendeten Daten ließ sich kein Diagramm zeichnen, deshalb wurde es entfernt.",
  chatMinimised: "Dieses Fenster minimiert",
  chatMoved: "Dieses Fenster aus dem Weg geschoben",
  // Screen-reader announcements of a run's progress.
  announceResponding: "Der Assistent antwortet",
  announceAnswerReady: "Der Assistent hat geantwortet",
  announceAwaitingDecision: "{count} Aktion wartet auf deine Genehmigung",
  announceFailed: "Die Antwort ist fehlgeschlagen",
  announceStopped: "Antwort angehalten",
  // Tool cards. The English statuses lead with a glyph; these say it in words.
  toolDone: "fertig",
  toolError: "Fehler",
  toolDeclined: "abgelehnt",
  toolInterrupted: "nicht fertig",
  toolDeferred: "wartet auf dich",
  argumentsLabel: "Argumente",
  resultLabel: "Ergebnis",
  errorLabel: "Fehler",
  declinedLabel: "Abgelehnt",
  interruptedLabel: "Nicht fertig",
  callNotFinished:
    "Nicht fertig: Der Lauf endete oder ging weiter, bevor dieser Werkzeugaufruf ein Ergebnis lieferte.",
  // Approvals and confirmations, including the reviewer that clears a call.
  approveAction: "Aktion genehmigen",
  confirmAction: "Aktion bestätigen",
  confirmAlways: "Immer erlauben",
  confirmCheckFailed:
    "Nicht ausgeführt: Die Prüfung, ob diese Aktion eine Bestätigung braucht, ist fehlgeschlagen.",
  approvalEditArgs: "Argumente vor dem Genehmigen bearbeiten",
  approvalArgsInvalid: "Das ist kein gültiges JSON, daher wurde nichts gesendet.",
  approvalArgsNotAnObject: "Die Argumente müssen ein JSON-Objekt sein.",
  decisionApproved: "von dir genehmigt",
  decisionDeclined: "von dir abgelehnt",
  answeredByReviewer: "Von einem Prüfmodell genehmigt",
  // A folded group's count of calls the reviewer cleared, and the model and sources of an answer.
  toolGroupPreApproved: "{count} vorab genehmigt",
  answeredByModel: "Beantwortet von {model}",
  citations: "Quellen ({count})",
  citationDocument: "Dokument",
  // Checkpoints: why a run cannot be continued yet.
  continueNeedsTurn:
    "Schreib zuerst den nächsten Beitrag ins Eingabefeld und wähle dann einen Lauf zum Fortsetzen.",
  continueWhileLoading:
    "Warte, bis das Gespräch geladen ist, und wähle dann einen Lauf zum Fortsetzen.",
  continueWhileRunning:
    "Warte auf die aktuelle Antwort oder halte sie an und wähle dann einen Lauf zum Fortsetzen.",
  // Attachments and voice.
  removeAttachment: "Anhang entfernen",
  retryUpload: "Hochladen wiederholen",
  uploadFailed: "Hochladen fehlgeschlagen",
  attachmentsStillUploading:
    "{n} Datei wird noch hochgeladen – sie wurde nicht mit dieser Nachricht gesendet und bleibt angehängt.",
  fileTypeNotAllowed: "Dateityp nicht erlaubt",
  tooLarge: "Zu groß (max. {size})",
  stopRecording: "Aufnahme beenden",
  transcribing: "Wird transkribiert…",
  transcriptionFailed: "Transkription fehlgeschlagen",
  recordingLimit: "Nach {n} Minuten angehalten – das Aufgenommene wird transkribiert.",
  // The skill editor, which the board mount serves.
  skills: "Skills",
  manageSkills: "Skills verwalten",
  newSkill: "Neuer Skill",
  newSkillTitle: "Neuer Skill",
  editSkillTitle: "Skill bearbeiten",
  noSkills: "Noch keine Skills",
  noSkillsBody:
    "Ein Skill ist eine Anleitung, die du oder der Agent beim Namen aufrufen kann, etwa {example}.",
  draftSkill: "Mit dem Agenten entwerfen",
  writeSkill: "Selbst schreiben",
  skillName: "Name",
  skillNameHint: "Kleinbuchstaben, Wörter mit Bindestrich verbunden. Das tippst du nach /.",
  skillDescription: "Beschreibung",
  skillDescriptionHint:
    "Bis er den Skill lädt, liest der Agent nur diese Zeile, also sag, wann er passt.",
  skillBody: "Anleitung",
  skillBodyHint: "Markdown. Ein Skill gewährt keine Werkzeuge: Freigaben gelten weiter.",
  skillReach: "Wer ihn nutzen kann",
  skillInMenu: "Im /-Menü",
  skillInMenuHint: "Du wählst ihn in der Palette.",
  skillAgentMayLoad: "Der Agent darf ihn selbst laden",
  skillAgentMayLoadHint: "Wenn die Beschreibung zur Anfrage passt.",
  skillUnreachable:
    "Sind beide aus, erreicht niemand diesen Skill. Schalte ihn lieber aus, wenn das gemeint ist.",
  skillOff: "Aus",
  skillSaved: "/{name} gespeichert",
  skillTurnedOn: "/{name} ist wieder an",
  skillTurnedOff: "/{name} ist aus",
  skillsUnavailable: "Die Skills konnten nicht geladen werden.",
  skillSaveFailed: "Der Skill konnte nicht gespeichert werden.",
  // Whose skill a row is: this policy answers `personal` or `shared`.
  "skillScope:personal": "Persönlich",
  "skillScope:shared": "Firma",
};
