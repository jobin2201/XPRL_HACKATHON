"use client";

import Link from "next/link";
import { use, useMemo, useState } from "react";
import { ArrowDownLeft, ArrowLeft, ArrowUpRight, Check, CircleSlash, Copy, Flag, Network, RotateCcw, Siren, Table2 } from "lucide-react";
import { C, FlowChart, LegendKey } from "@/components/charts";
import { Address, Card, Empty, ErrorState, Loading, ResultBadge, ScoreBar, StatusPill, Td, Th, TierBadge, riskColor } from "@/components/ui";
import { type AccountDetail, type CaseStatus, type RuleHit, apiFetch, useApi } from "@/lib/api";
import { dateOnly, dateTime, featureLabel, num, shortHash, usd } from "@/lib/format";

export default function CaseView({ params }: { params: Promise<{ account: string }> }) {
  const { account } = use(params);
  const { data, error, loading, reload } = useApi<AccountDetail>(`/api/accounts/${account}`);

  if (error) return <ErrorState error={error === "account not found" ? `Account ${account} is not in the dataset.` : error} onRetry={reload} />;
  if (loading && !data) return <Loading label="Loading case" className="h-[60vh]" />;
  if (!data) return null;
  return <Case d={data} onChange={reload} />;
}

function Case({ d, onChange }: { d: AccountDetail; onChange: () => void }) {
  const s = d.scores;
  const [copied, setCopied] = useState(false);
  const net = d.totals.received_usd - d.totals.sent_usd;
  const forwarding = d.rules.find((r) => r.id === "rapid_forward");

  return (
    <>
      <Link href="/cases" className="mb-4 inline-flex items-center gap-1.5 text-xs text-ink-2 hover:text-ink">
        <ArrowLeft className="h-3.5 w-3.5" /> Case queue
      </Link>

      {/* header */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wider text-accent">05 · Case details</div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="break-all font-mono text-lg font-medium md:text-xl">{d.account}</h1>
            <button
              onClick={() => {
                navigator.clipboard?.writeText(d.account).then(() => {
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1200);
                });
              }}
              className="rounded p-1 text-muted hover:bg-hover hover:text-ink"
              aria-label="Copy address"
            >
              {copied ? <Check className="h-4 w-4 text-good" /> : <Copy className="h-4 w-4" />}
            </button>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-2">
            <TierBadge tier={d.tier} />
            <StatusPill status={d.status.status} />
            <span className="text-muted">
              Active {dateOnly(d.totals.first_seen)} – {dateOnly(d.totals.last_seen)} · {num(d.totals.tx_count)} transactions
            </span>
            {s.labelled && <span className="rounded border border-line px-1.5 py-0.5 text-[11px] text-muted">Training label: {s.label === 1 ? "suspicious" : "normal"}</span>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href={`/network?account=${d.account}`} className="inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-xs text-ink-2 hover:bg-hover">
            <Network className="h-3.5 w-3.5" /> Network
          </Link>
          <Link href={`/transactions?account=${d.account}`} className="inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-xs text-ink-2 hover:bg-hover">
            <Table2 className="h-3.5 w-3.5" /> Transactions
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* scores */}
        <Card title="Risk assessment" subtitle={d.risk_formula} className="xl:col-span-2">
          <div className="grid gap-6 sm:grid-cols-[auto_1fr]">
            <div>
              <div className="text-xs text-ink-2">Combined risk</div>
              <div className="mt-1 text-5xl font-semibold tracking-tight" style={{ color: "var(--ink)" }}>
                {s.risk_score.toFixed(2)}
              </div>
              <div className="mt-2 h-1.5 w-40 overflow-hidden rounded-full bg-[#1b2c48]">
                <div className="h-full rounded-full" style={{ width: `${s.risk_score * 100}%`, background: riskColor(s.risk_score) }} />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <ScoreCell label="Supervised model" hint={s.model_score === null ? "No labels in this dataset" : "Random forest probability"} value={s.model_score} />
              <ScoreCell label="Anomaly" hint="Isolation Forest percentile" value={s.anomaly_score} />
              <ScoreCell label="Rule score" hint={`${d.rules.length} of ${d.rules.length + d.rules_not_triggered.length} rules`} value={s.rule_score / 100} display={`${s.rule_score} / 100`} />
            </div>
          </div>
        </Card>

        <DecisionCard account={d.account} status={d.status} onChange={onChange} />
      </div>

      {/* money */}
      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Money received versus sent"
          subtitle="Successful payments per day, USD at daily rates"
          actions={
            <LegendKey
              items={[
                { label: "Received", color: C.s1 },
                { label: "Sent", color: C.s2 },
              ]}
            />
          }
        >
          {d.timeline.length ? <FlowChart data={d.timeline} granularity={d.granularity} /> : <Empty>No successful payments.</Empty>}
        </Card>
        <Card title="Flow summary">
          <dl className="space-y-3 text-[13px]">
            <SumRow icon={<ArrowDownLeft className="h-4 w-4" style={{ color: C.s1 }} />} label="Received" value={usd(d.totals.received_usd)} sub={`${num(s.n_received)} payments from ${num(s.n_unique_src)} sources`} />
            <SumRow icon={<ArrowUpRight className="h-4 w-4" style={{ color: C.s2 }} />} label="Sent" value={usd(d.totals.sent_usd)} sub={`${num(s.n_sent)} transactions to ${num(s.n_unique_dest)} destinations`} />
            <div className="border-t border-line pt-3">
              <SumRow label="Net position" value={`${net >= 0 ? "+" : "−"}${usd(Math.abs(net))}`} sub={d.totals.sent_usd > 0 ? `Received / sent ratio ${(d.totals.received_usd / d.totals.sent_usd).toFixed(2)}` : "No outgoing value"} />
            </div>
          </dl>
        </Card>
      </div>

      {/* rules */}
      <Card className="mt-4" title="Rule-by-rule explanation" subtitle="Each typology rule, what it checks, and the evidence it found for this account." bodyClass="p-0">
        <div className="divide-y divide-line">
          {d.rules.map((r) => (
            <RuleRow key={r.id} r={r} account={d.account} />
          ))}
          {d.rules_not_triggered.map((r) => (
            <div key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-2.5 text-[13px]">
              <span className="inline-flex w-44 items-center gap-2 text-muted">
                <CircleSlash className="h-3.5 w-3.5" /> {r.name}
              </span>
              <span className="text-xs text-muted">Not triggered · {r.description}</span>
            </div>
          ))}
        </div>
      </Card>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Rapid-forwarding evidence" subtitle="Incoming payments passed on to a different account within 30 minutes" bodyClass="p-0">
          {forwarding?.evidence.examples?.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead className="border-b border-line">
                  <tr>
                    <Th>From</Th>
                    <Th className="text-right">In</Th>
                    <Th>To</Th>
                    <Th className="text-right">Out</Th>
                    <Th className="text-right">Kept</Th>
                    <Th className="text-right">Delay</Th>
                  </tr>
                </thead>
                <tbody>
                  {forwarding.evidence.examples.map((e, i) => {
                    const inUsd = Number(e.in_usd), outUsd = Number(e.out_usd);
                    const toMs = (v: unknown) => new Date(String(v).replace(" ", "T") + "Z").getTime();
                    const delay = (toMs(e.out_ts) - toMs(e.in_ts)) / 60000;
                    return (
                      <tr key={i} className="border-b border-line last:border-0">
                        <Td><Address value={String(e.src)} /></Td>
                        <Td className="tnum text-right">{usd(inUsd)}</Td>
                        <Td><Address value={String(e.dst)} /></Td>
                        <Td className="tnum text-right">{usd(outUsd)}</Td>
                        <Td className="tnum text-right text-ink-2">{usd(inUsd - outUsd)}</Td>
                        <Td className="tnum text-right text-ink-2">{delay.toFixed(0)} min</Td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="border-t border-line px-5 py-2.5 text-xs text-muted">
                {String(forwarding.evidence.count)} forwards in total · median delay {String(forwarding.evidence.median_delay_min)} min · longest chain {String(forwarding.evidence.longest_chain)} hop(s)
              </p>
            </div>
          ) : (
            <Empty>No payments were forwarded on within 30 minutes.</Empty>
          )}
        </Card>

        <Card title="Top counterparties" subtitle="By total value exchanged" bodyClass="p-0">
          {d.counterparties.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead className="border-b border-line">
                  <tr>
                    <Th>Account</Th>
                    <Th className="text-right">Received from</Th>
                    <Th className="text-right">Sent to</Th>
                    <Th>Risk</Th>
                  </tr>
                </thead>
                <tbody>
                  {d.counterparties.map((c) => (
                    <tr key={c.counterparty} className="border-b border-line last:border-0">
                      <Td>
                        <span className="inline-flex items-center gap-1.5">
                          <Address value={c.counterparty} />
                          {c.flagged && <Flag className="h-3 w-3 text-serious" aria-label="flagged" />}
                          {c.count_in > 0 && c.count_out > 0 && <span className="rounded border border-line px-1 text-[10px] text-ink-2">two-way</span>}
                        </span>
                      </Td>
                      <Td className="tnum text-right">{c.sum_in ? <>{usd(c.sum_in)} <span className="text-muted">· {c.count_in}</span></> : <span className="text-muted">—</span>}</Td>
                      <Td className="tnum text-right">{c.sum_out ? <>{usd(c.sum_out)} <span className="text-muted">· {c.count_out}</span></> : <span className="text-muted">—</span>}</Td>
                      <Td>{c.risk_score !== null ? <ScoreBar value={c.risk_score} color={riskColor(c.risk_score)} width={40} /> : "—"}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty>No counterparties.</Empty>
          )}
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Activity timeline" subtitle="Most recent first" bodyClass="p-0">
          <Timeline d={d} />
        </Card>
        <Card title="How this account differs" subtitle="Largest robust z-scores against the median account. These describe behaviour, not causes.">
          <ul className="space-y-3">
            {d.deviations.map((v) => (
              <li key={v.feature}>
                <div className="flex items-baseline justify-between gap-3 text-[13px]">
                  <span className="text-ink-2">{featureLabel(v.feature)}</span>
                  <span className="tnum text-xs text-ink">{v.z > 0 ? "+" : ""}{v.z.toFixed(1)}σ</span>
                </div>
                <div className="mt-1 text-xs text-muted tnum">
                  {num(v.value, 2)} here vs {num(v.median, 2)} typical
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}

function ScoreCell({ label, hint, value, display }: { label: string; hint: string; value: number | null; display?: string }) {
  const na = value === null || value === undefined;
  return (
    <div className="rounded-md border border-line bg-bg/40 px-4 py-3">
      <div className="text-xs text-ink-2">{label}</div>
      <div className={`tnum mt-1 text-xl font-semibold ${na ? "text-muted" : ""}`}>{na ? "n/a" : (display ?? value.toFixed(2))}</div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-[#1b2c48]">
        {!na && <div className="h-full rounded-full bg-accent-strong" style={{ width: `${Math.min(1, value) * 100}%` }} />}
      </div>
      <div className="mt-1.5 text-[11px] text-muted">{hint}</div>
    </div>
  );
}

function SumRow({ icon, label, value, sub }: { icon?: React.ReactNode; label: string; value: string; sub: string }) {
  return (
    <div className="flex gap-3">
      <div className="mt-0.5 w-4">{icon}</div>
      <div className="flex-1">
        <div className="flex items-baseline justify-between">
          <dt className="text-ink-2">{label}</dt>
          <dd className="tnum text-[15px] font-semibold">{value}</dd>
        </div>
        <div className="text-xs text-muted">{sub}</div>
      </div>
    </div>
  );
}

const EVIDENCE_SKIP = new Set(["summary", "examples", "codes"]);
const EX_LABELS: Record<string, string> = {
  tx_hash: "Hash", timestamp: "Time", destination: "To", account: "From", amount_usd: "USD", back_usd: "Returned USD",
  fee: "Fee", result: "Result", in_ts: "Received", src: "From", out_ts: "Forwarded", dst: "To", in_usd: "In USD", out_usd: "Out USD",
};

function RuleRow({ r, account }: { r: RuleHit; account: string }) {
  const [open, setOpen] = useState(false);
  const ev = r.evidence;
  const metrics = Object.entries(ev).filter(([k]) => !EVIDENCE_SKIP.has(k));
  const examples = ev.examples ?? [];
  const cols = examples.length ? Object.keys(examples[0]) : [];
  return (
    <div className="px-5 py-4">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
        <div className="flex w-44 items-center gap-2">
          <Siren className="h-3.5 w-3.5 text-serious" />
          <span className="text-[13px] font-medium text-ink">{r.name}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] text-ink">{ev.summary}</div>
          <div className="mt-0.5 text-xs text-muted">{r.description}</div>
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
            {metrics.map(([k, v]) => (
              <span key={k} className="text-ink-2">
                <span className="text-muted">{k.replaceAll("_", " ")}:</span> <span className="tnum text-ink">{typeof v === "number" ? num(v, 2) : String(v)}</span>
              </span>
            ))}
            {"codes" in ev && ev.codes ? (
              <span className="text-ink-2">
                <span className="text-muted">codes:</span>{" "}
                <span className="font-mono">{Object.entries(ev.codes as Record<string, number>).map(([c, n]) => `${c} ×${n}`).join(", ")}</span>
              </span>
            ) : null}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="tnum rounded border border-line-strong px-1.5 py-0.5 text-xs text-accent">+{r.weight} pts</span>
          {examples.length > 0 && (
            <button onClick={() => setOpen(!open)} className="text-xs text-accent hover:underline">
              {open ? "Hide" : "Show"} {examples.length} example{examples.length > 1 ? "s" : ""}
            </button>
          )}
        </div>
      </div>
      {open && (
        <div className="mt-3 overflow-x-auto rounded-md border border-line">
          <table className="w-full text-[12px]">
            <thead className="border-b border-line bg-bg/40">
              <tr>
                {cols.map((c) => (
                  <Th key={c}>{EX_LABELS[c] ?? c}</Th>
                ))}
              </tr>
            </thead>
            <tbody>
              {examples.map((e, i) => (
                <tr key={i} className="border-b border-line last:border-0">
                  {cols.map((c) => {
                    const v = e[c];
                    let cell: React.ReactNode = String(v ?? "—");
                    if (c === "tx_hash") cell = <Link className="font-mono text-ink-2 hover:text-accent" href={`/transactions?q=${v}`}>{shortHash(String(v))}</Link>;
                    else if (["destination", "account", "src", "dst"].includes(c)) cell = v === account ? <span className="text-muted">this account</span> : <Address value={String(v)} />;
                    else if (c.includes("usd")) cell = usd(Number(v));
                    else if (c === "result") cell = <ResultBadge result={String(v)} />;
                    else if (c === "fee") cell = `${num(Number(v))} drops`;
                    return (
                      <Td key={c} className={c.includes("usd") || c === "fee" ? "tnum" : ""}>
                        {cell}
                      </Td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Timeline({ d }: { d: AccountDetail }) {
  const [n, setN] = useState(30);
  const groups = useMemo(() => {
    const g: Record<string, typeof d.transactions> = {};
    for (const t of d.transactions.slice(0, n)) {
      const day = t.timestamp.slice(0, 10);
      (g[day] ??= []).push(t);
    }
    return Object.entries(g);
  }, [d, n]);
  if (!d.transactions.length) return <Empty>No transactions.</Empty>;
  return (
    <div>
      {groups.map(([day, txs]) => (
        <div key={day}>
          <div className="sticky top-14 border-b border-line bg-surface/95 px-5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-muted backdrop-blur">{dateOnly(day + "T00:00:00Z")}</div>
          <ul className="divide-y divide-line">
            {txs.map((t) => {
              const out = t.direction === "out";
              const other = out ? t.destination : t.account;
              return (
                <li key={t.tx_hash} className="grid grid-cols-[20px_64px_1fr_auto] items-center gap-3 px-5 py-2 text-[13px]">
                  {out ? <ArrowUpRight className="h-4 w-4" style={{ color: C.s2 }} /> : <ArrowDownLeft className="h-4 w-4" style={{ color: C.s1 }} />}
                  <span className="tnum text-xs text-muted">{dateTime(t.timestamp).split(", ")[1]?.replace(" UTC", "")}</span>
                  <span className="min-w-0 truncate text-ink-2">
                    {t.tx_type === "Payment" ? (
                      <>
                        {out ? "Sent to " : "Received from "}
                        <Address value={other} />
                      </>
                    ) : (
                      <span>{t.tx_type}</span>
                    )}
                    {t.result !== "tesSUCCESS" && <span className="ml-2"><ResultBadge result={t.result} /></span>}
                    {t.fee >= 1000 && <span className="ml-2 text-xs text-serious">fee {num(t.fee)} drops</span>}
                  </span>
                  <span className="tnum text-right">{t.tx_type === "Payment" ? usd(t.amount_usd) : ""}</span>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
      {n < d.transactions.length && (
        <button onClick={() => setN(n + 50)} className="w-full border-t border-line py-2.5 text-xs text-accent hover:bg-hover">
          Show more ({d.transactions.length - n} remaining{d.totals.tx_count > d.transactions.length ? `, ${d.totals.tx_count - d.transactions.length} more in Transaction Explorer` : ""})
        </button>
      )}
    </div>
  );
}

function DecisionCard({ account, status, onChange }: { account: string; status: AccountDetail["status"]; onChange: () => void }) {
  const [note, setNote] = useState(status.note);
  const [busy, setBusy] = useState<CaseStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function set(s: CaseStatus) {
    setBusy(s);
    setErr(null);
    try {
      await apiFetch(`/api/accounts/${account}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: s, note }) });
      onChange();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const btn = "inline-flex items-center justify-center gap-1.5 rounded-md border px-3 py-1.5 text-xs disabled:opacity-50";
  return (
    <Card title="Analyst decision" subtitle={status.updated_at ? `Last updated ${dateTime(status.updated_at)}` : "No decision recorded yet"}>
      <div className="mb-3 flex items-center gap-2 text-xs text-ink-2">
        Current status: <StatusPill status={status.status} />
      </div>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={3}
        placeholder="Add a note for the case file (optional)"
        className="w-full resize-none rounded-md border border-line bg-bg px-3 py-2 text-[13px] text-ink placeholder:text-muted focus:border-line-strong focus:outline-none"
      />
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button disabled={!!busy} onClick={() => set("review")} className={`${btn} border-accent-strong/60 bg-accent-strong/15 text-ink hover:bg-accent-strong/25`}>
          <Flag className="h-3.5 w-3.5 text-accent" /> Mark for review
        </button>
        <button disabled={!!busy} onClick={() => set("escalated")} className={`${btn} border-line-strong text-ink hover:bg-hover`}>
          <Siren className="h-3.5 w-3.5 text-serious" /> Escalate
        </button>
        <button disabled={!!busy} onClick={() => set("dismissed")} className={`${btn} border-line text-ink-2 hover:bg-hover`}>
          <CircleSlash className="h-3.5 w-3.5" /> Dismiss flag
        </button>
        <button disabled={!!busy || status.status === "open"} onClick={() => set("open")} className={`${btn} border-line text-ink-2 hover:bg-hover`}>
          <RotateCcw className="h-3.5 w-3.5" /> Reopen
        </button>
      </div>
      {err && <p className="mt-2 text-xs text-serious">{err}</p>}
      <p className="mt-3 text-[11px] text-muted">Decisions are saved to data/processed/case_status.json.</p>
    </Card>
  );
}
