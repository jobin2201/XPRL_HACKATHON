"""Transaction features. One function, used identically for train, validation and test.

All features are computed from one split's own transactions (the README allows using the whole
supplied window: "This is an offline investigation, not real-time detection"). No labels, no label
metadata, no absolute dates or ledger numbers (those identify the split, not the behaviour).

Groups
  A  the payment itself      amount (log USD), round amounts, currency, conversion legs, fee, hour, ledger position
  B  wallet history          account SEQUENCE: activity before the window, position inside it
  C  activity windows        sends/receives of sender and receiver in 10m / 1h / 6h / 24h / 72h windows (+ value)
  D  counterparties          distinct counterparties in 1h / 24h windows
  E  layering                receiver forwards a similar amount on / sender was just funded with a similar amount
  F  chains                  how many hops a similar amount keeps moving forward / came from (6h and 72h per hop)
  G  cycles                  money returns to the sender within 48h through up to 4 hops
  H  pairs                   how often this sender->receiver pair occurs, first time or repeat, reverse flow
  I  relative amount         amount compared with the sender's and receiver's usual amounts
  J  wallet profile (week)   counts, value, counterparties, pass-through, lifetime, burstiness, reciprocity
  K  neighbourhood           2-hop activity around the payment; how relay-like the neighbours are
  L  one-off clusters        payments on wallet pairs that never repeat, and the cluster they form in 30m / 3h / 12h
"""
import numpy as np
import pandas as pd

WINDOWS = {"10m": 600, "1h": 3_600, "6h": 21_600, "24h": 86_400, "72h": 259_200}
OFFSET = 2_000_000       # shift times so window bounds never go negative
SPAN = 10_000_000        # > OFFSET + 7 days + largest window: keeps account blocks apart in the composite key
CURRENCIES = ["XRP", "USD", "GBP", "EUR"]


class FlowIndex:
    """Every account's sends and receives, sorted by time, in flat arrays with a composite sort key."""

    def __init__(self, own: np.ndarray, other: np.ndarray, t: np.ndarray, v: np.ndarray, n_accounts: int):
        order = np.lexsort((t, own))
        self.own, self.other, self.t, self.v, self.row = own[order], other[order], t[order], v[order], order
        self.key = own[order].astype(np.int64) * SPAN + t[order]
        self.start = np.searchsorted(self.own, np.arange(n_accounts), "left")
        self.end = np.searchsorted(self.own, np.arange(n_accounts), "right")
        self.cum_v = np.concatenate([[0.0], np.cumsum(self.v)])

    def bounds(self, acct, t, before, after, left_closed=True, right_closed=True):
        """Vectorised [lo, hi) slice of acct's events with time in the window around t."""
        base = acct.astype(np.int64) * SPAN
        lo = np.searchsorted(self.key, base + t - before, "left" if left_closed else "right")
        hi = np.searchsorted(self.key, base + t + after, "right" if right_closed else "left")
        return lo, hi

    def count(self, acct, t, before, after, **kw):
        lo, hi = self.bounds(acct, t, before, after, **kw)
        return hi - lo

    def total(self, acct, t, before, after, **kw):
        lo, hi = self.bounds(acct, t, before, after, **kw)
        return self.cum_v[hi] - self.cum_v[lo]


def _distinct_in_window(index: FlowIndex, acct, t, w):
    lo, hi = index.bounds(acct, t, w, w)
    return np.array([len(np.unique(index.other[a:b])) if b > a else 0 for a, b in zip(lo, hi)])


def _match_gap(index: FlowIndex, acct, t, v, horizon, forward, band):
    """Minutes to the nearest event of acct (after t if forward, before t otherwise) whose value is
    within band x v. Returns horizon (in minutes) when there is none."""
    lo_r, hi_r = band
    out = np.full(len(t), horizon / 60.0)
    if forward:
        lo, hi = index.bounds(acct, t, 0, horizon, left_closed=False)
    else:
        lo, hi = index.bounds(acct, t, horizon, 0, right_closed=False)
    for i in np.nonzero(hi > lo)[0]:
        vals = index.v[lo[i]:hi[i]]
        ok = (vals >= lo_r * v[i]) & (vals <= hi_r * v[i])
        if ok.any():
            gaps = np.abs(index.t[lo[i]:hi[i]][ok] - t[i])
            out[i] = gaps.min() / 60.0
    return out


