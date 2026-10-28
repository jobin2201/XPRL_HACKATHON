"use client";

// Transactions: every test payment ranked by the v2 score, filters, and the joined detail of the selected one.
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import TxDetail from "@/components/v2/TxDetail";
import { Card, Empty, ErrorState, Loading, PageHeader, Pager, ScoreBar, Td, Th, Toggle, inputCls } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { dateTime, num, shortAddr, usd } from "@/lib/format";
import { type V2Tx, scoreColor } from "@/lib/v2";

const LIMIT = 50;

export default function FlaggedPage() {
  return (
    <Suspense fallback={<Loading className="h-[60vh]" />}>
      <Flagged />
    </Suspense>
  );
}

function Flagged() {
  const router = useRouter();
  const params = useSearchParams();
  const selected = params.get("tx");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(true);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(q);
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  const { data, error, loading, reload } = useApi<{ total: number; threshold: number; items: V2Tx[] }>(
    `/api/v2/transactions${qs({ q: query, flagged: flaggedOnly, limit: LIMIT, offset })}`,
  );
  const select = (h: string) => router.replace(`/flagged?tx=${h}`, { scroll: false });

  return (
    <>
      <PageHeader eyebrow="LightGBM v2 · transactions" title="Fraud alerts on the test data" />
      <div className="grid grid-cols-1 gap-4 2xl:grid-cols-[1fr_520px]">
        <Card bodyClass="p-0">
          <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Hash or wallet contains…" className={`${inputCls} w-full font-mono sm:w-64`} />
            <Toggle
              checked={flaggedOnly}
              onChange={(v) => {
                setFlaggedOnly(v);
                setOffset(0);
              }}
              label={`Flagged only (score ≥ ${data?.threshold.toFixed(3) ?? "…"})`}
            />
            <span className="tnum text-xs text-muted sm:ml-auto">{data ? `${num(data.total)} payments` : ""}</span>
          </div>
          {error ? (
            <ErrorState error={error} onRetry={reload} />
          ) : !data ? (
            <Loading />
          ) : !data.items.length ? (
            <Empty>No payments match.</Empty>
          ) : (
            <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`}>
              <table className="w-full text-[13px]">
                <thead className="border-b border-line">
                  <tr>
                    <Th className="text-right">Rank</Th>
                    <Th>Score</Th>
                    <Th>Status</Th>
                    <Th>Time (UTC)</Th>
                    <Th>From → To</Th>
                    <Th className="text-right">USD</Th>
                    <Th className="text-right">Legs</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((t) => (
                    <tr
                      key={t.TRANSACTION_HASH}
                      onClick={() => select(t.TRANSACTION_HASH)}
                      className={`cursor-pointer border-b border-line last:border-0 hover:bg-hover ${selected === t.TRANSACTION_HASH ? "bg-hover" : ""}`}
                    >
                      <Td className="tnum text-right text-muted">{num(t.rank)}</Td>
                      <Td>
                        <div className="flex items-center gap-2">
                          <ScoreBar value={t.score} color={scoreColor(t.score)} width={44} />
                          <span className="tnum">{t.score.toFixed(3)}</span>
                        </div>
                      </Td>
                      <Td>
                        {t.top1 ? (
                          <span className="rounded-full bg-[rgba(236,131,90,0.15)] px-2 py-0.5 text-[11px] text-serious">top 1%</span>
                        ) : t.flagged ? (
                          <span className="rounded-full bg-[rgba(250,178,25,0.12)] px-2 py-0.5 text-[11px] text-warning">flagged</span>
                        ) : (
                          <span className="text-[11px] text-muted">normal</span>
                        )}
                      </Td>
                      <Td className="whitespace-nowrap text-ink-2">{dateTime(t.time)}</Td>
                      <Td className="whitespace-nowrap font-mono text-xs">
                        {shortAddr(t.from)} → {shortAddr(t.to)}
                      </Td>
                      <Td className="tnum text-right">{usd(t.usd)}</Td>
                      <Td className="tnum text-right">{t.legs}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data && <Pager offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />}
        </Card>
        <div>{selected ? <TxDetail hash={selected} /> : <Card title="Transaction detail"><p className="text-[13px] text-muted">Click a payment to see its joined tables and why it was flagged.</p></Card>}</div>
      </div>
    </>
  );
}
