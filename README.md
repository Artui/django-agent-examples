# Framework integration gallery

One demo app, built once per frontend framework, against one shared Django
backend: a **scheduling board** the user can drag around and the agent can drive.
The point is not the board. The point is that the same
[`<ag-ui-chat>`](https://github.com/Artui/ag-ui-web-component) element, the same
AG-UI endpoint, and the same service specs work inside each framework's own
idioms, and that you can watch an agent scroll, drag, navigate and read a real
host page.

Every package here is installed **from PyPI and npm**, the way a stranger would
install it. Nothing is linked to a local checkout.

| Directory | What it is | Port |
| --- | --- | --- |
| [`backend/`](backend/) | The shared Django backend: board API, two agent mounts, the admin, an offline model | 8000 |
| [`react/`](react/) | React 19, Vite, React Router | 5173 |
| [`vue/`](vue/) | Vue 3 (`<script setup>`), Vite, Vue Router | 5174 |
| [`svelte/`](svelte/) | Svelte 5 runes, Vite, a twenty-line router | 5175 |
| [`angular/`](angular/) | Angular 22, standalone components, signals, zoneless | 4200 |

There is a fifth surface with no directory of its own: **the Django admin**, served
by the same backend at `/admin/`. It is the one place in this gallery where the
pages are server-rendered, the principal is a session, the component arrives as a
vendored bundle instead of an npm dependency, and every navigation is a real page
reload. See [The admin surface](#the-admin-surface).

## Quick start

Two terminals. The backend first:

```bash
cd backend && uv sync && uv run python manage.py migrate && uv run python manage.py seed_board && uv run uvicorn demo.asgi:application --port 8000
```

Then any of the apps — they are interchangeable, and all four talk to that one
backend:

```bash
cd react && pnpm install && pnpm dev
```

Open <http://localhost:5173> for the React app, or
<http://localhost:8000/demo-login/> for the admin surface (that URL signs the demo
user in; it works only while `DEBUG` is on, and it exists so the gallery needs no
password typed anywhere). No API key, no account, no model provider: the
backend answers with a scripted local model unless you tell it otherwise (see
[backend/README.md](backend/README.md#a-model-or-not)).

Ask the assistant:

- *what is on the board?*
- *move standup to Friday at 11:00*
- *book a design sync on Friday at 14:00*
- *scroll to Friday 17:00*
- *switch to the agenda view*
- *put the onboarding doc first in the backlog*
- *show only the Basalt room*
- *move standup to Friday* — a day and no hour, so it asks which slot

Or press the **What is on this day?** chip. In the day view it sends *What is on
Thu 13?*, because the page filled the day in; in the week view it refuses to send
and says which value is missing.

Or attach [`samples/week.csv`](samples/week.csv) with the clip in the composer and
say *import these events*. The file uploads out of band, the agent reads it
server-side, and each row it finds asks before it is written — so that one sentence
also shows what a batch of gated writes looks like.

## What the gallery demonstrates

| Interaction | How |
| --- | --- |
| Scroll a target into view, vertically | built-in `scroll_to` plus the page map |
| Scroll a target into view, horizontally | the same call, two-axis scroll container |
| Move an event to a new slot | built-in `drag_and_drop`, the page's own drop handler saves |
| Reorder within a list | the same call, list drop targets |
| Navigate between views | `routeMap` plus the host's `navigate` seam |
| Read the board's state | `read_page`, `read_board`, and the server's own `list_events` |
| Gate a saving move behind a confirmation | `confirmPredicate`, in the browser |
| Gate a server-side write behind an approval | the agent's own tool guard, over the wire |
| Refetch after a write the page did not make | the component's `ag-ui-run-finished` event |
| Co-edit one object with the agent | AG-UI shared state, in the React app's week note |
| Read a file the user attached | `attachment_store=` and the composer's `data-attachments-url` |
| Ask the user a question mid-run | `askUser`, the component's built-in `ask_user` frontend tool |
| Resume or fork a past run | `step_store=` and the ⭯ panel's `data-runs-url` |
| Launch a prompt the page completes | a skill with a `{placeholder}`, filled from `skillContext` |
| Make the widget look like the host | four different mechanisms, one per app (below) |
| Run the whole thing in another language | the component's `strings`, in the Svelte app |
| Dictate instead of typing | `transcription_backend=` and the composer's `data-transcribe-url` |

All four apps implement the first nine, and every one of them has been driven
agent-side in a browser rather than only compiled. The admin surface adds two more
that no single-page app can show — filling a form field and saving it, across full
page reloads. An interaction that needs a *new* built-in tool belongs upstream in
the web component, not here.

## What each framework taught us

The board copies across cleanly. What does not is the one boundary that matters:
several of the element's inputs are read once, while it connects, and the thread
history is fetched at that same moment. Each framework reaches that window
differently — and only one of them reaches it declaratively.

| App | Pre-insertion window | What it does |
| --- | --- | --- |
| React | None; refs attach after insertion | `createElement`, configure, `appendChild` |
| **Vue** | **Yes** — a directive's `beforeMount` | Attributes in the template, properties in the directive |
| Svelte | None; `use:` actions and `$effect` run after insertion | Same as React |
| Angular | None; bindings apply during change detection | Same as React, in `ngOnInit` with `@ViewChild({static: true})` |

Each app's README has the worked version, plus that framework's own surprise —
Vue's `isCustomElement`, Angular's `:host { display: contents }`, Svelte's runes.
The fallback in every framework is `element.reload()` once configuration lands.

## Four ways to make it look like yours

The widget is a shadow DOM, which is a wall with named doors in it. Each app opens a
different one, so the four together are the whole surface rather than one recipe
copied four times.

| App | Mechanism | Reaches | Cannot reach |
| --- | --- | --- | --- |
| [React](react/) | `--ag-ui-*` custom properties | any colour, radius or font the component parameterised — and they inherit, so dark mode comes free | anything it did not parameterise |
| [Vue](vue/) | `::part()` | any element the component named, structurally: the header is a plain bar and the bubbles are square | elements without a part; names are looked up, and a wrong one fails silently |
| [Angular](angular/) | named slots | *content* — this app projects its own SVG icons into the header buttons | layout, which is the shadow root's |
| [Svelte](svelte/) | `strings` | every word the component composes at runtime, in German | text the **server** sends: skills, tool labels, what the model says |

The last row is the one worth reading twice. Localizing the component does not
localize the conversation: the Svelte app's chips still read *Tidy up my week*
because that catalog comes from `/agent/skills/`, and localizing it is the server's
job, per request. `strings` covers what the component says about itself.

## The admin surface

`http://localhost:8000/admin/` is the same board through `django.contrib.admin`,
with [django-admin-agent](https://github.com/Artui/django-admin-agent) putting the
assistant in the admin chrome. It is in the gallery because it is *different from
the other four in every way that matters*, not because it is another framework:

| | The four apps | The admin |
| --- | --- | --- |
| Pages | One, client-routed | Many, server-rendered |
| Principal | A token in a header | A session cookie |
| CSRF | Does not apply (no cookie) | Applies, so `csrf_exempt=False` |
| The component | An npm dependency you bundle | A vendored bundle served as a static file |
| Navigation | `navigate` keeps the run in memory | A real reload, so the run is checkpointed and resumed |
| Tools | The board's own page actions | Admin-aware ORM and DOM tools |

Ask it:

- *how many events are there?* — answered server-side from the ORM
- *open the events list* — a navigating tool, completed from the page it lands on
- *rename Retro to Sprint retro* — find the row, open its form, type into the
  field, save: four tools across two full page reloads, with a confirmation at
  each write

**Serving static files is not optional, and a bare ASGI server does not.** The
agent endpoint streams, so the project runs under uvicorn; `runserver` would serve
static files but cannot stream. The component's bundle *is* a static file, so a
project that follows only the "deploy under ASGI" half gets an admin with no agent
in it and no error to explain why. This backend adds
`staticfiles_urlpatterns()` (DEBUG only) to close the gap; a real deployment uses
`collectstatic` behind a web server, or WhiteNoise.

## How the pieces fit

**One spec set, two transports.** The board's four operations are declared once
in `backend/board/specs.py` as `ServiceSpec` / `SelectorSpec` objects in a
`SpecRegistry`. The DRF viewset reads that registry for its HTTP routes, and
`AGUIServer(service_specs=registry)` turns the same objects into agent tools with
no MCP hop in the path. So the drag a user performs and the move an agent
performs end in the same service, with the same permission check and the same
business rules.

**The page is the authority on what exists.** The app reports its addressable
surface — event cards, grid slots, days, the backlog — through `getPageMap`, and
resolves those ids back to elements through `resolvePageTarget`. The agent never
guesses a selector: it reads the page, then names something the page told it
about. Everything else follows from that: a stale id fails cleanly, and the same
agent works against four different DOMs.

**A move is the page's to save.** The built-in `drag_and_drop` fires the native
drag sequence and the app's own drop handler posts the change. That is why the
element gates it behind a confirmation card here, and why the agent reads the page
again afterwards rather than assuming (see the notes below).

## Things that are not obvious

**The board must use native HTML5 drag and drop.** `drag_and_drop` dispatches the
standard sequence — `dragstart`, `dragenter`, `dragover`, `drop`, `dragend` —
with one shared `DataTransfer`. A board built on a pointer-event drag library
(dnd-kit, most "modern" React DnD packages) listens to `pointerdown`/`pointermove`
and will not react at all: the agent's drag becomes a silent no-op. Pick a library
that listens to drag events, or use the native API as these apps do. React's
synthetic `onDrop` does receive the dispatched sequence, including the
`DataTransfer`.

**A refused write says which kind of refusal it is.** The board raises
`ServiceConflict` for a taken slot and `ServiceNotFound` for an event that is absent
*or not yours* — the same answer for both, deliberately, since a 403 on a row you
cannot see confirms that it exists. Over HTTP that is `409` and `404`; under the
agent it is a readable tool error either way. These were plain `ServiceError`
subclasses when this gallery was built, because there was nothing else to raise:
everything non-validation mapped to a fixed `422`. Writing a `status_code` attribute
here, watching the 422 come back, and going to look is what produced the two members
upstream.

**There are two confirmation mechanisms here, and they are not variants of each
other.** `confirmPredicate` gates a *page action* inside the browser: the element
asks before it dispatches, and if you refuse, the server never hears about it. The
agent's tool guard gates a *service tool* inside the run: the call is deferred rather
than executed, the run finishes carrying an interrupt, the component renders the
approval card, and the loop resumes with your answer. Nothing runs until it does,
which is the difference that matters for a write. The board's writes are gated the
second way, per endpoint (`config=`), so the admin mount next door keeps its own
policy.

Two consequences worth knowing before you copy the pattern. A gated call is
invisible to the model — the tool stays in its list and the resumed round looks like
any other round, so gating is a deployment decision rather than something a model has
to be taught. And a *refusal* is a tool return, not an error: a denied approval
carries `outcome == "denied"`, while a cancelled page action is an ordinary
successful result whose text happens to say so. Read the outcome, not the wording.

**A server-side write is invisible to the page that is showing the data**, and
closing that is three lines. Approving a booking writes the row while the board keeps
showing what it fetched on mount, because nothing told it otherwise. That gap is what
produced the component's `ag-ui-run-finished` event (0.24.0), and all four apps now
listen for it:

```js
chat.addEventListener("ag-ui-run-finished", (event) => {
  if (event.detail.tools.some((tool) => tool.side === "server")) void board.reload();
});
```

Only `side === "server"` matters — a client tool ran in the app's own handler, which
already knows what it did.

**Shared state is the other channel, and it is not a substitute.** The React app's
**week note** rides `RunAgentInput.state`: the page sends it with every run, a
server-side tool rewrites it, and the snapshot streams back, so the page re-renders
having executed nothing. `registerPageState` is the opposite arrangement — the agent
calls back into the page's own writer. Ask for *summarise the week into the note* and
you can watch both halves at once: two server tools in **one** request, the second's
argument composed from the first's result, and the note appearing on the page from the
state event rather than from either tool's return value.

Worth being precise about, because it is easy to overstate: the write is still a tool
call, so it still renders a card and could still be gated. What differs is who holds
the value and who changes it.

**A page action reports that it fired, not that it worked.** `drag_and_drop`
returns as soon as it has dispatched the drag. Whether the page's own save
succeeded is invisible to it, so a refused move still looks like a successful tool
call. Two things follow, and both are in these apps: the page reports its own
refusals (the banner), and the agent reads the page again before claiming
anything. Where the truth matters more than the visible action, call the operation
as a server tool instead — `move_event` returns the real error.

**A page that saves asynchronously should say so.** The page map carries a
`saving` flag, because a verification read straight after a drag can outrun the
page's own save and conclude that nothing happened. An agent can wait for a page
that tells it when it is busy; it cannot wait for one that does not.

**`placement="embedded"` fills the box the host gives it — so give it one.** A
grid or flex item defaults to `min-height: auto`, which lets a growing transcript
push the composer off the bottom of the window instead of scrolling inside the
panel. `min-height: 0` plus `overflow: hidden` on the containing element is the
fix, and it belongs to the page.

**`RunAgentInput.context` does not reach the model.** The element can auto-inject
the page map into every run's `context`, but the Pydantic-AI AG-UI adapter does
not read that field, so on this backend it goes nowhere. The `read_page` tool is
the channel that works, and it is the one these apps rely on. Nothing to
configure; just do not expect the injected copy to be visible server-side.

**An attached file never travels on the wire, and the model is told about it in
its instructions.** The composer uploads to `attachments/` and keeps a ref — an
id, a name, a type, a size — which rides the message it sends. The server collects
the refs off the posted messages, renders them as a fenced manifest, and hands
that to the model as *additional run instructions*: not a message, not part of the
prompt, never stored on the thread. The model reaches the content by passing an id
to `read_attachment`, which exists only for that request and only for that user, so
an id the client invents resolves to nothing. Two consequences worth knowing: a
large file costs one upload rather than a payload on every turn, and — because the
manifest is derived from the *messages* — it rides every later turn of the
conversation, which is durable across a reload and therefore not a signal that the
current question is about the file.

**A skill either publishes its prompt or keeps it, and the choice is a real one.**
Two of the three chips carry no prompt text: the client sends the bare `/name`
token and the agent decides what it means, so nothing internal reaches anyone who
can read the catalog — and `/agent/skills/` is a plain GET. The third publishes
*What is on {day}?* on purpose, because it buys something the other kind cannot
have: a placeholder **the page fills in**. The server does not know which day you
are looking at, and the browser does.

`skillContext` is that seam — a callback read at the moment the chip is pressed.
The apps return a day only in the day view, so in the week view the placeholder
cannot be filled, and the component does something better than refusing: it puts
the partly-filled prompt in the composer with `{day}` **selected**, focuses it, and
says which value it wanted. The next keystroke replaces the placeholder. Switching
to the day view is the other fix, which makes the guard something you can drive
rather than read about.

**Voice is one method, and the gallery's is scripted like the model.** The mic posts
a clip to `transcribe/`, the backend answers with text, and the text lands in the
composer — not sent, so you read it first. A `TranscriptionBackend` is a single async
method with no store and no artefact behind it, which is why swapping in a real
provider is one argument on the mount:
`transcription_backend=OpenAITranscriptionBackend()`.

This one maps the clip's **byte length** onto a fixed list of phrases the board
already answers. That keeps it a function of the audio rather than of a counter: the
same recording always transcribes the same way, nothing is held between requests,
and every test stays independent of the order it ran in. A dictated sentence is an
ordinary one from there — it reaches the same approval gate a typed one does.

**Asking a question is a tool call, and a different mechanism from an approval.**
`askUser` offers the agent the component's built-in `ask_user`: the browser runs it,
renders a card, and returns the answer as that call's result. Nothing is configured
server-side and no interrupt is involved — unlike a gated write, where the call is
*deferred* and answered through `resume`. Both look like "the run paused" from the
outside, and only one of them has anything waiting on the server.

Two things this gallery does with it are worth copying. The options are the slots
the **page** reported, so the user is offered what exists rather than a list the
backend guessed at; and the free-text answer goes through the same matcher as the
original request, which is what makes `allow_custom` more than decoration — type a
slot the card never offered and it still resolves. The trigger is *ambiguity*, not
a missing word: "move standup to Friday" names four possible slots, and picking one
silently is the behaviour the question replaced.

**A resumed run is a new run seeded from a snapshot, not a stream you rejoin.** The
⭯ panel lists runs the server says have a snapshot; type the next turn, pick
*Resume* or *Fork*, and the component posts **only that turn** to
`resume/<id>/` — the prior history comes from the snapshot, so sending it again
would duplicate it. The two verbs are one mechanism: both branch a new run with a
fresh id and `parent_run_id` pointing back, so a fork never spends the snapshot it
came from and the source stays continuable. What you do *not* get is stream
resumability: if a connection drops mid-run, those events are gone and the run is
lost — resume is a deliberate action afterwards, not a reconnect.

**Two rough edges in the panel, and neither is the component's fault.** Rows are
labelled with a relative time and nothing else, because that is all the run index
sends — so three runs a minute apart are three identical rows. And they arrive
**oldest first**, while both packages' docs say newest first, which puts the run you
probably want at the bottom. Both are recorded as findings; if you build your own
panel, sort it yourself and do not trust `runs[0]` to be the latest.

**An error after the first byte of a stream is an event, not a status code.** The
run endpoint sends `RUN_STARTED` immediately, which commits the response at `200`.
Everything that can go wrong afterwards — a colliding run id, a model failure —
arrives as `RUN_ERROR` in the stream. A client that checks only `response.ok` will
call those runs successful.

**A batch of gated writes is answered one card at a time, and the cards do not say
which is which.** Importing three rows defers three `create_event` calls, and the
component asks about them in sequence, each card appended below the tool calls
rather than beside the one it gates. The wire lets you answer each one differently
and the demo does exactly that in its tests — but on screen the three questions are
identical, so tell them apart by the order they appear in until the component names
them. Recorded as a finding against the web component.

**Both ends of a two-axis scroll are not centred.** `scroll_to` centres the
target vertically and brings it into view horizontally (`inline: "nearest"`), so
on a wide board the target lands at the near edge rather than the middle. It is in
view, which is the contract.

**Smooth scrolling can be disabled in automation browsers.** If you drive these
apps with an automated browser and `scroll_to` appears to do nothing, check
whether a plain `scrollTo({behavior: "smooth"})` works there at all. Under
`prefers-reduced-motion` the component scrolls instantly instead, which is the
path that always works.

## Conventions across the apps

Each app is expected to:

- install the published `@artooi/ag-ui-web-component`, not a local build;
- proxy `/api` and `/agent` to `127.0.0.1:8000` from its own dev server, so the
  browser sees one origin and CORS stays out of the demo;
- send the demo token in the `Authorization` header, both from its own API calls
  and through the element's `headers`;
- register the same page map, route map and page state, so the agent behaves
  identically no matter which app it is looking at;
- document that framework's custom-element gotcha in its own README.

## Not a package

These are runnable apps, not something you install. The gate is that each one
builds, type-checks and boots against the backend, and that the agent can perform
every interaction in the table. The backend carries a small test suite that drives
the agent endpoint the way a client does; run it with `cd backend && uv run pytest`.
