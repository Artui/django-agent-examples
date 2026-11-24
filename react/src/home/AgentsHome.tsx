/**
 * The agents home: every agent this user may talk to, on one page.
 *
 * Three elements the library already has, under one `<ag-ui-agents>` provider,
 * as the agents-web-components "An agents home" recipe lays them out: what waits
 * on the user (`<ag-ui-inbox variant="list">`, with a badge in the header), the
 * conversations of the agent in front (`<ag-ui-threads>`, a rail on a wide page
 * and pills on a narrow one), and the chat as the page. The gallery draws no
 * section of its own: the run marks on each row (running, waiting, unread) are
 * the threads element's, from the mount's thread status.
 *
 * The same order of operations as `Assistant.tsx`: create, configure, append.
 * The provider reads the directory on connect, with its own headers, and the
 * chat keeps its own for its requests, so both get the token before insertion.
 */

import { defineAgents } from "@artooi/agents-web-components";
import { defineChat } from "@artooi/agents-web-components/chat";
import { registerMcpApps } from "@artooi/agents-web-components/mcp-apps";
import { defineInbox } from "@artooi/agents-web-components/inbox";
import { defineThreads } from "@artooi/agents-web-components/threads";
import { useEffect, useRef, useState } from "react";
import { authHeaders } from "../api";
import "./home.css";

const NARROW = "(max-width: 640px)";

type WithHeaders = HTMLElement & { headers: Record<string, string> };
type Provider = WithHeaders & { agent: string | null };
type Entry = { id: string; name: string };

export function AgentsHome({ onBoard }: { onBoard: () => void }) {
  const badgeHost = useRef<HTMLDivElement | null>(null);
  const host = useRef<HTMLDivElement | null>(null);
  const providerRef = useRef<Provider | null>(null);
  // The picker is the host's own chrome over the provider's `agents` and `agent`.
  const [agents, setAgents] = useState<Entry[]>([]);
  const [current, setCurrent] = useState<string | null>(null);

  useEffect(() => {
    defineAgents();
    defineChat();
    defineThreads();
    defineInbox();

    const provider = document.createElement("ag-ui-agents") as Provider;
    provider.id = "home";
    provider.setAttribute("data-agents-url", "/agents-home/agents/");
    provider.setAttribute("data-inbox-url", "/agents-home/inbox/");
    provider.style.display = "contents";
    provider.headers = authHeaders();

    const rail = document.createElement("aside");
    rail.className = "home-rail";
    const needsYou = document.createElement("ag-ui-inbox");
    needsYou.setAttribute("variant", "list");
    const threads = document.createElement("ag-ui-threads");
    rail.append(needsYou, threads);

    const chat = document.createElement("ag-ui-chat") as WithHeaders;
    chat.setAttribute("placement", "page");
    chat.setAttribute("title-text", "Agents home");
    // Runs outlive this page, so a thread left mid-answer is joined again when opened.
    chat.setAttribute("data-detach-runs", "");
    chat.headers = authHeaders();
    // The MCP agent's views are read through its own mount, whichever agent is in front.
    registerMcpApps(chat as unknown as Parameters<typeof registerMcpApps>[0], {
      url: "/mcp-agent/mcp-apps/",
    });

    provider.append(rail, chat);
    provider.addEventListener("ag-ui-agents-change", (event) => {
      setAgents((event as CustomEvent<{ agents: Entry[] }>).detail.agents);
      setCurrent(provider.agent);
    });
    provider.addEventListener("ag-ui-agent-change", (event) => {
      setCurrent((event as CustomEvent<{ agent: Entry }>).detail.agent.id);
    });

    // The badge sits outside the provider, in the header, bound by the provider's id.
    const badge = document.createElement("ag-ui-inbox");
    badge.setAttribute("agents", "home");

    // A rail of rows when there is room, a strip of pills when there is not.
    const narrow = window.matchMedia(NARROW);
    const fit = () => threads.setAttribute("variant", narrow.matches ? "pills" : "list");
    fit();
    narrow.addEventListener("change", fit);

    host.current?.appendChild(provider);
    providerRef.current = provider;
    badgeHost.current?.appendChild(badge);
    return () => {
      providerRef.current = null;
      narrow.removeEventListener("change", fit);
      badge.remove();
      provider.remove();
    };
  }, []);

  return (
    <div className="home">
      <header className="topbar home-header">
        <h1>Agents home</h1>
        <nav>
          <button type="button" onClick={onBoard}>
            Scheduling board
          </button>
        </nav>
        <label>
          <span className="home-label">Agent </span>
          <select
            value={current ?? ""}
            onChange={(event) => {
              if (providerRef.current !== null) {
                providerRef.current.agent = event.target.value;
              }
            }}
          >
            {agents.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name}
              </option>
            ))}
          </select>
        </label>
        <div className="home-badge" ref={badgeHost} />
      </header>
      <div ref={host} />
    </div>
  );
}
