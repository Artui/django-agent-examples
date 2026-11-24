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
  import type { PageMap, RouteMap, UiStrings } from "@artooi/agents-web-components";
  import { defineChat } from "@artooi/agents-web-components/chat";
  import { registerMcpApps, type McpAppsHost } from "@artooi/agents-web-components/mcp-apps";
  import { authHeaders } from "../api";
  import { BOARD, CHAT } from "../i18n";
  import { router } from "../router.svelte";

  let {
    getPageMap,
    skillContext,
    readBoardState,
    writeBoardState,
    routeMap,
    navigate,
    reload,
  }: {
    getPageMap: () => PageMap;
    skillContext: () => Record<string, unknown>;
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
    skillContext: () => Record<string, unknown>;
    getPageMap: () => PageMap;
    resolvePageTarget: (target: string) => HTMLElement | null;
    routeMap: RouteMap;
    navigate: (path: string) => void;
    confirmPredicate: (name: string, args: Record<string, unknown>) => boolean;
    strings: Partial<UiStrings>;
    refreshPlace: () => void;
    registerPageState: (binding: {
      name: string;
      read: () => unknown;
      write?: (args: Record<string, unknown>) => unknown;
      schema?: Record<string, unknown>;
    }) => void;
  };

  // The MCP mount's chat, reached with `?agent=mcp`: its tool results can carry views.
  const BASE = new URLSearchParams(window.location.search).get("agent") === "mcp" ? "/mcp-agent/" : "/agent/";
  let host: HTMLDivElement | undefined = $state();
  // Plain, not `$state`: the effect below must not rebuild the element.
  let element: ChatElement | undefined;

  $effect(() => {
    if (host === undefined) {
      return;
    }
    defineChat();
    const chat = document.createElement("ag-ui-chat") as ChatElement;

    // Read once, at connect: set before the element is inserted.
    chat.setAttribute("endpoint", BASE);
    chat.setAttribute("data-tools-url", `${BASE}tools/`);
    chat.setAttribute("data-skills-url", `${BASE}skills/`);
    chat.setAttribute("data-threads-url", `${BASE}threads/`);
    chat.setAttribute("data-attachments-url", `${BASE}attachments/`);
    chat.setAttribute("data-runs-url", `${BASE}runs/`);
    chat.setAttribute("data-transcribe-url", `${BASE}transcribe/`);
    chat.setAttribute("data-prompt-chips", "");
    chat.setAttribute("data-slash-commands", "");
    chat.setAttribute("data-page-actions", "scroll,drag");
    chat.setAttribute("placement", "embedded");
    chat.setAttribute("title-text", BOARD.assistant);
    chat.setAttribute("data-answer-well", "");
    chat.setAttribute("data-text-animation", "fade");
    // A frontend tool whose handler is a person: the agent calls `ask_user`,
    // the component renders the card, the answer returns as the tool result.
    chat.askUser = true;
    chat.headers = authHeaders();
    registerMcpApps(chat as unknown as McpAppsHost, { url: `${BASE}mcp-apps/` });

    // Read lazily: per request, per run, per tool round. The props are captured by
    // reference, so the element always sees the board as it is now.
    chat.getPageMap = () => getPageMap();
    chat.skillContext = () => skillContext();
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
    // This app is the gallery's localized one. Everything the component says comes
    // from here -- its buttons, its placeholders, the sentence it uses when a call
    // is declined -- because that text is composed inside the shadow DOM at
    // runtime, where no stylesheet or slot reaches it. The map is merged over the
    // English defaults, so the keys this file omits stay English rather than
    // blank.
    //
    // Read once, at connect, like the other inputs here: a language switch would
    // reassign `strings`, which re-localizes the chrome in place.
    chat.strings = CHAT;
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
    // underneath you", so this event is the signal.
    //
    // `invalidated` is the precise half and `tools` is the fallback, and the
    // `else` is the whole compatibility story: an older component leaves
    // `invalidated` undefined and this reloads coarsely, exactly as it did
    // before. Nothing negotiates and there is no version check.
    //
    // The board is one resource, so any key under `board.events` means reload.
    // Matching a prefix is the *host's* call -- on the wire matching is exact,
    // because a prefix rule there would be the library guessing at a scheme it
    // does not own.
    chat.addEventListener("ag-ui-run-finished", (event) => {
      const detail = (event as CustomEvent<{
        tools: { name: string; side: string }[];
        invalidated?: string[];
      }>).detail;
      const moved = detail.invalidated ?? [];
      if (moved.length > 0) {
        if (moved.some((key) => key === "board.events" || key.startsWith("board.events/"))) {
          reload();
        }
        return;
      }
      if (detail.tools.some((tool) => tool.side === "server")) {
        reload();
      }
    });

    host.appendChild(chat);
    element = chat;
    return () => {
      element = undefined;
      chat.remove();
    };
  });

  // The element re-reads the place on focus, popstate and before each run, not
  // on `pushState`, so without this the place chip shows the last view until then.
  $effect(() => {
    void router.path;
    element?.refreshPlace();
  });
</script>

<div class="assistant" bind:this={host}></div>
