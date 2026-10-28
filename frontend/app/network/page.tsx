"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Crosshair, ExternalLink, X } from "lucide-react";
import { C, LegendKey } from "@/components/charts";
import { NetworkGraph, PATTERN_META, type Pattern } from "@/components/NetworkGraph";
import { Address, Card, Empty, ErrorState, Loading, PageHeader, RuleChip, ScoreBar, Segmented, TierBadge, inputCls, riskColor } from "@/components/ui";
import { type NetNode, type Network, qs, useApi } from "@/lib/api";
import { num, usd } from "@/lib/format";

export default function NetworkPage() {
  return (
    <Suspense fallback={<Loading className="h-[60vh]" />}>
      <NetworkView />
    </Suspense>
  );
}

function NetworkView() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const account = sp.get("account") ?? "";
  const depth = sp.get("depth") ?? "1";
  const start = sp.get("start") ?? "";
  const end = sp.get("end") ?? "";
  const minUsd = sp.get("min_usd") ?? "";
  const maxNodes = sp.get("max_nodes") ?? "80";

  const [acctInput, setAcctInput] = useState(account);
  const [minInput, setMinInput] = useState(minUsd);
  const [active, setActive] = useState<Set<Pattern>>(new Set());
  const [selected, setSelected] = useState<string | null>(account || null);

  function update(patch: Record<string, string | null>) {
    const p = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
  }

  // when the focus account changes (URL), sync the input and select it
  const [prevAccount, setPrevAccount] = useState(account);
  if (prevAccount !== account) {
    setPrevAccount(account);
    setAcctInput(account);
    setSelected(account || null);
  }

  useEffect(() => {
    const t = setTimeout(() => minInput !== minUsd && update({ min_usd: minInput || null }), 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minInput]);

  const path = `/api/network${qs({ account, depth: account ? depth : undefined, start, end, min_usd: minUsd, max_nodes: maxNodes })}`;
  const { data, error, loading, reload } = useApi<Network>(path);

  const counts = useMemo(() => {
    const c: Record<Pattern, number> = { fan_out: 0, fan_in: 0, cycle: 0, peel_chain: 0 };
    data?.nodes.forEach((n) => n.patterns.forEach((p) => c[p]++));
    return c;
  }, [data]);

  const toggle = (p: Pattern) =>
    setActive((s) => {
      const n = new Set(s);
      if (n.has(p)) n.delete(p);
      else n.add(p);
      return n;
    });

  const sel = data?.nodes.find((n) => n.id === selected) ?? null;

  return (
    <>
      <PageHeader
        eyebrow="03 · Network analysis"
        title="Money-flow network"
      />

      <Card bodyClass="p-0">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              update({ account: acctInput.trim() || null });
            }}
            className="flex items-center gap-2"
          >
            <input value={acctInput} onChange={(e) => setAcctInput(e.target.value)} placeholder="Focus account address" className={`${inputCls} w-64 font-mono`} />
            {account && (
              <button type="button" onClick={() => update({ account: null, depth: null })} className="rounded-md border border-line px-2 py-1.5 text-xs text-ink-2 hover:bg-hover">
                Clear
              </button>
            )}
          </form>
          {account && (
            <Segmented
              value={depth}
              onChange={(v) => update({ depth: v })}
              options={[
                { value: "1", label: "1 hop" },
                { value: "2", label: "2 hops" },
              ]}
            />
          )}
          <label className="flex items-center gap-1.5 text-xs text-muted">
            From
            <input type="date" value={start} min={data?.range.start} max={data?.range.end} onChange={(e) => update({ start: e.target.value || null })} className={inputCls} />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-muted">
            To
            <input type="date" value={end} min={data?.range.start} max={data?.range.end} onChange={(e) => update({ end: e.target.value || null })} className={inputCls} />
          </label>
          <input value={minInput} onChange={(e) => setMinInput(e.target.value.replace(/[^\d.]/g, ""))} placeholder="Min payment USD" className={`${inputCls} w-32`} />
          <select value={maxNodes} onChange={(e) => update({ max_nodes: e.target.value })} className={inputCls} aria-label="Maximum nodes">
            {["40", "80", "150", "250"].map((v) => (
              <option key={v} value={v}>
                {v} nodes max
              </option>
            ))}
          </select>
          <span className="tnum ml-auto text-xs text-muted">{data ? `${num(data.nodes.length)} accounts · ${num(data.edges.length)} links` : ""}</span>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-2.5">
          <span className="mr-1 text-xs text-muted">Highlight</span>
          {(Object.keys(PATTERN_META) as Pattern[]).map((p) => {
            const on = active.has(p);
            return (
              <button
                key={p}
                onClick={() => toggle(p)}
                title={PATTERN_META[p].help}
                className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors ${on ? "border-line-strong bg-surface-2 text-ink" : "border-line text-ink-2 hover:bg-hover"}`}
              >
                <span className="h-0.5 w-3 rounded-full" style={{ background: PATTERN_META[p].color }} />
                {PATTERN_META[p].label}
                <span className="tnum text-muted">{counts[p]}</span>
              </button>
            );
          })}
          {active.size > 0 && (
            <button onClick={() => setActive(new Set())} className="text-xs text-accent hover:underline">
              Clear
            </button>
          )}
          <div className="ml-auto">
            <LegendKey
              items={[
                { label: "Critical", color: C.critical, kind: "dot" },
                { label: "High", color: C.serious, kind: "dot" },
                { label: "Medium", color: C.warning, kind: "dot" },
                { label: "Not flagged", color: "#3b5072", kind: "dot" },
              ]}
            />
          </div>
        </div>

        <div className="relative grid grid-cols-1 lg:grid-cols-[1fr_320px]">
          <div className={`min-w-0 transition-opacity ${loading ? "opacity-50" : ""}`}>
            {error ? (
              <div className="p-5">
                <ErrorState error={error} onRetry={reload} />
              </div>
            ) : !data ? (
              <Loading className="h-[560px]" label="Laying out graph" />
            ) : data.nodes.length === 0 ? (
              <Empty>No payments match these filters.</Empty>
            ) : (
              <NetworkGraph data={data} active={active} selected={selected} onSelect={setSelected} />
            )}
          </div>
          <aside className="border-t border-line lg:border-l lg:border-t-0">
            {sel ? <Inspector node={sel} onClose={() => setSelected(null)} onFocus={() => update({ account: sel.id })} isFocus={sel.id === account} /> : <Guide />}
          </aside>
        </div>
      </Card>
    </>
  );
}

function Inspector({ node, onClose, onFocus, isFocus }: { node: NetNode; onClose: () => void; onFocus: () => void; isFocus: boolean }) {
  return (
    <div className="p-5">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wider text-muted">Selected account</div>
          <div className="mt-1 break-all font-mono text-[12px] text-ink">{node.id}</div>
        </div>
        <button onClick={onClose} aria-label="Close" className="rounded p-1 text-muted hover:bg-hover hover:text-ink">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mb-4 flex items-center gap-3">
        <TierBadge tier={node.tier} />
        <ScoreBar value={node.risk_score} color={riskColor(node.risk_score)} width={80} />
      </div>
      <dl className="mb-4 space-y-2 text-[13px]">
        <div className="flex justify-between">
          <dt className="text-ink-2">Sent</dt>
          <dd className="tnum">{usd(node.usd_sent)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-2">Received</dt>
          <dd className="tnum">{usd(node.usd_received)}</dd>
        </div>
      </dl>
      {node.patterns.length > 0 && (
        <div className="mb-4">
          <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted">Network patterns</div>
          <ul className="space-y-1.5">
            {node.patterns.map((p) => (
              <li key={p} className="flex items-start gap-2 text-xs">
                <span className="mt-1.5 h-0.5 w-3 shrink-0 rounded-full" style={{ background: PATTERN_META[p].color }} />
                <span>
                  <span className="text-ink">{PATTERN_META[p].label}</span> <span className="text-muted">· {PATTERN_META[p].help}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mb-5">
        <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted">Rules triggered</div>
        <div className="flex flex-wrap gap-1">{node.rules.length ? node.rules.map((r) => <RuleChip key={r} id={r} />) : <span className="text-xs text-muted">None</span>}</div>
      </div>
      <div className="flex flex-col gap-2">
        <Link href={`/cases/${node.id}`} className="inline-flex items-center justify-center gap-1.5 rounded-md border border-line-strong bg-surface-2 px-3 py-1.5 text-xs text-ink hover:bg-hover">
          Open case <ExternalLink className="h-3.5 w-3.5" />
        </Link>
        {!isFocus && (
          <button onClick={onFocus} className="inline-flex items-center justify-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-xs text-ink-2 hover:bg-hover">
            <Crosshair className="h-3.5 w-3.5" /> Centre graph on this account
          </button>
        )}
        <Link href={`/transactions?account=${node.id}`} className="text-center text-xs text-accent hover:underline">
          Transaction history
        </Link>
      </div>
      <div className="mt-5 border-t border-line pt-3">
        <Address value={node.id} href={`/cases/${node.id}`} />
      </div>
    </div>
  );
}

function Guide() {
  return (
    <div className="space-y-4 p-5 text-xs leading-relaxed text-ink-2">
      <div className="text-[11px] uppercase tracking-wider text-muted">Reading the graph</div>
      {(Object.keys(PATTERN_META) as Pattern[]).map((p) => (
        <div key={p} className="flex gap-2.5">
          <span className="mt-1.5 h-0.5 w-4 shrink-0 rounded-full" style={{ background: PATTERN_META[p].color }} />
          <div>
            <div className="font-medium text-ink">{PATTERN_META[p].label}</div>
            {PATTERN_META[p].help}.
          </div>
        </div>
      ))}
      <p className="border-t border-line pt-3 text-muted">Two-way edges are drawn curved. Thicker edges carry more value. Select a node to isolate its direct connections.</p>
    </div>
  );
}
