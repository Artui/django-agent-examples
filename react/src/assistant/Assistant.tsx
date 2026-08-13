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
}

/** The element's typed shape, as far as this host uses it. */
type ChatElement = HTMLElement & {
  headers: Record<string, string>;
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
  const latest = useRef(props);
  latest.current = props;

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
    chat.headers = authHeaders();
    chat.getPageMap = () => latest.current.getPageMap();
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

    host.current?.appendChild(chat);
    return () => chat.remove();
    // Configured once, on mount, on purpose: recreating the element would throw
    // the conversation away. Everything that varies is read through `latest`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div className="assistant" ref={host} />;
}
