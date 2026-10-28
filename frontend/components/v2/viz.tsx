"use client";

// Chart building blocks for the v2 dashboard (recharts). Neutral colours follow the light/dark theme via CSS variables.
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export const PALETTE = { train: "#1ea3bc", test: "#9085e9", bad: "#e5484d", warn: "#f5a524", good: "#2bb673", soft: "var(--low)" };
const tick = { fill: "var(--muted)", fontSize: 11 };
const tooltipStyle = {
  contentStyle: { background: "var(--surface)", border: "1px solid var(--border-strong)", borderRadius: 8, fontSize: 12, color: "var(--ink)" },
  labelStyle: { color: "var(--ink-2)" },
  itemStyle: { color: "var(--ink)" },
  cursor: { fill: "var(--hover)" },
};

/** Ring gauge: value 0..max, big number in the middle. */
export function Gauge({ value, max = 1, label, display, color }: { value: number; max?: number; label: string; display: string; color: string }) {
  const data = [{ v: (value / max) * 100, fill: color }];
  return (
    <div className="flex min-w-0 flex-col items-center">
      <div className="relative aspect-square w-full max-w-[132px]">
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart innerRadius="78%" outerRadius="100%" data={data} startAngle={90} endAngle={-270}>
            <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
            <RadialBar dataKey="v" cornerRadius={10} background={{ fill: "var(--surface-2)" }} isAnimationActive animationDuration={1100} />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <span className="tnum text-lg font-semibold tracking-tight text-ink sm:text-[26px]">{display}</span>
        </div>
      </div>
      <span className="mt-1 text-center text-[11px] leading-tight text-ink-2 sm:text-xs">{label}</span>
    </div>
  );
}

/** Horizontal percentage bars with a soft track. */
export function MetricBars({ rows }: { rows: { label: string; value: number; display: string; color: string; hint?: string }[] }) {
  return (
    <div className="space-y-3.5">
      {rows.map((r) => (
        <div key={r.label}>
          <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
            <span className="text-ink-2">{r.label}</span>
            <span className="tnum font-medium text-ink">{r.display}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-surface-2">
            <div className="h-full rounded-full transition-[width] duration-1000 ease-out" style={{ width: `${Math.max(2, r.value * 100)}%`, background: r.color }} />
          </div>
          {r.hint && <p className="mt-0.5 text-[11px] text-muted">{r.hint}</p>}
        </div>
      ))}
    </div>
  );
}

/** Donut with a centre label and a legend underneath. */
export function Donut({ data, centre, sub }: { data: { name: string; value: number; color: string }[]; centre: string; sub: string }) {
  const total = data.reduce((a, d) => a + d.value, 0);
  return (
    <div>
      <div className="relative h-[170px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius="66%" outerRadius="92%" paddingAngle={data.length > 1 ? 2 : 0} stroke="none" animationDuration={900}>
              {data.map((d) => (
                <Cell key={d.name} fill={d.color} />
              ))}
            </Pie>
            <Tooltip {...tooltipStyle} formatter={(v) => [`${Number(v).toLocaleString("en-GB")} (${((Number(v) / total) * 100).toFixed(1)}%)`, ""]} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
          <div>
            <div className="tnum text-xl font-semibold text-ink">{centre}</div>
            <div className="text-[11px] text-muted">{sub}</div>
          </div>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 text-[11px] text-ink-2">
        {data.map((d) => (
          <span key={d.name} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
            {d.name} · {d.value.toLocaleString("en-GB")}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Grouped (or stacked) vertical bars. series = [{key, name, color}] */
export function Bars({
  data,
  x,
  series,
  height = 220,
  stacked = false,
  percent = false,
}: {
  data: Record<string, string | number>[];
  x: string;
  series: { key: string; name: string; color: string }[];
  height?: number;
  stacked?: boolean;
  percent?: boolean;
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }} barCategoryGap="22%">
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey={x} tick={tick} tickLine={false} axisLine={{ stroke: "var(--axis)" }} />
          <YAxis tick={tick} tickLine={false} axisLine={false} tickFormatter={(v) => (percent ? `${v}%` : Number(v) >= 1000 ? `${Math.round(Number(v) / 1000)}k` : String(v))} />
          <Tooltip {...tooltipStyle} formatter={(v, n) => [percent ? `${Number(v).toFixed(1)}%` : Number(v).toLocaleString("en-GB"), n]} />
          {series.length > 1 && <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: "var(--ink-2)" }} />}
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} stackId={stacked ? "a" : undefined} radius={stacked && i < series.length - 1 ? 0 : [5, 5, 0, 0]} animationDuration={900} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Smooth area trend for one or two series. */
export function Trend({ data, x, series, height = 220 }: { data: Record<string, string | number>[]; x: string; series: { key: string; name: string; color: string }[]; height?: number }) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
          <defs>
            {series.map((s) => (
              <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity={0.38} />
                <stop offset="100%" stopColor={s.color} stopOpacity={0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey={x} tick={tick} tickLine={false} axisLine={{ stroke: "var(--axis)" }} minTickGap={24} />
          <YAxis tick={tick} tickLine={false} axisLine={false} />
          <Tooltip {...tooltipStyle} cursor={{ stroke: "var(--axis)" }} />
          {series.length > 1 && <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: "var(--ink-2)" }} />}
          {series.map((s) => (
            <Area key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} fill={`url(#grad-${s.key})`} animationDuration={1000} />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
