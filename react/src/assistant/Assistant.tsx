/**
 * The chat element, hosted in React.
 *
 * The one thing to copy from this file is the order of operations. Several of the
 * element's inputs are read once, while it connects — the chrome-building
 * `data-*` attributes, and the catalogs it fetches immediately after. React
 * attaches refs *after* it inserts a node, so writing `<ag-ui-chat ref={...} />`
 * in JSX puts the configuration on the wrong side of that boundary. Create the
 * element, configure it, then append it.
 *
 * The second thing is `latest`: the element is created once, but its callbacks
 * must see the board as it is now. A ref updated on every render is what closes
 * that gap without recreating the element (which would discard the transcript).
 */

import { type PageMap, type RouteMap, defineAgUiChat } from "@artooi/ag-ui-web-component";
import { useEffect, useRef } from "react";
import { authHeaders } from "../api";

export interface AssistantProps {
  /** The board's addressable surface, recomputed per tool round. */
  getPageMap: () => PageMap;
  /** The view/filter/selection the agent may read. */
  readBoardState: () => unknown;
  /** The subset of that state the agent may set. */
  writeBoardState: (patch: Record<string, unknown>) => unknown;
  routeMap: RouteMap;
  /** Client-side routing: this single seam is what makes the app an SPA. */
  navigate: (path: string) => void;
  /**
   * Refetch the board. Called when a run finishes having used a *server* tool,
   * which is a write this page had no other way to learn about.
   */
  reload: () => void;
  /**
   * Values a templated skill's `{placeholder}`s are filled from. Read per pick,
   * so it reflects the page as it is when the chip is pressed.
   */
  skillContext: () => Record<string, unknown>;
  /** The shared week note, as the page currently holds it. */
  note: string;
  /** The agent rewrote the note: adopt it. */
  onNoteChanged: (note: string) => void;
}