def _chain_depth(out_idx: FlowIndex, in_idx: FlowIndex, s, r, t, v, hop, forward, max_depth=6, band=(0.5, 1.05)):
    """Follow a similar amount hop by hop (earliest match forward / latest match backward)."""
    depth = np.zeros(len(t), dtype=np.int32)
    for i in range(len(t)):
        acct, ti, vi, d = (r[i] if forward else s[i]), t[i], v[i], 0
        while d < max_depth:
            idx = out_idx if forward else in_idx
            a, b = idx.start[acct], idx.end[acct]
            times = idx.t[a:b]
            if forward:
                lo, hi = np.searchsorted(times, ti, "right"), np.searchsorted(times, ti + hop, "right")
                vals = idx.v[a + lo:a + hi]
                ok = np.nonzero((vals >= band[0] * vi) & (vals <= band[1] * vi))[0]
                if not len(ok):
                    break
                j = a + lo + ok[0]
            else:
                lo, hi = np.searchsorted(times, ti - hop, "left"), np.searchsorted(times, ti, "left")
                vals = idx.v[a + lo:a + hi]
                ok = np.nonzero((vals >= vi / band[1]) & (vals <= vi / band[0]))[0]
                if not len(ok):
                    break
                j = a + lo + ok[-1]
            acct, ti, vi, d = idx.other[j], idx.t[j], idx.v[j], d + 1
        depth[i] = d
    return depth


def _cycle_hops(out_idx: FlowIndex, s, r, t, v, horizon=172_800, max_hops=4, fan=5, band=(0.3, 1.1)):
    """Smallest number of hops (1..max_hops) after which value returns to the sender; 0 = no cycle."""
    res = np.zeros(len(t), dtype=np.int32)
    for i in range(len(t)):
        frontier, found = [(r[i], t[i])], 0
        for hops in range(1, max_hops + 1):
            nxt = []
            for acct, ti in frontier:
                a, b = out_idx.start[acct], out_idx.end[acct]
                times = out_idx.t[a:b]
                lo, hi = np.searchsorted(times, ti, "right"), np.searchsorted(times, t[i] + horizon, "right")
                vals = out_idx.v[a + lo:a + hi]
                ok = np.nonzero((vals >= band[0] * v[i]) & (vals <= band[1] * v[i]))[0][:fan]
                for k in ok:
                    j = a + lo + k
                    if out_idx.other[j] == s[i]:
                        found = hops
                        break
                    nxt.append((out_idx.other[j], out_idx.t[j]))
                if found:
                    break
            if found or not nxt:
                break
            frontier = nxt[:50]
        res[i] = found
    return res


def _two_hop_activity(out_idx: FlowIndex, in_idx: FlowIndex, s, r, t, w):
    """Number of payments in +-w touching any account that s or r dealt with in +-w (incl. s and r)."""
    so_lo, so_hi = out_idx.bounds(s, t, w, w)
    si_lo, si_hi = in_idx.bounds(s, t, w, w)
    ro_lo, ro_hi = out_idx.bounds(r, t, w, w)
    ri_lo, ri_hi = in_idx.bounds(r, t, w, w)
    res = np.zeros(len(t))
    for i in range(len(t)):
        nb = np.unique(np.concatenate([
            out_idx.other[so_lo[i]:so_hi[i]], in_idx.other[si_lo[i]:si_hi[i]],
            out_idx.other[ro_lo[i]:ro_hi[i]], in_idx.other[ri_lo[i]:ri_hi[i]], [s[i], r[i]]]))
        tt = np.full(len(nb), t[i])
        res[i] = (out_idx.count(nb, tt, w, w) + in_idx.count(nb, tt, w, w)).sum() / 2
    return res


