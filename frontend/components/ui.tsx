"use client";

import { ParallaxHero } from "./ParallaxHero";
import Link from "next/link";
import { AlertOctagon, AlertTriangle, CircleDot, Info, Loader2, ServerCrash, ShieldCheck } from "lucide-react";
import type { CaseStatus, Tier } from "@/lib/api";
import { ruleName, shortAddr } from "@/lib/format";

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: React.ReactNode; actions?: React.ReactNode }) {
  return <ParallaxHero eyebrow={eyebrow} title={title} description={description} actions={actions} />;
}

export function Card({ title, subtitle, actions, children, className = "", bodyClass = "p-5" }: { title?: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode; className?: string; bodyClass?: string }) {
  return (
    <section className={`card-anim min-w-0 rounded-xl border border-line bg-surface ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2 border-b border-line px-4 py-3 sm:px-5 sm:py-3.5">
          <div className="min-w-0">
            {title && <h2 className="text-[13px] font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

export function StatTile({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "critical" | "accent" }) {
  return (
    <div className="card-anim min-w-0 rounded-xl border border-line bg-surface px-4 py-3.5 sm:px-5 sm:py-4">
      <div className="flex items-center gap-1.5 text-xs text-ink-2">
        {tone === "critical" && <span className="h-1.5 w-1.5 rounded-full bg-critical" />}
        {tone === "accent" && <span className="h-1.5 w-1.5 rounded-full bg-accent-strong" />}
        {label}
      </div>
      <div className="mt-1.5 break-words text-[22px] font-semibold leading-tight tracking-tight sm:text-[26px]">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export const TIER_COLOR: Record<Tier, string> = {
  critical: "var(--critical)",
  high: "var(--serious)",
  medium: "var(--warning)",
  low: "var(--low)",
};

const TIER_ICON = { critical: AlertOctagon, high: AlertTriangle, medium: CircleDot, low: ShieldCheck };

export function TierBadge({ tier }: { tier: Tier }) {
  const Icon = TIER_ICON[tier];
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap rounded border border-line px-1.5 py-0.5 text-[11px] font-medium capitalize text-ink-2">
      <Icon className="h-3 w-3" style={{ color: TIER_COLOR[tier] }} strokeWidth={2.25} />
      {tier}
    </span>
  );
}

const STATUS_STYLE: Record<CaseStatus, string> = {
  open: "text-ink-2",
  review: "text-accent",
  escalated: "text-serious",
  dismissed: "text-muted line-through decoration-muted/60",
};
const STATUS_LABEL: Record<CaseStatus, string> = { open: "Open", review: "In review", escalated: "Escalated", dismissed: "Dismissed" };

export function StatusPill({ status }: { status: CaseStatus }) {
  return <span className={`whitespace-nowrap text-[11px] font-medium ${STATUS_STYLE[status]}`}>{STATUS_LABEL[status]}</span>;
}

export function RuleChip({ id, active = true }: { id: string; active?: boolean }) {
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] ${
        active ? "border-line-strong bg-surface-2 text-ink-2" : "border-line text-muted"
      }`}
    >
      {ruleName(id)}
    </span>
  );
}

