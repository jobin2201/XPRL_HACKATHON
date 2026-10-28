// LightGBM results on both fold sets, plus what the final model relies on.
import { Card, Td, Th } from "@/components/ui";
import type { Evaluation, Scheme } from "@/lib/txmodel";

const ROWS: { scheme: Scheme; label: string }[] = [
  { scheme: "grouped", label: "Grouped folds (honest)" },
  { scheme: "random", label: "Random folds (original)" },
];

export default function ComparisonPanel({ ev }: { ev: Evaluation }) {
  const m = ev.final_model;
  const maxGain = ev.feature_importance[0]?.gain || 1;

  return (
    <div className="space-y-4">
      <Card title="LightGBM cross-validation" bodyClass="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead className="border-b border-line">
              <tr>
                <Th>Folds</Th>
                <Th className="text-right">AP</Th>
                <Th className="text-right">Fold mean ± sd</Th>
                <Th className="text-right">Top 1% P / R</Th>
                <Th className="text-right">Precision / recall @0.5</Th>
                <Th className="text-right">Caught in top 1% (easy · medium · hard)</Th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map(({ scheme, label }) => {
                const r = ev.results[scheme][m];
                return (
                  <tr key={scheme} className="border-b border-line last:border-0">
                    <Td className="font-medium">{label}</Td>
                    <Td className={`tnum text-right ${scheme === "grouped" ? "text-accent" : ""}`}>{r.ap.toFixed(1)}</Td>
                    <Td className="tnum text-right text-ink-2">
                      {r.fold_ap_mean.toFixed(1)} ± {r.fold_ap_std.toFixed(1)}
                    </Td>
                    <Td className="tnum text-right">
                      {r.top1_precision.toFixed(2)} / {r.top1_recall.toFixed(2)}
                    </Td>
                    <Td className="tnum text-right">
                      {r.precision_at_0_5.toFixed(2)} / {r.recall_at_0_5.toFixed(2)}
                    </Td>
                    <Td className="tnum text-right">
                      {r.top1_recall_by_difficulty.easy} · {r.top1_recall_by_difficulty.medium} · {r.top1_recall_by_difficulty.hard}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {ev.feature_importance.length > 0 && (
        <Card title="What LightGBM relies on (top 20 features by gain)">
          <div className="space-y-1.5">
            {ev.feature_importance.slice(0, 20).map((f) => (
              <div key={f.feature} className="grid grid-cols-[220px_1fr] items-center gap-3 text-[12px]">
                <span className="truncate font-mono text-ink-2">{f.feature}</span>
                <div className="h-2 rounded bg-surface-2">
                  <div className="h-2 rounded bg-[var(--accent-strong)]" style={{ width: `${(100 * f.gain) / maxGain}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