def build_features(p: pd.DataFrame) -> pd.DataFrame:
    """p = data.build_payments(...) output. Returns one row per transaction (same order as sorted by time)."""
    p = p.sort_values(["ts", "ledger_index", "tx_index", "TRANSACTION_HASH"]).reset_index(drop=True)
    codes, accounts = pd.factorize(pd.concat([p.sender, p.receiver], ignore_index=True))
    n_acc = len(accounts)
    s, r = codes[:len(p)], codes[len(p):]
    t = p.ts.to_numpy(np.int64) - p.ts.min() + OFFSET
    v = p.usd.to_numpy(float)
    out_idx = FlowIndex(s, r, t, v, n_acc)   # sends, keyed by sender
    in_idx = FlowIndex(r, s, t, v, n_acc)    # receipts, keyed by receiver

    f = {"TRANSACTION_HASH": p.TRANSACTION_HASH.to_numpy()}

    # ---- A: the payment itself ----
    f["log_usd"] = np.log1p(v)
    units = p.delivered_units.to_numpy(float)
    f["round_units_1"] = (np.abs(units - np.round(units)) < 1e-9).astype(float)
    f["round_units_10"] = (np.abs(units - np.round(units, -1)) < 1e-9).astype(float)
    f["round_usd_10"] = (np.abs(v - np.round(v, -1)) < 0.5).astype(float)
    for c in CURRENCIES:
        f[f"delivered_{c}"] = (p.delivered_currency == c).to_numpy(float)
        f[f"source_{c}"] = (p.source_currency == c).to_numpy(float)
    f["is_conversion"] = p.is_conversion.to_numpy(float)
    f["n_legs"] = p.n_legs.to_numpy(float)
    f["has_paths"] = p.has_paths.to_numpy(float)
    f["has_sendmax"] = p.has_sendmax.to_numpy(float)
    f["fee_drops"] = p.fee_drops.to_numpy(float)
    hour = (p.ts.to_numpy() % 86_400) / 3_600
    f["hour_sin"], f["hour_cos"] = np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)
    f["tx_index"] = p.tx_index.to_numpy(float)
    f["txs_in_ledger"] = p.groupby("ledger_index").TRANSACTION_HASH.transform("size").to_numpy(float)
    all_t = np.sort(t)
    busy = np.searchsorted(all_t, t + 3_600, "right") - np.searchsorted(all_t, t - 3_600, "left")
    f["network_activity_2h_rel"] = busy / (len(t) / (7 * 12))          # vs the average 2-hour volume

    # ---- B: wallet history from SEQUENCE ----
    seq = p.sequence.to_numpy(np.int64)
    seq_min = pd.Series(seq).groupby(s).transform("min").to_numpy()
    f["sender_seq_before_window"] = seq_min.astype(float)
    f["sender_seq_in_window"] = (seq - seq_min).astype(float)
    acct_seq_min = pd.Series(seq).groupby(s).min()
    f["receiver_min_observed_sender_sequence"] = pd.Series(r).map(acct_seq_min).fillna(-1).to_numpy(float)

    # ---- C: activity windows ----
    for name, w in WINDOWS.items():
        f[f"s_out_{name}"] = out_idx.count(s, t, w, w)
        f[f"r_in_{name}"] = in_idx.count(r, t, w, w)
        f[f"s_in_before_{name}"] = in_idx.count(s, t, w, 0, right_closed=False)
        f[f"r_out_after_{name}"] = out_idx.count(r, t, 0, w, left_closed=False)
        f[f"r_fwd_ratio_{name}"] = np.minimum(out_idx.total(r, t, 0, w, left_closed=False) / np.maximum(v, 1e-9), 10)
        f[f"s_funded_ratio_{name}"] = np.minimum(in_idx.total(s, t, w, 0, right_closed=False) / np.maximum(v, 1e-9), 10)

    # ---- D: distinct counterparties ----
    for name in ["1h", "24h"]:
        f[f"s_out_cp_{name}"] = _distinct_in_window(out_idx, s, t, WINDOWS[name])
        f[f"r_in_cp_{name}"] = _distinct_in_window(in_idx, r, t, WINDOWS[name])

    # ---- E: layering (similar amount in / out) ----
    for name, band in [("tight", (0.9, 1.02)), ("loose", (0.5, 1.05))]:
        f[f"r_fwd_gap_min_{name}"] = _match_gap(out_idx, r, t, v, WINDOWS["72h"], True, band)
        f[f"s_funded_gap_min_{name}"] = _match_gap(in_idx, s, t, v, WINDOWS["72h"], False, (1 / band[1], 1 / band[0]))

    # ---- F: chains ----
    for name, hop in [("6h", WINDOWS["6h"]), ("72h", WINDOWS["72h"])]:
        f[f"chain_fwd_{name}"] = _chain_depth(out_idx, in_idx, s, r, t, v, hop, True)
        f[f"chain_bwd_{name}"] = _chain_depth(out_idx, in_idx, s, r, t, v, hop, False)
    f["chain_total_6h"] = f["chain_fwd_6h"] + f["chain_bwd_6h"]
    f["chain_total_72h"] = f["chain_fwd_72h"] + f["chain_bwd_72h"]

    # ---- G: cycles ----
    f["cycle_hops_48h"] = _cycle_hops(out_idx, s, r, t, v)

    # ---- H: pairs ----
    pair = pd.Series(s.astype(np.int64) * n_acc + r)
    f["pair_n"] = pair.map(pair.value_counts()).to_numpy(float)
    f["pair_k"] = pair.groupby(pair).cumcount().to_numpy(float)
    f["pair_first"] = (f["pair_k"] == 0).astype(float)
    rev = set((r.astype(np.int64) * n_acc + s).tolist()) & set(pair.tolist())
    f["pair_reverse_exists"] = (r.astype(np.int64) * n_acc + s).astype(np.int64)
    f["pair_reverse_exists"] = np.isin(f["pair_reverse_exists"], list(rev) or [-1]).astype(float)
    day = (t - t.min()) // 86_400
    f["pair_active_days"] = pd.Series(day).groupby(pair).transform("nunique").to_numpy(float)

    # ---- I: relative amount ----
    sv = pd.Series(v)
    f["usd_vs_sender_median"] = v / sv.groupby(s).transform("median").to_numpy()
    f["usd_vs_receiver_median"] = v / sv.groupby(r).transform("median").to_numpy()
    lv = pd.Series(np.log1p(v))
    f["log_usd_z_sender"] = ((lv - lv.groupby(s).transform("mean")) / lv.groupby(s).transform("std").fillna(1).replace(0, 1)).to_numpy()

    # ---- J: wallet profile over the week (for sender and receiver) ----
    prof = _profiles(s, r, t, v, p.is_conversion.to_numpy(bool), n_acc, f["r_fwd_gap_min_tight"])
    for col in prof.columns:
        f[f"s_{col}"] = prof[col].to_numpy()[s]
        f[f"r_{col}"] = prof[col].to_numpy()[r]

    # ---- K: neighbourhood ----
    for name in ["1h", "6h"]:
        f[f"two_hop_activity_{name}"] = _two_hop_activity(out_idx, in_idx, s, r, t, WINDOWS[name])
    relay = prof["relay_share"].to_numpy()
    nb = pd.DataFrame({"a": np.concatenate([s, r]), "b": np.concatenate([r, s])}).drop_duplicates()
    nb_relay = pd.Series(relay[nb.b.to_numpy()]).groupby(nb.a.to_numpy()).mean()
    f["s_neighbour_relay_share"] = pd.Series(s).map(nb_relay).fillna(0).to_numpy()
    f["r_neighbour_relay_share"] = pd.Series(r).map(nb_relay).fillna(0).to_numpy()

    # ---- L: clusters of one-off payments (planted patterns use wallet pairs that never repeat) ----
    global _V
    _V = v
    rare = f["pair_n"] <= 1
    rows = np.nonzero(rare)[0]
    rare_idx = FlowIndex(np.concatenate([s[rows], r[rows]]), np.concatenate([r[rows], s[rows]]),
                         np.concatenate([t[rows], t[rows]]), np.concatenate([rows, rows]).astype(float), n_acc)
    for name, w in [("30m", 1_800), ("3h", 10_800), ("12h", 43_200)]:
        f[f"s_rare_{name}"] = rare_idx.count(s, t, w, w)
        f[f"r_rare_{name}"] = rare_idx.count(r, t, w, w)
        f[f"rare_cluster_tx_{name}"], f[f"rare_cluster_accounts_{name}"] = _rare_cluster(rare_idx, s, r, t, w)
        sim1, sim2, cv2 = _rare_similar(rare_idx, s, r, t, v, w)
        f[f"rare_similar_1hop_{name}"], f[f"rare_similar_2hop_{name}"], f[f"rare_value_cv_2hop_{name}"] = sim1, sim2, cv2

    out = pd.DataFrame(f)
    feat = out.columns.drop("TRANSACTION_HASH")
    out[feat] = out[feat].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    # keys for the second-stage neighbour features (not model inputs)
    keys = pd.DataFrame({"_s": s, "_r": r, "_t": t, "_n_acc": n_acc}, index=out.index)
    return pd.concat([out, keys], axis=1)


