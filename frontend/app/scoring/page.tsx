"use client";

// 07 · Transaction scoring: one sub-tab per check of the transaction model (src/competition.py).
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import ComparisonPanel from "@/components/scoring/ComparisonPanel";
import EvaluationPanel from "@/components/scoring/EvaluationPanel";
import ScoresTable from "@/components/scoring/ScoresTable";
import SubmissionPanel from "@/components/scoring/SubmissionPanel";
import { ErrorState, Loading, PageHeader, Segmented } from "@/components/ui";
import { useApi } from "@/lib/api";
import type { Evaluation, SubmissionCheck } from "@/lib/txmodel";

type Tab = "test" | "train" | "evaluation" | "comparison" | "submission";

const TABS: { value: Tab; label: string }[] = [
  { value: "evaluation", label: "Folds & leakage" },
  { value: "train", label: "Training scores" },
];

export default function ScoringPage() {
  return (
    <Suspense fallback={<Loading className="h-[60vh]" />}>
      <Scoring />
    </Suspense>
  );
}

function Scoring() {
  const router = useRouter();
  const params = useSearchParams();
  const tab = (params.get("tab") as Tab) || "evaluation";
  const ev = useApi<Evaluation>("/api/txmodel/evaluation");
  const sub = useApi<SubmissionCheck>(tab === "submission" ? "/api/txmodel/submission" : null);

  return (
    <>
      <PageHeader
        eyebrow="LightGBM v2 · validation"
        title="How the v2 model was validated"
      />
      <div className="mb-4">
        <Segmented value={tab} options={TABS} onChange={(v) => router.replace(`/scoring?tab=${v}`)} />
      </div>

      {tab === "test" && <ScoresTable key="test" split="test" />}
      {tab === "train" && <ScoresTable key="train" split="train" />}
      {(tab === "evaluation" || tab === "comparison") &&
        (ev.error ? (
          <ErrorState error={ev.error} onRetry={ev.reload} />
        ) : !ev.data ? (
          <Loading />
        ) : tab === "evaluation" ? (
          <EvaluationPanel ev={ev.data} />
        ) : (
          <ComparisonPanel ev={ev.data} />
        ))}
      {tab === "submission" &&
        (sub.error ? <ErrorState error={sub.error} onRetry={sub.reload} /> : !sub.data ? <Loading /> : <SubmissionPanel sub={sub.data} />)}
    </>
  );
}
