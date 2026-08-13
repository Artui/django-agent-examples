<script lang="ts">
  /**
   * The chat element, hosted in Svelte.
   *
   * Svelte's `use:` actions and `$effect` both run **after** the element is in the
   * DOM, and several of the element's inputs are read once while it connects — the
   * `data-*` attributes, `headers` — with the thread-history request going out at
   * that same moment and deliberately not deferred. So there is no pre-insertion
   * hook to use here (Vue has one; Svelte does not), and the recipe is the same as
   * React's: create the element, configure it, then append it.
   *
   * The alternative, if you would rather write `<ag-ui-chat>` in the markup, is to
   * configure it in an action and then call `element.reload()` — the component's own
   * remedy for configuration that lands late. It costs one extra round of catalog
   * fetches.
   */
  import { type PageMap, type RouteMap, defineAgUiChat } from "@artooi/ag-ui-web-component";
  import { authHeaders } from "../api";

  let {
    getPageMap,
    readBoardState,
    writeBoardState,
    routeMap,
    navigate,
    reload,
  }: {
    getPageMap: () => PageMap;
    readBoardState: () => unknown;
    writeBoardState: (patch: Record<string, unknown>) => unknown;
    routeMap: RouteMap;
    navigate: (path: string) => void;
    /** Refetch the board after a run that used a server tool. */
    reload: () => void;
  } = $props();

  type ChatElement = HTMLElement & {
    headers: Record<string, string>;
    askUser: boolean;
    getPageMap: () => PageMap;
    resolvePageTarget: (target: string) => HTMLElement | null;
    routeMap: RouteMap;
    navigate: (path: string) => void;
    confirmPredicate: (name: string, args: Record<string, unknown>) => boolean;
    strings: Record<string, string>;
    registerPageState: (binding: {
      name: string;
      read: () => unknown;
      write?: (args: Record<string, unknown>) => unknown;
      schema?: Record<string, unknown>;
    }) => void;
  };

  let host: HTMLDivElement | undefined = $state();

  $effect(() => {
    if (host === undefined) {
      return;
    }
    defineAgUiChat();
    const chat = document.createElement("ag-ui-chat") as ChatElement;

    // Read once, at connect: set before the element is inserted.
    chat.setAttribute("endpoint", "/agent/");
    chat.setAttribute("data-tools-url", "/agent/tools/");
    chat.setAttribute("data-skills-url", "/agent/skills/");
    chat.setAttribute("data-threads-url", "/agent/threads/");
    chat.setAttribute("data-attachments-url", "/agent/attachments/");
    chat.setAttribute("data-prompt-chips", "");
    chat.setAttribute("data-slash-commands", "");
    chat.setAttribute("data-page-actions", "scroll,drag");
    chat.setAttribute("placement", "embedded");
    chat.setAttribute("title-text", "Board assistant");
    chat.setAttribute("data-answer-well", "");
    chat.setAttribute("data-text-animation", "fade");
    // A frontend tool whose handler is a person: the agent calls `ask_user`,
    // the component renders the card, the answer returns as the tool result.
    chat.askUser = true;
    chat.headers = authHeaders();

    // Read lazily: per request, per run, per tool round. The props are captured by
    // reference, so the element always sees the board as it is now.
    chat.getPageMap = () => getPageMap();
    // Page-map ids are not CSS selectors, so the default resolver cannot find them.
    chat.resolvePageTarget = (target) =>
      document.getElementById(target) ?? document.querySelector<HTMLElement>(target);
    chat.routeMap = routeMap;
    chat.navigate = (path) => navigate(path);
    // The board saves the moment a card lands, so a drag onto a slot is gated;
    // reordering the backlog is not, and `set_board` — which `registerPageState`
    // stamps destructive — is un-gated by the same predicate.
    chat.confirmPredicate = (name, args) =>
      name === "drag_and_drop" && String(args["to"] ?? "").startsWith("slot-");
    chat.strings = {
      confirmRun: "Move this on the board? The change is saved immediately.",
    };
    chat.registerPageState({
      name: "board",
      read: () => readBoardState(),
      write: (patch) => writeBoardState(patch),
      schema: {
        type: "object",
        properties: {
          room: { type: "string", description: "Room filter, or 'all'." },
          selection: { type: ["integer", "null"], description: "Selected event id." },
        },
      },
    });

    // A server-side tool writes without this page's knowledge: approve a booking
    // and the row exists while the board keeps showing what it fetched on mount.
    // Nothing else the element dispatches implies "something may have moved
    // underneath you", so this event is the signal. Only `side === "server"`
    // matters -- a client tool ran in this app's own handler.
    chat.addEventListener("ag-ui-run-finished", (event) => {
      const detail = (event as CustomEvent<{ tools: { name: string; side: string }[] }>).detail;
      if (detail.tools.some((tool) => tool.side === "server")) {
        reload();
      }
    });

    host.appendChild(chat);
    return () => chat.remove();
  });
</script>

<div class="assistant" bind:this={host}></div>
