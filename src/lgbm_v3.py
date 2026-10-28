"""LightGBM v3: refactored, self-contained submission pipeline.

  python src/lgbm_v3.py                    single-stage LightGBM (recommended)
  python src/lgbm_v3.py --seeds 3          average of 3 LightGBM seeds (steadier ranking)
  python src/lgbm_v3.py --two-stage        adds nested out-of-fold neighbour scores (slower)

Steps
  1. Load and join the five files per split (tx_data.py; every join is checked).
  2. Features: ~134 behavioural features (tx_features.py) + 47 pattern features (tx_patterns.py).
     Built from each split's own transactions, no labels; identical code for train and test.
  3. Grouped 5-fold validation (a planted scenario is never split between training and validation).
     Prints the site score (100 x AP), top-1% precision/recall, ROC-AUC, accuracy/precision/recall/F1.
  4. Fit on all labelled transactions, score the 40,101 test transactions, check the CSV.
  5. Write submission_v3/<run>/predictions.csv and source_code.zip, ready to upload.
Nothing outside outputs/models/<run>/ and submission_v3/<run>/ is written.
"""
import argparse
import json
import platform
import time
import zipfile
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import (accuracy_score, average_precision_score, f1_score, precision_recall_curve,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedGroupKFold

from tx_data import LABEL_META, load_split
from tx_features import build_features, feature_columns, neighbour_score_features
from tx_patterns import build_pattern_features

ROOT = Path(__file__).resolve().parents[1]
TRAIN_DIR = ROOT / "decode-and-detect-training-data" / "train"
TEST_DIR = ROOT / "decode-and-detect-test-data"
CACHE = ROOT / "outputs" / "models" / "lightgbm_v3_cache"
SEED, K = 0, 5
EXPECTED_TEST_ROWS = 40_101

PARAMS = dict(n_estimators=3000, learning_rate=0.01, num_leaves=63, min_child_samples=30,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.5, reg_lambda=5.0, n_jobs=-1, verbose=-1)
SOURCE_FILES = ["lgbm_v3.py", "tx_data.py", "tx_features.py", "tx_patterns.py"]


# ------------------------------------------------------------------ data + features
def features_for(directory: Path, name: str):
    """Feature table for one split (cached). Returns (F, payments)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f_path, p_path = CACHE / f"{name}_features.parquet", CACHE / f"{name}_payments.parquet"
    if f_path.exists() and p_path.exists():
        return pd.read_parquet(f_path), pd.read_parquet(p_path)
    p = load_split(directory)
    F = build_features(p)
    F = pd.concat([F, build_pattern_features(F)], axis=1)
    F.to_parquet(f_path, index=False)
    p.to_parquet(p_path, index=False)
    return F, p


# ------------------------------------------------------------------ model
class LightGBMScorer:
    """Seed-averaged LightGBM, optionally with a nested out-of-fold neighbour-score second stage."""

    def __init__(self, seeds: int = 1, two_stage: bool = False):
        self.seeds, self.two_stage = seeds, two_stage

    def _fit(self, X, y):
        return [lgb.LGBMClassifier(**PARAMS, random_state=SEED + k).fit(X, y) for k in range(self.seeds)]

    @staticmethod
    def _score(models, X):
        return np.mean([m.predict_proba(X)[:, 1] for m in models], axis=0)

    def fit(self, F, cols, y, groups):
        self.cols = cols
        self.stage1 = self._fit(F[cols], y)
        if self.two_stage:
            oof = np.zeros(len(y))
            for tr, va in StratifiedGroupKFold(K, shuffle=True, random_state=SEED + 1).split(F, y, groups):
                oof[va] = self._score(self._fit(F[cols].iloc[tr], y[tr]), F[cols].iloc[va])
            self.train_oof = oof
            X2 = pd.concat([F[cols], neighbour_score_features(F, oof)], axis=1)
            self.cols2 = list(X2.columns)
            self.stage2 = self._fit(X2, y)
        return self

    def predict(self, F, train_rows=None, train_scores=None):
        s1 = self._score(self.stage1, F[self.cols])
        if not self.two_stage:
            return s1
        if train_rows is not None:          # validation: training rows keep their out-of-fold scores
            s1 = s1.copy()
            s1[train_rows] = train_scores
        X2 = pd.concat([F[self.cols], neighbour_score_features(F, s1)], axis=1)[self.cols2]
        return self._score(self.stage2, X2)


# ------------------------------------------------------------------ evaluation
def metrics(y, p, difficulty):
    prec, rec, thr = precision_recall_curve(y, p)
    f1s = 2 * prec[:-1] * rec[:-1] / np.maximum(prec[:-1] + rec[:-1], 1e-12)
    t = float(thr[np.argmax(f1s)])
    top = p >= np.quantile(p, 0.99)
    return {
        "site_score_ap": round(100 * average_precision_score(y, p), 2),
        "top1_precision": round(float(y[top].mean()), 4),
        "top1_recall": round(float(y[top].sum() / y.sum()), 4),
        "roc_auc": round(roc_auc_score(y, p), 4),
        "threshold": round(t, 4),
        "accuracy": round(accuracy_score(y, p >= t), 4),
        "precision": round(precision_score(y, p >= t), 4),
        "recall": round(recall_score(y, p >= t), 4),
        "f1": round(f1_score(y, p >= t), 4),
        "ap_by_difficulty": {d: round(100 * average_precision_score(y[(difficulty == d) | (y == 0)], p[(difficulty == d) | (y == 0)]), 1)
                             for d in ["easy", "medium", "hard"]},
        "caught_in_top1": {d: f"{int((top & (difficulty == d)).sum())}/{int((difficulty == d).sum())}"
                           for d in ["easy", "medium", "hard"]},
    }


def check_submission(path: Path):
    back = pd.read_csv(path, dtype={"TRANSACTION_HASH": str})
    want = pd.read_parquet(TEST_DIR / "transactions.parquet", columns=["TRANSACTION_HASH"]).TRANSACTION_HASH
    checks = {
        "header is TRANSACTION_HASH,score": path.read_text(encoding="utf-8").splitlines()[0] == "TRANSACTION_HASH,score",
        f"{EXPECTED_TEST_ROWS:,} rows": len(back) == len(want) == EXPECTED_TEST_ROWS,
        "every hash exactly once": not back.TRANSACTION_HASH.duplicated().any(),
        "same hashes as the test data": set(back.TRANSACTION_HASH) == set(want),
        "scores are numbers in [0, 1]": (not back.score.isna().any()) and bool(back.score.between(0, 1).all()),
        "under 12 MiB": path.stat().st_size <= 12 * 1024 * 1024,
        "scores spread out (>1,000 distinct)": back.score.nunique() > 1000,
    }
    return checks


def write_package(run: str, folder: Path, m: dict, minutes: float, args):
    readme = f"""# Decode & Detect – Code Gladiators (LightGBM v3)

## Exact command
```
python -m pip install -r requirements.txt
python src/lgbm_v3.py{' --seeds ' + str(args.seeds) if args.seeds > 1 else ''}{' --two-stage' if args.two_stage else ''}
```
Writes `submission_v3/{run}/predictions.csv` (`TRANSACTION_HASH,score`, 40,101 rows) and this ZIP.

Data layout (not included): `decode-and-detect-training-data/train/` (5 files incl. labels.csv) and
`decode-and-detect-test-data/` (4 files), next to `src/`.
Hardware/time: laptop CPU, no GPU, about {minutes:.0f} minutes. Python {platform.python_version()}.

## Method
- `src/tx_data.py`: joins transactions, transfers (legs aggregated per transaction), blocks (one-to-one on ledger keys)
  and hourly market rates; every join is checked. XRP drops and token units are never mixed.
- `src/tx_features.py`: ~134 behavioural features: one-off wallet pairs, activity in 10m-72h windows, forwarding of
  similar amounts, multi-hop chains, cycles, wallet profiles, clusters of one-off payments.
- `src/tx_patterns.py`: 47 pattern features: how one-off payments around a payment link up (closed neighbourhoods,
  bipartite squares) and the pace of that local pattern (gaps between payments) in 15m-3h windows.
- `src/lgbm_v3.py`: LightGBM ({PARAMS['num_leaves']} leaves, {PARAMS['n_estimators']} trees, learning rate {PARAMS['learning_rate']})
  {'averaged over ' + str(args.seeds) + ' seeds' if args.seeds > 1 else ''}{', with a nested out-of-fold neighbour-score second stage' if args.two_stage else ''}.
- Label metadata (family, difficulty, scenario_id, cohort_id) is never a feature; scenario_id only keeps scenarios
  inside one validation fold.

## Validation (labelled training data, grouped 5-fold; not the test set)
| Measure | Value |
|---|---|
| 100 x Average Precision | {m['site_score_ap']} |
| Top-1% precision / recall | {m['top1_precision']:.1%} / {m['top1_recall']:.1%} |
| ROC-AUC | {m['roc_auc']} |
| Accuracy / precision / recall / F1 at threshold {m['threshold']} | {m['accuracy']:.2%} / {m['precision']:.1%} / {m['recall']:.1%} / {m['f1']:.3f} |
"""
    req = (f"# Python {platform.python_version()}\npandas=={pd.__version__}\npyarrow==26.0.0\nnumpy=={np.__version__}\n"
           f"scikit-learn=={sklearn.__version__}\nlightgbm=={lgb.__version__}\n")
    zpath = folder / "source_code.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, allowZip64=False) as z:
        z.writestr("README.md", readme)
        z.writestr("requirements.txt", req)
        for f in ["LICENSE", "THIRD_PARTY.md"]:
            z.write(ROOT / f, f)
        for f in SOURCE_FILES:
            z.write(ROOT / "src" / f, f"src/{f}")
    return zpath


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--two-stage", action="store_true")
    args = ap.parse_args()
    run = "lightgbm_v3" + (f"_seeds{args.seeds}" if args.seeds > 1 else "") + ("_two_stage" if args.two_stage else "")
    out = ROOT / "outputs" / "models" / run
    pkg = ROOT / "submission_v3" / run
    out.mkdir(parents=True, exist_ok=True)
    pkg.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print(f"[{run}] 1/4 training data: join + features (cached after the first run) ...", flush=True)
    F, p = features_for(TRAIN_DIR, "train")
    meta = p.set_index("TRANSACTION_HASH").loc[F.TRANSACTION_HASH]
    y = meta.is_suspicious.astype(int).to_numpy()
    difficulty = meta.difficulty.to_numpy()
    groups = np.where(meta.scenario_id.notna(), "scenario:" + meta.scenario_id.astype(str), "sender:" + meta.sender)
    cols = [c for c in feature_columns(F) if F[c].nunique() > 1]
    assert not set(cols) & set(LABEL_META + ["is_suspicious"]), "label information leaked into features"
    print(f"    {len(F):,} transactions, {int(y.sum()):,} suspicious, {len(cols)} features", flush=True)

    print("2/4 grouped 5-fold validation ...", flush=True)
    folds = list(StratifiedGroupKFold(K, shuffle=True, random_state=SEED).split(F, y, groups))
    oof, fold_prec, fold_ap = np.zeros(len(y)), [], []
    for i, (tr, va) in enumerate(folds, 1):
        model = LightGBMScorer(args.seeds, args.two_stage).fit(F.iloc[tr], cols, y[tr], groups[tr])
        oof[va] = (model.predict(F, train_rows=tr, train_scores=model.train_oof)[va] if args.two_stage
                   else model.predict(F.iloc[va]))
        fold_prec.append(round(float(y[va][oof[va] >= np.quantile(oof[va], 0.99)].mean()), 3))
        fold_ap.append(round(100 * average_precision_score(y[va], oof[va]), 1))
        print(f"    fold {i}/5: AP {fold_ap[-1]:5.1f}  top-1% precision {fold_prec[-1]:.3f}", flush=True)
    m = metrics(y, oof, difficulty)
    m.update(fold_ap=fold_ap, top1_precision_per_fold=fold_prec)

    print("3/4 final model on all labelled transactions + test scoring ...", flush=True)
    final = LightGBMScorer(args.seeds, args.two_stage).fit(F, cols, y, groups)
    T, _ = features_for(TEST_DIR, "test")
    missing = [c for c in cols if c not in T.columns]
    if missing:
        raise SystemExit(f"test features differ from training: {missing}")
    scores = np.clip(final.predict(T), 0, 1)

    print("4/4 writing and checking the submission ...", flush=True)
    sub = pd.DataFrame({"TRANSACTION_HASH": T.TRANSACTION_HASH.to_numpy(), "score": np.round(scores, 8)})
    csv = pkg / "predictions.csv"
    sub.to_csv(csv, index=False, lineterminator="\n")
    sub.to_csv(out / "submission.csv", index=False, lineterminator="\n")
    checks = check_submission(csv)
    pd.DataFrame({"TRANSACTION_HASH": F.TRANSACTION_HASH, "oof_score": oof.round(6), "is_suspicious": y,
                  "difficulty": difficulty}).to_csv(out / "oof_scores.csv", index=False)
    minutes = (time.time() - t0) / 60
    zpath = write_package(run, pkg, m, minutes, args)
    m.update(run=run, features=len(cols), checks=checks, minutes=round(minutes, 1),
             importance=sorted(((c, float(v)) for c, v in zip(cols, final.stage1[0].booster_.feature_importance("gain"))),
                               key=lambda t: -t[1])[:30])
    (out / "validation.json").write_text(json.dumps(m, indent=2))

    print(f"\n==================== {run.upper()} ====================")
    print(f"Site score (100 x AP)     : {m['site_score_ap']}   (folds {fold_ap})")
    print(f"Top-1% precision / recall : {m['top1_precision']:.1%} / {m['top1_recall']:.1%}   (folds {fold_prec})")
    print(f"AP by difficulty          : {m['ap_by_difficulty']}   caught in top 1%: {m['caught_in_top1']}")
    print(f"ROC-AUC                   : {m['roc_auc']}")
    print(f"At threshold {m['threshold']}      : accuracy {m['accuracy']:.2%}  precision {m['precision']:.1%}  "
          f"recall {m['recall']:.1%}  F1 {m['f1']:.3f}")
    print("Submission checks         : " + ("ALL PASSED" if all(checks.values()) else f"FAILED {[k for k, v in checks.items() if not v]}"))
    print(f"Upload                    : {csv}")
    print(f"                            {zpath}  ({zpath.stat().st_size / 1024:.0f} KB)")
    print(f"Time                      : {minutes:.1f} min   (validation is measured on labelled training data)")


if __name__ == "__main__":
    main()
