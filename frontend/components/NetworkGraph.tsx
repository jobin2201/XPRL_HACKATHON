"use client";

import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";
import { useEffect, useMemo, useRef, useState } from "react";
import { Maximize2, Minus, Plus } from "lucide-react";
import type { NetEdge, NetNode, Network } from "@/lib/api";
import { shortAddr, usd } from "@/lib/format";
import { C } from "./charts";

export type Pattern = "fan_out" | "fan_in" | "cycle" | "peel_chain";

export const PATTERN_META: Record<Pattern, { label: string; color: string; help: string }> = {
  fan_out: { label: "Fan-out", color: C.s1, help: "One account paying many destinations in a burst" },
  fan_in: { label: "Fan-in", color: C.s1, help: "Many sources paying one account in a burst" },
  cycle: { label: "Cycles", color: C.s3, help: "Value flowing out and back between the same accounts" },
  peel_chain: { label: "Peel chains", color: C.s2, help: "Payments received and forwarded on within minutes" },
};

type SimNode = NetNode & SimulationNodeDatum & { r: number };
type SimLink = SimulationLinkDatum<SimNode> & NetEdge & { kind: "cycle" | "peel" | "fan" | "plain" };

const TIER_FILL: Record<string, string> = { critical: C.critical, high: C.serious, medium: C.warning, low: "#3b5072" };
const W = 1000;
const H = 640;

