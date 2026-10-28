"""Turn the official Decode & Detect training split into the pipeline's input format.

Reads   decode-and-detect-training-data/train/   (the real dataset; never modified)
Writes  data/raw/official/                       (same layout as every other dataset)

    transactions.parquet  tx_hash, ledger_index, timestamp, tx_type, account, destination, amount, currency,
                          amount_usd, fee, destination_tag, result
    transfers.parquet     tx_hash, hop, from_account, to_account, amount, currency, timestamp
    blocks.parquet        ledger_index, close_time, tx_count
    market_rates.csv      date, currency, usd_rate   (daily mean of the hourly official rates, for reference)
    labels.csv            account, is_suspicious     (75% of sending accounts, used for training)
    tx_labels.csv         tx_hash, is_suspicious     (the official per-transaction labels, untouched)
    source.json           where the data came from
and data/processed/official/hidden_test_labels.csv (the other 25% of accounts, for an honest test score).

Value semantics follow the official README / payments.py:
  * DELIVERED_AMOUNT is JSON: XRP = string of drops (/1,000,000), token = {"currency","issuer","value"}.
  * Assets are grouped by issuer AND currency (USD from two issuers are different assets).
  * USD value = units x hourly PRICE_MICRO_USD / 1,000,000 for the hour containing the ledger timestamp.

Account labels: the official labels are per transaction. An account is labelled suspicious if it SENT at
least one suspicious transaction. Accounts that only ever receive are left unlabelled and get scored.

Run:
    python src/import_official.py
    python src/features.py ; python src/train.py ; python src/predict.py ; python src/detect.py
"""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from load_data import dataset_dirs, ROOT

SOURCE = ROOT / "decode-and-detect-training-data" / "train"
_, RAW, PROCESSED = dataset_dirs("official")

DROPS = 1_000_000
XRP_TOKEN_ADDRESS = "0x1111222211112222111122221111222211112222"
HOLDOUT, SEED = 0.25, 42


def label(cur: str, issuer: str | None) -> str:
    """Short currency label for the UI that still separates issuers: 'XRP', 'USD:rLeMq5iF'."""
    return "XRP" if cur == "XRP" or not issuer else f"{cur}:{issuer[:8]}"


def parse_delivered(raw: str):
    """-> (units, currency label, rate key) for one DELIVERED_AMOUNT JSON value."""
    v = json.loads(raw)
    if isinstance(v, str):
        return int(v) / DROPS, "XRP", "XRP"
    return float(v["value"]), label(v["currency"], v["issuer"]), f"{v['issuer']}:{v['currency']}"