/** The element's typed shape, as far as this host uses it. */
type ChatElement = HTMLElement & {
  headers: Record<string, string>;
  askUser: boolean;
  skillContext: () => Record<string, unknown>;
  sharedState: Record<string, unknown>;
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

export function Assistant(props: AssistantProps) {
  const host = useRef<HTMLDivElement | null>(null);
  const element = useRef<ChatElement | null>(null);
  const latest = useRef(props);
  latest.current = props;

  // The page's own edits go the other way. Assigning `sharedState` is the seam for
  // it, and unlike the connect-time inputs it can be written at any time -- the
  // element carries whatever it holds into the next run.
  useEffect(() => {
    if (element.current !== null && element.current.sharedState["note"] !== props.note) {
      element.current.sharedState = { ...element.current.sharedState, note: props.note };
    }
  }, [props.note]);

  useEffect(() => {
    // Registering the custom element is an explicit call, not an import side
    // effect, and it is idempotent — so calling it here is safe under Strict
    // Mode's double-invoked effects.
    defineAgUiChat();
    const chat = document.createElement("ag-ui-chat") as ChatElement;

    // --- read once, at connect: set them before the element is inserted -----
    chat.setAttribute("endpoint", "/agent/");
    chat.setAttribute("data-tools-url", "/agent/tools/");
    chat.setAttribute("data-skills-url", "/agent/skills/");
    chat.setAttribute("data-threads-url", "/agent/threads/");
    // The clip in the composer. Without this attribute the endpoint is still
    // mounted and the button is not built at all, so uploads are opt-in per host
    // rather than per deployment.
    chat.setAttribute("data-attachments-url", "/agent/attachments/");
    // The ⭯ panel in the header, which only exists when this is set: it lists the
    // runs the server says have a snapshot to seed from. Type the next turn, then
    // pick resume or fork -- the continuation streams into this same transcript.
    chat.setAttribute("data-runs-url", "/agent/runs/");
    // The mic, on the same terms as the clip: built only when a host points at
    // an endpoint, so an app that says nothing gets no dead control.
    chat.setAttribute("data-transcribe-url", "/agent/transcribe/");
    chat.setAttribute("data-prompt-chips", "");
    chat.setAttribute("data-slash-commands", "");
    // Opting in to the two built-in page actions. Without this the agent has no
    // way to scroll or drag: the host decides its own interaction surface.
    chat.setAttribute("data-page-actions", "scroll,drag");
    chat.setAttribute("placement", "embedded");
    chat.setAttribute("title-text", "Board assistant");
    chat.setAttribute("data-answer-well", "");
    chat.setAttribute("data-text-animation", "fade");

    // --- read per request or per round: these may be set at any time --------
    // The agent may ask a question and wait for the answer. This offers it a
    // *frontend* tool -- the model calls `ask_user`, the component renders a card
    // in the transcript, and the answer comes back as that call's result. Nothing
    // is configured server-side and no new protocol is involved: it is an ordinary
    // client tool whose handler happens to be a person.
    chat.askUser = true;

    chat.headers = authHeaders();
    chat.getPageMap = () => latest.current.getPageMap();
    // A skill whose prompt carries `{day}` is filled from here. An absent value
    // is not an error: the component blocks the send and names what is missing,
    // which is how the same chip can be ready in the day view and not in the week
    // view without the catalog knowing anything about views.
    chat.skillContext = () => latest.current.skillContext();
    // Page-map ids are not CSS selectors, so the default `querySelector`
    // resolver cannot find them. This is the documented seam for a host with
    // its own ids; the selector fallback keeps plain selectors working too.
    chat.resolvePageTarget = (target) =>
      document.getElementById(target) ?? document.querySelector<HTMLElement>(target);
    chat.routeMap = props.routeMap;
    chat.navigate = (path) => latest.current.navigate(path);

    // The board saves a move the moment a card lands, so the agent's drag is a
    // durable action and gets a confirmation card. Reordering the backlog does
    // not need one. A predicate can express that; a static schema flag cannot.
    // It is also authoritative in the other direction: `set_board` is stamped
    // destructive by `registerPageState`, and returning false here means
    // changing a filter does not prompt.
    chat.confirmPredicate = (name, args) =>
      name === "drag_and_drop" && String(args["to"] ?? "").startsWith("slot-");
    chat.strings = {
      confirmRun: "Move this on the board? The change is saved immediately.",
    };

    // AG-UI shared state, seeded before insertion like everything else read at
    // connect. The element sends it as `RunAgentInput.state` on every run.
    chat.sharedState = { note: latest.current.note };

    // The agent rewrote it. That is the whole inbound half: no tool result, no
    // transcript entry, just the object both ends hold.
    chat.addEventListener("ag-ui-state", (event) => {
      const state = (event as CustomEvent<{ state: Record<string, unknown> }>).detail.state;
      if (typeof state["note"] === "string") {
        latest.current.onNoteChanged(state["note"]);
      }
    });

    chat.registerPageState({
      name: "board",
      read: () => latest.current.readBoardState(),
      write: (patch) => latest.current.writeBoardState(patch),
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
    // underneath you" -- so this event is the signal, and a host that renders
    // agent-touchable data wants it.
    //
    // Only `side === "server"` matters. A `client` tool ran in this app's own
    // handler, which already refetched if it needed to.
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
      const detail = (
        event as CustomEvent<{
          tools: { name: string; side: string }[];
          invalidated?: string[];
        }>
      ).detail;
      const moved = detail.invalidated ?? [];
      if (moved.length > 0) {
        if (moved.some((key) => key === "board.events" || key.startsWith("board.events/"))) {
          latest.current.reload();
        }
        return;
      }
      if (detail.tools.some((tool) => tool.side === "server")) {
        latest.current.reload();
      }
    });

    host.current?.appendChild(chat);
    element.current = chat;
    return () => {
      element.current = null;
      chat.remove();
    };
    // Configured once, on mount, on purpose: recreating the element would throw
    // the conversation away. Everything that varies is read through `latest`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div className="assistant" ref={host} />;
}
