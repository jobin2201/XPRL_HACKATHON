"use client";

// Ranked transactions (highest score first) for the test or training split, with filters and a detail panel.
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { Address, Card, Empty, ErrorState, Loading, Pager, ScoreBar, Segmented, Td, Th, inputCls, riskColor } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { dateTime, num, shortHash, usd } from "@/lib/format";
import type { ScoredTx, Split } from "@/lib/txmodel";

const LIMIT = 50;

export default function ScoresTable({ split }: { split: Split }) {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [label, setLabel] = useState<"all" | "suspicious" | "normal">("all");
  const [minScore, setMinScore] = useState("");
  const [sort, setSort] = useState<"desc" | "asc">("desc");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<ScoredTx | null>(null);

  // debounce the search box
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(q);
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  const path = `/api/txmodel/scores${qs({ split, q: query, label: split === "train" ? label : "all", min_score: minScore || 0, sort, limit: LIMIT, offset })}`;
  const { data, error, loading, reload } = useApi<{ total: number; items: ScoredTx[] }>(path);
  const isTrain = split === "train";

  return (
    <div className="grid grid-cols-1 gap-4 2xl:grid-cols-[1fr_340px]">
      <Card
        title={isTrain ? "Training transactions, ranked by out-of-fold score" : "Test transactions, ranked by model score"}
        subtitle={
          isTrain
            ? "Each score comes from a model that never saw that transaction (grouped folds), so you can compare it with the known label."
            : "These are the scores in submission.csv. Highest first: review from the top."
        }
        bodyClass="p-0"
      >
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Hash or address contains…" className={`${inputCls} w-full font-mono sm:w-64`} />
          <input
            value={minScore}
            onChange={(e) => {
              setMinScore(e.target.value.replace(/[^\d.]/g, ""));
              setOffset(0);
            }}
            placeholder="Min score (0–1)"
            className={`${inputCls} w-full sm:w-32`}
          />
          {isTrain && (
            <Segmented
              value={label}
              onChange={(v) => {
                setLabel(v);
                setOffset(0);
              }}
              options={[
                { value: "all", label: "All" },
                { value: "suspicious", label: "Suspicious" },
                { value: "normal", label: "Normal" },
              ]}
            />
          )}
          <Segmented
            value={sort}
            onChange={(v) => {
              setSort(v);
              setOffset(0);
            }}
            options={[
              { value: "desc", label: "Highest first" },
              { value: "asc", label: "Lowest first" },
            ]}
          />
          <span className="tnum text-xs text-muted sm:ml-auto">{data ? `${num(data.total)} transactions` : ""}</span>
        </div>

        {error ? (
          <ErrorState error={error} onRetry={reload} />
        ) : !data ? (
          <Loading />
        ) : !data.items.length ? (
          <Empty>No transactions match these filters.</Empty>
        ) : (
          <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`}>
            <table className="w-full text-[13px]">
              <thead className="border-b border-line">
                <tr>
                  <Th className="text-right">Rank</Th>
                  <Th>Score</Th>
                  <Th>Transaction</Th>
                  <Th>Time (UTC)</Th>
                  <Th>From</Th>
                  <Th>To</Th>
                  <Th className="text-right">USD</Th>
                  <Th className="text-right">Legs</Th>
                  {isTrain && <Th>Label</Th>}
                </tr>
              </thead>
              <tbody>
                {data.items.map((t) => (
                  <tr
                    key={t.TRANSACTION_HASH}
                    onClick={() => setOpen(t)}
                    className={`cursor-pointer border-b border-line last:border-0 hover:bg-hover ${open?.TRANSACTION_HASH === t.TRANSACTION_HASH ? "bg-hover" : ""}`}
                  >
                    <Td className="tnum text-right text-muted">{num(t.rank)}</Td>
                    <Td>
                      <div className="flex items-center gap-2">
                        <ScoreBar value={t.score} color={riskColor(t.score)} width={48} />
                        <span className="tnum">{t.score.toFixed(3)}</span>
                      </div>
                    </Td>
                    <Td className="font-mono text-xs">{shortHash(t.TRANSACTION_HASH)}</Td>
                    <Td className="whitespace-nowrap text-ink-2">{dateTime(t.time)}</Td>
                    <Td><Address value={t.from} href={isTrain ? undefined : false} /></Td>
                    <Td><Address value={t.to} href={isTrain ? undefined : false} /></Td>
                    <Td className="tnum text-right">{usd(t.usd)}</Td>
                    <Td className="tnum text-right">{t.legs}</Td>
                    {isTrain && <Td><LabelPill label={t.label} /></Td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pager offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />}
      </Card>

      <TxDetail tx={open} isTrain={isTrain} onClose={() => setOpen(null)} />
    </div>
  );
}

function LabelPill({ label }: { label?: 0 | 1 }) {
  return label === 1 ? (
    <span className="rounded-full bg-[rgba(239,68,68,0.12)] px-2 py-0.5 text-xs text-critical">suspicious</span>
  ) : (
    <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-2">normal</span>
  );
}

function TxDetail({ tx, isTrain, onClose }: { tx: ScoredTx | null; isTrain: boolean; onClose: () => void }) {
  if (!tx) {
    return (
      <Card title="Transaction detail">
        <p className="text-[13px] text-muted">Click a row to investigate it.</p>
      </Card>
    );
  }
  const rows: [string, React.ReactNode][] = [
    ["Rank", `#${num(tx.rank)}`],
    ["Model score", <span key="s" className="tnum" style={{ color: riskColor(tx.score) }}>{tx.score.toFixed(4)}</span>],
    ["Time (UTC)", dateTime(tx.time)],
    ["Value", usd(tx.usd)],
    ["Transfer legs", `${tx.legs}${tx.conversion ? " (currency conversion)" : " (direct payment)"}`],
  ];
  if (isTrain) {
    rows.push(["Known label", <LabelPill key="l" label={tx.label} />]);
    rows.push(["Scenario family", tx.family ?? "—"]);
    rows.push(["Difficulty", tx.difficulty ?? "—"]);
  }
  return (
    <Card
      title="Transaction detail"
      actions={
        <button onClick={onClose} aria-label="Close" className="rounded p-1 text-muted hover:bg-hover hover:text-ink">
          <X className="h-4 w-4" />
        </button>
      }
    >
      <p className="mb-3 break-all font-mono text-[11px] text-ink-2">{tx.TRANSACTION_HASH}</p>
      <dl className="space-y-2 text-[13px]">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 border-b border-line pb-2 last:border-0">
            <dt className="text-muted">{k}</dt>
            <dd className="text-right text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-4 space-y-2 text-[12px]">
        <div>
          <div className="text-muted">From</div>
          <Address value={tx.from} full href={isTrain ? undefined : false} />
        </div>
        <div>
          <div className="text-muted">To</div>
          <Address value={tx.to} full href={isTrain ? undefined : false} />
        </div>
      </div>
      {isTrain && (
        <p className="mt-4 text-[11px] text-muted">Family and difficulty come from labels.csv. They are shown for review only and are never model inputs.</p>
      )}
    </Card>
  );
}
