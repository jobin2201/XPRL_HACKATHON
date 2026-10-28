"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Menu, Search } from "lucide-react";
import { useShell } from "./Shell";
import { ThemeToggle } from "./ThemeToggle";

type ApiState = "checking" | "up" | "down";

export function TopBar() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [api, setApi] = useState<ApiState>("checking");
  const { setOpen } = useShell();

  useEffect(() => {
    let alive = true;
    const ping = () =>
      fetch("/api/health", { cache: "no-store" })
        .then((r) => alive && setApi(r.ok ? "up" : "down"))
        .catch(() => alive && setApi("down"));
    ping();
    const id = setInterval(ping, 15000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const v = q.trim();
    if (!v) return;
    // XRPL classic addresses start with "r"; everything else is treated as a hash / free-text search
    // wallets open in the v2 network graph, transaction hashes in the v2 transaction view
    if (/^r[1-9A-HJ-NP-Za-km-z]{20,40}$/.test(v)) router.push(`/graph?wallet=${v}`);
    else router.push(`/flagged?tx=${encodeURIComponent(v.toUpperCase())}`);
  }

  const dot = api === "up" ? "bg-good" : api === "down" ? "bg-critical" : "bg-muted";
  const label = api === "up" ? "Pipeline API connected" : api === "down" ? "API offline — start uvicorn on :8000" : "Connecting…";

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-line bg-bg/85 px-3 backdrop-blur-md sm:gap-4 sm:px-5 lg:px-8">
      <button onClick={() => setOpen(true)} className="-ml-1 rounded-md p-2 text-ink-2 hover:bg-hover hover:text-ink lg:hidden" aria-label="Open menu">
        <Menu className="h-5 w-5" />
      </button>
      <form onSubmit={submit} className="relative min-w-0 flex-1 lg:max-w-xl">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search a wallet or transaction hash"
          className="h-9 w-full rounded-md border border-line bg-surface pl-9 pr-3 text-[13px] text-ink placeholder:text-muted focus:border-line-strong focus:outline-none"
        />
      </form>
      <div className="ml-auto flex items-center gap-2 whitespace-nowrap text-xs text-ink-2" title={label}>
        <span className={`relative h-2 w-2 rounded-full ${dot}`}>
          {api === "up" && <span className="absolute inset-0 animate-ping rounded-full bg-good opacity-60" />}
        </span>
        <span className="hidden lg:inline">{api === "up" ? "Live data" : api === "down" ? "API offline" : "Connecting"}</span>
      </div>
      <ThemeToggle />
    </header>
  );
}
