"""Optional feature groups for controlled experiments (switched on with run_model.py --extra ...).

  ratios    numerically stable amount ratios: log amount minus the wallet's median log amount, clipped to +-5
  activity  activity CHANGE: recent rate vs the wallet's longer-term rate, recent out/in balance,
            amount vs the wallet's recent (+-24h) median, forwarding speed vs the receiver's usual speed
  patterns  pattern structure and pace around one-off payments (tx_patterns.py)

All groups use only the split's own transactions (no labels) and are built identically for train and test.
Input: the output of tx_features.build_features (uses its columns and _s/_r/_t keys).
"""
import numpy as np
import pandas as pd

from tx_features import FlowIndex
from tx_patterns import build_pattern_features

CLIP = 5.0


def ratio_features(F: pd.DataFrame) -> pd.DataFrame:
    lv = F["log_usd"].to_numpy(float)
    if (lv < 0).any() or np.isnan(lv).any():
        raise ValueError("log_usd must be finite and non-negative (USD amounts >= 0)")
    s, r = F["_s"].to_numpy(), F["_r"].to_numpy()
    lvs = pd.Series(lv)
    return pd.DataFrame({
        "log_amt_vs_sender_median": np.clip(lv - lvs.groupby(s).transform("median").to_numpy(), -CLIP, CLIP),
        "log_amt_vs_receiver_median": np.clip(lv - lvs.groupby(r).transform("median").to_numpy(), -CLIP, CLIP),
    }, index=F.index)


def activity_features(F: pd.DataFrame) -> pd.DataFrame:
    s, r, t = F["_s"].to_numpy(np.int64), F["_r"].to_numpy(np.int64), F["_t"].to_numpy(np.int64)
    lv = F["log_usd"].to_numpy(float)
    n_acc = int(F["_n_acc"].iloc[0])

    def rate_change(short, long, w_short, w_long):
        # counts are over +-w, so both windows are 2w long; +1 smoothing keeps quiet wallets finite
        expected = F[long].to_numpy(float) * (w_short / w_long)
        return np.log((F[short].to_numpy(float) + 1) / (expected + 1))

    out = {
        "s_rate_change_10m_vs_24h": rate_change("s_out_10m", "s_out_24h", 600, 86_400),
        "r_rate_change_10m_vs_24h": rate_change("r_in_10m", "r_in_24h", 600, 86_400),
        "s_rate_change_1h_vs_72h": rate_change("s_out_1h", "s_out_72h", 3_600, 259_200),
        "r_rate_change_1h_vs_72h": rate_change("r_in_1h", "r_in_72h", 3_600, 259_200),
        "s_recent_out_in_balance_1h": np.log((F["s_out_1h"].to_numpy(float) + 1) / (F["s_in_before_1h"].to_numpy(float) + 1)),
        "r_recent_out_in_balance_1h": np.log((F["r_out_after_1h"].to_numpy(float) + 1) / (F["r_in_1h"].to_numpy(float) + 1)),
    }
    # amount vs the sender's median log amount over its sends in +-24h (excluding this payment)
    sends = FlowIndex(s, r, t, lv, n_acc)
    lo, hi = sends.bounds(s, t, 86_400, 86_400)
    rel = np.zeros(len(t))
    for i in range(len(t)):
        vals = sends.v[lo[i]:hi[i]]
        if len(vals) > 1:
            rel[i] = lv[i] - np.median(vals)
    out["log_amt_vs_sender_recent_median_24h"] = np.clip(rel, -CLIP, CLIP)
    # how fast the receiver forwards this payment compared with how fast it usually forwards
    gap = F["r_fwd_gap_min_loose"].to_numpy(float)
    usual = pd.Series(gap).groupby(r).transform("median").to_numpy()
    out["r_forward_speed_vs_usual"] = np.clip(np.log((gap + 1) / (usual + 1)), -CLIP, CLIP)
    return pd.DataFrame(out, index=F.index)


GROUPS = {"ratios": ratio_features, "activity": activity_features, "patterns": build_pattern_features}


def extra_features(F: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    parts = [GROUPS[g](F) for g in groups]
    return pd.concat(parts, axis=1) if parts else pd.DataFrame(index=F.index)
