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
- *scroll to Friday 17:00*
- *switch to the agenda view*
- *put the onboarding doc first in the backlog*
- *show only the Basalt room*

## What the gallery demonstrates

| Interaction | How |
| --- | --- |
| Scroll a target into view, vertically | built-in `scroll_to` plus the page map |
| Scroll a target into view, horizontally | the same call, two-axis scroll container |
| Move an event to a new slot | built-in `drag_and_drop`, the page's own drop handler saves |
| Reorder within a list | the same call, list drop targets |
| Navigate between views | `routeMap` plus the host's `navigate` seam |
| Read the board's state | `read_page`, `read_board`, and the server's own `list_events` |
| Gate a saving move behind a confirmation | `confirmPredicate` |

All four apps implement all seven, and every one of them has been driven
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
