"""Exercise 3: build a value-flow graph from a small, fixed range of Mainnet ledgers.

Downloads (and caches) the ledgers, connects payment senders to recipients, and computes per-account
incoming value, outgoing value, fan-in, fan-out and pass-through ratio.

    python src/ex3_flow_graph.py                 # first run: the 100 ledgers ending at the latest validated one
    python src/ex3_flow_graph.py                 # later runs: the SAME saved range (cached, no re-download)
    python src/ex3_flow_graph.py --count 300 --refresh

Outputs:
    data/raw/mainnet/range.json               the fixed ledger range
    data/raw/mainnet/xrp_payments.csv         one row per successful payment
    data/processed/mainnet/graph_features.csv one row per account
"""
import argparse
import json

import networkx as nx
import pandas as pd

from xrpl_common import MAINNET_PROCESSED, MAINNET_RAW, Xrpl, close_time, delivered, parse_amount, pipeline_currency, tx_parts

RANGE_FILE = MAINNET_RAW / "range.json"


def resolve_range(x: Xrpl, count: int, refresh: bool, end: int | None) -> tuple[int, int]:
    if RANGE_FILE.exists() and not refresh and end is None:
        r = json.loads(RANGE_FILE.read_text())
        return r["start"], r["end"]
    end = end or x.validated_index()
    start = end - count + 1
    MAINNET_RAW.mkdir(parents=True, exist_ok=True)
    RANGE_FILE.write_text(json.dumps({"start": start, "end": end}, indent=2))
    return start, end


def download(x: Xrpl, start: int, end: int) -> list[dict]:
    ledgers = []
    total = end - start + 1
    for i, idx in enumerate(range(start, end + 1), 1):
        ledgers.append(x.ledger(idx))
        if i % 25 == 0 or i == total:
            print(f"  ledgers {i}/{total}")
    return ledgers


def payments_frame(ledgers: list[dict]) -> pd.DataFrame:
    rows = []
    for led in ledgers:
        ts = close_time(led)
        for e in led["transactions"]:
            tx, meta, h = tx_parts(e)
            if tx.get("TransactionType") != "Payment" or meta.get("TransactionResult") != "tesSUCCESS":
                continue
            value, cur, issuer = parse_amount(delivered(e))
            rows.append({
                "tx_hash": h, "ledger_index": int(led["ledger_index"]), "timestamp": ts,
                "sender": tx["Account"], "recipient": tx.get("Destination"),
                "value": value, "currency": pipeline_currency(cur, issuer),
                "value_xrp": value if cur == "XRP" else 0.0,
                "fee_drops": int(tx.get("Fee", 0)), "destination_tag": tx.get("DestinationTag"),
            })
    return pd.DataFrame(rows)


def graph_features(pay: pd.DataFrame) -> tuple[nx.MultiDiGraph, pd.DataFrame]:
    flows = pay[pay.sender != pay.recipient]  # self-payments (arbitrage / path tricks) carry no value between accounts
    G = nx.MultiDiGraph()
    for r in flows.itertuples():
        G.add_edge(r.sender, r.recipient, value_xrp=r.value_xrp, tx_hash=r.tx_hash)

    out_v = flows.groupby("sender").value_xrp.sum()
    in_v = flows.groupby("recipient").value_xrp.sum()
    nodes = list(G.nodes)
    f = pd.DataFrame(index=pd.Index(nodes, name="account"))
    f["in_value_xrp"] = in_v.reindex(nodes).fillna(0.0)
    f["out_value_xrp"] = out_v.reindex(nodes).fillna(0.0)
    f["n_in"] = pd.Series({n: G.in_degree(n) for n in nodes})
    f["n_out"] = pd.Series({n: G.out_degree(n) for n in nodes})
    f["fan_in"] = pd.Series({n: len(set(G.predecessors(n))) for n in nodes})
    f["fan_out"] = pd.Series({n: len(set(G.successors(n))) for n in nodes})
    # pass-through: how much of what came in also went out (1 = everything forwarded). Only defined with both sides.
    both = (f.in_value_xrp > 0) & (f.out_value_xrp > 0)
    f["pass_through_ratio"] = (f[["in_value_xrp", "out_value_xrp"]].min(axis=1) / f[["in_value_xrp", "out_value_xrp"]].max(axis=1)).where(both)
    f["self_payments"] = pay[pay.sender == pay.recipient].groupby("sender").size().reindex(nodes).fillna(0).astype(int)
    return G, f.reset_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100, help="number of ledgers (only when choosing a new range)")
    ap.add_argument("--end", type=int, help="last ledger of a new range")
    ap.add_argument("--refresh", action="store_true", help="pick a new range ending at the latest validated ledger")
    args = ap.parse_args()

    x = Xrpl()
    start, end = resolve_range(x, args.count, args.refresh, args.end)
    print(f"Ledger range {start:,} – {end:,} ({end - start + 1} ledgers, cached in {MAINNET_RAW / 'cache'})")
    ledgers = download(x, start, end)
    pay = payments_frame(ledgers)
    if pay.empty:
        raise SystemExit("No successful payments in this range.")

    MAINNET_RAW.mkdir(parents=True, exist_ok=True)
    MAINNET_PROCESSED.mkdir(parents=True, exist_ok=True)
    pay.to_csv(MAINNET_RAW / "xrp_payments.csv", index=False)

    G, f = graph_features(pay)
    f.to_csv(MAINNET_PROCESSED / "graph_features.csv", index=False)

    n_tx = sum(len(l["transactions"]) for l in ledgers)
    simple = nx.DiGraph(G)
    span = (close_time(ledgers[-1]) - close_time(ledgers[0])).total_seconds() / 60
    print(f"\n{n_tx:,} transactions over {span:.1f} minutes; {len(pay):,} successful payments "
          f"({(pay.sender == pay.recipient).sum():,} self-payments excluded from the graph)")
    print(f"Graph: {G.number_of_nodes():,} accounts, {G.number_of_edges():,} payments, {simple.number_of_edges():,} distinct sender→recipient pairs")
    print(f"Weakly connected components: {nx.number_weakly_connected_components(G):,}; largest has "
          f"{max((len(c) for c in nx.weakly_connected_components(G)), default=0):,} accounts")
    print(f"XRP moved between accounts: {pay[pay.sender != pay.recipient].value_xrp.sum():,.0f} XRP")
    print(f"Payments by currency: {pay.currency.value_counts().head(5).to_dict()}")

    show = ["account", "fan_in", "fan_out", "in_value_xrp", "out_value_xrp", "pass_through_ratio"]
    fmt = {"in_value_xrp": "{:,.1f}".format, "out_value_xrp": "{:,.1f}".format, "pass_through_ratio": "{:.2f}".format}
    print("\nTop fan-out (distinct recipients)")
    print(f.sort_values("fan_out", ascending=False).head(5)[show].to_string(index=False, formatters=fmt))
    print("\nTop fan-in (distinct senders)")
    print(f.sort_values("fan_in", ascending=False).head(5)[show].to_string(index=False, formatters=fmt))
    pt = f[(f.pass_through_ratio >= 0.9) & (f.in_value_xrp >= 100)]
    print(f"\nPass-through ≥ 0.90 with ≥ 100 XRP in: {len(pt)} accounts")
    if len(pt):
        print(pt.sort_values("in_value_xrp", ascending=False).head(5)[show].to_string(index=False, formatters=fmt))
    print(f"\nSaved {MAINNET_RAW / 'xrp_payments.csv'}\n      {MAINNET_PROCESSED / 'graph_features.csv'}")


if __name__ == "__main__":
    main()
