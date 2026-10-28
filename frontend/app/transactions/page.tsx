"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ArrowDownLeft, ArrowRight, ArrowUpRight, X } from "lucide-react";
import { Address, Card, Empty, ErrorState, Loading, PageHeader, Pager, ResultBadge, Segmented, Td, Th, Toggle, inputCls } from "@/components/ui";
import { type Tx, qs, useApi } from "@/lib/api";
import { dateTime, num, shortHash, usd } from "@/lib/format";

const LIMIT = 50;

export default function TransactionsPage() {
  return (
    <Suspense fallback={<Loading className="h-[60vh]" />}>
      <Explorer />
    </Suspense>
  );
}

function Explorer() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const get = (k: string) => sp.get(k) ?? "";

  const [q, setQ] = useState(get("q"));
  const [acct, setAcct] = useState(get("account"));
  const [minUsd, setMinUsd] = useState(get("min_usd"));
  const [selected, setSelected] = useState<Tx | null>(null);

  const direction = (get("direction") || "all") as "all" | "in" | "out";
  const failed = get("failed") === "true";
  const dust = get("dust") === "true";
  const flaggedOnly = get("flagged_only") === "true";
  const txType = get("tx_type");
  const offset = Number(get("offset") || 0);

  function update(patch: Record<string, string | number | null>) {
    const p = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === "" || v === "false") p.delete(k);
      else p.set(k, String(v));
    }
    if (!("offset" in patch)) p.delete("offset");
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
  }

  // debounce text inputs into the URL
  useEffect(() => {
    const t = setTimeout(() => {
      if (q !== get("q") || acct !== get("account") || minUsd !== get("min_usd")) update({ q, account: acct, min_usd: minUsd });
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, acct, minUsd]);

  // keep inputs in sync when navigated here from elsewhere (e.g. the top search bar)
  const urlKey = `${get("q")}|${get("account")}`;
  const [prevKey, setPrevKey] = useState(urlKey);
  if (prevKey !== urlKey) {
    setPrevKey(urlKey);
    setQ(get("q"));
    setAcct(get("account"));
  }

  const path = `/api/transactions${qs({
    q: get("q"),
    account: get("account"),
    direction: get("account") ? direction : undefined,
    failed,
    dust,
    tx_type: txType,
    min_usd: get("min_usd"),
    flagged_only: flaggedOnly,
    limit: LIMIT,
    offset,
  })}`;
  const { data, error, loading, reload } = useApi<{ total: number; tx_types: string[]; items: Tx[] }>(path);
  const focus = get("account");

  return (
    <>
      <PageHeader
        eyebrow="04 · Transaction Explorer"
        title="Transaction explorer"
      />

      <Card bodyClass="p-0">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Hash or address contains…" className={`${inputCls} w-64 font-mono`} />
          <input value={acct} onChange={(e) => setAcct(e.target.value.trim())} placeholder="Pin account (exact address)" className={`${inputCls} w-64 font-mono`} />
          {focus && (
            <Segmented
              value={direction}
              onChange={(v) => update({ direction: v === "all" ? null : v })}
              options={[
                { value: "all", label: "All" },
                { value: "in", label: "Incoming" },
                { value: "out", label: "Outgoing" },
              ]}
            />
          )}
          <input value={minUsd} onChange={(e) => setMinUsd(e.target.value.replace(/[^\d.]/g, ""))} placeholder="Min USD" className={`${inputCls} w-24`} />
          <Toggle checked={dust} onChange={(v) => update({ dust: v ? "true" : null })} label="Dust (< 1 USD)" />
          <Toggle checked={flaggedOnly} onChange={(v) => update({ flagged_only: v ? "true" : null })} label="Flagged parties" />
          <span className="tnum ml-auto text-xs text-muted">{data ? `${num(data.total)} transactions` : ""}</span>
        </div>

        {error ? (
          <div className="p-5">
            <ErrorState error={error} onRetry={reload} />
          </div>
        ) : !data ? (
          <Loading />
        ) : data.items.length === 0 ? (
          <Empty>No transactions match these filters.</Empty>
        ) : (
          <div className={`overflow-x-auto transition-opacity ${loading ? "opacity-60" : ""}`}>
            <table className="w-full text-[13px]">
              <thead className="border-b border-line">
                <tr>
                  <Th>Hash</Th>
                  <Th>Time (UTC)</Th>
                  <Th>Type</Th>
                  {focus && <Th>Dir.</Th>}
                  <Th>Sender</Th>
                  <Th />
                  <Th>Destination</Th>
                  <Th className="text-right">Amount</Th>
                  <Th className="text-right">USD</Th>
                  <Th className="text-right">Fee</Th>
                  <Th>Result</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((t) => {
                  const out = focus ? t.account === focus : undefined;
                  return (
                    <tr key={t.tx_hash} onClick={() => setSelected(t)} className={`cursor-pointer border-b border-line last:border-0 hover:bg-hover ${selected?.tx_hash === t.tx_hash ? "bg-hover" : ""}`}>
                      <Td className="font-mono text-[12px] text-ink-2">{shortHash(t.tx_hash)}</Td>
                      <Td className="tnum text-ink-2">{dateTime(t.timestamp).replace(" UTC", "")}</Td>
                      <Td className="text-ink-2">{t.tx_type}</Td>
                      {focus && (
                        <Td>
                          {out ? (
                            <span className="inline-flex items-center gap-1 text-xs text-ink-2">
                              <ArrowUpRight className="h-3.5 w-3.5 text-[var(--s2)]" />
                              Out
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs text-ink-2">
                              <ArrowDownLeft className="h-3.5 w-3.5 text-accent" />
                              In
                            </span>
                          )}
                        </Td>
                      )}
                      <Td>
                        <Address value={t.account} />
                      </Td>
                      <Td className="px-0 text-muted">
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Td>
                      <Td>
                        <Address value={t.destination} />
                      </Td>
                      <Td className="tnum text-right">
                        {t.tx_type === "Payment" ? (
                          <>
                            {num(t.amount, t.amount < 1 ? 6 : 2)} <span className="text-muted">{t.currency}</span>
                          </>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </Td>
                      <Td className={`tnum text-right ${t.tx_type === "Payment" && t.amount_usd < 1 ? "text-warning" : ""}`}>{t.tx_type === "Payment" ? usd(t.amount_usd) : "—"}</Td>
                      <Td className={`tnum text-right ${t.fee >= 1000 ? "text-serious" : "text-ink-2"}`}>{num(t.fee)}</Td>
                      <Td>
                        <ResultBadge result={t.result} />
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pager offset={offset} limit={LIMIT} total={data.total} onChange={(o) => update({ offset: o })} />}
      </Card>

      {selected && <TxPanel tx={selected} onClose={() => setSelected(null)} onPin={(a) => (setAcct(a), update({ account: a }))} />}
    </>
  );
}

function TxPanel({ tx, onClose, onPin }: { tx: Tx; onClose: () => void; onPin: (a: string) => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  const rows: [string, React.ReactNode][] = [
    ["Hash", <span key="h" className="break-all font-mono text-[12px]">{tx.tx_hash}</span>],
    ["Ledger", <span key="l" className="tnum">{num(tx.ledger_index)}</span>],
    ["Timestamp", dateTime(tx.timestamp)],
    ["Type", tx.tx_type],
    ["Result", <ResultBadge key="r" result={tx.result} />],
    ["Amount", tx.tx_type === "Payment" ? `${num(tx.amount, 6)} ${tx.currency}` : "—"],
    ["USD value", tx.tx_type === "Payment" ? usd(tx.amount_usd) : "—"],
    ["Fee", `${num(tx.fee)} drops`],
    ["Destination tag", tx.destination_tag ?? "—"],
  ];
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={onClose}>
      <aside onClick={(e) => e.stopPropagation()} className="h-full w-full max-w-md overflow-y-auto border-l border-line-strong bg-panel p-6 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-[15px] font-semibold">Transaction</h2>
          <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-hover hover:text-ink" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="mb-5 grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-lg border border-line bg-surface p-4">
          <PartyBox label="Sender" value={tx.account} onPin={onPin} />
          <ArrowRight className="h-4 w-4 text-muted" />
          <PartyBox label="Destination" value={tx.destination} onPin={onPin} />
        </div>
        <dl className="divide-y divide-line text-[13px]">
          {rows.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[120px_1fr] gap-3 py-2.5">
              <dt className="text-muted">{k}</dt>
              <dd className="min-w-0 text-ink">{v}</dd>
            </div>
          ))}
        </dl>
      </aside>
    </div>
  );
}

function PartyBox({ label, value, onPin }: { label: string; value: string | null; onPin: (a: string) => void }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-muted">{label}</div>
      <Address value={value} />
      {value && (
        <div className="mt-1 flex gap-2 text-[11px]">
          <Link href={`/cases/${value}`} className="text-accent hover:underline">
            Case
          </Link>
          <button onClick={() => onPin(value)} className="text-ink-2 hover:text-ink">
            History
          </button>
        </div>
      )}
    </div>
  );
}