KEY_COLS = ["TRANSACTION_HASH", "_s", "_r", "_t", "_n_acc"]


def feature_columns(F: pd.DataFrame) -> list[str]:
    return [c for c in F.columns if c not in KEY_COLS]


def neighbour_score_features(F: pd.DataFrame, score: np.ndarray) -> pd.DataFrame:
    """Second stage: scores of OTHER payments that share a wallet with this one within a window.
    `score` must be out-of-sample for every row (out-of-fold on train, a train-fitted model on test)."""
    s, r, t = F["_s"].to_numpy(np.int64), F["_r"].to_numpy(np.int64), F["_t"].to_numpy(np.int64)
    n = len(t)
    n_acc = int(F["_n_acc"].iloc[0])
    if len(score) != n or np.isnan(score).any():
        raise ValueError("neighbour scores must be one finite value per row")
    if n and max(s.max(), r.max()) >= n_acc:
        raise ValueError("wallet codes exceed the number of accounts: keys do not belong to this table")
    rows = np.arange(n)
    idx = FlowIndex(np.concatenate([s, r]), np.concatenate([r, s]), np.concatenate([t, t]),
                    np.concatenate([rows, rows]).astype(float), int(F["_n_acc"].iloc[0]))
    out = {}
    for name, w in [("10m", 600), ("1h", 3_600), ("6h", 21_600), ("24h", 86_400)]:
        lo1, hi1 = idx.bounds(s, t, w, w)
        lo2, hi2 = idx.bounds(r, t, w, w)
        mx, mean, high, cnt = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
        for i in range(n):
            other = np.unique(np.concatenate([idx.v[lo1[i]:hi1[i]], idx.v[lo2[i]:hi2[i]]]).astype(np.int64))
            other = other[other != i]
            if len(other) and (other.min() < 0 or other.max() >= n):
                raise ValueError("neighbour lookup returned an invalid row")
            if len(other):
                sc = score[other]
                mx[i], mean[i], high[i], cnt[i] = sc.max(), sc.mean(), (sc >= 0.5).sum(), len(other)
        out[f"nb_max_{name}"], out[f"nb_mean_{name}"], out[f"nb_high_{name}"], out[f"nb_count_{name}"] = mx, mean, high, cnt
    return pd.DataFrame(out, index=F.index)