export function NetworkGraph({ data, active, selected, onSelect }: { data: Network; active: Set<Pattern>; selected: string | null; onSelect: (id: string | null) => void }) {
  const { nodes, links } = useMemo(() => layout(data), [data]);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [hover, setHover] = useState<{ node?: SimNode; link?: SimLink; x: number; y: number; w: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null);

  // reset pan/zoom whenever a new graph arrives
  const [prevData, setPrevData] = useState(data);
  if (prevData !== data) {
    setPrevData(data);
    setView({ x: 0, y: 0, k: 1 });
  }

  // wheel zoom (non-passive listener so we can preventDefault)
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const mx = ((e.clientX - rect.left) / rect.width) * W;
      const my = ((e.clientY - rect.top) / rect.height) * H;
      setView((v) => {
        const k = Math.min(6, Math.max(0.4, v.k * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
        return { k, x: mx - ((mx - v.x) * k) / v.k, y: my - ((my - v.y) * k) / v.k };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const neighbours = useMemo(() => {
    if (!selected) return null;
    const s = new Set([selected]);
    for (const l of links) {
      const a = (l.source as SimNode).id, b = (l.target as SimNode).id;
      if (a === selected) s.add(b);
      if (b === selected) s.add(a);
    }
    return s;
  }, [selected, links]);

  const highlighting = active.size > 0;
  const nodeOn = (n: SimNode) => {
    if (neighbours) return neighbours.has(n.id);
    if (!highlighting) return true;
    return n.patterns.some((p) => active.has(p));
  };
  const linkKindOn = (l: SimLink) => {
    if (l.kind === "cycle") return active.has("cycle");
    if (l.kind === "peel") return active.has("peel_chain");
    if (l.kind === "fan") return active.has("fan_out") || active.has("fan_in");
    return false;
  };
  const linkOn = (l: SimLink) => {
    const a = l.source as SimNode, b = l.target as SimNode;
    if (neighbours) return a.id === selected || b.id === selected;
    if (!highlighting) return true;
    return linkKindOn(l);
  };
  // Neutral by default; cycles and peel chains always carry their colour, fans only when highlighted.
  const linkColor = (l: SimLink) => {
    const show = neighbours ? true : highlighting ? linkKindOn(l) : true;
    if (!show) return C.axis;
    if (l.kind === "cycle") return C.s3;
    if (l.kind === "peel") return C.s2;
    if (l.kind === "fan" && (active.has("fan_out") || active.has("fan_in"))) return C.s1;
    return "#3a4f72";
  };

  function toLocal(e: React.MouseEvent) {
    const rect = svgRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top, w: rect.width };
  }

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="h-[560px] w-full cursor-grab touch-none select-none active:cursor-grabbing md:h-[640px]"
        role="img"
        aria-label="Payment network graph"
        onMouseDown={(e) => (drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false })}
        onMouseMove={(e) => {
          const d = drag.current;
          if (!d) return;
          const rect = svgRef.current!.getBoundingClientRect();
          const dx = ((e.clientX - d.x) / rect.width) * W, dy = ((e.clientY - d.y) / rect.height) * H;
          if (Math.abs(dx) + Math.abs(dy) > 2) d.moved = true;
          setView((v) => ({ ...v, x: d.vx + dx, y: d.vy + dy }));
        }}
        onMouseUp={() => {
          if (drag.current && !drag.current.moved) onSelect(null);
          drag.current = null;
        }}
        onMouseLeave={() => {
          drag.current = null;
          setHover(null);
        }}
      >
        <defs>
          {[C.s1, C.s2, C.s3, "#3a4f72", C.axis].map((c) => (
            <marker key={c} id={`arrow-${c.slice(1)}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill={c} />
            </marker>
          ))}
        </defs>
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {links.map((l, i) => {
            const a = l.source as SimNode, b = l.target as SimNode;
            const on = linkOn(l);
            const color = linkColor(l);
            const dx = b.x! - a.x!, dy = b.y! - a.y!;
            const len = Math.hypot(dx, dy) || 1;
            // curve reciprocal edges so both directions stay visible; stop at the target's rim
            const curve = l.reciprocal ? 0.18 : 0;
            const tx = b.x! - (dx / len) * (b.r + 3), ty = b.y! - (dy / len) * (b.r + 3);
            const mx = (a.x! + tx) / 2 - dy * curve, my = (a.y! + ty) / 2 + dx * curve;
            return (
              <path
                key={i}
                d={`M${a.x},${a.y} Q${mx},${my} ${tx},${ty}`}
                fill="none"
                stroke={color}
                strokeWidth={(on ? l.w : Math.max(0.6, l.w * 0.6)) / Math.sqrt(view.k)}
                strokeOpacity={on ? (color === "#3a4f72" ? 0.45 : 0.9) : 0.1}
                markerEnd={on ? `url(#arrow-${color.slice(1)})` : undefined}
                onMouseMove={(e) => setHover({ link: l, ...toLocal(e) })}
                onMouseLeave={() => setHover(null)}
              />
            );
          })}
          {nodes.map((n) => {
            const on = nodeOn(n);
            const isSel = n.id === selected;
            return (
              <g
                key={n.id}
                transform={`translate(${n.x},${n.y})`}
                opacity={on ? 1 : 0.2}
                className="cursor-pointer"
                onMouseDown={(e) => e.stopPropagation()}
                onMouseUp={(e) => {
                  e.stopPropagation();
                  onSelect(isSel ? null : n.id);
                }}
                onMouseMove={(e) => setHover({ node: n, ...toLocal(e) })}
                onMouseLeave={() => setHover(null)}
              >
                <circle r={n.r + 8} fill="transparent" />
                {(n.focus || isSel) && <circle r={n.r + 5} fill="none" stroke={C.s1} strokeWidth={2 / view.k} />}
                <circle r={n.r} fill={n.flagged ? TIER_FILL[n.tier] : "#3b5072"} stroke={C.surface} strokeWidth={2 / view.k} />
                {(n.flagged || n.focus) && view.k >= 0.8 && n.r >= 7 && (
                  <text y={n.r + 12 / view.k} textAnchor="middle" fontSize={10 / view.k} fill={C.ink2} className="pointer-events-none font-mono">
                    {shortAddr(n.id, 5, 3)}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      <div className="absolute right-3 top-3 flex flex-col overflow-hidden rounded-md border border-line bg-panel/90">
        <button aria-label="Zoom in" onClick={() => setView((v) => zoomAt(v, 1.3))} className="p-1.5 text-ink-2 hover:bg-hover hover:text-ink">
          <Plus className="h-4 w-4" />
        </button>
        <button aria-label="Zoom out" onClick={() => setView((v) => zoomAt(v, 1 / 1.3))} className="border-t border-line p-1.5 text-ink-2 hover:bg-hover hover:text-ink">
          <Minus className="h-4 w-4" />
        </button>
        <button aria-label="Reset view" onClick={() => setView({ x: 0, y: 0, k: 1 })} className="border-t border-line p-1.5 text-ink-2 hover:bg-hover hover:text-ink">
          <Maximize2 className="h-4 w-4" />
        </button>
      </div>

      {hover && (
        <div className="pointer-events-none absolute z-10 min-w-[180px] rounded-md border border-line-strong bg-[#0a1426] px-3 py-2 text-xs shadow-xl" style={{ left: Math.min(hover.x + 14, hover.w - 220), top: hover.y + 14 }}>
          {hover.node ? (
            <>
              <div className="mb-1 font-mono text-ink">{shortAddr(hover.node.id, 8, 6)}</div>
              <Row k="Risk" v={`${hover.node.risk_score.toFixed(2)} · ${hover.node.tier}`} />
              <Row k="Sent" v={usd(hover.node.usd_sent, { compact: true })} />
              <Row k="Received" v={usd(hover.node.usd_received, { compact: true })} />
              {hover.node.patterns.length > 0 && <Row k="Patterns" v={hover.node.patterns.map((p) => PATTERN_META[p].label).join(", ")} />}
            </>
          ) : hover.link ? (
            <>
              <div className="mb-1 font-mono text-ink">
                {shortAddr((hover.link.source as SimNode).id, 5, 3)} → {shortAddr((hover.link.target as SimNode).id, 5, 3)}
              </div>
              <Row k="Payments" v={String(hover.link.count)} />
              <Row k="Value" v={usd(hover.link.usd)} />
              {hover.link.kind !== "plain" && <Row k="Pattern" v={hover.link.kind === "cycle" ? "Two-way (cycle)" : hover.link.kind === "peel" ? "Rapid forward" : "Burst fan"} />}
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-4 py-0.5">
      <span className="text-ink-2">{k}</span>
      <span className="tnum text-ink">{v}</span>
    </div>
  );
}

function zoomAt(v: { x: number; y: number; k: number }, f: number) {
  const k = Math.min(6, Math.max(0.4, v.k * f));
  const cx = W / 2, cy = H / 2;
  return { k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k };
}

function layout(data: Network) {
  const maxVol = Math.max(1, ...data.nodes.map((n) => n.usd_sent + n.usd_received));
  const nodes: SimNode[] = data.nodes.map((n) => ({
    ...n,
    r: 4 + 12 * Math.sqrt((n.usd_sent + n.usd_received) / maxVol) + (n.flagged ? 2 : 0),
  }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const maxUsd = Math.max(1, ...data.edges.map((e) => e.usd));
  const links = data.edges
    .filter((e) => byId.has(e.source) && byId.has(e.target))
    .map((e) => {
      const s = byId.get(e.source)!, t = byId.get(e.target)!;
      const fan = s.patterns.includes("fan_out") || t.patterns.includes("fan_in");
      const kind: SimLink["kind"] = e.reciprocal && (s.patterns.includes("cycle") || t.patterns.includes("cycle")) ? "cycle" : e.peel ? "peel" : fan ? "fan" : "plain";
      return { ...e, kind, w: 0.8 + 2.4 * Math.sqrt(e.usd / maxUsd) } as SimLink & { w: number };
    });

  const sim = forceSimulation<SimNode>(nodes)
    .force("link", forceLink<SimNode, SimLink>(links).id((d) => d.id).distance((l) => (l.kind === "plain" ? 90 : 55)).strength(0.15))
    .force("charge", forceManyBody<SimNode>().strength((d) => (d.flagged ? -320 : -90)))
    .force("collide", forceCollide<SimNode>().radius((d) => d.r + 4))
    // a wider-than-tall pull so the layout uses the landscape canvas
    .force("x", forceX(W / 2).strength(0.03))
    .force("y", forceY(H / 2).strength(0.08))
    .stop();
  for (let i = 0; i < 320; i++) sim.tick();

  // fit to the viewBox
  const xs = nodes.map((n) => n.x!), ys = nodes.map((n) => n.y!);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const pad = 40;
  const s = Math.min((W - 2 * pad) / Math.max(1, maxX - minX), (H - 2 * pad) / Math.max(1, maxY - minY), 2.5);
  const ox = (W - (maxX - minX) * s) / 2, oy = (H - (maxY - minY) * s) / 2;
  for (const n of nodes) {
    n.x = ox + (n.x! - minX) * s;
    n.y = oy + (n.y! - minY) * s;
  }
  return { nodes, links: links as (SimLink & { w: number })[] };
}
