"""Generate a small SYNTHETIC sample dataset in data/raw for building/testing the pipeline.

This is NOT the competition data. Replace the files in data/raw with the official
organiser files when you get them (and adjust column names in load_data.py if needed).
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

SEED = 42
N_ACCOUNTS = 500
SUSPICIOUS_RATE = 0.08
LABELLED_FRACTION = 0.7  # the rest act as the "test" accounts with hidden labels
START = pd.Timestamp("2026-09-01", tz="UTC")
DAYS = 30
XRPL_ALPHABET = list("rpshnaf39wBUDNEGHJKLM4PQRST7VWXYZ2bcdeCg65jkm8oFqi1tuvAxyz")
CURRENCIES = ["XRP", "USD", "EUR", "BTC"]
CURRENCY_P = [0.75, 0.12, 0.08, 0.05]
BASE_USD = {"XRP": 0.55, "USD": 1.0, "EUR": 1.08, "BTC": 62000.0}
OTHER_TYPES = ["OfferCreate", "TrustSet", "OfferCancel", "AccountSet"]

rng = np.random.default_rng(SEED)


def make_accounts(n):
    return ["r" + "".join(rng.choice(XRPL_ALPHABET, 24)) for _ in range(n)]


def make_market_rates():
    rows = []
    for cur, base in BASE_USD.items():
        price = base
        for d in range(DAYS):
            if cur != "USD":
                price *= float(np.exp(rng.normal(0, 0.02)))
            rows.append({"date": (START + pd.Timedelta(days=d)).date().isoformat(),
                         "currency": cur, "usd_rate": round(price, 6)})
    return pd.DataFrame(rows)


def rate_lookup(rates):
    return {(r.date, r.currency): r.usd_rate for r in rates.itertuples()}


def rand_time(night=False):
    day = int(rng.integers(0, DAYS))
    hour = int(rng.integers(0, 5)) if night else int(np.clip(rng.normal(14, 4), 0, 23))
    return START + pd.Timedelta(days=day, hours=hour,
                                minutes=int(rng.integers(0, 60)), seconds=int(rng.integers(0, 60)))


def tx(account, dest, ts, amount, currency, tx_type="Payment", fee=None, result="tesSUCCESS", dest_tag=None):
    return {"account": account, "destination": dest, "timestamp": ts, "tx_type": tx_type,
            "amount": float(amount), "currency": currency,
            "fee": int(fee if fee is not None else rng.integers(10, 13)),
            "destination_tag": dest_tag, "result": result}


def pick_other(accounts, acc):
    dest = rng.choice(accounts)
    while dest == acc:
        dest = rng.choice(accounts)
    return dest


def usd_to(rates, ts, cur, usd):
    # stay inside the rate table if a burst spills past the last day
    day = min(ts, START + pd.Timedelta(days=DAYS - 1)).date().isoformat()
    return usd / rates[(day, cur)]


def normal_activity(acc, accounts, rates):
    rows = []
    for _ in range(int(rng.poisson(rng.lognormal(3.0, 0.6)))):
        ts = rand_time(night=rng.random() < 0.08)
        if rng.random() < 0.8:
            cur = str(rng.choice(CURRENCIES, p=CURRENCY_P))
            amt = usd_to(rates, ts, cur, rng.lognormal(4.5, 1.3))
            tag = int(rng.integers(1, 10**6)) if rng.random() < 0.3 else None
            res = "tesSUCCESS" if rng.random() > 0.02 else str(rng.choice(["tecPATH_DRY", "tecUNFUNDED_PAYMENT"]))
            rows.append(tx(acc, pick_other(accounts, acc), ts, amt, cur, dest_tag=tag, result=res))
        else:
            rows.append(tx(acc, None, ts, 0.0, "XRP", tx_type=str(rng.choice(OTHER_TYPES))))
    return rows


def suspicious_activity(acc, accounts, ring, rates):
    """One of several typologies: structuring, fan-out, night bursts with failures, round-tripping."""
    pattern = str(rng.choice(["structuring", "fan_out", "night_burst", "round_trip", "fan_in", "peel_chain"]))
    rows = []
    if pattern == "fan_in":  # collector: many distinct senders pay it within one hour
        t0 = rand_time()
        for src in rng.choice([a for a in accounts if a != acc], int(rng.integers(12, 30)), replace=False):
            ts = t0 + pd.Timedelta(seconds=int(rng.integers(0, 3500)))
            rows.append(tx(str(src), acc, ts, usd_to(rates, ts, "XRP", rng.lognormal(5.0, 0.4)), "XRP"))
    elif pattern == "peel_chain":  # pass-through mule: receive, peel off a slice, forward the rest fast
        for _ in range(int(rng.integers(4, 9))):
            ts = rand_time()
            usd = rng.lognormal(7.5, 0.5)
            rows.append(tx(pick_other(accounts, acc), acc, ts, usd_to(rates, ts, "XRP", usd), "XRP"))
            hop, cur_ts = acc, ts
            for _ in range(int(rng.integers(2, 4))):  # the chain continues through further accounts
                nxt = pick_other(accounts, hop)
                cur_ts = cur_ts + pd.Timedelta(minutes=int(rng.integers(2, 20)))
                usd *= rng.uniform(0.85, 0.97)
                rows.append(tx(hop, nxt, cur_ts, usd_to(rates, cur_ts, "XRP", usd), "XRP"))
                hop = nxt
    elif pattern == "structuring":  # many payments just under a 10k USD threshold
        for _ in range(int(rng.integers(15, 40))):
            ts = rand_time()
            rows.append(tx(acc, pick_other(accounts, acc), ts, usd_to(rates, ts, "XRP", rng.uniform(9000, 9990)), "XRP"))
    elif pattern == "fan_out":  # quickly sprays funds to many destinations
        t0 = rand_time()
        for i in range(int(rng.integers(30, 80))):
            ts = t0 + pd.Timedelta(seconds=int(i * rng.integers(5, 60)))
            rows.append(tx(acc, pick_other(accounts, acc), ts, usd_to(rates, ts, "XRP", rng.lognormal(5.5, 0.5)), "XRP",
                           dest_tag=int(rng.integers(1, 10**6))))
    elif pattern == "night_burst":  # nocturnal activity, high fees, many failed payments
        for _ in range(int(rng.integers(20, 50))):
            ts = rand_time(night=True)
            res = "tesSUCCESS" if rng.random() > 0.35 else str(rng.choice(["tecPATH_DRY", "tecUNFUNDED_PAYMENT", "tecNO_DST"]))
            rows.append(tx(acc, pick_other(accounts, acc), ts, usd_to(rates, ts, "XRP", rng.lognormal(6, 1)), "XRP",
                           fee=int(rng.integers(50, 5000)), result=res))
    else:  # round_trip: value cycles around a ring of colluding accounts
        partners = [r for r in ring if r != acc] or [pick_other(accounts, acc)]
        for _ in range(int(rng.integers(15, 35))):
            ts = rand_time()
            partner = str(rng.choice(partners))
            amt = usd_to(rates, ts, "USD", rng.lognormal(7, 0.4))
            rows.append(tx(acc, partner, ts, amt, "USD"))
            rows.append(tx(partner, acc, ts + pd.Timedelta(minutes=int(rng.integers(1, 30))), amt * 0.995, "USD"))
    return rows, pattern


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)

    accounts = make_accounts(N_ACCOUNTS)
    is_sus = rng.random(N_ACCOUNTS) < SUSPICIOUS_RATE
    sus_accounts = [a for a, s in zip(accounts, is_sus) if s]
    ring = sus_accounts[: max(3, len(sus_accounts) // 3)]

    market_rates = make_market_rates()
    rates = rate_lookup(market_rates)

    rows, patterns = [], {}
    for acc, sus in zip(accounts, is_sus):
        rows += normal_activity(acc, accounts, rates)
        if sus:
            extra, patterns[acc] = suspicious_activity(acc, accounts, ring, rates)
            rows += extra

    txs = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    txs["tx_hash"] = [f"{h:064X}" for h in rng.integers(0, 2**63 - 1, len(txs), dtype=np.int64)]
    txs["ledger_index"] = 98_000_000 + ((txs["timestamp"] - START).dt.total_seconds() // 4).astype("int64")
    txs["destination_tag"] = txs["destination_tag"].astype("Int64")
    txs = txs[["tx_hash", "ledger_index", "timestamp", "tx_type", "account", "destination",
               "amount", "currency", "fee", "destination_tag", "result"]]

    blocks = (txs.groupby("ledger_index")
                 .agg(close_time=("timestamp", "max"), tx_count=("tx_hash", "size"))
                 .reset_index())

    # transfers: one hop per successful payment, plus an intermediary hop for ~10% (path payments)
    pay = txs[(txs.tx_type == "Payment") & (txs.result == "tesSUCCESS")]
    t_rows = []
    for r in pay.itertuples():
        if rng.random() < 0.1:
            mid = pick_other(accounts, r.account)
            t_rows += [(r.tx_hash, 0, r.account, mid, r.amount, r.currency, r.timestamp),
                       (r.tx_hash, 1, mid, r.destination, r.amount * 0.999, r.currency, r.timestamp)]
        else:
            t_rows.append((r.tx_hash, 0, r.account, r.destination, r.amount, r.currency, r.timestamp))
    transfers = pd.DataFrame(t_rows, columns=["tx_hash", "hop", "from_account", "to_account",
                                              "amount", "currency", "timestamp"])

    all_labels = pd.DataFrame({"account": accounts, "is_suspicious": is_sus.astype(int)})
    labelled = rng.random(N_ACCOUNTS) < LABELLED_FRACTION
    labels = all_labels[labelled]
    hidden = all_labels[~labelled].copy()
    hidden["pattern"] = hidden["account"].map(patterns).fillna("normal")

    txs.to_parquet(RAW / "transactions.parquet", index=False)
    transfers.to_parquet(RAW / "transfers.parquet", index=False)
    blocks.to_parquet(RAW / "blocks.parquet", index=False)
    market_rates.to_csv(RAW / "market_rates.csv", index=False)
    labels.to_csv(RAW / "labels.csv", index=False)
    # Hidden answers for the "test" accounts. Only exists for the synthetic sample; predict.py uses it as a sanity check.
    hidden.to_csv(PROCESSED / "sample_hidden_test_labels.csv", index=False)

    print(f"transactions: {len(txs):,}  transfers: {len(transfers):,}  blocks: {len(blocks):,}")
    print(f"accounts: {N_ACCOUNTS}  suspicious: {int(is_sus.sum())}  labelled: {len(labels)}  test: {len(hidden)}")
    print(f"written to {RAW}")


if __name__ == "__main__":
    main()
