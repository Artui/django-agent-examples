# Vue

Vue 3 (`<script setup>`), Vite, Vue Router. Same board, same seams, same backend
as the other apps in the gallery.

```bash
pnpm install
pnpm dev        # http://localhost:5174, proxying /api and /agent to :8000
pnpm build      # vue-tsc plus a production build
```

The backend must be running first — see [../backend/README.md](../backend/README.md).

## The Vue interop recipe

**Two kinds of configuration, two places for them.** Several of the element's
inputs are read once, while it connects: the chrome-building `data-*` attributes,
`headers`, `strings`. Everything else — the page map, the route map, the
predicates — is read lazily, per request or per tool round.

Vue patches attributes **before** it inserts an element, so the connect-time
attributes belong in the template and Vue gets that right for free:

```vue
<ag-ui-chat endpoint="/agent/" data-page-actions="scroll,drag" placement="embedded" />
```

**`onMounted` is too late for the rest, and the failure is silent.** The first
version of `Assistant.vue` set `headers` there, which runs after insertion — so
the thread-history request (deliberately not deferred, unlike the catalogs) went
out unauthenticated. That is a `401` in the network panel, an empty history drawer,
and nothing on screen to explain it.

**A custom directive's `beforeMount` hook is the window that works.** It runs
before the element is inserted, which is exactly where the property assignments
have to be:

```vue
<script setup lang="ts">
const vConfigure = {
  beforeMount(element: ChatElement) {
    element.headers = authHeaders();
    element.getPageMap = () => props.getPageMap();
    element.routeMap = props.routeMap;
    // ...
  },
};
</script>

<template>
  <ag-ui-chat v-configure endpoint="/agent/" />
</template>
```

React reaches the same window by creating the element with
`document.createElement` and appending it afterwards. Vue does not need to,
because the directive hook exists.

**`isCustomElement` is required, in `vite.config.ts`.** Without it the Vue compiler
treats `<ag-ui-chat>` as an unresolved component and warns on every render:

```ts
vue({ template: { compilerOptions: { isCustomElement: (tag) => tag === "ag-ui-chat" } } })
```

**Do not put function props in the template.** A function bound as an attribute is
stringified; the seams that take callbacks are properties, which is the other
reason they live in the directive.

## The board

`src/board/` mirrors the React app: a CSS grid with a bounded, two-axis scroll
container, native `draggable` cards, and `@dragover.prevent` / `@drop` handlers.

**Native HTML5 drag and drop is a requirement, not a preference.** The agent's
`drag_and_drop` fires the native sequence; a pointer-event drag library would never
see it, and the agent's drag would silently do nothing.

`src/api.ts`, `src/board/calendar.ts`, `src/board/dragging.ts` and
`src/board/pageMap.ts` are byte-identical across the apps in this gallery. They are
copied rather than shared on purpose: each app has to stand alone as something you
can read start to finish and lift into your own project.

## How this app themes the widget: `::part()`

The gallery themes each app a different way, and this one uses parts. Custom
properties (see [the React app](../react/README.md)) can only change what the
component chose to expose as a variable; a part is a stable name on an element,
so a host can restyle things the component never parameterised. Here the header
stops being a filled accent bar and becomes a plain one in the page's colours,
and the bubbles go square:

```css
ag-ui-chat::part(header) {
  background: var(--card);
  color: var(--ink);
  border-bottom: 1px solid var(--line);
}

ag-ui-chat::part(message) {
  border-radius: 2px;
}
```

Two things worth knowing. **Part names are looked up, not guessed** — the bubble's
part is `message`, not `bubble`, and a wrong name fails silently with no warning
anywhere. And a part rule competes with the component's own shadow CSS, where the
outer stylesheet wins at equal specificity, so no `!important` is needed — but the
properties do have to be spelled out, because the rule being overridden is still
there.

## Notes

- State is a composable (`useBoard`), so the board's refs are passed to components
  as one object. Refs reached through a prop are not auto-unwrapped in templates,
  hence the `.value` reads; that is Vue's rule, not this component's.
- The three routes render nothing themselves — `App.vue` owns the board state and
  picks the view from the current path. That keeps the state in one place without
  a store, at the cost of one small oddity in `main.ts`.
- Reloading used to truncate the restored transcript: the server sends
  `"toolCalls": null` on an assistant turn that called no tool, and the replay
  guarded only against the key being absent, so a `TypeError` stopped it at the
  first plain answer. **Found by this gallery and fixed upstream in web component
  0.23.1**, which is what these apps now install.
