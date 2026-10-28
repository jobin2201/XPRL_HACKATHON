"""Per-transaction features for the Decode & Detect data (shared by training, scoring and the API).

load_split(dir)    -> one row per transaction: effective edge from the official payments.py + legs/fee info
make_features(df)  -> one feature row per transaction (computed within the split only, no labels used)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "decode-and-detect-training-data"
TEST_DATA = ROOT / "decode-and-detect-test-data"
sys.path.insert(0, str(DATA))
from payments import load_payments  # noqa: E402  (official loader, values payments in reference USD)

HOUR, TEN_MIN, DAY = 3600, 600, 86400


def _window_count(times, t, before, after):
    if times is None:
        return 0
    return int(np.searchsorted(times, t + after, "right") - np.searchsorted(times, t - before, "left"))


def load_split(directory: Path) -> pd.DataFrame:
    """One row per transaction: effective edge (payments.py) + leg/fee info from the raw tables."""
    pay = pd.DataFrame(load_payments(directory))
    tx = pd.read_parquet(directory / "transactions.parquet",
                         columns=["TRANSACTION_HASH", "FEE", "MEMOS", "SOURCE_TAG", "EXTRA_TRANSACTION_FIELDS"])
    tx["has_memo"] = tx.MEMOS.notna() & (tx.MEMOS.astype(str).str.len() > 2)
    tx["has_source_tag"] = tx.SOURCE_TAG.notna()
    extra = tx.EXTRA_TRANSACTION_FIELDS.map(json.loads)
    tx["has_dest_tag"] = extra.map(lambda e: e.get("DestinationTag") is not None)
    tx["has_sendmax"] = extra.map(lambda e: e.get("SendMax") is not None)
    legs = pd.read_parquet(directory / "transfers.parquet", columns=["TRANSACTION_HASH", "TRANSFER_TYPE", "SYMBOL"])
    lg = legs.groupby("TRANSACTION_HASH").agg(n_legs=("SYMBOL", "size"), n_assets=("SYMBOL", "nunique"),
                                              is_path=("TRANSFER_TYPE", lambda s: (s == "path_payment").any()))
    sym = legs.sort_values("TRANSACTION_HASH").groupby("TRANSACTION_HASH").SYMBOL.last()
    lg = lg.join(pd.get_dummies(sym, prefix="dst").astype(float))
    df = pay.merge(tx.drop(columns=["MEMOS", "SOURCE_TAG", "EXTRA_TRANSACTION_FIELDS"]), on="TRANSACTION_HASH")
    return df.merge(lg, left_on="TRANSACTION_HASH", right_index=True, how="left")


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("TIMESTAMP").reset_index(drop=True)
    t = df.TIMESTAMP.astype(np.int64).to_numpy()
    v = df.VALUE.to_numpy(float)
    snd, rcv = df.FROM_ADDRESS, df.TO_ADDRESS
    sends = {a: g.TIMESTAMP.astype(np.int64).to_numpy() for a, g in df.groupby("FROM_ADDRESS")}
    gets = {a: g.TIMESTAMP.astype(np.int64).to_numpy() for a, g in df.groupby("TO_ADDRESS")}
    sent_v = {a: g.VALUE.to_numpy(float) for a, g in df.groupby("FROM_ADDRESS")}
    got_v = {a: g.VALUE.to_numpy(float) for a, g in df.groupby("TO_ADDRESS")}

    f = pd.DataFrame({"TRANSACTION_HASH": df.TRANSACTION_HASH})
    # --- payment itself ---
    f["log_value"] = np.log1p(v)
    f["round_10"] = (np.abs(v - np.round(v, -1)) < 0.5).astype(float)
    f["round_100"] = (np.abs(v - np.round(v, -2)) < 1).astype(float)
    f["hour_of_day"] = (t % DAY) // HOUR
    f["fee"] = df.FEE.astype(float)
    for c in ["has_memo", "has_source_tag", "has_dest_tag", "has_sendmax", "n_legs", "n_assets", "is_path"]:
        f[c] = df[c].astype(float)
    for c in [c for c in df.columns if c.startswith("dst_")]:
        f[c] = df[c].fillna(0)

    # --- account activity over the whole window ---
    out_n, in_n = snd.value_counts(), rcv.value_counts()
    out_cp = df.groupby("FROM_ADDRESS").TO_ADDRESS.nunique()
    in_cp = df.groupby("TO_ADDRESS").FROM_ADDRESS.nunique()
    for side, col in (("sender", snd), ("receiver", rcv)):
        f[f"{side}_out_n"] = col.map(out_n).fillna(0)
        f[f"{side}_in_n"] = col.map(in_n).fillna(0)
        f[f"{side}_out_cp"] = col.map(out_cp).fillna(0)
        f[f"{side}_in_cp"] = col.map(in_cp).fillna(0)
    pair = snd + ">" + rcv
    f["pair_n"] = pair.map(pair.value_counts())
    f["reverse_pair_exists"] = (rcv + ">" + snd).isin(set(pair)).astype(float)

    # --- flow / relay timing (from starter notebook, plus wider windows) ---
    f["sender_burst_10m"] = [_window_count(sends.get(a), ti, TEN_MIN, TEN_MIN) for a, ti in zip(snd, t)]
    f["receiver_burst_10m"] = [_window_count(gets.get(a), ti, TEN_MIN, TEN_MIN) for a, ti in zip(rcv, t)]
    f["receiver_fwd_1h"] = [_window_count(sends.get(a), ti, 0, HOUR) for a, ti in zip(rcv, t)]
    f["receiver_fwd_24h"] = [_window_count(sends.get(a), ti, 0, DAY) for a, ti in zip(rcv, t)]
    f["sender_got_1h_before"] = [_window_count(gets.get(a), ti, HOUR, 0) for a, ti in zip(snd, t)]
    f["sender_got_24h_before"] = [_window_count(gets.get(a), ti, DAY, 0) for a, ti in zip(snd, t)]

    def nearest_match(times_map, vals_map, acct, ti, amt, forward, horizon):
        times = times_map.get(acct)
        if times is None:
            return 0.0, horizon
        if forward:
            lo, hi = np.searchsorted(times, ti, "right"), np.searchsorted(times, ti + horizon, "right")
        else:
            lo, hi = np.searchsorted(times, ti - horizon, "left"), np.searchsorted(times, ti, "left")
        if lo >= hi:
            return 0.0, horizon
        rel = np.abs(vals_map[acct][lo:hi] - amt) / max(amt, 1e-9)
        ok = rel <= 0.1
        if not ok.any():
            return 0.0, horizon
        gap = np.abs(times[lo:hi][ok] - ti).min()
        return 1.0, float(gap)

    fw = [nearest_match(sends, sent_v, a, ti, x, True, DAY) for a, ti, x in zip(rcv, t, v)]
    bw = [nearest_match(gets, got_v, a, ti, x, False, DAY) for a, ti, x in zip(snd, t, v)]
    f["receiver_fwd_similar_24h"], f["receiver_fwd_similar_gap_min"] = zip(*fw)
    f["sender_got_similar_24h"], f["sender_got_similar_gap_min"] = zip(*bw)
    f["receiver_fwd_similar_gap_min"] = f.receiver_fwd_similar_gap_min.astype(float) / 60
    f["sender_got_similar_gap_min"] = f.sender_got_similar_gap_min.astype(float) / 60

    # --- pass-through: share of received value an account sends on ---
    sent_tot, got_tot = df.groupby("FROM_ADDRESS").VALUE.sum(), df.groupby("TO_ADDRESS").VALUE.sum()
    pt = (sent_tot / got_tot.reindex(sent_tot.index)).clip(0, 3)
    f["sender_pass_through"] = snd.map(pt).fillna(0)
    f["receiver_pass_through"] = rcv.map(pt).fillna(0)
    f["sender_value_share"] = v / snd.map(sent_tot).replace(0, np.nan)
    f["receiver_value_share"] = v / rcv.map(got_tot).replace(0, np.nan)

    # --- when in the window an account is active (planted motifs live in short bursts) ---
    first = pd.concat([df.groupby("FROM_ADDRESS").TIMESTAMP.min(), df.groupby("TO_ADDRESS").TIMESTAMP.min()]).groupby(level=0).min()
    last = pd.concat([df.groupby("FROM_ADDRESS").TIMESTAMP.max(), df.groupby("TO_ADDRESS").TIMESTAMP.max()]).groupby(level=0).max()
    life = (last - first).astype(float) / HOUR
    f["sender_life_h"] = snd.map(life)
    f["receiver_life_h"] = rcv.map(life)

    # --- neighbourhood: how relay-like are the accounts one hop away ---
    relay = (pt.between(0.8, 1.2)).astype(float)
    nb = df.assign(r=rcv.map(relay).fillna(0)).groupby("FROM_ADDRESS").r.mean()
    f["sender_relay_neighbours"] = snd.map(nb).fillna(0)
    f["receiver_relay_neighbours"] = rcv.map(nb).fillna(0)

    return f.fillna(0).astype({c: float for c in f.columns if c != "TRANSACTION_HASH"})
