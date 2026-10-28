"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Address, Card, Empty, ErrorState, Loading, PageHeader, RuleChip, ScoreBar, Segmented, StatusPill, Td, Th, TierBadge, riskColor } from "@/components/ui";
import { type AccountRow, type CaseStatus, qs, useApi } from "@/lib/api";
import { num, usd } from "@/lib/format";

type View = "flagged" | CaseStatus;

export default function CasesPage() {
  const [view, setView] = useState<View>("flagged");
  const router = useRouter();
  const params = view === "flagged" ? { flagged: "true", status: "open" } : { status: view };
  const { data, error, reload } = useApi<{ total: number; items: AccountRow[] }>(`/api/accounts${qs({ ...params, limit: 200 })}`);

  return (
    <>
      <PageHeader
        eyebrow="05 · Case details"
        title="Case queue"
        actions={
          <Segmented
            value={view}
            onChange={setView}
            options={[
              { value: "flagged", label: "Awaiting decision" },
              { value: "review", label: "In review" },
              { value: "escalated", label: "Escalated" },
              { value: "dismissed", label: "Dismissed" },
            ]}
          />
        }
      />
      <Card bodyClass="p-0">
        {error ? (
          <div className="p-5">
            <ErrorState error={error} onRetry={reload} />
          </div>
        ) : !data ? (
          <Loading />
        ) : data.items.length === 0 ? (
          <Empty>{view === "flagged" ? "Every flagged account has a decision." : "No cases with this status yet. Open a case and record a decision."}</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead className="border-b border-line">
                <tr>
                  <Th>Account</Th>
                  <Th>Tier</Th>
                  <Th>Risk</Th>
                  <Th>Rules</Th>
                  <Th className="text-right">Sent</Th>
                  <Th className="text-right">Received</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.account} onClick={() => router.push(`/cases/${a.account}`)} className="cursor-pointer border-b border-line last:border-0 hover:bg-hover">
                    <Td><Address value={a.account} /></Td>
                    <Td><TierBadge tier={a.tier} /></Td>
                    <Td><ScoreBar value={a.risk_score} color={riskColor(a.risk_score)} /></Td>
                    <Td>
                      <div className="flex gap-1">{a.rules.length ? a.rules.map((r) => <RuleChip key={r} id={r} />) : <span className="text-xs text-muted">Model / anomaly only</span>}</div>
                    </Td>
                    <Td className="tnum text-right text-ink-2">{usd(a.usd_sent_total, { compact: true })}</Td>
                    <Td className="tnum text-right text-ink-2">{usd(a.usd_received_total, { compact: true })}</Td>
                    <Td><StatusPill status={a.status ?? "open"} /></Td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="border-t border-line px-5 py-3 text-xs text-muted tnum">{num(data.total)} cases</div>
          </div>
        )}
      </Card>
    </>
  );
}
