"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Fragment, Suspense, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink, Network } from "lucide-react";
import { Address, Card, Empty, ErrorState, Loading, PageHeader, Pager, RuleChip, ScoreBar, Segmented, StatusPill, Td, Th, TierBadge, Toggle, inputCls, riskColor } from "@/components/ui";
import { type AccountDetail, type AccountRow, qs, useApi } from "@/lib/api";
import { RULE_NAMES, featureLabel, num, usd } from "@/lib/format";

type Sort = "risk_score" | "rule_score" | "anomaly_score" | "model_score" | "usd_sent_total";
const LIMIT = 25;

export default function InvestigationsPage() {
  return (
    <Suspense fallback={<Loading className="h-[60vh]" />}>
      <Investigations />
    </Suspense>
  );
}

function Investigations() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const [q, setQ] = useState(sp.get("q") ?? "");
  const [debQ, setDebQ] = useState(q);
  const tier = sp.get("tier") ?? "";
  const rule = sp.get("rule") ?? "";
  const status = sp.get("status") ?? "";
  const flaggedOnly = sp.get("flagged") !== "all";
  const sort = (sp.get("sort") as Sort) ?? "risk_score";
  const order = (sp.get("order") as "asc" | "desc") ?? "desc";
  const offset = Number(sp.get("offset") ?? 0);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebQ(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  function update(patch: Record<string, string | number | null>) {
    const p = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === "") p.delete(k);
      else p.set(k, String(v));
    }
    if (!("offset" in patch)) p.delete("offset");
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
  }

  useEffect(() => {
    if (debQ !== (sp.get("q") ?? "")) update({ q: debQ });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debQ]);

  const path = `/api/accounts${qs({ q: debQ, tier, rule, status, flagged: flaggedOnly ? "true" : undefined, sort, order, limit: LIMIT, offset })}`;
  const { data, error, loading, reload } = useApi<{ total: number; items: AccountRow[] }>(path);

  const sortBy = (k: Sort) => update({ sort: k, order: sort === k && order === "desc" ? "asc" : "desc" });

  return (
    <>
      <PageHeader
        eyebrow="02 · Investigations"
        title="Investigation queue"
      />

      <Card bodyClass="p-0">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by address" className={`${inputCls} w-56`} />
          <Segmented
            value={tier || "all"}
            onChange={(v) => update({ tier: v === "all" ? "" : v })}
            options={[
              { value: "all", label: "All tiers" },
              { value: "critical", label: "Critical" },
              { value: "high", label: "High" },
              { value: "medium", label: "Medium" },
              { value: "low", label: "Low" },
            ]}
          />
          <select value={rule} onChange={(e) => update({ rule: e.target.value })} className={inputCls}>
            <option value="">Any rule</option>
            {Object.entries(RULE_NAMES).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
          <select value={status} onChange={(e) => update({ status: e.target.value })} className={inputCls}>
            <option value="">Any status</option>
            <option value="open">Open</option>
            <option value="review">In review</option>
            <option value="escalated">Escalated</option>
            <option value="dismissed">Dismissed</option>
          </select>
          <Toggle checked={flaggedOnly} onChange={(v) => update({ flagged: v ? null : "all" })} label="Flagged only" />
          <span className="tnum ml-auto text-xs text-muted">{data ? `${num(data.total)} accounts` : ""}</span>
        </div>

        {error ? (
          <div className="p-5">
            <ErrorState error={error} onRetry={reload} />
          </div>
        ) : !data ? (
          <Loading />
        ) : data.items.length === 0 ? (
          <Empty>No accounts match these filters.</Empty>
        ) : (
          <div className={`overflow-x-auto transition-opacity ${loading ? "opacity-60" : ""}`}>
            <table className="w-full text-[13px]">
              <thead className="border-b border-line">
                <tr>
                  <Th className="w-8" />
                  <Th>Account</Th>
                  <Th>Tier</Th>
                  <Th onClick={() => sortBy("risk_score")} active={sort === "risk_score"} dir={order}>
                    Risk
                  </Th>
                  <Th onClick={() => sortBy("rule_score")} active={sort === "rule_score"} dir={order}>
                    Rule score
                  </Th>
                  <Th onClick={() => sortBy("anomaly_score")} active={sort === "anomaly_score"} dir={order}>
                    Anomaly
                  </Th>
                  <Th onClick={() => sortBy("model_score")} active={sort === "model_score"} dir={order}>
                    Model
                  </Th>
                  <Th>Reasons</Th>
                  <Th onClick={() => sortBy("usd_sent_total")} active={sort === "usd_sent_total"} dir={order} className="text-right">
                    Sent
                  </Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <Fragment key={a.account}>
                    <tr onClick={() => setOpen(open === a.account ? null : a.account)} className={`cursor-pointer border-b border-line hover:bg-hover ${open === a.account ? "bg-hover" : ""}`}>
                      <Td className="text-muted">{open === a.account ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</Td>
                      <Td>
                        <Address value={a.account} />
                      </Td>
                      <Td>
                        <TierBadge tier={a.tier} />
                      </Td>
                      <Td>
                        <ScoreBar value={a.risk_score} color={riskColor(a.risk_score)} width={56} />
                      </Td>
                      <Td className="tnum">
                        <span className={a.rule_score ? "text-ink" : "text-muted"}>{a.rule_score}</span>
                        <span className="text-muted"> / 100</span>
                      </Td>
                      <Td>
                        <ScoreBar value={a.anomaly_score} width={44} />
                      </Td>
                      <Td>
                        <ScoreBar value={a.model_score} width={44} />
                      </Td>
                      <Td>
                        <div className="flex max-w-[280px] gap-1 overflow-hidden">
                          {a.rules.length ? a.rules.map((r) => <RuleChip key={r} id={r} />) : <span className="text-xs text-muted">No rule hit</span>}
                        </div>
                      </Td>
                      <Td className="tnum text-right text-ink-2">{usd(a.usd_sent_total, { compact: true })}</Td>
                      <Td>
                        <StatusPill status={a.status ?? "open"} />
                      </Td>
                    </tr>
                    {open === a.account && (
                      <tr className="border-b border-line bg-[#0c172b]">
                        <td colSpan={10} className="px-5 py-4">
                          <Reasons account={a.account} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pager offset={offset} limit={LIMIT} total={data.total} onChange={(o) => update({ offset: o })} />}
      </Card>
    </>
  );
}

function Reasons({ account }: { account: string }) {
  const { data, error } = useApi<AccountDetail>(`/api/accounts/${account}`);
  if (error) return <div className="text-xs text-serious">{error}</div>;
  if (!data) return <Loading className="h-20" />;
  return (
    <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr_auto]">
      <div>
        <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted">Why it was flagged</div>
        {data.rules.length ? (
          <ul className="space-y-2">
            {data.rules.map((r) => (
              <li key={r.id} className="flex gap-3 text-[13px]">
                <span className="tnum w-9 shrink-0 text-right text-xs text-accent">+{r.weight}</span>
                <div>
                  <span className="font-medium text-ink">{r.name}</span>
                  <span className="text-ink-2"> · {r.evidence.summary}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-ink-2">No typology rule fired. The score comes from the supervised model and the anomaly detector, based on the feature deviations shown here.</p>
        )}
      </div>
      <div>
        <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted">Most unusual features</div>
        <ul className="space-y-1.5">
          {data.deviations.slice(0, 4).map((d) => (
            <li key={d.feature} className="flex items-baseline justify-between gap-3 text-[13px]">
              <span className="text-ink-2">{featureLabel(d.feature)}</span>
              <span className="tnum text-xs">
                <span className="text-ink">{num(d.value, 2)}</span>
                <span className="text-muted"> vs median {num(d.median, 2)}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex flex-col gap-2 lg:items-end">
        <Link href={`/cases/${account}`} className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-xs text-ink hover:bg-hover">
          Open case <ExternalLink className="h-3.5 w-3.5" />
        </Link>
        <Link href={`/network?account=${account}`} className="inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-xs text-ink-2 hover:bg-hover">
          View in network <Network className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}
