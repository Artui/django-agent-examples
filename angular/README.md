# Angular

Angular 22, standalone components, signals, zoneless change detection. Same board,
same seams, same backend as the other apps in the gallery.

```bash
pnpm install
pnpm dev        # http://localhost:4200, proxying /api and /agent to :8000
pnpm build      # ng build, which type-checks templates as it goes
```

The backend must be running first — see [../backend/README.md](../backend/README.md).

## The Angular interop recipe

**Angular applies template bindings during change detection, which runs after the
element is in the DOM.** That is the same boundary React's refs have, and several of
the element's inputs are read once while it connects — the `data-*` attributes,
`headers` — with the thread-history request going out at that moment and
deliberately not deferred. So `assistant.component.ts` creates the element itself:

```ts
@ViewChild("host", { static: true }) private host!: ElementRef<HTMLDivElement>;

ngOnInit(): void {
  defineAgUiChat();
  const chat = document.createElement("ag-ui-chat") as ChatElement;
  chat.setAttribute("endpoint", "/agent/");
  chat.headers = authHeaders();
  chat.getPageMap = () => this.getPageMap()();
  this.host.nativeElement.appendChild(chat);
}
```

`static: true` is what makes `ngOnInit` the right hook: the host `div` is available
before the view renders. If you would rather write `<ag-ui-chat>` in the template —
with `CUSTOM_ELEMENTS_SCHEMA` so the compiler accepts an unknown tag — configure it
in `ngAfterViewInit` and finish with `element.reload()`, which is the component's
own remedy for configuration that lands late.

**`:host { display: contents }` on every component that takes part in the page
layout.** This is the Angular-specific surprise, and it is about the framework
rather than the component: Angular wraps each component in a host element
(`<app-week-grid>`, `<app-assistant>`), which lands between the page's CSS grid and
the children it is meant to size. Without it the chat panel renders a few hundred
pixels tall in the middle of the page. `display: contents` removes the host from
layout so the children participate in the parent grid, exactly as they do in the
other three apps.

**Function-valued inputs are ordinary inputs.** The board passes `getPageMap`,
`readBoardState` and `navigate` as `input.required<() => …>()`. Signals make the
double call (`this.getPageMap()()`) look odd — the first pair reads the signal, the
second calls the function — but it keeps the seams typed end to end.

## The board

`src/app/board/` mirrors the other apps: a CSS grid with a bounded, two-axis
scroll container, native `draggable` cards, `(dragover)` / `(drop)` handlers, and
state in an injectable service built on signals.

**Native HTML5 drag and drop is a requirement, not a preference.** The agent's
`drag_and_drop` fires the native sequence. Angular's own `@angular/cdk/drag-drop`
is pointer-event based and would never see it, so the agent's drag would silently
do nothing while a user's worked fine. That rules the CDK out for this demo.

`src/app/api.ts`, `board/calendar.ts`, `board/dragging.ts` and `board/pageMap.ts`
are identical across the apps in this gallery. They are copied rather than shared on
purpose: each app has to stand alone as something you can read start to finish and
lift into your own project.

## Notes

- `pnpm-workspace.yaml` records which package build scripts are allowed. pnpm 11
  blocks them by default and *fails* the install; the Angular CLI needs esbuild's
  native binary and lmdb, so the allowance is committed rather than answered at a
  prompt.
- The production budget is raised to 800 kB. Most of the bundle is the chat element
  and `@ag-ui/client`; a real app would code-split them.
- Reloading used to truncate the restored transcript: the server sends
  `"toolCalls": null` on an assistant turn that called no tool, and the replay
  guarded only against the key being absent, so a `TypeError` stopped it at the
  first plain answer. **Found by this gallery and fixed upstream in web component
  0.23.1**, which is what these apps now install.
