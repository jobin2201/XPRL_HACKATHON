// Types for the transaction model outputs (written by src/competition.py, served by /api/txmodel/*).

export type Split = "test" | "train";

export interface ScoredTx {
  TRANSACTION_HASH: string;
  time: string;
  from: string;
  to: string;
  usd: number;
  legs: number;
  conversion: boolean;
  score: number;
  rank: number;
  // training split only
  label?: 0 | 1;
  family?: string;
  difficulty?: string;
}

export interface CvResult {
  ap: number;
  fold_ap: number[];
  fold_ap_mean: number;
  fold_ap_std: number;
  top1_precision: number;
  top1_recall: number;
  accuracy_at_0_5: number;
  precision_at_0_5: number;
  recall_at_0_5: number;
  top1_recall_by_difficulty: Record<string, string>;
  seconds: number;
}

export interface Leakage {
  fold_sizes: number[];
  fold_suspicious: number[];
  suspicious_scenarios: number;
  scenarios_split_across_folds: number;
  suspicious_rows_whose_scenario_is_also_in_training: number;
  suspicious_rows: number;
  share_of_check_rows_whose_sender_is_in_training: number;
}

export type Scheme = "random" | "grouped";

export interface Evaluation {
  generated_at: string;
  final_model: string;
  train: { rows: number; suspicious: number; features: string[] };
  test: { rows: number; folder: string };
  fold_method: Record<Scheme | "out_of_fold" | "feature_note", string>;
  leakage: Record<Scheme, Leakage>;
  results: Record<Scheme, Record<string, CvResult>>;
  headline: { random_ap: number; grouped_ap: number; optimism: number };
  feature_importance: { feature: string; gain: number }[];
  submission: { rows: number; all_passed: boolean; size_kb: number };
}

export interface SubmissionCheck {
  file: string;
  rows: number;
  expected_rows: number;
  size_kb: number;
  distinct_scores: number;
  score_min: number;
  score_max: number;
  checks: { check: string; passed: boolean }[];
  all_passed: boolean;
}

export const MODEL_NAMES: Record<string, string> = { lightgbm: "LightGBM" };

export const modelName = (m: string) => MODEL_NAMES[m] ?? m;
