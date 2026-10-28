"use client";

// Wallet-to-wallet payment graph: arrows are payments (grouped per sender->receiver), coloured by the
// highest v2 score on that link; node size = number of payments. Click a wallet to re-centre, a link to inspect it.
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";
import { useMemo, useState } from "react";
import { shortAddr, usd } from "@/lib/format";
import { type V2Graph, type V2GraphEdge, scoreColor } from "@/lib/v2";

type Node = V2Graph["nodes"][number] & SimulationNodeDatum & { r: number };
type Link = SimulationLinkDatum<Node> & V2GraphEdge;
const W = 1000;
const H = 620;

function layout(g: V2Graph) {
  const nodes: Node[] = g.nodes.map((n) => ({ ...n, r: 7 + Math.min(18, Math.sqrt(n.payments) * 3) }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const links: Link[] = g.edges.map((e) => ({ ...e, source: byId.get(e.from)!, target: byId.get(e.to)! }));
  const sim = forceSimulation(nodes)
    .force("link", forceLink<Node, Link>(links).distance(110).strength(0.5))
    .force("charge", forceManyBody().strength(-420))
    .force("collide", forceCollide<Node>().radius((d) => d.r + 10))
    .force("x", forceX(W / 2).strength(0.05))
    .force("y", forceY(H / 2).strength(0.07))
    .stop();
  for (let i = 0; i < 320; i++) sim.tick();
  for (const n of nodes) {
    n.x = Math.max(30, Math.min(W - 30, n.x ?? W / 2));
    n.y = Math.max(30, Math.min(H - 30, n.y ?? H / 2));
  }
  return { nodes, links };
}

export default function FlowGraph({ data, onWallet, onEdge }: { data: V2Graph; onWallet: (id: string) => void; onEdge: (e: V2GraphEdge) => void }) {
  const { nodes, links } = useMemo(() => layout(data), [data]);
  const [hover, setHover] = useState<string | null>(null);

  if (!nodes.length) return <p className="p-6 text-sm text-muted">No payments in this window.</p>;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Payment graph between wallets">
      <defs>
        {["#3b5072", "#fab219", "#ec835a", "#d03b3b"].map((c) => (
          <marker key={c} id={`arrow-${c.slice(1)}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill={c} />
          </marker>
        ))}
      </defs>
      {links.map((l) => {
        const s = l.source as Node;
        const t = l.target as Node;
        const dx = t.x! - s.x!;
        const dy = t.y! - s.y!;
        const len = Math.hypot(dx, dy) || 1;
        // stop the arrow at the target circle; bend slightly so A->B and B->A do not overlap
        const ex = t.x! - (dx / len) * (t.r + 4);
        const ey = t.y! - (dy / len) * (t.r + 4);
        const mx = (s.x! + ex) / 2 - (dy / len) * 18;
        const my = (s.y! + ey) / 2 + (dx / len) * 18;
        const c = scoreColor(l.max_score);
        const dim = hover && hover !== s.id && hover !== t.id;
        return (
          <path
            key={`${l.from}-${l.to}`}
            d={`M${s.x},${s.y} Q${mx},${my} ${ex},${ey}`}
            fill="none"
            stroke={c}
            strokeWidth={1.2 + Math.min(5, l.count)}
            strokeOpacity={dim ? 0.12 : 0.85}
            markerEnd={`url(#arrow-${c.slice(1)})`}
            className="cursor-pointer"
            onClick={() => onEdge(l)}
          >
            <title>{`${shortAddr(l.from)} → ${shortAddr(l.to)}\n${l.count} payment(s), ${usd(l.usd)}\nhighest score ${l.max_score.toFixed(3)}`}</title>
          </path>
        );
      })}
      {nodes.map((n) => (
        <g
          key={n.id}
          transform={`translate(${n.x},${n.y})`}
          className="cursor-pointer"
          onMouseEnter={() => setHover(n.id)}
          onMouseLeave={() => setHover(null)}
          onClick={() => onWallet(n.id)}
        >
          <circle r={n.r} fill={n.centre ? "#1ea3bc" : "var(--surface)"} stroke={scoreColor(n.max_score)} strokeWidth={n.flagged ? 3 : 1.5} />
          <text y={n.r + 14} textAnchor="middle" fontSize="11" fill={n.centre ? "var(--ink)" : "var(--ink-2)"} fontFamily="monospace">
            {shortAddr(n.id, 5, 3)}
          </text>
          <title>{`${n.id}\n${n.payments} payment(s) in view\nhighest score ${n.max_score.toFixed(3)}${n.flagged ? " · flagged" : ""}`}</title>
        </g>
      ))}
    </svg>
  );
}
