"use client";

// Network graph: wallets as nodes, payments as arrows, around a payment or a wallet, coloured by the v2 score.
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import FlowGraph from "@/components/v2/FlowGraph";
import TxDetail from "@/components/v2/TxDetail";
import { Card, ErrorState, Loading, PageHeader, Segmented, inputCls } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { dateTime, num, shortAddr, usd } from "@/lib/format";
import { type V2Graph, type V2GraphEdge, scoreColor } from "@/lib/v2";

const WINDOWS = [
  { value: "1", label: "±1 h" },
  { value: "3", label: "±3 h" },
  { value: "6", label: "±6 h" },
  { value: "24", label: "±24 h" },
] as const;

export default function GraphPage() {
  return (
    <Suspense fallback={<Loading className="h-[60vh]" />}>
      <Graph />
    </Suspense>
  );
}

function Graph() {
  const router = useRouter();
  const params = useSearchParams();
  const tx = params.get("tx") ?? "";
  const wallet = params.get("wallet") ?? "";
  const [hours, setHours] = useState<(typeof WINDOWS)[number]["value"]>("3");
  const [search, setSearch] = useState("");
  const [edge, setEdge] = useState<V2GraphEdge | null>(null);
  const { data, error, loading, reload } = useApi<V2Graph>(`/api/v2/graph${qs({ tx, wallet, hours })}`);

  const go = (q: Record<string, string>) => {
    setEdge(null);
    router.replace(`/graph${qs(q)}`, { scroll: false });
  };

  return (
    <>
      <PageHeader eyebrow="LightGBM v2 · network" title="Who paid whom" />
      <Card bodyClass="p-0" className="mb-4">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3 text-xs">
          <Segmented value={hours} options={[...WINDOWS]} onChange={setHours} />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const v = search.trim();
              if (v) go(v.startsWith("r") ? { wallet: v } : { tx: v });
            }}
            className="flex w-full gap-2 sm:w-auto"
          >
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Wallet (r…) or transaction hash" className={`${inputCls} w-full font-mono sm:w-80`} />
          </form>
          <button onClick={() => go({})} className="rounded-md border border-line px-2.5 py-1.5 text-ink-2 hover:bg-hover">
            Most suspicious payment
          </button>
          {data && (
            <span className="w-full text-muted lg:ml-auto lg:w-auto">
              {num(data.nodes.length)} wallets · {num(data.payments_in_view)} payments · {dateTime(data.from)} – {dateTime(data.to)}
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-4 px-4 py-2 text-[11px] text-muted">
          <span>Arrow colour = highest score on that link:</span>
          {[
            ["#d03b3b", "≥ 0.9"],
            ["#ec835a", "0.5–0.9"],
            ["#fab219", `flagged (≥ ${data?.threshold.toFixed(3) ?? "0.171"})`],
            ["#3b5072", "normal"],
          ].map(([c, l]) => (
            <span key={l} className="flex items-center gap-1">
              <span className="inline-block h-2 w-4 rounded" style={{ background: c }} /> {l}
            </span>
          ))}
          <span>· blue node = centre · thick arrow = several payments · click a wallet to re-centre</span>
        </div>
        <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`}>
          <div className="min-w-[600px]">
            {error ? <ErrorState error={error} onRetry={reload} /> : !data ? <Loading className="h-[560px]" /> : <FlowGraph data={data} onWallet={(id) => go({ wallet: id })} onEdge={setEdge} />}
          </div>
        </div>
        <p className="px-4 pb-3 text-[11px] text-muted sm:hidden">Swipe sideways to see the whole graph.</p>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {edge ? (
          <Card title="Selected link" bodyClass="p-0">
            <table className="w-full table-fixed text-[13px]">
              <tbody>
                {[
                  ["From", <span key="f" className="font-mono text-xs">{edge.from}</span>],
                  ["To", <span key="t" className="font-mono text-xs">{edge.to}</span>],
                  ["Payments", num(edge.count)],
                  ["Total value", usd(edge.usd)],
                  ["Highest score", <span key="s" style={{ color: scoreColor(edge.max_score) }}>{edge.max_score.toFixed(3)}</span>],
                  ["First payment", dateTime(edge.first)],
                ].map(([k, v]) => (
                  <tr key={String(k)} className="border-b border-line last:border-0">
                    <td className="w-28 px-3 py-2 align-top text-muted sm:w-36 sm:px-4">{k}</td>
                    <td className="min-w-0 break-all px-3 py-2 sm:px-4">{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex flex-wrap gap-3 px-4 py-3 text-xs">
              <button onClick={() => go({ wallet: edge.from })} className="text-accent hover:underline">Centre on {shortAddr(edge.from)}</button>
              <button onClick={() => go({ wallet: edge.to })} className="text-accent hover:underline">Centre on {shortAddr(edge.to)}</button>
            </div>
          </Card>
        ) : (
          <Card title="Selected link">
            <p className="text-[13px] text-muted">Click an arrow to see the payments on it.</p>
          </Card>
        )}
        {(edge?.top_tx || data?.tx) && <TxDetail hash={(edge?.top_tx || data?.tx)!} />}
      </div>
    </>
  );
}
