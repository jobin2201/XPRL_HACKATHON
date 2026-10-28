export const RULE_NAMES: Record<string, string> = {
  structuring: "Structuring",
  fan_out: "Fan-out burst",
  fan_in: "Fan-in burst",
  round_trip: "Round-tripping",
  rapid_forward: "Rapid forwarding",
  failed_probing: "Failed probing",
  night_activity: "Odd-hour activity",
  fee_spike: "Fee spikes",
  dust: "Dust spraying",
};

export const FEATURE_LABELS: Record<string, string> = {
  n_sent: "Transactions sent",
  n_payments_sent: "Payments sent",
  n_tx_types: "Transaction types used",
  usd_sent_total: "USD sent (total)",
  usd_sent_mean: "USD per payment (mean)",
  usd_sent_max: "Largest payment (USD)",
  usd_sent_std: "Payment size spread (USD)",
  n_unique_dest: "Unique destinations",
  frac_failed: "Share failed",
  frac_night: "Share at night (00-05 UTC)",
  frac_near_threshold: "Share just under 10k USD",
  frac_dest_tag: "Share with destination tag",
  fee_mean: "Mean fee (drops)",
  fee_max: "Max fee (drops)",
  active_days: "Active days",
  max_tx_per_hour: "Peak transactions per hour",
  median_gap_sec: "Median gap between tx (s)",
  tx_per_active_day: "Transactions per active day",
  dest_per_payment: "Destinations per payment",
  n_received: "Payments received",
  usd_received_total: "USD received (total)",
  n_unique_src: "Unique sources",
  n_round_trip_partners: "Two-way counterparties",
  n_transfer_hops_out: "Transfer hops out",
  frac_multi_hop_out: "Share multi-hop",
  in_out_usd_ratio: "Received / sent ratio",
};

export const featureLabel = (f: string) => FEATURE_LABELS[f] ?? f;
export const ruleName = (r: string) => RULE_NAMES[r] ?? r;

export function usd(v: number | null | undefined, opts: { compact?: boolean } = {}) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (opts.compact) {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 }).format(v);
  }
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: v >= 100 ? 0 : 2 }).format(v);
}

export function num(v: number | null | undefined, digits = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(v);
}

export function compact(v: number) {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(v);
}

export function pct(v: number | null | undefined, digits = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function score(v: number | null | undefined) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(2);
}

export function shortAddr(a: string | null | undefined, head = 6, tail = 4) {
  if (!a) return "—";
  return a.length <= head + tail + 1 ? a : `${a.slice(0, head)}…${a.slice(-tail)}`;
}

export function shortHash(h: string) {
  const t = h.replace(/^0+/, "");
  return t.length > 12 ? `${t.slice(0, 6)}…${t.slice(-6)}` : t || h.slice(-8);
}

export function dateTime(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC";
}

export function dateOnly(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

export function dayLabel(d: string) {
  return new Date(`${d}T00:00:00Z`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" });
}

export type Granularity = "minute" | "hour" | "day";

/** Label for an activity bucket key ("2026-10-24T02:48", "2026-10-24T02:00" or "2026-10-24"). */
export function bucketLabel(key: string, g: Granularity = "day", long = false) {
  if (g === "day") return dayLabel(key);
  const d = new Date(`${key}:00Z`);
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
  if (g === "minute" && !long) return time;
  return `${dayLabel(key.slice(0, 10))} ${time}${long ? " UTC" : ""}`;
}
