<script setup lang="ts">
/**
 * The chat element, hosted in Vue.
 *
 * Vue can do this better than React can, and the reason is a lifecycle hook.
 * Several of the element's inputs are read once, while it connects — the
 * chrome-building `data-*` attributes, `headers`, `strings` — and the thread
 * history is fetched at that same moment and deliberately **not** deferred. So
 * anything set in `onMounted` is too late for it: the first version of this file
 * did exactly that and the history request went out unauthenticated, which is a
 * `401` and an empty drawer with nothing on screen to explain it.
 *
 * A custom directive's `beforeMount` hook runs **before the element is inserted**,
 * which is the window React does not offer through a ref. Configure there and the
 * element connects already knowing who it is. (React's answer is to create the
 * element by hand and append it afterwards; both are the same idea.)
 */
import { onBeforeUnmount, ref, watch } from "vue";
import { useRoute } from "vue-router";
import type { PageMap, RouteMap, UiStrings } from "@artooi/agents-web-components";
import { defineChat } from "@artooi/agents-web-components/chat";
import { registerMcpApps, type McpAppsHost } from "@artooi/agents-web-components/mcp-apps";
import { authHeaders } from "../api";

// The MCP mount's chat, reached with `?agent=mcp`: its tool results can carry views.
const BASE = new URLSearchParams(window.location.search).get("agent") === "mcp" ? "/mcp-agent/" : "/agent/";
// The agent this chat serves, and the thread a child-session link asked it to open.
const AGENT = BASE === "/mcp-agent/" ? "mcp" : "board";
const WANTED = new URLSearchParams(window.location.search).get("thread");

const props = defineProps<{
  getPageMap: () => PageMap;
  /**
   * Values a templated skill's `{placeholder}`s are filled from, read per pick.
   * The day view has a day and the week view does not, so the same chip is ready
   * in one and blocked in the other.
   */
  skillContext: () => Record<string, unknown>;
  readBoardState: () => unknown;
  writeBoardState: (patch: Record<string, unknown>) => unknown;
  routeMap: RouteMap;
  navigate: (path: string) => void;
  /** Refetch the board after a run that used a server tool. */
  reload: () => void;
}>();

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
  switchThread: (threadId: string) => Promise<void>;
  registerPageState: (binding: {
    name: string;
    read: () => unknown;
    write?: (args: Record<string, unknown>) => unknown;
    schema?: Record<string, unknown>;
  }) => void;
};

const chat = ref<ChatElement | null>(null);

// The element re-reads the place on focus, popstate and before each run, not on
// `pushState`, so without this the place chip shows the last view until then.
const route = useRoute();
watch(
  () => route.path,
  () => chat.value?.refreshPlace(),
);

// Registering the custom element is an explicit call, not an import side effect,
// and it is idempotent.
defineChat();

/** Everything the element must know before it connects. */
const vConfigure = {
  beforeMount(element: ChatElement) {
    chat.value = element;
    // A frontend tool whose handler is a person: the agent calls `ask_user`,
    // the component renders the card, the answer returns as the tool result.
    element.askUser = true;
    element.headers = authHeaders();
    registerMcpApps(element as unknown as McpAppsHost, { url: `${BASE}mcp-apps/` });
    element.getPageMap = () => props.getPageMap();
    element.skillContext = () => props.skillContext();
    // Page-map ids are not CSS selectors, so the default resolver cannot find
    // them. The selector fallback keeps plain selectors working too.
    element.resolvePageTarget = (target) =>
      document.getElementById(target) ?? document.querySelector<HTMLElement>(target);
    element.routeMap = props.routeMap;
    element.navigate = (path) => props.navigate(path);
    // The board saves the moment a card lands, so a drag onto a slot is gated;
    // reordering the backlog is not, and `set_board` — which `registerPageState`
    // stamps destructive — is un-gated by the same predicate.
    element.confirmPredicate = (name, args) =>
      name === "drag_and_drop" && String(args["to"] ?? "").startsWith("slot-");
    element.strings = {
      confirmRun: "Move this on the board? The change is saved immediately.",
    };
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
    element.addEventListener("ag-ui-run-finished", (event) => {
      const detail = (event as CustomEvent<{
        tools: { name: string; side: string }[];
        invalidated?: string[];
      }>).detail;
      const moved = detail.invalidated ?? [];
      if (moved.length > 0) {
        if (moved.some((key) => key === "board.events" || key.startsWith("board.events/"))) {
          props.reload();
        }
        return;
      }
      if (detail.tools.some((tool) => tool.side === "server")) {
        props.reload();
      }
    });

    // A child-session link or its parent breadcrumb names the agent the thread runs on. This
    // app has no agents home, so a thread on the other mount reloads the page on that mount.
    element.addEventListener("ag-ui-open-thread", (event) => {
      const { agentId, threadId } = (event as CustomEvent<{ agentId: string | null; threadId: string }>)
        .detail;
      if (agentId === null || agentId === AGENT) {
        return;
      }
      event.preventDefault();
      const query = new URLSearchParams({ agent: agentId, thread: threadId });
      window.location.assign(`${window.location.pathname}?${query}`);
    });

    element.registerPageState({
      name: "board",
      read: () => props.readBoardState(),
      write: (patch) => props.writeBoardState(patch),
      schema: {
        type: "object",
        properties: {
          room: { type: "string", description: "Room filter, or 'all'." },
          selection: { type: ["integer", "null"], description: "Selected event id." },
        },
      },
    });
  },
  // Only a connected element can switch threads, so this waits for insertion.
  mounted(element: ChatElement) {
    if (WANTED !== null) {
      void element.switchThread(WANTED);
    }
  },
};

onBeforeUnmount(() => {
  chat.value?.remove();
});
</script>

<template>
  <div class="assistant">
    <!-- The attributes are read as the element connects, and Vue patches them
         before insertion, so the template is the right place for them. The
         directive covers everything that has to be a property. -->
    <ag-ui-chat
      v-configure
      :endpoint="BASE"
      :data-tools-url="`${BASE}tools/`"
      :data-skills-url="BASE === '/agent/' ? '/agent/skills/' : undefined"
      :data-skill-editor-url="BASE === '/agent/' ? '/agent/skills/editor/' : undefined"
      :data-skill-editor-button="BASE === '/agent/' ? '' : undefined"
      :data-threads-url="`${BASE}threads/`"
      :data-attachments-url="BASE === '/agent/' ? '/agent/attachments/' : undefined"
      :data-runs-url="`${BASE}runs/`"
      :data-transcribe-url="BASE === '/agent/' ? '/agent/transcribe/' : undefined"
      data-prompt-chips=""
      data-slash-commands=""
      data-page-actions="scroll,drag"
      placement="embedded"
      title-text="Board assistant"
      data-answer-well=""
      data-text-animation="fade"
    />
  </div>
</template>
