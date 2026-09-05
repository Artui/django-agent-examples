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
| `board/admin.py` | An ordinary `ModelAdmin`; the agent drives admin's own DOM. |
| `demo/demo_login.py` | A demo-only one-click sign-in, so no password is typed anywhere. |
| `agent/tools.py` | Server-side tools that are not board operations. |
| `agent/scripted.py` | The offline model. |
| `agent/transcribe.py` | The offline speech-to-text, on the same terms. |
| `agent/auth.py` | Who is acting, on the agent endpoint. |

## Endpoints

| Route | What it is |
| --- | --- |
| `GET /api/events/` | The acting user's board. |
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
| `GET /demo-login/` | Demo only, DEBUG only: signs the seeded user in. |

## One declaration, two transports

`board/specs.py` builds a `SpecRegistry` and nothing else reads the specs
directly. The viewset takes its `action_specs` from it, and
`AGUIServer(service_specs=registry)` projects the same objects into agent tools.
A fifth operation added there appears on both surfaces at once, which is the
property the split exists for.

Two consequences worth knowing:

- **Every spec sets `permission_classes`.** Off HTTP there is no viewset and no
  `DEFAULT_PERMISSION_CLASSES` to inherit, so an unset one would be callable by
  whatever the model decided to call. `AGUIServer` refuses to start on a spec
  that leaves it unset, which is the behaviour you want to meet at deploy time.
- **A service's docstring is the tool description.** The spec toolset warns at
  startup about an operation without one, because a model picks tools almost
  entirely by description.

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

Under the agent, a refusal comes back as a tool return carrying
`{"error": "..."}` with `outcome == "success"`, because AG-UI's
`TOOL_CALL_RESULT` has no field to say otherwise. An answer therefore has to
read the *shape* of what came back rather than trust the outcome -- which is
what `_import_verdict` and the single-booking path in `agent/scripted.py` both
do, and what the chat card in the corner still cannot show you.

## Tests

```bash
uv run pytest
```

They drive the real endpoints the way a client does — a token in a header, a
`RunAgentInput` body, SSE parsed off the wire — including the multi-round tool
loop, the declined confirmation, and the verification read that waits for a page
that is still saving.