def _rare_cluster(rare_idx: FlowIndex, s, r, t, w, max_depth=3, max_accounts=60):
    """Connected cluster of one-off payments within +-w of t, grown from the sender and receiver.
    Returns (number of one-off payments in the cluster, number of wallets in it)."""
    n_tx, n_acc = np.zeros(len(t)), np.zeros(len(t))
    for i in range(len(t)):
        seen_acc, seen_tx, frontier = {s[i], r[i]}, set(), [s[i], r[i]]
        for _ in range(max_depth):
            nxt = []
            for a in frontier:
                lo, hi = rare_idx.bounds(np.array([a]), np.array([t[i]]), w, w)
                for j in range(lo[0], hi[0]):
                    seen_tx.add(int(rare_idx.v[j]))
                    b = rare_idx.other[j]
                    if b not in seen_acc:
                        seen_acc.add(b)
                        nxt.append(b)
            if not nxt or len(seen_acc) >= max_accounts:
                break
            frontier = nxt
        n_tx[i], n_acc[i] = len(seen_tx), len(seen_acc)
    return n_tx, n_acc


def _rare_similar(rare_idx: FlowIndex, s, r, t, v, w, band=(0.75, 1.33)):
    """One-off payments within +-w that touch the sender/receiver (1 hop) or their one-off partners (2 hops)
    and carry a similar amount (band x v); plus the spread (CV) of amounts in the 2-hop set."""
    vals_all = None
    sim1, sim2, cv2 = np.zeros(len(t)), np.zeros(len(t)), np.zeros(len(t))
    for i in range(len(t)):
        lo, hi = rare_idx.bounds(np.array([s[i], r[i]]), np.array([t[i], t[i]]), w, w)
        tx1 = {int(rare_idx.v[j]) for a, b in zip(lo, hi) for j in range(a, b)}
        nb = {rare_idx.other[j] for a, b in zip(lo, hi) for j in range(a, b)} - {s[i], r[i]}
        tx2 = set(tx1)
        if nb:
            nb = np.fromiter(nb, dtype=np.int64)
            lo2, hi2 = rare_idx.bounds(nb, np.full(len(nb), t[i]), w, w)
            tx2.update(int(rare_idx.v[j]) for a, b in zip(lo2, hi2) for j in range(a, b))
        tx1.discard(i)
        tx2.discard(i)
        if tx1:
            vv = _V[np.fromiter(tx1, dtype=np.int64)]
            sim1[i] = ((vv >= band[0] * v[i]) & (vv <= band[1] * v[i])).sum()
        if tx2:
            vv = _V[np.fromiter(tx2, dtype=np.int64)]
            sim2[i] = ((vv >= band[0] * v[i]) & (vv <= band[1] * v[i])).sum()
            cv2[i] = vv.std() / vv.mean() if len(vv) > 1 and vv.mean() > 0 else 0
    return sim1, sim2, cv2


