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

## This is the gallery's localized app

Everything on screen is German, and it comes from two places that are worth
keeping apart. [`src/i18n.ts`](src/i18n.ts) holds both.

**The board's own text** is translated the way any app translates itself — a map
this app reads when it renders.

**The component's text** cannot be reached that way. Its buttons, placeholders,
relative timestamps and the sentence it uses when a tool call is declined are all
composed inside the shadow DOM at runtime, so no stylesheet and no slot touches
them. It takes them from the `strings` property (or a `data-strings` JSON
attribute), merged over its English defaults:

```ts
chat.strings = CHAT; // 30-odd keys; the rest stay English
```

A partial map is legitimate, and that is the useful part: keys you omit keep the
English default rather than going blank, so this file does not have to be revisited
every time the component gains a string. Keys are looked up from `UiStrings` — an
invented one is ignored in silence, which is how `placeholder` and `confirmYes`
sat in this file doing nothing until they were checked against the real list.

**What stays English, and why that is correct.** The skill chips read *Tidy up my
week*, because they come from the **server's** catalog, and so do tool labels and
anything the model says. `strings` localizes what the component composes; content
the server sends is the server's to localize, per request. The board's event titles
are in the same category: they are data.

## Notes

- The router is `src/router.svelte.ts`: the History API plus one rune. Three routes
  do not need a dependency, and it makes the seam the agent uses obvious —
  `navigate()` is what the chat element calls and what the header buttons call.
- `tsconfig.json` targets `ES2023` because the board uses `toSorted()`.
- Reloading used to truncate the restored transcript: the server sends
  `"toolCalls": null` on an assistant turn that called no tool, and the replay
  guarded only against the key being absent, so a `TypeError` stopped it at the
  first plain answer. **Found by this gallery and fixed upstream in web component
  0.23.1**, which is what these apps now install.
