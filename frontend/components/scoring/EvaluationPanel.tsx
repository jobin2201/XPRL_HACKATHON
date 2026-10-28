// How the folds were built, whether they leak, and whether the score is out-of-fold.
import { CheckCircle2, AlertTriangle } from "lucide-react";
import { Card, StatTile, Td, Th } from "@/components/ui";
import { num, pct } from "@/lib/format";
import { type Evaluation, type Scheme, modelName } from "@/lib/txmodel";

const SCHEME_LABEL: Record<Scheme, string> = { random: "Random folds (original)", grouped: "Grouped folds (honest)" };

export default function EvaluationPanel({ ev }: { ev: Evaluation }) {
  const final = ev.final_model;
  const g = ev.results.grouped[final];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="AP · random folds" value={ev.headline.random_ap.toFixed(1)} sub="Original method (optimistic)" />
        <StatTile label="AP · grouped folds" value={ev.headline.grouped_ap.toFixed(1)} tone="accent" sub="Unseen scenarios: expect the site score near this" />
        <StatTile label="Optimism of random folds" value={`+${ev.headline.optimism.toFixed(1)}`} tone="critical" sub="AP points from leakage" />
        <StatTile label="Final model" value={modelName(final)} sub={`${num(ev.train.rows)} training rows · ${ev.train.features.length} features`} />
      </div>

      <Card title="How the five folds were created">
        <ul className="space-y-3 text-[13px] text-ink-2">
          {(["random", "grouped"] as Scheme[]).map((s) => (
            <li key={s}>
              <span className="font-medium text-ink">{SCHEME_LABEL[s]}:</span> {ev.fold_method[s]}
            </li>
          ))}
          <li className="flex gap-2">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
            <span>
              <span className="font-medium text-ink">Out-of-fold:</span> {ev.fold_method.out_of_fold}
            </span>
          </li>
          <li className="flex gap-2">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
            <span>
              <span className="font-medium text-ink">Features:</span> {ev.fold_method.feature_note}
            </span>
          </li>
        </ul>
      </Card>

      <Card title="Leakage across folds" subtitle="Do related transactions end up on both sides of a split?" bodyClass="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead className="border-b border-line">
              <tr>
                <Th>Check</Th>
                <Th className="text-right">Random folds</Th>
                <Th className="text-right">Grouped folds</Th>
              </tr>
            </thead>
            <tbody>
              <LeakRow
                label="Suspicious scenarios split across folds"
                r={`${ev.leakage.random.scenarios_split_across_folds} / ${ev.leakage.random.suspicious_scenarios}`}
                g={`${ev.leakage.grouped.scenarios_split_across_folds} / ${ev.leakage.grouped.suspicious_scenarios}`}
                bad={ev.leakage.random.scenarios_split_across_folds > 0}
                good={ev.leakage.grouped.scenarios_split_across_folds === 0}
              />
              <LeakRow
                label="Suspicious rows whose scenario is also in training"
                r={`${num(ev.leakage.random.suspicious_rows_whose_scenario_is_also_in_training)} / ${num(ev.leakage.random.suspicious_rows)}`}
                g={`${num(ev.leakage.grouped.suspicious_rows_whose_scenario_is_also_in_training)} / ${num(ev.leakage.grouped.suspicious_rows)}`}
                bad={ev.leakage.random.suspicious_rows_whose_scenario_is_also_in_training > 0}
                good={ev.leakage.grouped.suspicious_rows_whose_scenario_is_also_in_training === 0}
              />
              <LeakRow
                label="Check rows whose sender also appears in training"
                r={pct(ev.leakage.random.share_of_check_rows_whose_sender_is_in_training, 1)}
                g={pct(ev.leakage.grouped.share_of_check_rows_whose_sender_is_in_training, 1)}
              />
              <LeakRow label="Rows per fold" r={ev.leakage.random.fold_sizes.map((n) => num(n)).join(" · ")} g={ev.leakage.grouped.fold_sizes.map((n) => num(n)).join(" · ")} />
              <LeakRow label="Suspicious per fold" r={ev.leakage.random.fold_suspicious.join(" · ")} g={ev.leakage.grouped.fold_suspicious.join(" · ")} />
            </tbody>
          </table>
        </div>
        <p className="border-t border-line px-4 py-3 text-xs text-muted">
          Senders still overlap in grouped folds: the same wallets send both normal and suspicious payments, so a split can keep scenarios apart but not
          wallets. The test set uses different wallets, so the grouped number is the safer estimate.
        </p>
      </Card>

      <Card title={`${modelName(final)} on grouped folds`} subtitle="Per-fold Average Precision and the site's top-1% view" bodyClass="p-0">
        <div className="grid grid-cols-3 gap-px bg-line sm:grid-cols-5">
          {g.fold_ap.map((ap, i) => (
            <div key={i} className="bg-panel px-4 py-3">
              <div className="text-xs text-muted">Fold {i + 1}</div>
              <div className="tnum text-lg text-ink">{ap.toFixed(1)}</div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-px border-t border-line bg-line lg:grid-cols-4">
          <Mini label="Top 1% precision" v={g.top1_precision.toFixed(3)} />
          <Mini label="Top 1% recall" v={g.top1_recall.toFixed(3)} />
          <Mini label="Precision / recall @0.5" v={`${g.precision_at_0_5.toFixed(3)} / ${g.recall_at_0_5.toFixed(3)}`} />
          <Mini label="Caught in top 1% (easy · medium · hard)" v={`${g.top1_recall_by_difficulty.easy} · ${g.top1_recall_by_difficulty.medium} · ${g.top1_recall_by_difficulty.hard}`} />
        </div>
      </Card>
    </div>
  );
}

function LeakRow({ label, r, g, bad, good }: { label: string; r: string; g: string; bad?: boolean; good?: boolean }) {
  return (
    <tr className="border-b border-line last:border-0">
      <Td className="text-ink-2">{label}</Td>
      <Td className={`tnum text-right ${bad ? "text-critical" : ""}`}>
        <span className="inline-flex items-center gap-1">
          {bad && <AlertTriangle className="h-3.5 w-3.5" />}
          {r}
        </span>
      </Td>
      <Td className={`tnum text-right ${good ? "text-accent" : ""}`}>
        <span className="inline-flex items-center gap-1">
          {good && <CheckCircle2 className="h-3.5 w-3.5" />}
          {g}
        </span>
      </Td>
    </tr>
  );
}

function Mini({ label, v }: { label: string; v: string }) {
  return (
    <div className="bg-panel px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="tnum mt-0.5 text-[15px] text-ink">{v}</div>
    </div>
  );
}
