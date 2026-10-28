"""Quick, controlled comparison: LightGBM (current best config) vs one CatBoost configuration.

Same features (tx_features.py), same grouped folds (a scenario never spans folds), single stage only.
Reports grouped-fold Average Precision and top-1% precision (overall and per fold) and training time.
Writes only to outputs/compare/ - no submission file is touched.

Run:  python src/compare_quick.py            (about 5-8 minutes; features are cached after the first run)
"""
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import average_precision_score
from sklearn.model_selection import StratifiedGroupKFold

from tx_data import LABEL_META, load_split
from tx_features import build_features, feature_columns

ROOT = Path(__file__).resolve().parents[1]
TRAIN_DIR = ROOT / "decode-and-detect-training-data" / "train"
OUT = ROOT / "outputs" / "compare"
SEED, K = 0, 5

MODELS = {
    "lightgbm (53.3 config)": lambda: lgb.LGBMClassifier(
        n_estimators=1500, learning_rate=0.02, num_leaves=15, min_child_samples=40, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.5, reg_lambda=5.0, random_state=SEED, n_jobs=-1, verbose=-1),
    "catboost": lambda: CatBoostClassifier(
        iterations=800, depth=6, learning_rate=0.05, random_seed=SEED, verbose=0, thread_count=-1),
}


def top1_precision(y, p):
    return float(y[p >= np.quantile(p, 0.99)].mean())


def load_features():
    cache = OUT / "train_features_v2.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    p = load_split(TRAIN_DIR)
    F = build_features(p)
    meta = p.set_index("TRANSACTION_HASH").loc[F.TRANSACTION_HASH]
    F["__y"] = meta.is_suspicious.astype(int).to_numpy()
    F["__group"] = np.where(meta.scenario_id.notna(), "scenario:" + meta.scenario_id.astype(str), "sender:" + meta.sender)
    F["__difficulty"] = meta.difficulty.to_numpy()
    F.to_parquet(cache, index=False)
    return F


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    F = load_features()
    y, groups, diff = F["__y"].to_numpy(), F["__group"].to_numpy(), F["__difficulty"].to_numpy()
    cols = [c for c in feature_columns(F) if not c.startswith("__") and F[c].nunique() > 1]
    assert not set(cols) & set(LABEL_META + ["is_suspicious"])
    folds = list(StratifiedGroupKFold(K, shuffle=True, random_state=SEED).split(F, y, groups))
    print(f"{len(F):,} transactions, {int(y.sum())} suspicious, {len(cols)} features  (ready in {time.time() - t0:.0f}s)", flush=True)

    results, oofs = {}, {}
    for name, make in MODELS.items():
        oof, ts = np.zeros(len(y)), time.time()
        for tr, va in folds:
            oof[va] = make().fit(F[cols].iloc[tr], y[tr]).predict_proba(F[cols].iloc[va])[:, 1]
        oofs[name] = oof
        top = oof >= np.quantile(oof, 0.99)
        results[name] = {
            "grouped_ap": round(100 * average_precision_score(y, oof), 2),
            "top1_precision": round(top1_precision(y, oof), 3),
            "top1_precision_per_fold": [round(top1_precision(y[va], oof[va]), 3) for _, va in folds],
            "top1_caught": {d: int((top & (diff == d)).sum()) for d in ["easy", "medium", "hard"]},
            "seconds": round(time.time() - ts, 1),
        }
        r = results[name]
        print(f"{name:24s} AP {r['grouped_ap']:5.1f}  top-1% precision {r['top1_precision']:.3f}  "
              f"per fold {r['top1_precision_per_fold']}  caught {r['top1_caught']}  [{r['seconds']}s]", flush=True)

    avg = np.mean(list(oofs.values()), axis=0)
    results["average of both"] = {"grouped_ap": round(100 * average_precision_score(y, avg), 2),
                                  "top1_precision": round(top1_precision(y, avg), 3),
                                  "top1_precision_per_fold": [round(top1_precision(y[va], avg[va]), 3) for _, va in folds]}
    r = results["average of both"]
    print(f"{'average of both':24s} AP {r['grouped_ap']:5.1f}  top-1% precision {r['top1_precision']:.3f}  per fold {r['top1_precision_per_fold']}")
    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    print(f"saved {OUT / 'results.json'}  ({(time.time() - t0) / 60:.1f} min)")


if __name__ == "__main__":
    main()
