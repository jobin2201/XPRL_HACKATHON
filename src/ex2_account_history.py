"""Exercise 2: download one account's transaction history using pagination markers.

Writes data/raw/mainnet/accounts/<ACCOUNT>_history.csv with sender, recipient, time, outcome and delivered amount.

    python src/ex2_account_history.py rACCOUNT...            # up to 5 pages of 200
    python src/ex2_account_history.py rACCOUNT... --pages 20
    python src/ex2_account_history.py                        # picks the busiest payer in the latest ledger
"""
import argparse
from collections import Counter

import pandas as pd
from xrpl.models.requests import AccountTx

from xrpl_common import MAINNET_RAW, Xrpl, close_time, delivered, is_address, parse_amount, tx_parts


def busiest_payer(x: Xrpl) -> str:
    """Most frequent sender of successful payments to *other* accounts (skips self-paying arbitrage bots)."""
    led = x.ledger(x.validated_index())
    c = Counter()
    for e in led["transactions"]:
        tx, meta, _ = tx_parts(e)
        if tx.get("TransactionType") == "Payment" and meta.get("TransactionResult") == "tesSUCCESS" and tx.get("Destination") != tx["Account"]:
            c[tx["Account"]] += 1
    if not c:
        raise SystemExit("No payments in the latest ledger; pass an account address.")
    return c.most_common(1)[0][0]


def fetch_history(x: Xrpl, account: str, pages: int, limit: int = 200) -> list[dict]:
    rows, marker = [], None
    for page in range(1, pages + 1):
        res = x.request(AccountTx(account=account, ledger_index_min=-1, ledger_index_max=-1, limit=limit, marker=marker, forward=False))
        for e in res.get("transactions", []):
            tx, meta, h = tx_parts(e)
            value, cur, issuer = parse_amount(delivered(e)) if tx.get("TransactionType") == "Payment" else (0.0, "", None)
            sender, recipient = tx.get("Account"), tx.get("Destination")
            rows.append({
                "hash": h,
                "ledger_index": e.get("ledger_index") or tx.get("ledger_index"),
                "time": close_time(e).strftime("%Y-%m-%d %H:%M:%S") if e.get("close_time_iso") else None,
                "type": tx.get("TransactionType"),
                "direction": "self" if sender == recipient == account else "out" if sender == account else "in" if recipient == account else "other",
                "sender": sender,
                "recipient": recipient,
                "result": meta.get("TransactionResult"),
                "delivered_value": value,
                "delivered_currency": cur,
                "delivered_issuer": issuer,
                "fee_xrp": int(tx.get("Fee", 0)) / 1e6,
                "destination_tag": tx.get("DestinationTag"),
            })
        marker = res.get("marker")
        print(f"  page {page}: {len(res.get('transactions', []))} transactions{'' if marker else ' (end of history)'}")
        if not marker:
            break
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("account", nargs="?")
    ap.add_argument("--pages", type=int, default=5)
    args = ap.parse_args()

    x = Xrpl()
    account = args.account or busiest_payer(x)
    if not is_address(account):
        raise SystemExit(f"Not a classic XRPL address: {account}")
    print(f"Account {account}")
    df = pd.DataFrame(fetch_history(x, account, args.pages))

    out_dir = MAINNET_RAW / "accounts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{account}_history.csv"
    df.to_csv(out, index=False)

    if df.empty:
        print("No transactions found.")
        return
    pay = df[(df.type == "Payment") & (df.result == "tesSUCCESS")]
    print(f"\n{len(df):,} transactions, {df.time.min()} to {df.time.max()} UTC")
    print(df.type.value_counts().head(8).to_string())
    print("\nResults:", df.result.value_counts().head(5).to_dict())
    print(f"Successful payments: {len(pay)} ({(pay.direction == 'in').sum()} in, {(pay.direction == 'out').sum()} out, {(pay.direction == 'self').sum()} to self)")
    xrp = pay[pay.delivered_currency == "XRP"]
    if len(xrp):
        print(f"XRP received {xrp[xrp.direction == 'in'].delivered_value.sum():,.2f}, sent {xrp[xrp.direction == 'out'].delivered_value.sum():,.2f}")
        print(f"Distinct counterparties: {pd.concat([pay[pay.direction == 'out'].recipient, pay[pay.direction == 'in'].sender]).nunique()}")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
