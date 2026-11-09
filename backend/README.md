# The gallery's shared backend

One Django project serving every app in the gallery: a board API, an AG-UI agent
endpoint, and a scripted model so none of it needs an account anywhere.

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py seed_board
uv run uvicorn demo.asgi:application --port 8000
```

ASGI is not optional — the agent endpoint streams.

## What is where

| File | What it holds |
| --- | --- |
| `board/models.py` | One model. An event is either in a grid cell or in the backlog. |
| `board/services.py` | The write side: plain callables, plus the state rule that guards both writes. |
| `board/selectors.py` | The read side. |
| `board/serializers.py` | Input dataclasses and the output serializer. |
| `board/specs.py` | The four operations, declared once, in a `SpecRegistry`. |
| `board/views.py` | HTTP routes over those same specs. |
| `agent/server.py` | The `AGUIServer` every single-page app points at. |
| `agent/admin_server.py` | The `AdminAgentServer` the admin sidebar points at. |
| `agent/mcp_server.py` | Two board operations served by an MCP server, and an agent that reaches them. |
| `board/admin.py` | An ordinary `ModelAdmin`; the agent drives admin's own DOM. |
| `demo/demo_login.py` | A demo-only one-click sign-in, so no password is typed anywhere. |
| `agent/delegation.py` | The planner sub-agent, and the capability both agent mounts delegate to it with. |
| `agent/tools.py` | Server-side tools that are not board operations. |
| `agent/scripted.py` | The offline model. |
| `agent/transcribe.py` | The offline speech-to-text, on the same terms. |
| `agent/auth.py` | Who is acting, on the agent endpoint. |

## Endpoints

| Route | What it is |
| --- | --- |
| `GET /api/events/` | The acting user's board; `?fields=title,day` narrows each row. |
| `POST /api/events/move/` | Schedule or unschedule an event. |
| `POST /api/events/reorder/` | Reorder the backlog. |
| `POST /api/events/` | Create an event. |
| `POST /agent/` | The AG-UI run endpoint. |
| `GET /agent/tools/` | Tool label catalog, for the chat element's cards. |
| `GET /agent/skills/` | Skill catalog, for the prompt chips. |
| `GET /agent/threads/` | Thread index, for the history drawer. |
| `POST /agent/attachments/` | Upload a file; answers with a ref, never the bytes. |
| `GET /agent/attachments/<id>/` | Download one, owner-checked. |
| `GET /agent/runs/` | Which runs have a snapshot, for the ⭯ checkpoint panel. |
| `POST /agent/resume/<id>/` | A new run seeded from that run's snapshot. |
| `POST /agent/fork/<id>/` | The same mechanism, under the verb that says why. |
| `POST /agent/transcribe/` | A clip in, a transcript out; scripted, so no provider. |
| `/admin/` | The board through `django.contrib.admin`, with the agent in its chrome. |
| `POST /admin-agent/` | The admin's own AG-UI endpoint: session principal, CSRF on. |
| `POST /mcp-agent/` | An AG-UI endpoint whose tools come from an MCP server, not the specs. |
| `GET /mcp-agent/tools/` | Its label catalog, read off the server's registrations. |
| `GET /demo-login/` | Demo only, DEBUG only: signs the seeded user in. |

## One declaration, two transports

`board/specs.py` builds a `SpecRegistry` and nothing else reads the specs
directly. The viewset takes its `action_specs` from it, and
`AGUIServer(service_specs=registry)` projects the same objects into agent tools.
A fifth operation added there appears on both surfaces at once, which is the
property the split exists for.

Two consequences worth knowing:

- **Every spec sets `permissions`.** The board's are DRF permission classes in a
  `DRFPermissionCheck`. Off HTTP there is no viewset and no
  `DEFAULT_PERMISSION_CLASSES` to inherit, so an unset one would be callable by
  whatever the model decided to call. The `SpecRegistry` refuses to register a
  spec that leaves it unset, so `board/specs.py` fails at import, which is the
  behaviour you want to meet at deploy time.
- **A service's docstring is the tool description.** The spec toolset warns at
  startup about an operation without one, because a model picks tools almost
  entirely by description.

A read-shaping argument is declared there too. `list_events` declares a `fields`
parameter in its spec's `shapes`, because over HTTP the query string supplies
`?fields=` and under the agent nothing does: the transport advertises it on the
tool, and the presenter hands the call's shapes to the serializer as the query
string of the request it renders under, so `SelectableEventSerializer` reads it
from `request.query_params` on either transport. A name no event has is
refused by the serializer in its own words -- a `400` over HTTP, and under the
agent a retry that also says the selection applies to each item in `items`, never
to the page around them. *just the titles on the board* shows that retry: the
scripted model aims its first selection at the page, on purpose, and corrects it.

## A model, or not

`agent/model.py` decides. With `DEMO_MODEL` unset you get `agent/scripted.py`: a
`FunctionModel` that routes a handful of phrasings to the tool sequence they
imply. It is not pretending to be an LLM — it exists so the gallery runs offline,
in CI, and on a machine with no API key.

```bash
DEMO_MODEL=anthropic:claude-sonnet-4.6 ANTHROPIC_API_KEY=... uv run uvicorn demo.asgi:application
```

With a real model, the provider's extra has to be installed
(`uv add "pydantic-ai-slim[anthropic]"`). Nothing else changes: the tools,
instructions, permissions and stores are the same.

Two things in the scripted model are worth copying into a real system prompt
rather than treated as scaffolding. It **reads the page before acting**, so it
addresses ids the page reported rather than ones it invented. And after driving
the page it **reads the page again before reporting**, because a page action
returns as soon as the DOM event is dispatched — a refused move otherwise gets
announced as a success.

## Authentication, and what it is standing in for

The frontends send `Authorization: Token <key>`, seeded by `seed_board` as a
deliberately fake token. DRF authenticates its own routes. The AG-UI views are
plain Django views, so DRF's authentication classes do not reach them: the
endpoint takes a `get_user` hook instead (`agent/auth.py`), which resolves the
same header. One credential, two layers, no cookie anywhere.

Because no cookie is involved, CSRF does not apply and the endpoint's default
exemption is correct here. **A deployment that authenticates with session cookies
must pass `csrf_exempt=False`** and send the token from the client, or any
third-party page can drive the agent as the logged-in user.

The demo user owns every row it can see: `list_events` filters on `owner=user`
and `owned_event` resolves an id against its owner rather than against the id
alone. That is the only thing standing between two users' boards, on both
transports.

## Two mounts, two auth models

`agent/server.py` and `agent/admin_server.py` are the same class underneath and
differ where the deployment differs. The single-page apps send a token in a header:
no cookie, so CSRF does not apply and the endpoint's default exemption is right.
The admin authenticates with a session cookie, so `csrf_exempt=False` is mandatory
there — without it any third-party page could drive the admin as the signed-in
staff user. Neither mount knows about the other, which is what makes running both
in one project a useful thing to look at.

Static files are the admin's other requirement, and the reason `demo/urls.py` adds
`staticfiles_urlpatterns()`: the agent endpoint streams, so this runs under an ASGI
server, and a bare ASGI server serves no static files. The component's bundle is a
static file, so without that the sidebar is simply absent.

## The other route: an MCP server

`agent/mcp_server.py` reaches the board a second way. It builds a django-spec-mcp
`MCPServer`, registers two operations on it, and hands it to
`AGUIServer(mcp_server=...)` with no `service_specs=`. The bridge then calls the
server's own `tools/list` and `tools/call` in process, as the user the endpoint
resolved, so the schemas, argument checks and permission answers are the ones an
MCP client would get, with no network hop. The server is not mounted over HTTP:
authorizing an outside MCP client is the deployment's job.

An MCP server registers a kernel spec, so the two operations are declared there
the kernel's way over the same `board/selectors.py` and `board/services.py`
functions, not taken from `board/specs.py`, whose specs put DRF in their seats.
The functions, and what they import, are shared; the specs, validator,
presenters and permission checks here are the kernel's own, so the server is
handed nothing DRF-shaped. A blank title is the one
input rule the dataclass does not state, so `title_is_set` adds it there, and
a blank title is refused on every route.

The two routes stream a call the same way, by design. They differ in three
places, and `tests/test_mcp_bridge.py` holds each over the wire:

- **The labels.** The catalog at `/mcp-agent/tools/` carries the `title` and
  `description` the server registered, where `/agent/tools/` carries a
  prettified name and the service's docstring.
- **The gate.** The mount names no tool in `require_approval`. The bridge marks
  `create_event` destructive from the annotations the server lists, and the tool
  guard defers it on that alone.
- **The refusals.** A taken slot is a failed call the model reads, as on the
  board mount. A user without `board.add_event` is answered `-32006`, which the
  bridge raises as Django's `PermissionDenied`: the run ends on `RUN_ERROR`, the
  model is never asked to answer it, and the reason goes to the audit log.
  The server lists a user only the tools their permissions allow
  (`filter_listings_by_permissions`), and `create_event` is registered
  `always_listed=True` so that second refusal is reachable at all; without it
  `tools/list` hides the write from that user.

No frontend selects this mount; a client sees it by setting the chat element's
`endpoint` to `/mcp-agent/` and its `data-tools-url` to `/mcp-agent/tools/`.

## Delegating to a sub-agent

The board mount and the admin mount can each hand one question to a second agent,
the **planner**, which finds the free hours on a day of the board. Ask either one
*ask the planner when Friday is free*.

The planner runs in a run of its own: its own model, its one `free_hours` tool,
and none of the conversation that asked. pydantic-ai-harness's `SubAgents` gives
the parent the `delegate_task` tool that starts it; django-ag-ui's
`SubAgentObserver`, wrapped around that capability, is what tells the browser.
Without the wrapper the hand-off still works and the chat shows a
`delegate_task` card that waits silently until the answer arrives. With it the
stream carries, inside that one tool call:

| Event | What it says |
| --- | --- |
| `SUBAGENT_STARTED` | The planner is working, on the card whose `toolCallId` is its `parentToolCallId`. |
| `CUSTOM` `ag_ui.subagent` | One per tool call the planner makes, and one per result. |
| `SUBAGENT_FINISHED` | The planner is done; its answer is the call's `TOOL_CALL_RESULT`. |

The web component draws all three onto the card it already drew, with no setting
on the page. Under its default step-group display that card is one click down,
in the row the run's tool calls fold into. The admin sidebar draws the opened
call as a compact row: the planner's steps stay on it, and its arguments and
result are one click further. All four apps and the admin sidebar have been
driven to it in a browser.
`tests/test_delegation.py` reads them off both mounts' streams.

## Errors

Business-rule failures raise `ServiceError` (or `ServiceValidationError`), never a
DRF exception. The *member* says what kind of failure it is, and every transport
gets the distinction: `ServiceConflict` is a `409` and `ServiceNotFound` a `404`
over HTTP, and a readable tool error under the agent. A DRF `APIException` would
be correct over HTTP and an unhandled failure everywhere else.

This paragraph used to say that every non-validation service error maps to `422`
and that a `status_code` attribute on a subclass has no effect. That was true
when this gallery was built and stopped being true in drf-services 0.40.0, which
is where the two members arrived -- see the comment above `SlotTaken` in
`board/services.py`, which records how the change was noticed.

Under the agent, a refusal is a *failed* tool call. The service's
`ServiceConflict` reaches the model as a tool return marked
`outcome == "failed"` and carrying the service's own sentence, and django-ag-ui
forwards that flag onto the `TOOL_CALL_RESULT` the browser receives, under
`metadata`, which is where the web component reads it to settle the card as an
error. Two tests in `tests/test_approval.py` hold both copies of it, off the wire:

- `test_a_board_refusal_reaches_the_browser_marked_failed` books a slot that is
  already taken and asserts that the last `TOOL_CALL_RESULT` in the stream has
  `metadata.outcome == "failed"` and that its content carries the reason
  (`"already held by"`).
- `test_a_board_refusal_is_stored_marked_failed` reads the same conversation
  back through `/agent/threads/<id>/`, the copy a reload replays, and asserts
  the stored tool message carries the same `metadata.outcome`.

An answer therefore reads the flag, not the wording: `_import_verdict` and
`_board_refused` in `agent/scripted.py` both branch on `outcome == "failed"`.
The one refusal with no field is a decline made in the browser, which is an
ordinary successful return whose text says so, and `_refused` still tells that
one apart by its shape.

## Tests

```bash
uv run pytest
```

They drive the real endpoints the way a client does — a token in a header, a
`RunAgentInput` body, SSE parsed off the wire — including the multi-round tool
loop, the declined confirmation, and the verification read that waits for a page
that is still saving.
