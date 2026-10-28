"use client";

import { useCallback, useEffect, useState } from "react";

/* All requests go to /api/*, which next.config.ts rewrites to the FastAPI server on :8000. */

export type Tier = "critical" | "high" | "medium" | "low";
export type CaseStatus = "open" | "review" | "dismissed" | "escalated";

export interface AccountRow {
  account: string;
  model_score: number | null;
  anomaly_score: number;
  rule_score: number;
  rules_triggered: number;
  risk_score: number;
  tier: Tier;
  flagged: boolean;
  labelled: boolean;
  label: number | null;
  rules: string[];
  n_sent: number;
  n_received: number;
  usd_sent_total: number;
  usd_received_total: number;
  n_unique_dest: number;
  n_unique_src: number;
  status?: CaseStatus;
}

export interface Tx {
  tx_hash: string;
  ledger_index?: number;
  timestamp: string;
  tx_type: string;
  account: string;
  destination: string | null;
  amount: number;
  currency: string;
  amount_usd: number;
  fee: number;
  destination_tag: number | null;
  result: string;
  direction?: "in" | "out" | "self";
}

export interface RuleMeta {
  id: string;
  name: string;
  weight: number;
  description: string;
  disabled?: string | null;
}

export type Granularity = "minute" | "hour" | "day";

/** Where a dataset came from (written by import_official.py or ex4_mainnet_to_pipeline.py). */
export interface DataSource {
  network: string;
  ledger_start: number;
  ledger_end: number;
  first_close: string;
  last_close: string;
  xrp_usd: number;
  xrp_usd_source: string;
}

export interface RuleHit extends RuleMeta {
  evidence: Record<string, unknown> & { summary: string; examples?: Record<string, unknown>[] };
}

export interface Overview {
  kpis: {
    transactions: number;
    accounts: number;
    flagged: number;
    critical: number;
    high: number;
    usd_volume: number;
    failed_rate: number;
    start: string;
    end: string;
    under_review: number;
    self_payments?: number;
  };
  granularity: Granularity;
  dataset: string;
  supervised_available: boolean;
  source?: DataSource | null;
  tiers: Record<Tier, number>;
  score_distribution: { bin: string; lo: number; hi: number; count: number }[];
  rule_counts: (RuleMeta & { count: number })[];
  activity: { date: string; transactions: number; flagged: number; failed: number; usd: number }[];
  top_accounts: (Pick<AccountRow, "account" | "risk_score" | "model_score" | "anomaly_score" | "rule_score" | "tier" | "rules" | "usd_sent_total"> & { status: CaseStatus })[];
  recent_flagged_tx: Tx[];
  model_version: string;
  generated_at: string;
}

export interface AccountDetail {
  account: string;
  scores: AccountRow;
  features: Record<string, number>;
  rules: RuleHit[];
  rules_not_triggered: RuleMeta[];
  deviations: { feature: string; z: number; value: number; median: number }[];
  timeline: { date: string; received_usd: number; sent_usd: number; received_n: number; sent_n: number }[];
  granularity: Granularity;
  counterparties: {
    counterparty: string;
    sum_in: number;
    sum_out: number;
    count_in: number;
    count_out: number;
    total: number;
    risk_score: number | null;
    flagged: boolean;
  }[];
  totals: { received_usd: number; sent_usd: number; first_seen: string | null; last_seen: string | null; tx_count: number };
  transactions: Tx[];
  status: { status: CaseStatus; note: string; updated_at: string | null };
  risk_formula: string;
  tier: Tier;
}

export interface NetNode {
  id: string;
  risk_score: number;
  tier: Tier;
  flagged: boolean;
  rules: string[];
  patterns: ("fan_out" | "fan_in" | "cycle" | "peel_chain")[];
  usd_sent: number;
  usd_received: number;
  focus: boolean;
}
export interface NetEdge {
  source: string;
  target: string;
  count: number;
  usd: number;
  reciprocal: boolean;
  peel: boolean;
}
export interface Network {
  nodes: NetNode[];
  edges: NetEdge[];
  range: { start: string; end: string };
}

export interface ModelInsights {
  dataset: string;
  supervised_available: boolean;
  source?: DataSource | null;
  rule_params?: Record<string, number | boolean | null>;
  model_version: string;
  generated_at: string;
  supervised_model: string;
  anomaly_model: string;
  risk_formula: string;
  flag_rule: string;
  n_accounts: number;
  n_labelled: number;
  metrics: Record<string, number>;
  feature_importance: { feature: string; importance: number }[];
  rules: RuleMeta[];
  limitations: string[];
  spearman: Record<string, Record<string, number>>;
  overlap: { k: number; anomaly_vs_rules: number; model_vs_anomaly?: number; model_vs_rules?: number; all_three?: number };
  scatter: Pick<AccountRow, "account" | "model_score" | "anomaly_score" | "rule_score" | "risk_score" | "tier" | "flagged" | "label">[];
  anomaly_distribution: { bin: string; all: number; flagged: number }[];
  disagreements: Pick<AccountRow, "account" | "model_score" | "anomaly_score" | "rule_score" | "risk_score" | "rules">[];
  labelled_suspicious: number;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { cache: "no-store", ...init });
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new Error(detail);
  }
  return r.json() as Promise<T>;
}

/** Minimal data hook: refetches whenever `path` changes. Pass null to skip. */
export function useApi<T>(path: string | null) {
  const [nonce, setNonce] = useState(0);
  // `key` identifies the request; loading = the latest settled response is for a different key.
  const key = path === null ? null : `${path}#${nonce}`;
  const [state, setState] = useState<{ key?: string; data?: T; error?: string }>({});

  useEffect(() => {
    if (path === null || key === null) return;
    let alive = true;
    apiFetch<T>(path)
      .then((d) => alive && setState({ key, data: d }))
      .catch((e: Error) => alive && setState((s) => ({ key, data: s.data, error: e.message })));
    return () => {
      alive = false;
    };
  }, [path, key]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const loading = key !== null && state.key !== key;
  // keep showing the previous data while a new request is in flight
  return { data: state.data, error: loading ? undefined : state.error, loading, reload };
}

export function qs(params: Record<string, string | number | boolean | undefined | null>) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}
