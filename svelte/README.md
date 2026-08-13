# Svelte

Svelte 5 with runes, Vite, and a twenty-line router. Same board, same seams, same
backend as the other apps in the gallery.

```bash
pnpm install
pnpm dev        # http://localhost:5175, proxying /api and /agent to :8000
pnpm build      # svelte-check plus a production build
```

The backend must be running first — see [../backend/README.md](../backend/README.md).

## The Svelte interop recipe

**Svelte has no pre-insertion hook, so the element is created by hand.** Both of
the places you would naturally configure it — a `use:` action and an `$effect` —
run *after* the element is in the DOM. Several of its inputs are read once while
it connects (the `data-*` attributes, `headers`), and the thread-history request
goes out at that same moment and is deliberately not deferred. So
`src/assistant/Assistant.svelte` does what the React app does:

```svelte
let host: HTMLDivElement | undefined = $state();

$effect(() => {
  defineAgUiChat();
  const chat = document.createElement("ag-ui-chat") as ChatElement;
  chat.setAttribute("endpoint", "/agent/");
  chat.headers = authHeaders();
  chat.getPageMap = () => getPageMap();
  host!.appendChild(chat);
  return () => chat.remove();
});
```

Of the four frameworks here, **only Vue offers a hook that runs before insertion**
(a directive's `beforeMount`). React, Svelte and Angular all need this shape, or
they need `element.reload()` after configuring — the component's own remedy for
configuration that lands late, at the cost of one extra round of catalog fetches.

**Markup is still an option, with that caveat.** If you would rather write
`<ag-ui-chat>` in the template, do it, configure it in an action, and call
`reload()` at the end of the action.

**Props are captured by reference, so the element sees current state.** The
element is created once inside an `$effect`, and the callbacks it is given close
over the component's props rather than over a snapshot — which is what React
needs a ref for.

## The board

`src/board/` mirrors the other apps: a CSS grid with a bounded, two-axis scroll
container, native `draggable` cards, `ondragover` / `ondrop` handlers, and state in
a `$state` class (`board.svelte.ts`).

**Native HTML5 drag and drop is a requirement, not a preference.** The agent's
`drag_and_drop` fires the native sequence; a pointer-event drag library would never
see it, and the agent's drag would silently do nothing.

`src/api.ts`, `src/board/calendar.ts`, `src/board/dragging.ts` and
`src/board/pageMap.ts` are identical across the apps in this gallery. They are
copied rather than shared on purpose: each app has to stand alone as something you
can read start to finish and lift into your own project.

## Notes

- The router is `src/router.svelte.ts`: the History API plus one rune. Three routes
  do not need a dependency, and it makes the seam the agent uses obvious —
  `navigate()` is what the chat element calls and what the header buttons call.
- `tsconfig.json` targets `ES2023` because the board uses `toSorted()`.
- **Reloading truncates the restored transcript**, as of web component 0.23.0. The
  server sends `"toolCalls": null` on an assistant turn that called no tool, the
  replay guards only against the key being absent, and the resulting `TypeError`
  stops the replay at the first plain answer. Reported upstream; the conversation
  itself is intact in the database.