def hourly_usd(rates: pd.DataFrame, timestamps, keys) -> np.ndarray:
    lookup = dict(zip(zip(rates.TIMESTAMP.astype(np.int64), rates.ASSET), rates.PRICE_MICRO_USD / DROPS))
    hours = (np.asarray(timestamps, dtype=np.int64) // 3600) * 3600
    return np.array([lookup.get((h, k), np.nan) for h, k in zip(hours, keys)])


def main():
    tx = pd.read_parquet(SOURCE / "transactions.parquet")
    tr = pd.read_parquet(SOURCE / "transfers.parquet")
    rates = pd.read_csv(SOURCE / "market_rates.csv")
    tx_labels = pd.read_csv(SOURCE / "labels.csv", usecols=["TRANSACTION_HASH", "is_suspicious"])

    # ---- transactions ----
    extra = tx.EXTRA_TRANSACTION_FIELDS.map(json.loads)
    units, cur, key = zip(*tx.DELIVERED_AMOUNT.map(parse_delivered))
    price = hourly_usd(rates, tx.TIMESTAMP, key)
    txs = pd.DataFrame({
        "tx_hash": tx.TRANSACTION_HASH,
        "ledger_index": tx.LEDGER_INDEX.astype(np.int64),
        "timestamp": pd.to_datetime(tx.TIMESTAMP.astype(np.int64), unit="s", utc=True),
        "tx_type": tx.TRANSACTION_TYPE,
        "account": tx.ACCOUNT,
        "destination": extra.map(lambda e: e.get("Destination")),
        "amount": np.array(units, dtype=float),
        "currency": cur,
        "amount_usd": np.array(units, dtype=float) * price,
        "fee": tx.SOURCE_FEE.astype(np.int64),  # drops (FEE is the same value in XRP)
        "destination_tag": extra.map(lambda e: e.get("DestinationTag")).astype("Int64"),
        "result": tx.TRANSACTION_RESULT,
    }).sort_values("timestamp").reset_index(drop=True)

    # ---- transfers (every executed leg) ----
    is_xrp = (tr.SYMBOL == "XRP") | (tr.TOKEN_ADDRESS == XRP_TOKEN_ADDRESS)
    transfers = pd.DataFrame({
        "tx_hash": tr.TRANSACTION_HASH,
        "hop": tr.TRANSFER_INDEX.astype(int),
        "from_account": tr.FROM_ADDRESS,
        "to_account": tr.TO_ADDRESS,
        "amount": tr.VALUE.astype(float),  # already asset units (XRP, or token units)
        "currency": [("XRP" if x else label(s, a)) for x, s, a in zip(is_xrp, tr.SYMBOL, tr.TOKEN_ADDRESS)],
        "timestamp": pd.to_datetime(tr.TIMESTAMP.astype(np.int64), unit="s", utc=True),
    }).sort_values(["timestamp", "tx_hash", "hop"]).reset_index(drop=True)

    # ---- blocks ----
    blocks_src = pd.read_parquet(SOURCE / "blocks.parquet", columns=["LEDGER_INDEX", "TIMESTAMP"])
    counts = txs.groupby("ledger_index").size()
    blocks = pd.DataFrame({
        "ledger_index": blocks_src.LEDGER_INDEX.astype(np.int64),
        "close_time": pd.to_datetime(blocks_src.TIMESTAMP.astype(np.int64), unit="s", utc=True),
    })
    blocks["tx_count"] = blocks.ledger_index.map(counts).fillna(0).astype(int)
    blocks = blocks.sort_values("ledger_index").reset_index(drop=True)

    # ---- daily reference rates (pricing itself uses the hourly amount_usd above) ----
    r = rates.copy()
    r["date"] = pd.to_datetime(r.TIMESTAMP, unit="s", utc=True).dt.date.astype(str)
    r["currency"] = r.ASSET.map(lambda a: "XRP" if a == "XRP" else label(a.split(":")[1], a.split(":")[0]))
    daily = (r.groupby(["date", "currency"]).PRICE_MICRO_USD.mean() / DROPS).round(6).rename("usd_rate").reset_index()

    # ---- labels: per transaction -> per sending account, then a 75/25 account split ----
    lab = txs[["tx_hash", "account"]].merge(tx_labels.rename(columns={"TRANSACTION_HASH": "tx_hash"}), on="tx_hash")
    acct = lab.groupby("account").is_suspicious.max().astype(int).reset_index()
    train_acc, hidden_acc = train_test_split(acct, test_size=HOLDOUT, stratify=acct.is_suspicious, random_state=SEED)

    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    txs.to_parquet(RAW / "transactions.parquet", index=False)
    transfers.to_parquet(RAW / "transfers.parquet", index=False)
    blocks.to_parquet(RAW / "blocks.parquet", index=False)
    daily.to_csv(RAW / "market_rates.csv", index=False)
    train_acc.to_csv(RAW / "labels.csv", index=False)
    lab[["tx_hash", "is_suspicious"]].to_csv(RAW / "tx_labels.csv", index=False)
    hidden_acc.to_csv(PROCESSED / "hidden_test_labels.csv", index=False)
    xrp_mean = float(rates.loc[rates.ASSET == "XRP", "PRICE_MICRO_USD"].mean() / DROPS)
    (RAW / "source.json").write_text(json.dumps({
        "network": "Decode & Detect official training split (synthetic ledger)",
        "ledger_start": int(txs.ledger_index.min()), "ledger_end": int(txs.ledger_index.max()),
        "first_close": txs.timestamp.min().isoformat(), "last_close": txs.timestamp.max().isoformat(),
        "xrp_usd": round(xrp_mean, 6), "xrp_usd_source": "mean of the hourly official market_rates.csv; each payment uses its own hour",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2))

    print(f"{len(txs):,} transactions · {len(transfers):,} transfer legs · {len(blocks):,} ledgers")
    print(f"payments without a USD rate: {int(np.isnan(price).sum())}")
    print(f"transaction labels: {int(tx_labels.is_suspicious.sum()):,} suspicious of {len(tx_labels):,}")
    print(f"sending accounts: {len(acct):,} ({int(acct.is_suspicious.sum())} suspicious) -> "
          f"train {len(train_acc):,} / hidden test {len(hidden_acc):,}")
    print(f"receive-only accounts (unlabelled, will be scored): "
          f"{len(set(txs.destination) - set(txs.account)):,}")
    print(f"wrote {RAW}")


if __name__ == "__main__":
    main()
