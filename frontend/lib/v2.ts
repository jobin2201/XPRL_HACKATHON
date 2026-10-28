// Types for the LightGBM v2 dashboard API (api/v2.py).

export interface V2Validation {
  site_score_ap: number;
  top1_precision: number;
  top1_recall: number;
  roc_auc: number;
  threshold: number;
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  caught_in_top1: Record<"easy" | "medium" | "hard", string>;
  top1_precision_per_fold?: number[];
  ap_per_fold?: number[];
  extra_groups?: string[];
}

export interface V2Tx {
  TRANSACTION_HASH: string;
  time: string;
  from: string;
  to: string;
  usd: number;
  legs: number;
  conversion?: boolean;
  score: number;
  rank: number;
  flagged?: boolean;
  top1?: boolean;
}

export interface V2Summary {
  run: string;
  command: string;
  validation: V2Validation;
  threshold: number;
  test: { rows: number; flagged: number; top1_cutoff: number; top1_rows: number; usd_flagged: number; wallets_flagged: number };
  histogram: { bin: string; lo: number; hi: number; count: number }[];
  activity: { date: string; transactions: number; flagged: number }[];
  top: V2Tx[];
  importance: { feature: string; gain: number }[];
  has_explanations: boolean;
  llm: boolean;
}

export interface V2Reason {
  feature: string;
  value: number;
  contribution: number;
  text: string;
}

export interface V2Detail {
  hash: string;
  score: number;
  rank: number;
  total: number;
  flagged: boolean;
  top1: boolean;
  threshold: number;
  transaction: Record<string, string | number | boolean>;
  legs: { leg: number; type: string; from: string; to: string; asset: string; issuer: string | null; amount: number; usd: number | null }[];
  block: Record<string, string | number>;
  rate: { asset: string; hour: string; usd_per_unit: number | null };
  wallets: Record<"sender" | "receiver", { address: string; payments: number; flagged: number }>;
  reasons: V2Reason[];
}

export interface V2GraphEdge {
  from: string;
  to: string;
  count: number;
  usd: number;
  max_score: number;
  flagged: boolean;
  top_tx: string;
  first: string;
}

export interface V2Graph {
  centre: string[];
  tx: string | null;
  window_hours: number;
  from: string;
  to: string;
  nodes: { id: string; centre: boolean; payments: number; max_score: number; flagged: boolean }[];
  edges: V2GraphEdge[];
  threshold: number;
  payments_in_view: number;
}

export interface V2Model {
  key: string;
  name: string;
  algorithm: string;
  features: string;
  selected: boolean;
  ap: number | null;
  top1_precision: number | null;
  top1_recall: number | null;
  roc_auc: number | null;
  accuracy: number | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  caught: Record<string, string> | null;
  ap_per_fold: number[] | null;
  site: { score: number; precision: number; recall: number } | null;
  upload_folder: string | null;
}

export interface V2Models {
  models: V2Model[];
  ablation: { label: string; ap: number; top1_precision: number }[];
  isolation_forest_ready: boolean;
  site_file?: string;
}

export interface V2Split {
  folder: string;
  files: Record<string, number>;
  payments: number;
  wallets: number;
  senders: number;
  start: string;
  end: string;
  usd_total: number;
  usd_median: number;
  conversion_share: number;
  per_day: { day: number; payments: number }[];
  currencies: { currency: string; payments: number }[];
  legs: { legs: number; payments: number }[];
  amounts: { band: string; payments: number }[];
  labels?: {
    normal: number;
    suspicious: number;
    look_alikes: number;
    by_difficulty: { difficulty: string; payments: number }[];
    by_family: { family: string; payments: number }[];
    suspicious_per_day: { day: number; payments: number }[];
  };
  flagged?: number;
  top1?: number;
}

export interface V2Datasets {
  train: V2Split;
  test: V2Split;
}

// score -> colour, shared by tables and the graph (low = slate, high = red)
export function scoreColor(s: number) {
  if (s >= 0.9) return "#d03b3b";
  if (s >= 0.5) return "#ec835a";
  if (s >= 0.171) return "#fab219";
  return "#3b5072";
}
