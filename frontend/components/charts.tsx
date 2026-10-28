"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { type Granularity, bucketLabel, compact, featureLabel, num, ruleName, shortAddr, usd } from "@/lib/format";

/* Chart tokens: series colours validated against the --surface navy (#0f1b30). */
export const C = {
  // series colours stay the same in both themes; neutrals follow the theme through CSS variables
  s1: "#1ea3bc",
  s2: "#d95926",
  s3: "#9085e9",
  grid: "var(--grid)",
  axis: "var(--axis)",
  muted: "var(--muted)",
  ink: "var(--ink)",
  ink2: "var(--ink-2)",
  surface: "var(--surface)",
  deemph: "var(--low)",
  critical: "#d03b3b",
  serious: "#ec835a",
  warning: "#fab219",
};

const tick = { fill: C.muted, fontSize: 11 };
const axisProps = { tick, tickLine: false, axisLine: { stroke: C.axis }, stroke: C.axis };

type TipRow = { label: string; value: string; color?: string };

function TipBox({ title, rows }: { title?: string; rows: TipRow[] }) {
  return (
    <div className="min-w-[150px] rounded-md border border-line-strong bg-[#0a1426] px-3 py-2 text-xs shadow-xl">
      {title && <div className="mb-1.5 text-[11px] text-muted">{title}</div>}
      {rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between gap-4 py-0.5">
          <span className="flex items-center gap-1.5 text-ink-2">
            {r.color && <span className="h-2 w-2 rounded-sm" style={{ background: r.color }} />}
            {r.label}
          </span>
          <span className="tnum font-medium text-ink">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

export function LegendKey({ items }: { items: { label: string; color: string; kind?: "line" | "box" | "dot" }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5">
          {i.kind === "line" ? (
            <span className="h-0.5 w-3.5 rounded-full" style={{ background: i.color }} />
          ) : i.kind === "dot" ? (
            <span className="h-2 w-2 rounded-full" style={{ background: i.color }} />
          ) : (
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: i.color }} />
          )}
          {i.label}
        </span>
      ))}
    </div>
  );
}

/* eslint-disable @typescript-eslint/no-explicit-any */

// ------------------------------------------------------------ activity over time
export function ActivityChart({ data, granularity = "day" }: { data: { date: string; transactions: number; flagged: number }[]; granularity?: Granularity }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={C.grid} />
        <XAxis dataKey="date" {...axisProps} tickFormatter={(k) => bucketLabel(k, granularity)} minTickGap={28} />
        <YAxis {...axisProps} axisLine={false} tickFormatter={compact} width={44} />
        <Tooltip
          cursor={{ stroke: C.axis, strokeWidth: 1 }}
          content={({ active, payload, label }: any) =>
            active && payload?.length ? (
              <TipBox
                title={bucketLabel(label, granularity, true)}
                rows={[
                  { label: "All transactions", value: num(payload[0].payload.transactions), color: C.s1 },
                  { label: "Touching flagged", value: num(payload[0].payload.flagged), color: C.s2 },
                ]}
              />
            ) : null
          }
        />
        <Area isAnimationActive={false} type="monotone" dataKey="transactions" stroke={C.s1} strokeWidth={2} fill={C.s1} fillOpacity={0.1} dot={false} activeDot={{ r: 4, stroke: C.surface, strokeWidth: 2 }} />
        <Line isAnimationActive={false} type="monotone" dataKey="flagged" stroke={C.s2} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: C.surface, strokeWidth: 2 }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ------------------------------------------------------------ risk score distribution
export function tierFill(lo: number) {
  return lo >= 0.75 ? C.critical : lo >= 0.5 ? C.serious : lo >= 0.3 ? C.warning : C.deemph;
}

