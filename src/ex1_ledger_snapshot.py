"""Exercise 1: snapshot one validated XRPL Mainnet ledger.

Prints the ledger index and close time, current reserves, and counts of transaction types and results.

    python src/ex1_ledger_snapshot.py            # latest validated ledger
    python src/ex1_ledger_snapshot.py 107862344  # a specific ledger
"""
import sys
from collections import Counter

from xrpl_common import Xrpl, close_time, tx_parts


def main():
    x = Xrpl()
    info = x.server_info()
    vl = info["validated_ledger"]
    index = int(sys.argv[1]) if len(sys.argv) > 1 else int(vl["seq"])
    led = x.ledger(index)
    txs = led["transactions"]

    types, results = Counter(), Counter()
    for e in txs:
        tx, meta, _ = tx_parts(e)
        types[tx.get("TransactionType", "?")] += 1
        results[meta.get("TransactionResult", "?")] += 1

    print(f"Ledger {int(led['ledger_index']):,}  closed {close_time(led):%Y-%m-%d %H:%M:%S} UTC  hash {led['ledger_hash'][:16]}…")
    print(f"Server {info.get('build_version', '?')}  latest validated {int(vl['seq']):,}")
    print(f"Reserves: base {vl['reserve_base_xrp']} XRP, owner increment {vl['reserve_inc_xrp']} XRP  (base fee {vl.get('base_fee_xrp')} XRP)")
    print(f"\n{len(txs)} transactions")
    print("\nTransaction types")
    for t, n in types.most_common():
        print(f"  {t:<24}{n:>5}  {n / len(txs):6.1%}")
    print("\nResults")
    for r, n in results.most_common():
        print(f"  {r:<24}{n:>5}  {n / len(txs):6.1%}")


if __name__ == "__main__":
    main()
