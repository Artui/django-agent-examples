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
  input,
} from "@angular/core";
import { type PageMap, type RouteMap, defineAgUiChat } from "@artooi/ag-ui-web-component";
import { authHeaders } from "../api";

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
  readonly readBoardState = input.required<() => unknown>();
  readonly writeBoardState = input.required<(patch: Record<string, unknown>) => unknown>();
  readonly routeMap = input.required<RouteMap>();
  readonly navigate = input.required<(path: string) => void>();
  /** Refetch the board after a run that used a server tool. */
  readonly reload = input.required<() => void>();

  @ViewChild("host", { static: true }) private host!: ElementRef<HTMLDivElement>;

  private chat: ChatElement | null = null;

  ngOnInit(): void {
    // `static: true` gives us the host div in ngOnInit, before the view is
    // rendered — which is where the element has to be configured.
    defineAgUiChat();
    const chat = document.createElement("ag-ui-chat") as ChatElement;

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

    chat.getPageMap = () => this.getPageMap()();
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
    // underneath you", so this event is the signal. Only `side === "server"`
    // matters -- a client tool ran in this app's own handler.
    chat.addEventListener("ag-ui-run-finished", (event) => {
      const detail = (event as CustomEvent<{ tools: { name: string; side: string }[] }>).detail;
      if (detail.tools.some((tool) => tool.side === "server")) {
        this.reload()();
      }
    });

    this.host.nativeElement.appendChild(chat);
    this.chat = chat;
  }

  ngOnDestroy(): void {
    this.chat?.remove();
  }
}
