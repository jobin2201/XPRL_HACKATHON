"use client";

// Home: the LightGBM v2 model and the data it was built on, in charts.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, BrainCircuit, Database, FlaskConical, ListOrdered, Network as NetIcon, ShieldCheck } from "lucide-react";
import { ActivityChart } from "@/components/charts";
import { ParallaxHero } from "@/components/ParallaxHero";
import FlowGraph from "@/components/v2/FlowGraph";
import { Bars, Donut, Gauge, MetricBars, PALETTE, Trend } from "@/components/v2/viz";
import { Card, ErrorState, Loading, ScoreBar, Td, Th } from "@/components/ui";
import { useApi } from "@/lib/api";
import { dateOnly, dateTime, num, pct, shortAddr, usd } from "@/lib/format";
import { type V2Datasets, type V2Graph, type V2Summary, scoreColor } from "@/lib/v2";

const DIFF_TOTAL: Record<string, number> = { easy: 800, medium: 225, hard: 225 };

function Section({ icon: Icon, title, text }: { icon: typeof Database; title: string; text: string }) {
  return (
    <div className="mb-3 mt-8 flex items-end gap-3 first:mt-0">
      <div className="grid h-9 w-9 place-items-center rounded-lg bg-surface-2 text-accent shadow-[0_0_18px_var(--glow)]">
        <Icon className="h-[18px] w-[18px]" />
      </div>
      <div>
        <h2 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h2>
        <p className="text-xs text-muted">{text}</p>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const { data: s, error, reload } = useApi<V2Summary>("/api/v2/summary");
  const { data: ds } = useApi<V2Datasets>("/api/v2/datasets");
  const { data: g } = useApi<V2Graph>("/api/v2/graph?hours=1");
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!s) return <Loading label="Loading the v2 model" className="h-[60vh]" />;
  const v = s.validation;
  const folds = (v.ap_per_fold ?? []).map((ap, i) => ({ fold: `Fold ${i + 1}`, AP: ap, Precision: Math.round((v.top1_precision_per_fold?.[i] ?? 0) * 1000) / 10 }));
  const caught = Object.entries(v.caught_in_top1).map(([k, val]) => {
    const c = Number(val.split("/")[0]);
    return { kind: k, Caught: c, Missed: DIFF_TOTAL[k] - c };
  });

  return (
    <div className="rise-in">
      {/* hero with parallax */}
      <ParallaxHero
        eyebrow="LightGBM v2 · XRPL fraud detection"
        title="Suspicious transaction detection"
        description={
          <>
            Trained on {ds ? num(ds.train.payments) : "40,131"} labelled payments, scoring {ds ? num(ds.test.payments) : "40,101"} test payments. Every number below is
            measured honestly: scenarios are never split between training and checking.
          </>
        }
      >
        <div className="mt-4 flex flex-wrap gap-2">
          {[
            { href: "/flagged", icon: ListOrdered, title: "Transactions" },
            { href: "/graph", icon: NetIcon, title: "Network graph" },
            { href: "/models", icon: BrainCircuit, title: "Models" },
            { href: "/scoring?tab=evaluation", icon: ShieldCheck, title: "Validation" },
          ].map(({ href, icon: Icon, title }) => (
            <Link key={href} href={href} className="group inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-xs text-ink-2 transition-all hover:-translate-y-0.5 hover:border-line-strong hover:text-ink">
              <Icon className="h-3.5 w-3.5 text-accent" /> {title}
              <ArrowRight className="h-3 w-3 opacity-0 transition-all group-hover:translate-x-0.5 group-hover:opacity-100" />
            </Link>
          ))}
        </div>
      </ParallaxHero>

      {/* model performance */}
      <Section icon={FlaskConical} title="Model performance" text="Grouped 5-fold validation on the labelled training data (out-of-fold scores)" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-12">
        <Card title="Headline scores" className="md:col-span-2 2xl:col-span-5">
          <div className="grid grid-cols-3 gap-1 sm:gap-2">
            <Gauge value={v.site_score_ap} max={100} display={v.site_score_ap.toFixed(1)} label="Score (100 × AP)" color={PALETTE.train} />
            <Gauge value={v.top1_precision} display={pct(v.top1_precision, 0)} label="Top-1% precision" color={PALETTE.good} />
            <Gauge value={v.roc_auc} display={v.roc_auc.toFixed(2)} label="ROC-AUC" color={PALETTE.test} />
          </div>
          <p className="mt-3 text-center text-[11px] text-muted">Top-1% recall {pct(v.top1_recall, 1)} (max possible ≈ 32%: 402 alerts for 1,250 suspicious)</p>
        </Card>
        <Card title={`At the alert threshold (${v.threshold.toFixed(3)})`} className="2xl:col-span-3">
          <MetricBars
            rows={[
              { label: "Accuracy", value: v.accuracy, display: pct(v.accuracy, 2), color: PALETTE.soft, hint: "High because 97% of payments are normal" },
              { label: "Precision", value: v.precision, display: pct(v.precision, 1), color: PALETTE.good },
              { label: "Recall", value: v.recall, display: pct(v.recall, 1), color: PALETTE.warn },
              { label: "F1", value: v.f1, display: v.f1.toFixed(3), color: PALETTE.train },
            ]}
          />
        </Card>
        <Card title="Score per fold" subtitle="AP and top-1% precision (%) · steady = stable model" className="2xl:col-span-4">
          <Bars data={folds} x="fold" series={[{ key: "AP", name: "AP", color: PALETTE.train }, { key: "Precision", name: "Top-1% precision", color: PALETTE.test }]} height={210} />
        </Card>
      </div>

      {/* datasets */}
      <Section icon={Database} title="The data" text="Official Decode & Detect training and test packages, joined across all files" />
      {ds ? (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {(["train", "test"] as const).map((k) => {
              const d = ds[k];
              const isTrain = k === "train";
              return (
                <Card
                  key={k}
                  title={isTrain ? "Training data" : "Test data"}
                  subtitle={<span className="break-all font-mono text-[11px]">{d.folder}</span>}
                >
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-1 2xl:grid-cols-2">
                    <div>
                      {isTrain && d.labels ? (
                        <Donut
                          data={[
                            { name: "Normal", value: d.labels.normal, color: PALETTE.soft },
                            { name: "Suspicious", value: d.labels.suspicious, color: PALETTE.bad },
                          ]}
                          centre={pct(d.labels.suspicious / d.payments, 1)}
                          sub="suspicious"
                        />
                      ) : (
                        <Donut
                          data={[
                            { name: "Not flagged", value: d.payments - (d.flagged ?? 0), color: PALETTE.soft },
                            { name: "Flagged by v2", value: d.flagged ?? 0, color: PALETTE.warn },
                          ]}
                          centre={num(d.flagged ?? 0)}
                          sub="flagged by v2"
                        />
                      )}
                    </div>
                    <dl className="min-w-0 space-y-1.5 text-[12px]">
                      {[
                        ["Payments", num(d.payments)],
                        ["Wallets", num(d.wallets)],
                        ["Week", `${dateOnly(d.start)} – ${dateOnly(d.end)}`],
                        ["Value moved", usd(d.usd_total, { compact: true })],
                        ["Median payment", usd(d.usd_median)],
                        ["Currency conversions", pct(d.conversion_share, 0)],
                        ...Object.entries(d.files).map(([f, n]) => [`${f}`, num(n)]),
                      ].map(([a, b]) => (
                        <div key={a} className="flex justify-between gap-3 border-b border-line pb-1 last:border-0">
                          <dt className="shrink-0 text-muted">{a}</dt>
                          <dd className="tnum min-w-0 break-words text-right text-ink">{b}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                  {isTrain && d.labels && (
                    <div className="mt-4">
                      <p className="mb-1 text-xs text-ink-2">Suspicious payments by pattern family</p>
                      <Bars data={d.labels.by_family.map((f) => ({ family: f.family.replace(/_/g, " "), Payments: f.payments }))} x="family" series={[{ key: "Payments", name: "Payments", color: PALETTE.bad }]} height={170} />
                    </div>
                  )}
                  {!isTrain && (
                    <p className="mt-4 rounded-lg bg-surface-2 p-3 text-xs text-ink-2">
                      No labels: the organisers keep the answers. The {num(d.top1 ?? 0)} highest scores form the top-1% review list the leaderboard checks.
                    </p>
                  )}
                </Card>
              );
            })}
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-4">
            <Card title="Payments per day" subtitle="Training vs test week">
              <Trend
                data={ds.train.per_day.map((p, i) => ({ day: `Day ${p.day}`, Training: p.payments, Test: ds.test.per_day[i]?.payments ?? 0 }))}
                x="day"
                series={[{ key: "Training", name: "Training", color: PALETTE.train }, { key: "Test", name: "Test", color: PALETTE.test }]}
                height={200}
              />
            </Card>
            <Card title="Delivered currency" subtitle="Payments by asset">
              <Bars
                data={ds.train.currencies.map((c) => ({ currency: c.currency, Training: c.payments, Test: ds.test.currencies.find((t) => t.currency === c.currency)?.payments ?? 0 }))}
                x="currency"
                series={[{ key: "Training", name: "Training", color: PALETTE.train }, { key: "Test", name: "Test", color: PALETTE.test }]}
                height={200}
              />
            </Card>
            <Card title="Transfer legs per payment" subtitle="1 = direct, 2–3 = conversion">
              <Bars
                data={ds.train.legs.map((l) => ({ legs: `${l.legs} leg${l.legs > 1 ? "s" : ""}`, Training: l.payments, Test: ds.test.legs.find((t) => t.legs === l.legs)?.payments ?? 0 }))}
                x="legs"
                series={[{ key: "Training", name: "Training", color: PALETTE.train }, { key: "Test", name: "Test", color: PALETTE.test }]}
                height={200}
              />
            </Card>
            <Card title="Payment size (USD)" subtitle="Hourly reference prices">
              <Bars
                data={ds.train.amounts.map((a, i) => ({ band: a.band, Training: a.payments, Test: ds.test.amounts[i]?.payments ?? 0 }))}
                x="band"
                series={[{ key: "Training", name: "Training", color: PALETTE.train }, { key: "Test", name: "Test", color: PALETTE.test }]}
                height={200}
              />
            </Card>
          </div>
        </>
      ) : (
        <Loading className="h-64" label="Reading the training and test data (first time takes ~20 s)" />
      )}

      {/* results on the test data */}
      <Section icon={ShieldCheck} title="What the model found" text="Scores on the 40,101 test payments and how well each kind of pattern is caught" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3">
        <Card title="Test score distribution" subtitle="Payments per 0.05 band (most are near 0)">
          <Bars data={s.histogram.map((h) => ({ band: h.bin, Payments: h.count }))} x="band" series={[{ key: "Payments", name: "Payments", color: PALETTE.train }]} height={220} />
        </Card>
        <Card title="Caught in the top 1%, by difficulty" subtitle="Validation: planted suspicious payments">
          <Bars data={caught} x="kind" stacked series={[{ key: "Caught", name: "Caught", color: PALETTE.good }, { key: "Missed", name: "Not in top 1%", color: PALETTE.soft }]} height={220} />
        </Card>
        <Card title="Test activity over time" subtitle="Payments per hour, flagged in colour" className="md:col-span-2 2xl:col-span-1">
          <ActivityChart data={s.activity} granularity="hour" />
        </Card>
      </div>

      <Card
        title="Network around the most suspicious payment"
        subtitle="Wallets as nodes, payments as arrows (±1 h) · red = highest scores · click a wallet or arrow"
        className="mt-4"
        actions={
          <Link href="/graph" className="text-xs text-accent hover:underline">
            Open full graph →
          </Link>
        }
        bodyClass="p-0 overflow-x-auto"
      >
        {g ? <div className="min-w-[560px]"><FlowGraph data={g} onWallet={(id) => router.push(`/graph?wallet=${id}`)} onEdge={(e) => router.push(`/flagged?tx=${e.top_tx}`)} /></div> : <Loading className="h-[420px]" label="Drawing the graph" />}
      </Card>

      <div className="mt-4 grid grid-cols-1 gap-4 2xl:grid-cols-3">
        <Card title="Most suspicious test payments" subtitle="Click a row for joined details and the AI explanation" bodyClass="p-0" className="2xl:col-span-2">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead className="border-b border-line">
                <tr>
                  <Th className="text-right">#</Th>
                  <Th>Score</Th>
                  <Th>Time (UTC)</Th>
                  <Th>From → To</Th>
                  <Th className="text-right">USD</Th>
                </tr>
              </thead>
              <tbody>
                {s.top.map((t) => (
                  <tr key={t.TRANSACTION_HASH} onClick={() => router.push(`/flagged?tx=${t.TRANSACTION_HASH}`)} className="cursor-pointer border-b border-line transition-colors last:border-0 hover:bg-hover">
                    <Td className="tnum text-right text-muted">{t.rank}</Td>
                    <Td>
                      <div className="flex items-center gap-2">
                        <ScoreBar value={t.score} color={scoreColor(t.score)} width={48} />
                        <span className="tnum">{t.score.toFixed(3)}</span>
                      </div>
                    </Td>
                    <Td className="whitespace-nowrap text-ink-2">{dateTime(t.time)}</Td>
                    <Td className="whitespace-nowrap font-mono text-xs">
                      {shortAddr(t.from)} → {shortAddr(t.to)}
                    </Td>
                    <Td className="tnum text-right">{usd(t.usd)}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="What the model relies on" subtitle="Top features by LightGBM gain">
          {s.importance.length ? (
            <Bars
              data={s.importance.slice(0, 8).map((f) => ({ feature: f.feature.replace(/_/g, " ").slice(0, 18), Gain: Math.round(f.gain / 1000) }))}
              x="feature"
              series={[{ key: "Gain", name: "Gain (k)", color: PALETTE.test }]}
              height={300}
            />
          ) : (
            <p className="text-xs text-muted">Run run_model.py … --dashboard to show feature importance.</p>
          )}
        </Card>
      </div>
      <p className="mt-4 break-words text-xs text-muted">
        Model: <span className="break-all font-mono">{s.command}</span>
      </p>
    </div>
  );
}
