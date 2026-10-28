"""Pattern features: how payments on one-off wallet pairs link up around each payment.

Why: planted patterns (fan-out, bipartite, stack, chains...) are made of payments between wallet pairs that
never repeat, among a small set of wallets that are linked to each other within minutes to hours.
Legitimate look-alikes have the same shapes, but a different PACE (suspicious: ~1 min between payments
for easy cases, ~18 min for medium ones; legitimate look-alikes: ~6-10 min). Ordinary one-off payments go to
unrelated wallets, so their neighbourhood is not closed.

Input: the output of tx_features.build_features (needs pair_n and the _s/_r/_t/_n_acc keys).
Uses only the split's own transactions, never labels. Identical for train and test.

Groups
  oneoff_*   structure in +-30m / 1h / 3h: number of one-off neighbours, links between those neighbours
             (closed neighbourhood), bipartite squares, one-off payments in before/out after
  pace*_*    pace in +-15m / 30m / 1h / 3h: minutes to the previous/next one-off payment on the same wallets,
             size, span and median/max gap of the local pattern, wallets in it, position of this payment in it
"""
import numpy as np
import pandas as pd

from tx_features import FlowIndex

STRUCTURE_WINDOWS = (1_800, 3_600, 10_800)
PACE_WINDOWS = (900, 1_800, 3_600, 10_800)


def _label(w):
    return f"{w // 60}m"


def _indexes(F):
    s, r, t = F["_s"].to_numpy(np.int64), F["_r"].to_numpy(np.int64), F["_t"].to_numpy(np.int64)
    n_acc = int(F["_n_acc"].iloc[0])
    one_off = F["pair_n"].to_numpy() <= 1
    rows = np.nonzero(one_off)[0]
    both = FlowIndex(np.concatenate([s[rows], r[rows]]), np.concatenate([r[rows], s[rows]]),
                     np.concatenate([t[rows], t[rows]]), np.concatenate([rows, rows]).astype(float), n_acc)
    out = FlowIndex(s[rows], r[rows], t[rows], rows.astype(float), n_acc)   # one-off sends per wallet
    inn = FlowIndex(r[rows], s[rows], t[rows], rows.astype(float), n_acc)   # one-off receipts per wallet
    return s, r, t, one_off, both, out, inn


def _one(index, acct, ti, before, after):
    lo, hi = index.bounds(np.array([acct]), np.array([ti]), before, after)
    return lo[0], hi[0]


def structure_features(F, s, r, t, both, out, inn, w):
    n = len(t)
    res = {k: np.zeros(n) for k in ["n_nb", "closed", "closed_ratio", "squares", "path2"]}
    for i in range(n):
        a1, b1 = _one(both, s[i], t[i], w, w)
        a2, b2 = _one(both, r[i], t[i], w, w)
        nb = set(both.other[a1:b1].tolist()) | set(both.other[a2:b2].tolist())
        nb.discard(s[i])
        nb.discard(r[i])
        res["n_nb"][i] = len(nb)
        if nb:
            nbs = np.fromiter(nb, np.int64)
            lo, hi = both.bounds(nbs, np.full(len(nbs), t[i]), w, w)
            closed = {int(both.v[j]) for a, b in zip(lo, hi) for j in range(a, b) if both.other[j] in nb}
            res["closed"][i] = len(closed)
            res["closed_ratio"][i] = len(closed) / len(nb)
        a, b = _one(inn, r[i], t[i], w, w)
        senders_r = set(inn.other[a:b].tolist()) - {s[i]}
        a, b = _one(out, s[i], t[i], w, w)
        receivers_s = set(out.other[a:b].tolist()) - {r[i]}
        if senders_r and receivers_s:
            sq = 0
            for sp in senders_r:
                a, b = _one(out, sp, t[i], w, w)
                sq += len(set(out.other[a:b].tolist()) & receivers_s)
            res["squares"][i] = sq
        a, b = _one(inn, s[i], t[i], w, 0)
        c, d = _one(out, r[i], t[i], 0, w)
        res["path2"][i] = (b - a) + (d - c)
    return {f"oneoff_{k}_{_label(w)}": v for k, v in res.items()}


def pace_features(F, s, r, t, one_off, both, w):
    n = len(t)
    cap = w / 60
    res = {k: np.zeros(n) for k in ["gap_prev", "gap_next", "pat_n", "pat_span", "pat_gap_med", "pat_gap_max",
                                    "pat_wallets", "pat_rank"]}
    for i in range(n):
        lo, hi = both.bounds(np.array([s[i], r[i]]), np.array([t[i], t[i]]), w, w)
        near = {int(both.v[j]) for a, b in zip(lo, hi) for j in range(a, b)}
        near.discard(i)
        res["gap_prev"][i] = res["gap_next"][i] = cap
        if near:
            tt = t[np.fromiter(near, np.int64)]
            before, after = tt[tt <= t[i]], tt[tt > t[i]]
            if len(before):
                res["gap_prev"][i] = (t[i] - before.max()) / 60
            if len(after):
                res["gap_next"][i] = (after.min() - t[i]) / 60
        nb = set(both.other[lo[0]:hi[0]].tolist()) | set(both.other[lo[1]:hi[1]].tolist()) | {s[i], r[i]}
        nbs = np.fromiter(nb, np.int64)
        l2, h2 = both.bounds(nbs, np.full(len(nbs), t[i]), w, w)
        pat = {int(both.v[j]) for a, b in zip(l2, h2) for j in range(a, b) if both.other[j] in nb}
        if one_off[i]:
            pat.add(i)
        if len(pat) >= 2:
            pr = np.fromiter(pat, np.int64)
            tt = np.sort(t[pr])
            gaps = np.diff(tt) / 60
            res["pat_n"][i] = len(pr)
            res["pat_span"][i] = (tt[-1] - tt[0]) / 60
            res["pat_gap_med"][i] = np.median(gaps)
            res["pat_gap_max"][i] = gaps.max()
            res["pat_wallets"][i] = len(set(s[pr]) | set(r[pr]))
            res["pat_rank"][i] = np.searchsorted(tt, t[i]) / len(tt)
    return {f"pace{_label(w)}_{k}": v for k, v in res.items()}


def build_pattern_features(F: pd.DataFrame) -> pd.DataFrame:
    """Returns pattern features aligned with F's rows."""
    s, r, t, one_off, both, out, inn = _indexes(F)
    feats = {}
    for w in STRUCTURE_WINDOWS:
        feats.update(structure_features(F, s, r, t, both, out, inn, w))
    for w in PACE_WINDOWS:
        feats.update(pace_features(F, s, r, t, one_off, both, w))
    return pd.DataFrame(feats, index=F.index)
