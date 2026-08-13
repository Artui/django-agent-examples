# React

React 19, Vite, React Router. The board is native HTML5 drag and drop; the
assistant is `<ag-ui-chat>` hosted imperatively.

```bash
pnpm install
pnpm dev        # http://localhost:5173, proxying /api and /agent to :8000
pnpm build      # tsc -b plus a production build
```

The backend must be running first — see [../backend/README.md](../backend/README.md).

## The React interop recipe

**Create the element, configure it, then insert it.** This is the whole gotcha,
and it is specific to React. Several of the element's inputs are read once while
it connects: the chrome-building `data-*` attributes, `strings`, the upload and
transcription handlers — and the catalogs and thread history are fetched at that
same moment. React attaches refs *after* it inserts a node, so writing
`<ag-ui-chat ref={...} />` in JSX and configuring in the ref callback puts the
configuration on the wrong side of that boundary. (Most of it survives, because
the catalog requests are held back one microtask, but the thread-history request
is deliberately not deferred and goes out with whatever was configured at
insertion.)

`src/assistant/Assistant.tsx` does it the other way round:

```tsx
useEffect(() => {
  defineAgUiChat();
  const chat = document.createElement("ag-ui-chat") as ChatElement;
  chat.setAttribute("endpoint", "/agent/");
  chat.setAttribute("data-page-actions", "scroll,drag");
  chat.headers = authHeaders();
  chat.getPageMap = () => latest.current.getPageMap();
  host.current?.appendChild(chat);
  return () => chat.remove();
}, []);
```

**The element is created once; its callbacks must see current state.** A `ref`
reassigned on every render (`latest.current = props`) is what bridges the two
lifetimes. Recreating the element when the board changes would work and would also
throw the conversation away on every keystroke.

`defineAgUiChat()` is idempotent and is an explicit call rather than an import
side effect, so calling it inside an effect is safe under Strict Mode's
double-invoked effects.

**JSX and unknown elements.** React 19 passes unknown attributes through to
custom elements and sets properties where they exist, so no schema declaration or
wrapper component is needed — which is the claim this app exists to check. Because
the element is created with `document.createElement`, TypeScript never needs a
JSX intrinsic-element declaration for it either; the local `ChatElement` type
covers the properties this host sets.

## The board

`src/board/` is deliberately plain: a CSS grid, native `draggable` cards, and
`onDragOver` / `onDrop` handlers.

**Why not a drag library.** The agent's `drag_and_drop` fires the native drag
sequence. dnd-kit and its relatives listen to pointer events and would never see
it, so the agent's drag would silently do nothing while a user's worked fine.
React's synthetic `onDrop` does receive the dispatched sequence, `DataTransfer`
included — verified in this app.

`src/board/dragging.ts` carries the dragged id both through the `DataTransfer` and
through a module-scoped handle, so a drop handler still knows what it received in a
browser that hands it an empty transfer.

**Two-axis scrolling is a layout decision.** `.grid-scroller` has a bounded height
and `overflow: auto`, which is what makes "scroll the timeline to Friday 17:00" a
real interaction rather than a page scroll.

## What the assistant is given

| Seam | Where | Why |
| --- | --- | --- |
| `getPageMap` | `src/board/pageMap.ts` | Ids, labels and coordinates — the addressable surface, recomputed per tool round. |
| `resolvePageTarget` | `Assistant.tsx` | Page-map ids are not CSS selectors, so the default resolver cannot find them. |
| `routeMap` + `navigate` | `src/App.tsx` | Wiring `navigate` to the router is the single seam that makes this an SPA: view changes do not reload, so the run loop continues. |
| `registerPageState` | `Assistant.tsx` | `read_board` / `set_board` over the view, filter and selection. |
| `confirmPredicate` | `Assistant.tsx` | One line, both directions: gate a drag onto a slot (it saves), and un-gate `set_board` (which `registerPageState` stamps destructive). |
| `strings` | `Assistant.tsx` | The confirmation prompt, in this board's words. |
| `headers` | `src/api.ts` | The same token the app's own fetches send — the element authenticates every request it makes, not just the run. |

## Notes

- The production bundle is around 640 kB unsplit, most of it the chat element and
  `@ag-ui/client`. Code-split it in a real app; a demo does not need to.
- The element requests the current thread's messages on mount, which is a `404`
  for a thread that has never been saved. Harmless, and visible in the console on
  a first visit.
- Reloading used to truncate the restored transcript: the server sends
  `"toolCalls": null` on an assistant turn that called no tool, and the replay
  guarded only against the key being absent, so a `TypeError` stopped it at the
  first plain answer. **Found by this gallery and fixed upstream in web component
  0.23.1**, which is what these apps now install.
- Dark mode comes from `prefers-color-scheme` on the page. The element inherits
  `--ag-ui-accent` from it, so the ring it draws on the page is the board's accent
  colour rather than the component's default.
