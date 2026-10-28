"use client";

import { useRouter } from "next/navigation";
import { AnomalyHistogram, C, HBarChart, LegendKey, RankScatter, featureBarData } from "@/components/charts";
import { Address, Card, ErrorState, Loading, PageHeader, RuleChip, ScoreBar, StatTile, Td, Th } from "@/components/ui";
import { type ModelInsights, useApi } from "@/lib/api";
import { dateTime, num } from "@/lib/format";

const SCORE_LABEL: Record<string, string> = { model_score: "Supervised", anomaly_score: "Anomaly", rule_score: "Rules", risk_score: "Combined" };

export default function ModelPage() {
  const { data, error, loading, reload } = useApi<ModelInsights>("/api/model");
  const router = useRouter();
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading && !data) return <Loading label="Loading model insights" className="h-[60vh]" />;
  if (!data) return null;
  const m = data.metrics;
  const cols = Object.keys(SCORE_LABEL);

  return (
    <>
      <PageHeader
        eyebrow="06 · Model insights"
        title="How the scores are produced"
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Cross-validated ROC-AUC" value={m.cv_roc_auc?.toFixed(3) ?? "—"} sub="Supervised model, 5-fold, labelled accounts" />
        <StatTile label="Cross-validated PR-AUC" value={m.cv_pr_auc?.toFixed(3) ?? "—"} sub={`${data.labelled_suspicious} suspicious of ${data.n_labelled} labelled`} />
        <StatTile label="Hidden-test ROC-AUC" value={m.holdout_test_roc_auc_risk_score?.toFixed(3) ?? "—"} sub="Combined risk, held-back accounts only" />
        <StatTile label="Top-25 agreement" value={`${data.overlap.all_three} / ${data.overlap.k}`} sub="Accounts all three detectors rank in their top 25" />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card title="Model card" className="xl:col-span-1">
          <dl className="space-y-3.5 text-[13px]">
            {[
              ["Supervised model", data.supervised_model],
              ["Anomaly model", data.anomaly_model],
              ["Combined risk", data.risk_formula],
              ["Flag rule", data.flag_rule],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-muted">{k}</dt>
                <dd className="mt-0.5 break-words font-mono text-[12px] text-ink-2">{v}</dd>
              </div>
            ))}
            {Object.entries(m)
              .filter(([k]) => k.startsWith("holdout_test_roc_auc_"))
              .map(([k, v]) => (
                <div key={k} className="flex justify-between border-t border-line pt-2 text-xs">
                  <span className="text-ink-2">Hidden-test ROC-AUC · {SCORE_LABEL[k.replace("holdout_test_roc_auc_", "")]}</span>
                  <span className="tnum text-ink">{v.toFixed(3)}</span>
                </div>
              ))}
          </dl>
        </Card>
        <Card className="xl:col-span-2" title="Feature importance" subtitle="Mean impurity decrease in the random forest, top 15. It shows what the model relies on overall, not why any one account scored high.">
          <HBarChart data={featureBarData(data.feature_importance.slice(0, 15))} labelWidth={200} valueFormat={(v) => v.toFixed(3)} />
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card
          className="xl:col-span-3"
          title="Supervised versus anomaly score"
          subtitle="Each dot is an account. Agreement sits top-right. Off-diagonal points are where the detectors disagree. Click a dot to open its case."
          actions={
            <LegendKey
              items={[
                { label: "Not flagged", color: C.s1, kind: "dot" },
                { label: "Flagged", color: C.s2, kind: "dot" },
              ]}
            />
          }
        >
          <RankScatter data={data.scatter} onSelect={(a) => router.push(`/cases/${a}`)} />
        </Card>
        <Card
          className="xl:col-span-2"
          title="Isolation Forest anomaly scores"
          subtitle="Accounts per anomaly percentile band"
          actions={
            <LegendKey
              items={[
                { label: "Not flagged", color: C.s1 },
                { label: "Flagged", color: C.s2 },
              ]}
            />
          }
        >
          <AnomalyHistogram data={data.anomaly_distribution} />
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card
          className="xl:col-span-3"
          title="Supervised versus anomaly score"
          subtitle="Each dot is an account. Agreement sits top-right. Off-diagonal points are where the detectors disagree. Click a dot to open its case."
          actions={
            <LegendKey
              items={[
                { label: "Not flagged", color: C.s1, kind: "dot" },
                { label: "Flagged", color: C.s2, kind: "dot" },
              ]}
            />
          }
        >
          <RankScatter data={data.scatter} onSelect={(a) => router.push(`/cases/${a}`)} />
        </Card>
        <Card
          className="xl:col-span-2"
          title="Isolation Forest anomaly scores"
          subtitle="Accounts per anomaly percentile band"
          actions={
            <LegendKey
              items={[
                { label: "Not flagged", color: C.s1 },
                { label: "Flagged", color: C.s2 },
              ]}
            />
          }
        >
          <AnomalyHistogram data={data.anomaly_distribution} />
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Ranking agreement" subtitle="Spearman rank correlation between the scores (1 means identical ranking)" bodyClass="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead className="border-b border-line">
                <tr>
                  <Th />
                  {cols.map((c) => (
                    <Th key={c} className="text-right">
                      {SCORE_LABEL[c]}
                    </Th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cols.map((r) => (
                  <tr key={r} className="border-b border-line last:border-0">
                    <Td className="text-ink-2">{SCORE_LABEL[r]}</Td>
                    {cols.map((c) => {
                      const v = data.spearman[c]?.[r] ?? 0;
                      return (
                        <Td key={c} className="tnum text-right">
                          <span className="inline-block rounded px-1.5 py-0.5" style={{ background: r === c ? "transparent" : `rgba(30,163,188,${Math.max(0, v) * 0.45})` }}>
                            {r === c ? <span className="text-muted">—</span> : v.toFixed(2)}
                          </span>
                        </Td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid grid-cols-3 border-t border-line text-center text-xs">
            {[
              ["Supervised ∩ anomaly", data.overlap.model_vs_anomaly],
              ["Supervised ∩ rules", data.overlap.model_vs_rules],
              ["Anomaly ∩ rules", data.overlap.anomaly_vs_rules],
            ].map(([k, v]) => (
              <div key={k as string} className="border-r border-line px-3 py-3 last:border-0">
                <div className="tnum text-lg font-semibold">
                  {v}
                  <span className="text-xs font-normal text-muted"> / {data.overlap.k}</span>
                </div>
                <div className="text-muted">{k} in top {data.overlap.k}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Where the detectors disagree" subtitle="Highly anomalous with no rule hit, or rule hits without a strong anomaly signal. Review these first when tuning." bodyClass="p-0">
          {data.disagreements.length ? (
            <div className="max-h-[330px] overflow-auto">
              <table className="w-full text-[13px]">
                <thead className="sticky top-0 border-b border-line bg-surface">
                  <tr>
                    <Th>Account</Th>
                    <Th>Anomaly</Th>
                    <Th>Rules</Th>
                    <Th>Model</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.disagreements.map((a) => (
                    <tr key={a.account} onClick={() => router.push(`/cases/${a.account}`)} className="cursor-pointer border-b border-line last:border-0 hover:bg-hover">
                      <Td><Address value={a.account} /></Td>
                      <Td><ScoreBar value={a.anomaly_score} width={44} /></Td>
                      <Td>
                        <div className="flex gap-1">{a.rules.length ? a.rules.slice(0, 2).map((r) => <RuleChip key={r} id={r} />) : <span className="text-xs text-muted">none</span>}</div>
                      </Td>
                      <Td><ScoreBar value={a.model_score} width={44} /></Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="p-5 text-xs text-muted">The detectors agree on every account.</p>
          )}
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3" title="Typology rules" subtitle="Transparent rules. Their weights add up to the rule score, capped at 100." bodyClass="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead className="border-b border-line">
                <tr>
                  <Th>Rule</Th>
                  <Th className="text-right">Weight</Th>
                  <Th>What it checks</Th>
                </tr>
              </thead>
              <tbody>
                {data.rules.map((r) => (
                  <tr key={r.id} className="border-b border-line last:border-0">
                    <Td className="font-medium">{r.name}</Td>
                    <Td className="tnum text-right text-accent">+{r.weight}</Td>
                    <td className="px-3 py-2.5 pr-5 text-ink-2">{r.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card className="xl:col-span-2" title="Dataset limitations">
          <ul className="space-y-2.5 text-[13px] text-ink-2">
            {data.limitations.map((l) => (
              <li key={l} className="flex gap-2.5">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted" />
                {l}
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