_V = np.zeros(0)  # payment values by row, set in build_features before the rare features run


def _profiles(s, r, t, v, conv, n_acc, fwd_gap_tight):
    """Per-account summary of the whole week, from both roles."""
    acc = np.arange(n_acc)
    out = pd.DataFrame({"a": s, "b": r, "t": t, "v": v, "conv": conv, "fwd": fwd_gap_tight < 60})
    inn = pd.DataFrame({"a": r, "b": s, "t": t, "v": v, "fwd": fwd_gap_tight < 60})
    go, gi = out.groupby("a"), inn.groupby("a")
    prof = pd.DataFrame(index=acc)
    prof["out_n"] = go.size()
    prof["in_n"] = gi.size()
    prof["out_cp"] = go.b.nunique()
    prof["in_cp"] = gi.b.nunique()
    prof["out_usd"] = go.v.sum()
    prof["in_usd"] = gi.v.sum()
    prof = prof.fillna(0)
    hi = prof[["out_usd", "in_usd"]].max(axis=1)
    prof["pass_through"] = (prof[["out_usd", "in_usd"]].min(axis=1) / hi.replace(0, np.nan)).fillna(0)
    prof["in_out_balance"] = (prof.in_usd - prof.out_usd) / (prof.in_usd + prof.out_usd).replace(0, np.nan)
    both = pd.concat([out[["a", "t"]], inn[["a", "t"]]])
    gb = both.groupby("a").t
    prof["life_h"] = (gb.max() - gb.min()) / 3_600
    prof["active_hours"] = both.assign(h=both.t // 3_600).groupby("a").h.nunique()
    gaps = out.sort_values(["a", "t"]).groupby("a").t.diff()
    prof["send_gap_median_min"] = gaps.groupby(out.sort_values(["a", "t"]).a).median() / 60
    prof["burst_share"] = (gaps < 600).groupby(out.sort_values(["a", "t"]).a).mean()
    prof["conversion_share"] = go.conv.mean()
    prof["relay_share"] = gi.fwd.mean()           # share of receipts forwarded (similar amount) within 1h
    prof["log_usd_out_mean"] = np.log1p(out.v).groupby(out.a).mean()
    prof["log_usd_out_std"] = np.log1p(out.v).groupby(out.a).std()
    edges = set(zip(s.tolist(), r.tolist()))
    recip = pd.Series([1 for a, b in edges if (b, a) in edges], index=[a for a, b in edges if (b, a) in edges], dtype=float)
    prof["reciprocal_cp"] = recip.groupby(level=0).sum() if len(recip) else 0
    return prof.fillna(0)
