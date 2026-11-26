/**
 * The chat element, hosted in Angular.
 *
 * Angular applies template bindings during change detection, which runs after the
 * element is already in the DOM — the same boundary React's refs have. Several of
 * the element's inputs are read once while it connects (the `data-*` attributes,
 * `headers`), and the thread-history request goes out at that moment and is
 * deliberately not deferred. So this component creates the element itself,
 * configures it, and appends it, rather than declaring `<ag-ui-chat>` in a
 * template.
 *
 * If you would rather use the template — with `CUSTOM_ELEMENTS_SCHEMA`, or
 * standalone imports, so the compiler accepts an unknown tag — configure it in
 * `ngAfterViewInit` and finish with `element.reload()`.
 */

import {
  Component,
  ElementRef,
  OnDestroy,
  OnInit,
  ViewChild,
  inject,
  input,
} from "@angular/core";
import { NavigationEnd, Router } from "@angular/router";
import { Subscription, filter } from "rxjs";
import type { PageMap, RouteMap, UiStrings } from "@artooi/agents-web-components";
import { defineChat } from "@artooi/agents-web-components/chat";
import { registerMcpApps, type McpAppsHost } from "@artooi/agents-web-components/mcp-apps";
import { authHeaders } from "../api";

// The MCP mount's chat, reached with `?agent=mcp`: its tool results can carry views.
const BASE = new URLSearchParams(window.location.search).get("agent") === "mcp" ? "/mcp-agent/" : "/agent/";
// The agent this chat serves, and the thread a child-session link asked it to open.
const AGENT = BASE === "/mcp-agent/" ? "mcp" : "board";
const WANTED = new URLSearchParams(window.location.search).get("thread");

/** This app's own marks, in place of the component's text glyphs. */
const HISTORY_PATH = "M4 6h16M4 12h16M4 18h10";
const PLUS_PATH = "M12 5v14M5 12h14";

/**
 * One icon, projected into a named slot in the component's header.
 *
 * Built with `createElementNS`: an `<svg>` created through `createElement` lands
 * in the HTML namespace, where it renders as nothing at all and gives no error to
 * explain itself.
 */
function icon(slot: string, path: string): SVGSVGElement {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("slot", slot);
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  const line = document.createElementNS(ns, "path");
  line.setAttribute("d", path);
  svg.append(line);
  return svg;
}

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

@Component({
  selector: "app-assistant",
  template: `<div class="assistant" #host></div>`,
  // Angular wraps every component in a host element, which would sit between the
  // page's grid and its children and break the layout. `display: contents` takes
  // the host out of layout so the children participate in the parent grid as they
  // do in the other apps. This is the one thing about the board that is Angular's
  // rather than the board's.
  styles: [":host { display: contents; }"],
})
export class AssistantComponent implements OnInit, OnDestroy {
  readonly getPageMap = input.required<() => PageMap>();
  readonly skillContext = input.required<() => Record<string, unknown>>();
  readonly readBoardState = input.required<() => unknown>();
  readonly writeBoardState = input.required<(patch: Record<string, unknown>) => unknown>();
  readonly routeMap = input.required<RouteMap>();
  readonly navigate = input.required<(path: string) => void>();
  /** Refetch the board after a run that used a server tool. */
  readonly reload = input.required<() => void>();

  @ViewChild("host", { static: true }) private host!: ElementRef<HTMLDivElement>;

  private chat: ChatElement | null = null;
  // The element re-reads the place on focus, popstate and before each run, not
  // on `pushState`, so without this the place chip shows the last view until then.
  private readonly navigations: Subscription = inject(Router)
    .events.pipe(filter((event) => event instanceof NavigationEnd))
    .subscribe(() => this.chat?.refreshPlace());

  ngOnInit(): void {
    // `static: true` gives us the host div in ngOnInit, before the view is
    // rendered — which is where the element has to be configured.
    defineChat();
    const chat = document.createElement("ag-ui-chat") as ChatElement;

    chat.setAttribute("endpoint", BASE);
    chat.setAttribute("data-tools-url", `${BASE}tools/`);
    // Skills, attachments and transcription live on the board mount only: the MCP mount has none.
    if (BASE === "/agent/") {
      chat.setAttribute("data-skills-url", `${BASE}skills/`);
      chat.setAttribute("data-attachments-url", `${BASE}attachments/`);
      chat.setAttribute("data-transcribe-url", `${BASE}transcribe/`);
      chat.setAttribute("data-skill-editor-url", "/agent/skills/editor/");
      chat.setAttribute("data-skill-editor-button", "");
    }
    chat.setAttribute("data-threads-url", `${BASE}threads/`);
    // A reopened child thread shows its parent link only once the thread list is watched.
    if (AGENT === "mcp") {
      chat.setAttribute("data-thread-status", "poll");
    }
    chat.setAttribute("data-runs-url", `${BASE}runs/`);
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
    registerMcpApps(chat as unknown as McpAppsHost, { url: `${BASE}mcp-apps/` });

    // This app's theming mechanism, and the third of four in the gallery: slots.
    // React retints with custom properties and Vue restyles with `::part()`, and
    // neither can replace *content* -- a design system that ships its own icon set
    // needs to put its own mark in the button, not recolour a glyph the component
    // chose. Each header button renders a named slot with the built-in glyph as
    // its fallback, so projecting a child claims one and leaves the rest alone.
    //
    // Light-DOM children, which is what makes this framework-neutral: they are
    // ordinary elements this component owns and Angular renders, and the shadow
    // root pulls them into place.
    chat.append(icon("icon-history", HISTORY_PATH), icon("icon-new", PLUS_PATH));
    // The built-in toggle, which is a different opt-in from theming: it flips the
    // component between its own light and dark palettes and does not touch the
    // page. Off unless asked for, so it never competes with a host's own switch in
    // the `header-actions` slot.
    chat.setAttribute("data-theme-toggle", "");

    chat.getPageMap = () => this.getPageMap()();
    chat.skillContext = () => this.skillContext()();
    // Page-map ids are not CSS selectors, so the default resolver cannot find them.
    chat.resolvePageTarget = (target) =>
      document.getElementById(target) ?? document.querySelector<HTMLElement>(target);
    chat.routeMap = this.routeMap();
    chat.navigate = (path) => this.navigate()(path);
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
      read: () => this.readBoardState()(),
      write: (patch) => this.writeBoardState()(patch),
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
          this.reload()();
        }
        return;
      }
      if (detail.tools.some((tool) => tool.side === "server")) {
        this.reload()();
      }
    });

    // A child-session link or its parent breadcrumb names the agent the thread runs on. This
    // app has no agents home, so a thread on the other mount reloads the page on that mount.
    chat.addEventListener("ag-ui-open-thread", (event) => {
      const { agentId, threadId } = (event as CustomEvent<{ agentId: string | null; threadId: string }>)
        .detail;
      if (agentId === null || agentId === AGENT) {
        return;
      }
      event.preventDefault();
      const query = new URLSearchParams({ agent: agentId, thread: threadId });
      window.location.assign(`${window.location.pathname}?${query}`);
    });

    this.host.nativeElement.appendChild(chat);
    this.chat = chat;
    // Only a connected element can switch threads, so this follows insertion.
    if (WANTED !== null) {
      void chat.switchThread(WANTED);
    }
  }

  ngOnDestroy(): void {
    this.navigations.unsubscribe();
    this.chat?.remove();
  }
}
