"""Load one split (train, validation or test) and join its files into one row per transaction.

Every join is checked: no transaction may be duplicated, dropped or mismatched.

Joins (keys from the official README):
  transactions  1 row per TRANSACTION_HASH                         (base table)
  transfers     1..3 legs per TRANSACTION_HASH, ordered by TRANSFER_INDEX -> aggregated to 1 row, then joined
  blocks        1 row per (LEDGER_INDEX, LEDGER_HASH)               -> joined one-to-one for the ledger close time
                (the block TRANSACTION_HASH column is NOT a key; it is never used)
  market_rates  hourly USD price per ASSET ('XRP' or 'issuer:currency') -> looked up by (hour, asset)
  labels        1 row per TRANSACTION_HASH (train only)              -> only is_suspicious is used as the target

Value semantics (README "Assets and values"):
  DELIVERED_AMOUNT  XRP: string of integer drops (/1,000,000) | IOU: {"currency","issuer","value"} in token units
  transfers VALUE   asset units (XRP for XRP legs, token units for IOUs)
  Assets are identified by issuer AND currency. The first executed leg is the real source cost;
  the last leg is what the destination receives (it must equal DELIVERED_AMOUNT).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

DROPS_PER_XRP = 1_000_000
MICRO_USD = 1_000_000                 # PRICE_MICRO_USD / 1e6 = USD per unit
XRP_ASSET = "XRP"                     # how XRP is written in market_rates.csv
XRP_TOKEN_ADDRESS = "0x1111222211112222111122221111222211112222"  # XRP placeholder TOKEN_ADDRESS in transfers
LABEL_META = ["family", "difficulty", "scenario_id", "cohort_id"]  # never model inputs


def _read_rates(directory: Path) -> pd.DataFrame:
    for name in ("market_rates.csv", "market_rates.parquet"):
        path = directory / name
        if path.exists():
            return pd.read_csv(path) if path.suffix == ".csv" else pd.read_parquet(path)
    raise FileNotFoundError(f"market_rates.csv/.parquet not found in {directory}")


def load_raw(directory: Path) -> dict:
    directory = Path(directory)
    raw = {
        "transactions": pd.read_parquet(directory / "transactions.parquet"),
        "transfers": pd.read_parquet(directory / "transfers.parquet"),
        "blocks": pd.read_parquet(directory / "blocks.parquet",
                                  columns=["LEDGER_INDEX", "LEDGER_HASH", "TIMESTAMP", "PARENT_CLOSE_TIME", "CLOSE_TIME"]),
        "rates": _read_rates(directory),
    }
    labels = directory / "labels.csv"
    raw["labels"] = pd.read_csv(labels) if labels.exists() else None
    return raw


def _parse_amount(value) -> tuple[str, float]:
    """XRPL amount JSON -> (asset id, units). Never mixes drops with token units."""
    if isinstance(value, str):
        return XRP_ASSET, int(value) / DROPS_PER_XRP
    return f"{value['issuer']}:{value['currency']}", float(value["value"])


def _currency(asset: str) -> str:
    return XRP_ASSET if asset == XRP_ASSET else asset.split(":")[1]


class RateBook:
    """Hourly reference prices. Use the hour containing the ledger timestamp (README)."""

    def __init__(self, rates: pd.DataFrame):
        self.lookup = dict(zip(zip(rates.TIMESTAMP.astype(np.int64), rates.ASSET), rates.PRICE_MICRO_USD / MICRO_USD))

    def usd(self, timestamps, assets, units) -> np.ndarray:
        hours = (np.asarray(timestamps, dtype=np.int64) // 3600) * 3600
        price = np.array([self.lookup.get((h, a), np.nan) for h, a in zip(hours, assets)])
        if np.isnan(price).any():
            raise ValueError(f"{int(np.isnan(price).sum())} amounts have no hourly market rate")
        return np.asarray(units, dtype=float) * price


def _legs(transfers: pd.DataFrame, rates: RateBook) -> tuple[pd.DataFrame, pd.DataFrame]:
    t = transfers.copy()
    t["TS"] = t.TIMESTAMP.astype(np.int64)
    t["TRANSFER_INDEX"] = t.TRANSFER_INDEX.astype(int)
    is_xrp = (t.SYMBOL == "XRP") | (t.TOKEN_ADDRESS == XRP_TOKEN_ADDRESS)
    t["ASSET"] = np.where(is_xrp, XRP_ASSET, t.TOKEN_ADDRESS + ":" + t.SYMBOL)
    t["UNITS"] = t.VALUE.astype(float)
    t["USD"] = rates.usd(t.TS, t.ASSET, t.UNITS)
    t = t.sort_values(["TRANSACTION_HASH", "TRANSFER_INDEX"])

    if t.duplicated(["TRANSACTION_HASH", "TRANSFER_INDEX"]).any():
        raise ValueError("duplicate (TRANSACTION_HASH, TRANSFER_INDEX) in transfers")
    expected = t.groupby("TRANSACTION_HASH").cumcount()
    if (expected.to_numpy() != t.TRANSFER_INDEX.to_numpy()).any():
        raise ValueError("transfer indices are not 0..n-1 within a transaction")

    g = t.groupby("TRANSACTION_HASH", sort=False)
    first, last = g.first(), g.last()
    agg = pd.DataFrame({
        "n_legs": g.size(),
        "n_leg_assets": g.ASSET.nunique(),
        "is_conversion": g.TRANSFER_TYPE.agg(lambda s: bool((s == "path_payment").any())),
        "source_asset": first.ASSET,
        "source_usd": first.USD,          # actual cost to the sender (first executed leg)
        "last_leg_asset": last.ASSET,
        "last_leg_units": last.UNITS,
        "last_leg_to": last.TO_ADDRESS,
        "first_leg_from": first.FROM_ADDRESS,
    })
    return agg, t


def build_payments(raw: dict) -> pd.DataFrame:
    """One row per transaction with everything the features need. Raises on any join problem."""
    tx = raw["transactions"]
    if tx.TRANSACTION_HASH.duplicated().any():
        raise ValueError("duplicate TRANSACTION_HASH in transactions")
    rates = RateBook(raw["rates"])

    extra = tx.EXTRA_TRANSACTION_FIELDS.map(json.loads)
    asset, units = zip(*tx.DELIVERED_AMOUNT.map(lambda s: _parse_amount(json.loads(s))))
    p = pd.DataFrame({
        "TRANSACTION_HASH": tx.TRANSACTION_HASH.to_numpy(),
        "ts": tx.TIMESTAMP.astype(np.int64).to_numpy(),
        "ledger_index": tx.LEDGER_INDEX.astype(np.int64).to_numpy(),
        "ledger_hash": tx.LEDGER_HASH.to_numpy(),
        "tx_index": tx.TRANSACTION_INDEX.astype(int).to_numpy(),
        "sender": tx.ACCOUNT.to_numpy(),
        "receiver": extra.map(lambda e: e["Destination"]).to_numpy(),
        "fee_drops": tx.SOURCE_FEE.astype(int).to_numpy(),
        "sequence": tx.SEQUENCE.astype(np.int64).to_numpy(),
        "delivered_asset": asset,
        "delivered_units": np.asarray(units, dtype=float),
        "has_sendmax": extra.map(lambda e: "SendMax" in e).to_numpy(),
        "has_paths": extra.map(lambda e: "Paths" in e).to_numpy(),
    })
    p["usd"] = rates.usd(p.ts, p.delivered_asset, p.delivered_units)
    p["delivered_currency"] = p.delivered_asset.map(_currency)

    # ---- transfers: aggregate legs, then join one-to-one ----
    legs, _ = _legs(raw["transfers"], rates)
    n = len(p)
    p = p.merge(legs, left_on="TRANSACTION_HASH", right_index=True, how="left", validate="one_to_one")
    if len(p) != n or p.n_legs.isna().any():
        raise ValueError("some transactions have no transfer legs")
    same = (p.last_leg_asset == p.delivered_asset) & np.isclose(p.last_leg_units, p.delivered_units, rtol=1e-9, atol=1e-6)
    if not same.all():
        raise ValueError(f"{int((~same).sum())} transactions: last leg != DELIVERED_AMOUNT")
    if not ((p.first_leg_from == p.sender) & (p.last_leg_to == p.receiver)).all():
        raise ValueError("first leg must start at the sender and the last leg must end at the receiver")
    p["source_currency"] = p.source_asset.map(_currency)

    # ---- blocks: one-to-one on (LEDGER_INDEX, LEDGER_HASH) ----
    b = raw["blocks"].assign(LEDGER_INDEX=lambda d: d.LEDGER_INDEX.astype(np.int64))
    if b.duplicated(["LEDGER_INDEX", "LEDGER_HASH"]).any():
        raise ValueError("duplicate ledger keys in blocks")
    b = b.rename(columns={"LEDGER_INDEX": "ledger_index", "LEDGER_HASH": "ledger_hash"})
    b["block_ts"] = b.TIMESTAMP.astype(np.int64)
    p = p.merge(b[["ledger_index", "ledger_hash", "block_ts"]], on=["ledger_index", "ledger_hash"], how="left", validate="many_to_one")
    if len(p) != n or p.block_ts.isna().any():
        raise ValueError("some transactions have no matching block")
    if (p.block_ts != p.ts).any():
        raise ValueError("transaction timestamp differs from its ledger close time")

    return p.drop(columns=["last_leg_asset", "last_leg_units", "last_leg_to", "first_leg_from", "block_ts"])


def attach_labels(p: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Target + label metadata (metadata only for grouping/reporting, never features)."""
    out = p.merge(labels[["TRANSACTION_HASH", "is_suspicious", *LABEL_META]], on="TRANSACTION_HASH",
                  how="left", validate="one_to_one")
    if out.is_suspicious.isna().any():
        raise ValueError("some training transactions have no label")
    return out


def load_split(directory: Path) -> pd.DataFrame:
    raw = load_raw(directory)
    p = build_payments(raw)
    return attach_labels(p, raw["labels"]) if raw["labels"] is not None else p
