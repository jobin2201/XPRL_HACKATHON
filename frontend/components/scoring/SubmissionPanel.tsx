// Result of every check run on submission.csv by src/competition.py.
import { CheckCircle2, XCircle } from "lucide-react";
import { Card, StatTile } from "@/components/ui";
import { num } from "@/lib/format";
import type { SubmissionCheck } from "@/lib/txmodel";

export default function SubmissionPanel({ sub }: { sub: SubmissionCheck }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Status" value={sub.all_passed ? "Ready to upload" : "Not ready"} tone={sub.all_passed ? "accent" : "critical"} />
        <StatTile label="Rows" value={num(sub.rows)} sub={`Expected ${num(sub.expected_rows)}`} />
        <StatTile label="Distinct scores" value={num(sub.distinct_scores)} sub={`${sub.score_min.toFixed(4)} – ${sub.score_max.toFixed(4)}`} />
        <StatTile label="File size" value={`${sub.size_kb.toFixed(0)} KB`} sub="Limit 12 MiB" />
      </div>
      <Card title="Submission checks" subtitle={<span className="break-all font-mono">{sub.file}</span>}>
        <ul className="space-y-2 text-[13px]">
          {sub.checks.map((c) => (
            <li key={c.check} className="flex items-center gap-2">
              {c.passed ? <CheckCircle2 className="h-4 w-4 text-accent" /> : <XCircle className="h-4 w-4 text-critical" />}
              <span className={c.passed ? "text-ink" : "text-critical"}>{c.check}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-muted">
          Upload <span className="font-mono">submission.csv</span> and your code ZIP at hackathon.ukcbt.org. Regenerate with{" "}
          <span className="font-mono">python src/competition.py</span>.
        </p>
      </Card>
    </div>
  );
}
