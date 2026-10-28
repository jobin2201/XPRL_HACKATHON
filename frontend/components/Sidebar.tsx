"use client";

// Navigation for the LightGBM v2 dashboard.
// Phones and tablets (< 1024px): an off-canvas drawer that slides in from the left (☰ in the top bar).
// Laptops/desktops (>= 1024px): a sticky sidebar; "Collapse" shrinks it to icons. The collapsed look comes
// from <html data-sidebar="collapsed"> + CSS (globals.css: .sb, .sb-label, .sb-fade, .sb-hide, .sb-chevron),
// so the markup never differs between server and browser.
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Activity, ArrowLeftRight, BrainCircuit, ChevronsLeft, LayoutDashboard, Network, ShieldAlert, X } from "lucide-react";
import { useShell } from "./Shell";

export const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, n: "01" },
  { href: "/flagged", label: "Transactions", icon: ArrowLeftRight, n: "02" },
  { href: "/graph", label: "Network graph", icon: Network, n: "03" },
  { href: "/models", label: "Models", icon: BrainCircuit, n: "04" },
  { href: "/scoring?tab=evaluation", label: "Validation", icon: ShieldAlert, n: "05" },
];

function isActive(pathname: string, tab: string, href: string) {
  const [path, query] = href.split("?");
  const hrefTab = new URLSearchParams(query ?? "").get("tab");
  return pathname.startsWith(path) && (hrefTab === null || hrefTab === tab);
}

function LinkList({ active, onNavigate }: { active: (href: string) => boolean; onNavigate: () => void }) {
  return (
    <>
      {NAV.map(({ href, label, icon: Icon, n }) => {
        const on = active(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            title={label}
            className={`group relative flex items-center gap-3 overflow-hidden rounded-lg px-2.5 py-2.5 text-[13px] transition-all duration-200 ${
              on ? "bg-surface-2 text-ink shadow-[inset_3px_0_0_var(--accent)]" : "text-ink-2 hover:translate-x-0.5 hover:bg-hover hover:text-ink"
            }`}
          >
            <Icon className={`h-[18px] w-[18px] shrink-0 transition-colors ${on ? "text-accent" : "text-muted group-hover:text-ink-2"}`} strokeWidth={1.9} />
            <span className="sb-label flex-1 whitespace-nowrap transition-all duration-300">{label}</span>
            <span className="sb-fade tnum text-[10px] text-muted transition-opacity duration-300">{n}</span>
          </Link>
        );
      })}
    </>
  );
}

function ActiveLinks({ onNavigate }: { onNavigate: () => void }) {
  const pathname = usePathname();
  const tab = useSearchParams().get("tab") ?? "evaluation";
  return <LinkList active={(href) => isActive(pathname, tab, href)} onNavigate={onNavigate} />;
}

export function Sidebar() {
  const { open, setOpen, toggleCollapsed } = useShell();
  const close = () => setOpen(false);
  return (
    <>
      {/* backdrop for the drawer (phones and tablets) */}
      <div
        onClick={close}
        className={`fixed inset-0 z-40 bg-black/45 backdrop-blur-[2px] transition-opacity duration-300 lg:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        aria-hidden
      />
      <aside
        className={`sb fixed inset-y-0 left-0 z-50 flex w-[min(18rem,85vw)] shrink-0 flex-col border-r border-line bg-panel shadow-2xl transition-[transform,width] duration-300 ease-[cubic-bezier(.22,1,.36,1)] lg:sticky lg:top-0 lg:h-screen lg:w-60 lg:translate-x-0 lg:shadow-none ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Main navigation"
      >
        <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-line px-4">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-line-strong bg-surface-2 shadow-[0_0_18px_var(--glow)]">
            <Activity className="h-4 w-4 text-accent" strokeWidth={2.25} />
          </div>
          <div className="sb-label overflow-hidden leading-tight transition-all duration-300">
            <div className="whitespace-nowrap text-[13px] font-semibold tracking-tight">Ledgerwatch</div>
            <div className="whitespace-nowrap text-[11px] text-muted">XRPL fraud detection</div>
          </div>
          <button onClick={close} className="ml-auto rounded-md p-1.5 text-muted hover:bg-hover hover:text-ink lg:hidden" aria-label="Close menu">
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto overflow-x-hidden px-3 py-4">
          <div className="sb-fade px-2 pb-2 text-[11px] font-medium uppercase tracking-wider text-muted transition-opacity">Workspace</div>
          <Suspense fallback={<LinkList active={() => false} onNavigate={close} />}>
            <ActiveLinks onNavigate={close} />
          </Suspense>
        </nav>

        <div className="sb-hide border-t border-line px-4 py-3 text-[11px] leading-relaxed text-muted">
          <div className="mb-0.5 font-medium text-ink-2">LightGBM v2 model</div>
          191 features · grouped validation AP 61.6
        </div>
        <button
          onClick={toggleCollapsed}
          className="hidden items-center gap-2 border-t border-line px-5 py-3 text-xs text-muted transition-colors hover:bg-hover hover:text-ink lg:flex"
          aria-label="Collapse or expand the sidebar"
        >
          <ChevronsLeft className="sb-chevron h-4 w-4 shrink-0 transition-transform duration-300" />
          <span className="sb-fade whitespace-nowrap transition-opacity duration-300">Collapse</span>
        </button>
      </aside>
    </>
  );
}

// kept so older imports still work; the drawer replaces the old horizontal mobile bar
export function MobileNav() {
  return null;
}
