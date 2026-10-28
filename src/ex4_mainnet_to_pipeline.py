"""Exercise 4: turn the cached Mainnet ledger range into the pipeline's input format.

Reads data/raw/mainnet/range.json (written by ex3_flow_graph.py) and the cached ledgers, and writes the
same files the synthetic sample uses, into data/raw/mainnet/ so nothing in data/raw/ is overwritten:

    transactions.parquet  tx_hash, ledger_index, timestamp, tx_type, account, destination, amount, currency, fee, destination_tag, result
    transfers.parquet     tx_hash, hop, from_account, to_account, amount, currency, timestamp
    blocks.parquet        ledger_index, close_time, tx_count
    market_rates.csv      date, currency, usd_rate   (XRP priced from the on-ledger XRP/RLUSD order book)
    source.json           where the data came from
    (no labels.csv: Mainnet has no ground truth)

Then run the normal pipeline against it:

    $env:XRPL_DATASET = "mainnet"
    python src/features.py
    python src/detect.py
"""
import argparse
import json
from datetime import datetime, timezone

import pandas as pd

from xrpl_common import MAINNET_RAW, SERVERS, Xrpl, close_time, delivered, parse_amount, pipeline_currency, tx_parts

RANGE_FILE = MAINNET_RAW / "range.json"


def build(ledgers):
    tx_rows, transfer_rows, block_rows = [], [], []
    for led in ledgers:
        ts = close_time(led)
        idx = int(led["ledger_index"])
        block_rows.append({"ledger_index": idx, "close_time": ts, "tx_count": len(led["transactions"])})
        for e in led["transactions"]:
            tx, meta, h = tx_parts(e)
            ttype = tx.get("TransactionType")
            result = meta.get("TransactionResult")
            amount, cur, issuer = (0.0, "XRP", None)
            if ttype == "Payment":
                v, c, i = parse_amount(delivered(e))
                if c:  # failed payments deliver nothing: keep the requested currency, amount 0
                    amount, cur, issuer = v, c, i
                else:
                    _, cur, issuer = parse_amount(tx.get("DeliverMax", tx.get("Amount")))
            currency = pipeline_currency(cur, issuer)
            dest = tx.get("Destination")
            tx_rows.append({
                "tx_hash": h, "ledger_index": idx, "timestamp": ts, "tx_type": ttype,
                "account": tx.get("Account"), "destination": dest,
                "amount": float(amount), "currency": currency,
                "fee": int(tx.get("Fee", 0)), "destination_tag": tx.get("DestinationTag"), "result": result,
            })
            if ttype == "Payment" and result == "tesSUCCESS" and dest and dest != tx.get("Account"):
                transfer_rows.append({"tx_hash": h, "hop": 0, "from_account": tx["Account"], "to_account": dest,
                                      "amount": float(amount), "currency": currency, "timestamp": ts})
    txs = pd.DataFrame(tx_rows)
    txs["destination_tag"] = txs["destination_tag"].astype("Int64")
    return txs, pd.DataFrame(transfer_rows), pd.DataFrame(block_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xrp-usd", type=float, help="override the XRP/USD price instead of reading the order book")
    args = ap.parse_args()
    if not RANGE_FILE.exists():
        raise SystemExit("No ledger range yet. Run  python src/ex3_flow_graph.py  first.")
    r = json.loads(RANGE_FILE.read_text())
    x = Xrpl()

    print(f"Ledger range {r['start']:,} – {r['end']:,}")
    ledgers = [x.ledger(i) for i in range(r["start"], r["end"] + 1)]  # served from cache after ex3
    txs, transfers, blocks = build(ledgers)

    price, price_source = args.xrp_usd, "--xrp-usd argument"
    if price is None:
        price = r.get("xrp_usd") or x.xrp_usd()
        price_source = "XRP/RLUSD order book mid price"
    if price is None:
        raise SystemExit("Could not read an XRP/USD price from the order book; pass --xrp-usd.")
    r["xrp_usd"] = price
    RANGE_FILE.write_text(json.dumps(r, indent=2))  # pin the price to the range so reruns are reproducible

    dates = sorted({t.date().isoformat() for t in txs.timestamp})
    rates = pd.DataFrame([{"date": d, "currency": c, "usd_rate": v} for d in dates for c, v in (("XRP", round(price, 6)), ("USD", 1.0))])

    txs.to_parquet(MAINNET_RAW / "transactions.parquet", index=False)
    transfers.to_parquet(MAINNET_RAW / "transfers.parquet", index=False)
    blocks.to_parquet(MAINNET_RAW / "blocks.parquet", index=False)
    rates.to_csv(MAINNET_RAW / "market_rates.csv", index=False)
    (MAINNET_RAW / "source.json").write_text(json.dumps({
        "network": "XRPL Mainnet", "servers": SERVERS, "ledger_start": r["start"], "ledger_end": r["end"],
        "first_close": txs.timestamp.min().isoformat(), "last_close": txs.timestamp.max().isoformat(),
        "xrp_usd": round(price, 6), "xrp_usd_source": price_source,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2))

    accounts = pd.concat([txs.account, txs.destination.dropna()]).nunique()
    print(f"{len(txs):,} transactions · {len(transfers):,} value transfers · {len(blocks)} ledgers · {accounts:,} accounts")
    print(f"XRP/USD {price:.4f} ({price_source})")
    print(f"Wrote pipeline files to {MAINNET_RAW}")
    print('\nNext:\n  $env:XRPL_DATASET = "mainnet"\n  python src/features.py\n  python src/detect.py')


if __name__ == "__main__":
    main()