/** Horizontal meter. Track is a lighter step of the fill so state reads across the whole bar. */
export function ScoreBar({ value, color = "var(--accent-strong)", width = 64 }: { value: number | null; color?: string; width?: number }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return (
      <span className="inline-flex items-center gap-2" title="Not available for this dataset">
        <span className="h-1.5 rounded-full bg-surface-2" style={{ width }} />
        <span className="w-8 text-right text-xs text-muted">n/a</span>
      </span>
    );
  }
  const v = Math.max(0, Math.min(1, value || 0));
  return (
    <span className="inline-flex items-center gap-2">
      <span className="relative h-1.5 overflow-hidden rounded-full bg-surface-2" style={{ width }}>
        <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${v * 100}%`, background: color }} />
      </span>
      <span className="tnum w-8 text-right text-xs text-ink">{v.toFixed(2)}</span>
    </span>
  );
}

export function riskColor(v: number) {
  return v >= 0.75 ? TIER_COLOR.critical : v >= 0.5 ? TIER_COLOR.high : v >= 0.3 ? TIER_COLOR.medium : "var(--accent-strong)";
}

export function Address({ value, href, full = false }: { value: string | null; href?: string | false; full?: boolean }) {
  if (!value) return <span className="text-muted">—</span>;
  const text = full ? value : shortAddr(value);
  const link = href === false ? null : href ?? `/cases/${value}`;
  return link ? (
    <Link href={link} title={value} className="font-mono text-[12px] text-ink hover:text-accent">
      {text}
    </Link>
  ) : (
    <span title={value} className="font-mono text-[12px] text-ink">
      {text}
    </span>
  );
}

export function Loading({ label = "Loading", className = "h-40" }: { label?: string; className?: string }) {
  return (
    <div className={`flex items-center justify-center gap-2 text-xs text-muted ${className}`}>
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: string; onRetry?: () => void }) {
  const offline = /fetch|ECONNREFUSED|500|502|503|504|Failed/i.test(error);
  return (
    <div className="rounded-lg border border-line bg-surface p-6">
      <div className="flex items-start gap-3">
        <ServerCrash className="mt-0.5 h-5 w-5 shrink-0 text-serious" />
        <div className="min-w-0 text-[13px]">
          <div className="font-medium text-ink">{offline ? "Can't reach the pipeline API" : "Request failed"}</div>
          <p className="mt-1 text-ink-2">{offline ? "Start the FastAPI server from the project root:" : error}</p>
          {offline && (
            <pre className="mt-3 overflow-x-auto rounded-md border border-line bg-bg px-3 py-2 font-mono text-xs text-ink-2">
              F:\ana\envs\xrpl_env\python.exe -m uvicorn api.main:app --port 8000
            </pre>
          )}
          {onRetry && (
            <button onClick={onRetry} className="mt-3 rounded-md border border-line-strong px-3 py-1.5 text-xs text-ink hover:bg-hover">
              Retry
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-xs text-muted">
      <Info className="h-4 w-4" /> {children}
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-md border border-line bg-bg p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`rounded px-2.5 py-1 text-xs transition-colors ${value === o.value ? "bg-surface-2 text-ink" : "text-ink-2 hover:text-ink"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export const inputCls =
  "h-8 rounded-md border border-line bg-bg px-2.5 text-xs text-ink placeholder:text-muted focus:border-line-strong focus:outline-none";

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="inline-flex cursor-pointer select-none items-center gap-2 text-xs text-ink-2">
      <span
        role="switch"
        aria-checked={checked}
        tabIndex={0}
        onClick={() => onChange(!checked)}
        onKeyDown={(e) => (e.key === " " || e.key === "Enter") && (e.preventDefault(), onChange(!checked))}
        className={`relative h-4 w-7 rounded-full border transition-colors ${checked ? "border-accent-strong bg-accent-strong/40" : "border-line-strong bg-bg"}`}
      >
        <span className={`absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full transition-all ${checked ? "left-3.5 bg-accent" : "left-0.5 bg-muted"}`} />
      </span>
      {label}
    </label>
  );
}

export function Pager({ offset, limit, total, onChange }: { offset: number; limit: number; total: number; onChange: (o: number) => void }) {
  const end = Math.min(offset + limit, total);
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-3 text-xs text-ink-2">
      <span className="tnum">
        {total === 0 ? "0 results" : `${offset + 1}–${end} of ${total.toLocaleString()}`}
      </span>
      <div className="flex gap-1.5">
        <button disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))} className="rounded-md border border-line px-2.5 py-1 hover:bg-hover disabled:opacity-40">
          Previous
        </button>
        <button disabled={end >= total} onClick={() => onChange(offset + limit)} className="rounded-md border border-line px-2.5 py-1 hover:bg-hover disabled:opacity-40">
          Next
        </button>
      </div>
    </div>
  );
}

export function Th({ children, className = "", onClick, active, dir }: { children?: React.ReactNode; className?: string; onClick?: () => void; active?: boolean; dir?: "asc" | "desc" }) {
  return (
    <th className={`whitespace-nowrap px-3 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-muted first:pl-5 last:pr-5 ${className}`}>
      {onClick ? (
        <button onClick={onClick} className={`inline-flex items-center gap-1 uppercase hover:text-ink ${active ? "text-ink" : ""}`}>
          {children}
          {active && <span aria-hidden>{dir === "asc" ? "↑" : "↓"}</span>}
        </button>
      ) : (
        children
      )}
    </th>
  );
}

export function Td({ children, className = "" }: { children?: React.ReactNode; className?: string }) {
  return <td className={`whitespace-nowrap px-3 py-2.5 first:pl-5 last:pr-5 ${className}`}>{children}</td>;
}

export function ResultBadge({ result }: { result: string }) {
  const ok = result === "tesSUCCESS";
  return (
    <span className={`inline-flex items-center gap-1 font-mono text-[11px] ${ok ? "text-ink-2" : "text-serious"}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-good" : "bg-critical"}`} />
      {result}
    </span>
  );
}
