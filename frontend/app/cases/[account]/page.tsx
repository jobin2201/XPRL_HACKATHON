import { Suspense } from "react";
import { Loading } from "@/components/ui";
import CaseView from "./CaseView";

export default function CasePage({ params }: PageProps<"/cases/[account]">) {
  return (
    <Suspense fallback={<Loading label="Loading case" className="h-[60vh]" />}>
      <CaseView params={params} />
    </Suspense>
  );
}
