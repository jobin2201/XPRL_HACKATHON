"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { ActivityChart, C, HBarChart, LegendKey, RiskHistogram, ruleBarData } from "@/components/charts";
import { Address, Card, ErrorState, Loading, PageHeader, RuleChip, ScoreBar, StatTile, StatusPill, Td, Th, TierBadge, riskColor } from "@/components/ui";
import { type Overview, useApi } from "@/lib/api";
import { dateOnly, dateTime, num, pct, shortHash, usd } from "@/lib/format";

export default function OverviewPage() {
  const { data, error, loading, reload } = useApi<Overview>("/api/overview");
  const router = useRouter();

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading && !data) return <Loading label="Loading overview" className="h-[60vh]" />;
  if (!data) return null;
  const k = data.kpis;
  const tierTotal = Object.values(data.tiers).reduce((a, b) => a + b, 0);

  return (
    <>
      <PageHeader
        eyebrow="01 · Overview"
        title="Monitoring overview"
        actions={
          <Link href="/investigations" className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-xs text-ink hover:bg-hover">
            Open investigation queue <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatTile label="Transactions analysed" value={num(k.transactions)} sub={`${dateOnly(k.start)} – ${dateOnly(k.end)}`} />
        <StatTile label="Accounts monitored" value={num(k.accounts)} sub="Senders and receivers" />
        <StatTile label="Flagged for review" value={num(k.flagged)} tone="critical" sub={`${k.critical} critical · ${k.high} high`} />
        <StatTile
          label="Value moved"
          value={usd(k.usd_volume, { compact: true })}
          sub={k.self_payments ? `Between accounts · ${num(k.self_payments)} self-payments excluded` : "USD at hourly market rates"}
        />
        <StatTile label="Cases in review" value={num(k.under_review)} tone="accent" sub="Marked by analysts" />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Activity over time"
          subtitle={`Transactions per ${data.granularity}, and those sent or received by a flagged account`}
          actions={
            <LegendKey
              items={[
                { label: "All transactions", color: C.s1, kind: "line" },
                { label: "Touching flagged accounts", color: C.s2, kind: "line" },
              ]}
            />
          }
        >
          <ActivityChart data={data.activity} granularity={data.granularity} />
        </Card>

        <Card title="Risk tiers" subtitle="Accounts by combined risk score">
          <div className="space-y-3.5">
            {(["critical", "high", "medium", "low"] as const).map((t) => {
              const n = data.tiers[t];
              return (
                <Link key={t} href={`/investigations?tier=${t}`} className="group block">
                  <div className="mb-1.5 flex items-center justify-between text-xs">
                    <TierBadge tier={t} />
                    <span className="tnum text-ink">
                      {num(n)} <span className="text-muted">· {pct(n / tierTotal, 1)}</span>
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[#1b2c48]">
                    <div className="h-full rounded-full transition-opacity group-hover:opacity-80" style={{ width: `${Math.max(1.5, (n / tierTotal) * 100)}%`, background: t === "low" ? "#33476a" : riskColor(t === "critical" ? 0.8 : t === "high" ? 0.6 : 0.4) }} />
                  </div>
                </Link>
              );
            })}
          </div>
          <p className="mt-5 border-t border-line pt-3 text-xs leading-relaxed text-muted">
            Critical ≥ 0.75 · High ≥ 0.50 · Medium ≥ 0.30. An account is flagged at risk ≥ 0.40 or when rules add up to 30+ points.
          </p>
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Rule triggers" subtitle="Rules that matched at least one account. Click a rule to filter the queue.">
          <HBarChart data={ruleBarData(data.rule_counts.filter((r) => r.count > 0))} labelWidth={140} onClick={(id) => router.push(`/investigations?rule=${id}`)} />
        </Card>
        <Card
          title="Risk score distribution"
          subtitle="Accounts per 0.05 band. Square-root scale so the small high-risk tail stays visible."
          actions={
            <LegendKey
              items={[
                { label: "Low", color: C.deemph },
                { label: "Medium", color: C.warning },
                { label: "High", color: C.serious },
                { label: "Critical", color: C.critical },
              ]}
            />
          }
        >
          <RiskHistogram data={data.score_distribution} />
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Priority shortlist"
          subtitle="Highest combined risk. Open a case to see the evidence."
          bodyClass="p-0"
          actions={
            <Link href="/investigations" className="text-xs text-accent hover:underline">
              View all
            </Link>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead className="border-b border-line">
                <tr>
                  <Th>Account</Th>
                  <Th>Tier</Th>
                  <Th>Risk</Th>
                  <Th>Triggered rules</Th>
                  <Th className="text-right">Sent</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {data.top_accounts.map((a) => (
                  <tr key={a.account} onClick={() => router.push(`/cases/${a.account}`)} className="cursor-pointer border-b border-line last:border-0 hover:bg-hover">
                    <Td>
                      <Address value={a.account} />
                    </Td>
                    <Td>
                      <TierBadge tier={a.tier} />
                    </Td>
                    <Td>
                      <ScoreBar value={a.risk_score} color={riskColor(a.risk_score)} />
                    </Td>
                    <Td>
                      <div className="flex gap-1">
                        {a.rules.length ? a.rules.slice(0, 2).map((r) => <RuleChip key={r} id={r} />) : <span className="text-xs text-muted">Model / anomaly only</span>}
                        {a.rules.length > 2 && <span className="text-[11px] text-muted">+{a.rules.length - 2}</span>}
                      </div>
                    </Td>
                    <Td className="tnum text-right text-ink-2">{usd(a.usd_sent_total, { compact: true })}</Td>
                    <Td>
                      <StatusPill status={a.status} />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Recent flagged activity" subtitle="Latest transactions involving flagged accounts" bodyClass="p-0">
          <ul className="divide-y divide-line">
            {data.recent_flagged_tx.map((t) => (
              <li key={t.tx_hash} className="px-5 py-3">
                <div className="flex items-center justify-between gap-3">
                  <Link href={`/transactions?q=${t.tx_hash}`} className="font-mono text-[12px] text-ink-2 hover:text-accent">
                    {shortHash(t.tx_hash)}
                  </Link>
                  {t.tx_type === "Payment" ? <span className="tnum text-[13px] font-medium">{usd(t.amount_usd)}</span> : <span className="text-xs text-ink-2">{t.tx_type}</span>}
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-xs text-muted">
                  <Address value={t.account} />
                  {t.destination && (
                    <>
                      <ArrowUpRight className="h-3 w-3" />
                      <Address value={t.destination} />
                    </>
                  )}
                  <span className="ml-auto">{dateTime(t.timestamp)}</span>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
