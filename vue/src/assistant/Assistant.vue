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
import { onBeforeUnmount, ref } from "vue";
import { type PageMap, type RouteMap, defineAgUiChat } from "@artooi/ag-ui-web-component";
import { authHeaders } from "../api";

const props = defineProps<{
  getPageMap: () => PageMap;
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

const chat = ref<ChatElement | null>(null);

// Registering the custom element is an explicit call, not an import side effect,
// and it is idempotent.
defineAgUiChat();

/** Everything the element must know before it connects. */
const vConfigure = {
  beforeMount(element: ChatElement) {
    chat.value = element;
    // A frontend tool whose handler is a person: the agent calls `ask_user`,
    // the component renders the card, the answer returns as the tool result.
    element.askUser = true;
    element.headers = authHeaders();
    element.getPageMap = () => props.getPageMap();
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
    // underneath you", so this event is the signal. Only `side === "server"`
    // matters -- a client tool ran in this app's own handler.
    element.addEventListener("ag-ui-run-finished", (event) => {
      const detail = (event as CustomEvent<{ tools: { name: string; side: string }[] }>).detail;
      if (detail.tools.some((tool) => tool.side === "server")) {
        props.reload();
      }
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
      endpoint="/agent/"
      data-tools-url="/agent/tools/"
      data-skills-url="/agent/skills/"
      data-threads-url="/agent/threads/"
      data-attachments-url="/agent/attachments/"
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
