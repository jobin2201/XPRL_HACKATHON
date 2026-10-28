"use client";

// One payment, joined across the data files: transaction row, transfer legs, block, market rate,
// wallet context, v2 score, the features that pushed the score up, and an on-demand explanation.
import Link from "next/link";
import { useState } from "react";
import { Bot, Network as NetIcon } from "lucide-react";
import { Card, ErrorState, Loading, ScoreBar, Td, Th } from "@/components/ui";
import { useApi } from "@/lib/api";
import { dateTime, num, shortAddr, usd } from "@/lib/format";
import { type V2Detail, scoreColor } from "@/lib/v2";

export default function TxDetail({ hash }: { hash: string }) {
  const { data: d, error, reload } = useApi<V2Detail>(`/api/v2/transactions/${hash}`);
  const [explain, setExplain] = useState<{ source: string; text: string; note?: string } | null>(null);
  const [busy, setBusy] = useState(false);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!d || d.hash !== hash) return <Loading className="h-64" />;

  async function ask() {
    setBusy(true);
    try {
      const r = await fetch(`/api/v2/explain/${hash}`, { method: "POST" });
      setExplain(await r.json());
    } finally {
      setBusy(false);
    }
  }

  const t = d.transaction;
  return (
    <div className="space-y-4">
      <Card
        title={
          <span className="flex flex-wrap items-center gap-2">
            {d.flagged ? (
              <span className="rounded-full bg-[rgba(208,59,59,0.15)] px-2 py-0.5 text-xs font-medium text-critical">Flagged as suspicious</span>
            ) : (
              <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-2">Not flagged</span>
            )}
            {d.top1 && <span className="rounded-full bg-[rgba(236,131,90,0.15)] px-2 py-0.5 text-xs text-serious">Top 1% alert</span>}
          </span>
        }
        actions={
          <Link href={`/graph?tx=${hash}`} className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
            <NetIcon className="h-3.5 w-3.5" /> Show in graph
          </Link>
        }
      >
        <p className="mb-3 break-all font-mono text-[11px] text-ink-2">{hash}</p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <ScoreBar value={d.score} color={scoreColor(d.score)} width={160} />
          <span className="tnum text-2xl font-semibold" style={{ color: scoreColor(d.score) }}>{d.score.toFixed(3)}</span>
          <span className="text-xs text-muted">rank {num(d.rank)} of {num(d.total)} · flag threshold {d.threshold.toFixed(3)}</span>
        </div>
      </Card>

      <Card title="Why the model flagged it" subtitle="Features that pushed this payment's score up the most (LightGBM contributions)">
        {d.reasons.length ? (
          <ol className="space-y-2 text-[13px]">
            {d.reasons.map((r, i) => (
              <li key={r.feature} className="flex gap-3">
                <span className="tnum mt-0.5 w-4 shrink-0 text-muted">{i + 1}</span>
                <span className="flex-1 text-ink">{r.text}</span>
                <span className="tnum shrink-0 text-xs text-serious">+{r.contribution.toFixed(2)}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-[13px] text-muted">
            Reasons appear after running <span className="font-mono">run_model.py --model lightgbm --extra ratios activity patterns --dashboard</span>.
          </p>
        )}
        <div className="mt-4 border-t border-line pt-4">
          <button onClick={ask} disabled={busy} className="inline-flex items-center gap-2 rounded-md border border-line bg-surface-2 px-3 py-1.5 text-xs text-ink hover:bg-hover disabled:opacity-50">
            <Bot className="h-3.5 w-3.5" /> {busy ? "Explaining…" : "Explain with AI (Groq)"}
          </button>
          {explain && (
            <div className="mt-3 rounded-md border border-line bg-bg p-3 text-[13px] leading-relaxed">
              <div className="mb-1 text-[11px] uppercase tracking-wider text-muted">{explain.source}</div>
              <p className="whitespace-pre-line text-ink">{explain.text}</p>
              {explain.note && <p className="mt-2 text-xs text-muted">{explain.note}</p>}
            </div>
          )}
        </div>
      </Card>

      <Card title="Transaction" subtitle="transactions.parquet + blocks.parquet + market_rates.csv" bodyClass="p-0">
        <table className="w-full table-fixed text-[13px]">
          <tbody>
            {[
              ["Time (UTC)", dateTime(String(t.time))],
              ["Sender", <span key="s" className="break-all font-mono text-xs">{String(t.sender)}</span>],
              ["Receiver", <span key="r" className="break-all font-mono text-xs">{String(t.receiver)}</span>],
              ["Delivered", `${t.delivered} · ${usd(Number(t.usd))}`],
              ["Paid with", String(t.source)],
              ["Transfer legs", `${t.legs}${t.conversion ? " (currency conversion)" : " (direct payment)"}`],
              ["Type / result", `${t.type} · ${t.result}`],
              ["Fee", `${t.fee_xrp} XRP`],
              ["Ledger / position", `${num(Number(d.block.ledger_index))} · #${t.position_in_ledger} · closed ${dateTime(String(d.block.close_time))}`],
              ["Price used", d.rate.usd_per_unit ? `${d.rate.asset} = $${d.rate.usd_per_unit.toFixed(4)} (hour ${dateTime(d.rate.hour)})` : "—"],
            ].map(([k, v]) => (
              <tr key={String(k)} className="border-b border-line last:border-0">
                <td className="w-28 px-3 py-2 align-top text-muted sm:w-40 sm:px-4">{k}</td>
                <td className="min-w-0 break-words px-3 py-2 text-ink sm:px-4">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Transfer legs" subtitle="transfers.parquet, joined on TRANSACTION_HASH" bodyClass="p-0 overflow-x-auto">
        <table className="w-full min-w-[440px] text-[13px]">
          <thead className="border-b border-line">
            <tr>
              <Th>Leg</Th>
              <Th>From</Th>
              <Th>To</Th>
              <Th className="text-right">Amount</Th>
              <Th className="text-right">USD</Th>
            </tr>
          </thead>
          <tbody>
            {d.legs.map((l) => (
              <tr key={l.leg} className="border-b border-line last:border-0">
                <Td className="tnum text-muted">{l.leg}</Td>
                <Td className="font-mono text-xs">{shortAddr(l.from)}</Td>
                <Td className="font-mono text-xs">{shortAddr(l.to)}</Td>
                <Td className="tnum text-right">{l.amount.toLocaleString("en-GB", { maximumFractionDigits: 6 })} {l.asset}</Td>
                <Td className="tnum text-right">{l.usd == null ? "—" : usd(l.usd)}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Wallet context (test week)" bodyClass="p-0 overflow-x-auto">
        <table className="w-full min-w-[420px] text-[13px]">
          <tbody>
            {(["sender", "receiver"] as const).map((k) => (
              <tr key={k} className="border-b border-line last:border-0">
                <td className="w-28 px-4 py-2 capitalize text-muted">{k}</td>
                <td className="px-4 py-2 font-mono text-xs">{shortAddr(d.wallets[k].address)}</td>
                <td className="tnum px-4 py-2 text-ink-2">{num(d.wallets[k].payments)} payments</td>
                <td className="tnum px-4 py-2 text-serious">{num(d.wallets[k].flagged)} flagged</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