export function RiskHistogram({ data }: { data: { bin: string; lo: number; hi: number; count: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }} barCategoryGap={2}>
        <CartesianGrid vertical={false} stroke={C.grid} />
        <XAxis dataKey="lo" {...axisProps} tickFormatter={(v) => Number(v).toFixed(1)} interval={1} />
        <YAxis {...axisProps} axisLine={false} scale="sqrt" width={44} tickFormatter={compact} />
        <Tooltip
          cursor={{ fill: "rgba(94,207,224,0.05)" }}
          content={({ active, payload }: any) =>
            active && payload?.length ? (
              <TipBox title={`Risk ${payload[0].payload.lo.toFixed(2)}–${payload[0].payload.hi.toFixed(2)}`} rows={[{ label: "Accounts", value: num(payload[0].payload.count), color: tierFill(payload[0].payload.lo) }]} />
            ) : null
          }
        />
        <Bar isAnimationActive={false} dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={24}>
          {data.map((d) => (
            <Cell key={d.bin} fill={tierFill(d.lo)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ------------------------------------------------------------ horizontal bars (rules / features)
export function HBarChart({
  data,
  height,
  valueFormat = (v: number) => num(v),
  labelWidth = 150,
  color = C.s1,
  onClick,
}: {
  data: { key: string; label: string; value: number }[];
  height?: number;
  valueFormat?: (v: number) => string;
  labelWidth?: number;
  color?: string;
  onClick?: (key: string) => void;
}) {
  // Plain HTML bars: label column, 12px bar with a 4px rounded data-end, value at the tip.
  const max = Math.max(...data.map((d) => d.value), 1e-9);
  return (
    <ul className="space-y-1" style={height ? { minHeight: height } : undefined}>
      {data.map((d) => {
        const inner = (
          <>
            <span className="truncate text-right text-xs text-ink-2" style={{ width: labelWidth, flex: `0 0 ${labelWidth}px` }}>
              {d.label}
            </span>
            <span className="relative flex h-6 flex-1 items-center">
              <span
                className="h-3 rounded-r-[4px] transition-opacity group-hover:opacity-80"
                style={{ width: `${(d.value / max) * 85}%`, minWidth: d.value > 0 ? 2 : 0, background: color }}
              />
              <span className="tnum ml-2 text-[11px] text-ink-2">{valueFormat(d.value)}</span>
            </span>
          </>
        );
        const cls = "group flex w-full items-center gap-3 rounded px-1 hover:bg-hover";
        return (
          <li key={d.key} title={`${d.label}: ${valueFormat(d.value)}`}>
            {onClick ? (
              <button type="button" onClick={() => onClick(d.key)} className={cls}>
                {inner}
              </button>
            ) : (
              <div className={cls}>{inner}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export const ruleBarData = (rows: { id: string; count: number }[]) => rows.map((r) => ({ key: r.id, label: ruleName(r.id), value: r.count }));
export const featureBarData = (rows: { feature: string; importance: number }[]) => rows.map((r) => ({ key: r.feature, label: featureLabel(r.feature), value: r.importance }));

// ------------------------------------------------------------ received vs sent per day
export function FlowChart({ data, granularity = "day" }: { data: { date: string; received_usd: number; sent_usd: number; received_n: number; sent_n: number }[]; granularity?: Granularity }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -4, bottom: 0 }} barGap={2} barCategoryGap="20%">
        <CartesianGrid vertical={false} stroke={C.grid} />
        <XAxis dataKey="date" {...axisProps} tickFormatter={(k) => bucketLabel(k, granularity)} minTickGap={24} />
        <YAxis {...axisProps} axisLine={false} tickFormatter={(v) => usd(v, { compact: true })} width={56} />
        <Tooltip
          cursor={{ fill: "rgba(94,207,224,0.05)" }}
          content={({ active, payload, label }: any) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload;
            return (
              <TipBox
                title={bucketLabel(label, granularity, true)}
                rows={[
                  { label: `Received (${p.received_n})`, value: usd(p.received_usd), color: C.s1 },
                  { label: `Sent (${p.sent_n})`, value: usd(p.sent_usd), color: C.s2 },
                ]}
              />
            );
          }}
        />
        <Bar isAnimationActive={false} dataKey="received_usd" fill={C.s1} radius={[4, 4, 0, 0]} maxBarSize={14} />
        <Bar isAnimationActive={false} dataKey="sent_usd" fill={C.s2} radius={[4, 4, 0, 0]} maxBarSize={14} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ------------------------------------------------------------ model score vs anomaly score
export function RankScatter({
  data,
  onSelect,
  yAxis = "model",
}: {
  data: { account: string; model_score: number | null; anomaly_score: number; rule_score: number; flagged: boolean }[];
  onSelect?: (account: string) => void;
  /** "model" plots the supervised score; "rules" plots rule_score / 100 (for unlabelled datasets) */
  yAxis?: "model" | "rules";
}) {
  const pts = data.map((d) => ({ ...d, y: yAxis === "model" ? (d.model_score ?? 0) : d.rule_score / 100 }));
  const others = pts.filter((d) => !d.flagged);
  const flagged = pts.filter((d) => d.flagged);
  const tip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const p = payload[0].payload;
    return (
      <TipBox
        title={shortAddr(p.account, 8, 6)}
        rows={[
          ...(yAxis === "model" ? [{ label: "Model score", value: p.model_score === null ? "n/a" : p.model_score.toFixed(2) }] : []),
          { label: "Anomaly pct.", value: p.anomaly_score.toFixed(2) },
          { label: "Rule score", value: String(p.rule_score) },
          { label: "Status", value: p.flagged ? "Flagged" : "Not flagged", color: p.flagged ? C.s2 : C.s1 },
        ]}
      />
    );
  };
  return (
    <ResponsiveContainer width="100%" height={320}>
      <ScatterChart margin={{ top: 8, right: 16, left: 16, bottom: 16 }}>
        <CartesianGrid stroke={C.grid} />
        <XAxis
          type="number"
          dataKey="anomaly_score"
          domain={[0, 1]}
          {...axisProps}
          tickFormatter={(v) => v.toFixed(1)}
          label={{ value: "Isolation Forest anomaly percentile", position: "insideBottom", offset: -10, fill: C.muted, fontSize: 11 }}
        />
        <YAxis
          type="number"
          dataKey="y"
          domain={[0, 1]}
          {...axisProps}
          tickFormatter={(v) => v.toFixed(1)}
          width={40}
          label={{ value: yAxis === "model" ? "Supervised score" : "Rule score / 100", angle: -90, position: "left", offset: -4, fill: C.muted, fontSize: 11 }}
        />
        <ZAxis range={[48, 48]} />
        <Tooltip cursor={{ stroke: C.axis }} content={tip} />
        <Scatter isAnimationActive={false} data={others} fill={C.s1} fillOpacity={0.55} stroke={C.surface} strokeWidth={1} onClick={(d: any) => onSelect?.(d.account ?? d.payload?.account)} cursor="pointer" />
        <Scatter isAnimationActive={false} data={flagged} fill={C.s2} stroke={C.surface} strokeWidth={2} onClick={(d: any) => onSelect?.(d.account ?? d.payload?.account)} cursor="pointer" />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

// ------------------------------------------------------------ anomaly distribution (stacked)
export function AnomalyHistogram({ data }: { data: { bin: string; all: number; flagged: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }} barCategoryGap={2}>
        <CartesianGrid vertical={false} stroke={C.grid} />
        <XAxis dataKey="bin" {...axisProps} tickFormatter={(v) => Number(v).toFixed(1)} interval={1} />
        <YAxis {...axisProps} axisLine={false} width={44} />
        <Tooltip
          cursor={{ fill: "rgba(94,207,224,0.05)" }}
          content={({ active, payload }: any) =>
            active && payload?.length ? (
              <TipBox
                title={`Percentile ${Number(payload[0].payload.bin).toFixed(2)}+`}
                rows={[
                  { label: "Not flagged", value: num(payload[0].payload.all), color: C.s1 },
                  { label: "Flagged", value: num(payload[0].payload.flagged), color: C.s2 },
                ]}
              />
            ) : null
          }
        />
        <Bar isAnimationActive={false} dataKey="all" stackId="a" fill={C.s1} stroke={C.surface} strokeWidth={2} maxBarSize={24} />
        <Bar isAnimationActive={false} dataKey="flagged" stackId="a" fill={C.s2} stroke={C.surface} strokeWidth={2} radius={[4, 4, 0, 0]} maxBarSize={24} />
      </BarChart>
    </ResponsiveContainer>
  );
}
