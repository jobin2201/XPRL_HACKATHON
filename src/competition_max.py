"""Decode & Detect: maximum-precision variant (separate from competition.py, which stays LightGBM-only).

Goal: the highest precision in the top 1% of scores (the site's "precision" number), measured honestly.

Candidates, all on the SAME grouped folds (a scenario never spans folds):
  lightgbm, xgboost, catboost              single models
  ensemble                                 average of the three
  ensemble + two-stage                     second stage sees the out-of-fold scores of nearby payments that
                                           share a wallet (nested, so it cannot leak); stage 2 is again the
                                           average of the three model types
Selection: top-1% precision on pooled out-of-fold scores (tie-break: Average Precision).

Same data loader and features as competition.py (tx_data.py, tx_features.py).
Outputs go to outputs/competition_max/ only:
  submission.csv, submission_check.json, evaluation.json, train_scores.parquet, test_scores.parquet, run_log.txt

Run:  python src/competition_max.py        (about 30-45 minutes on a laptop CPU)
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from catboost import CatBoostClassifier
from sklearn.metrics import average_precision_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

from competition import K, MAX_BYTES, MAX_ROWS, SEED, TEST_DIR, TRAIN_DIR, details, leakage_report, summarise
from tx_data import LABEL_META, load_split
from tx_features import build_features, feature_columns, neighbour_score_features

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "competition_max"

MODELS = {
    "lightgbm": lambda: lgb.LGBMClassifier(n_estimators=800, learning_rate=0.03, num_leaves=31, min_child_samples=20,
                                           subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=1.0,
                                           random_state=SEED, n_jobs=-1, verbose=-1),
    "xgboost": lambda: xgb.XGBClassifier(n_estimators=800, learning_rate=0.03, max_depth=6, min_child_weight=1,
                                         subsample=0.8, colsample_bytree=0.7, reg_lambda=1.0, tree_method="hist",
                                         eval_metric="aucpr", random_state=SEED, n_jobs=-1),
    "catboost": lambda: CatBoostClassifier(iterations=800, depth=6, learning_rate=0.05, random_seed=SEED,
                                           verbose=0, thread_count=-1),
}
ENSEMBLE = list(MODELS)


class Pipeline:
    """members: model names averaged. two_stage: add nested out-of-fold neighbour-score features."""

    def __init__(self, members, two_stage=False):
        self.members, self.two_stage = members, two_stage

    def _fit(self, X, y):
        return [MODELS[m]().fit(X, y) for m in self.members]

    @staticmethod
    def _score(models, X):
        return np.mean([m.predict_proba(X)[:, 1] for m in models], axis=0)

    def fit(self, F, cols, y, groups):
        self.cols = cols
        X = F[cols]
        self.stage1 = self._fit(X, y)
        if self.two_stage:
            oof = np.zeros(len(y))
            for tr, va in StratifiedGroupKFold(K, shuffle=True, random_state=SEED + 1).split(X, y, groups):
                oof[va] = self._score(self._fit(X.iloc[tr], y[tr]), X.iloc[va])
            self.train_oof = oof
            X2 = pd.concat([X, neighbour_score_features(F, oof)], axis=1)
            self.cols2 = list(X2.columns)
            self.stage2 = self._fit(X2, y)
        return self

    def predict(self, F, train_rows=None, train_scores=None):
        s1 = self._score(self.stage1, F[self.cols])
        if not self.two_stage:
            return s1
        if train_rows is not None:
            s1 = s1.copy()
            s1[train_rows] = train_scores
        X2 = pd.concat([F[self.cols], neighbour_score_features(F, s1)], axis=1)[self.cols2]
        return self._score(self.stage2, X2)


def cross_validate(members, two_stage, F, cols, y, groups, folds):
    oof, fold_ap, t0 = np.zeros(len(y)), [], time.time()
    for tr, va in folds:
        pipe = Pipeline(members, two_stage).fit(F.iloc[tr], cols, y[tr], groups[tr])
        oof[va] = (pipe.predict(F, train_rows=tr, train_scores=pipe.train_oof)[va] if two_stage
                   else pipe.predict(F.iloc[va]))
        fold_ap.append(round(100 * average_precision_score(y[va], oof[va]), 2))
    return oof, fold_ap, round(time.time() - t0, 1)


def top1_precision(y, p):
    return float(y[p >= np.quantile(p, 0.99)].mean())


def write_and_check(hashes, scores, test_dir):
    path = OUT / "submission.csv"
    pd.DataFrame({"TRANSACTION_HASH": hashes, "score": np.round(scores, 8)}).to_csv(path, index=False, lineterminator="\n")
    back = pd.read_csv(path, dtype={"TRANSACTION_HASH": str})
    header = path.read_text(encoding="utf-8").splitlines()[0]
    expected = pd.read_parquet(test_dir / "transactions.parquet", columns=["TRANSACTION_HASH"]).TRANSACTION_HASH
    got, want = set(back.TRANSACTION_HASH), set(expected)
    checks = [
        ("Header is exactly TRANSACTION_HASH,score", header == "TRANSACTION_HASH,score"),
        (f"Row count equals test transactions ({len(expected):,})", len(back) == len(expected)),
        ("Every hash appears exactly once", not back.TRANSACTION_HASH.duplicated().any()),
        ("No test transaction is missing", want <= got),
        ("No extra hashes", got <= want),
        ("No empty scores", not back.score.isna().any()),
        ("Scores are between 0 and 1", bool(back.score.between(0, 1).all())),
        (f"At most {MAX_ROWS:,} rows", len(back) <= MAX_ROWS),
        ("File is under 12 MiB", path.stat().st_size <= MAX_BYTES),
        ("Scores are spread out (more than 1,000 distinct values)", back.score.nunique() > 1000),
    ]
    report = {"file": str(path), "rows": int(len(back)), "expected_rows": int(len(expected)),
              "size_kb": round(path.stat().st_size / 1024, 1), "distinct_scores": int(back.score.nunique()),
              "score_min": float(back.score.min()), "score_max": float(back.score.max()),
              "checks": [{"check": c, "passed": bool(ok)} for c, ok in checks], "all_passed": all(ok for _, ok in checks)}
    (OUT / "submission_check.json").write_text(json.dumps(report, indent=2))
    return report


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    print("1/5 loading + joining training files, building features ...", flush=True)
    p = load_split(TRAIN_DIR)
    F = build_features(p)
    meta = p.set_index("TRANSACTION_HASH").loc[F.TRANSACTION_HASH]
    y = meta.is_suspicious.astype(int).to_numpy()
    difficulty, sender = meta.difficulty.to_numpy(), meta.sender.to_numpy()
    groups = np.where(meta.scenario_id.notna(), "scenario:" + meta.scenario_id.astype(str), "sender:" + sender)
    cols = [c for c in feature_columns(F) if F[c].nunique() > 1]
    assert not set(cols) & set(LABEL_META + ["is_suspicious"]), "label information leaked into features"
    folds = list(StratifiedGroupKFold(K, shuffle=True, random_state=SEED).split(F, y, groups))
    print(f"    {len(F):,} transactions, {int(y.sum()):,} suspicious, {len(cols)} features", flush=True)

    print("2/5 single models and their average on grouped folds ...", flush=True)
    results = {}
    for name in MODELS:
        results[name] = (([name], False),) + cross_validate([name], False, F, cols, y, groups, folds)
    results["ensemble"] = ((ENSEMBLE, False), np.mean([results[m][1] for m in MODELS], axis=0), [], 0)
    ens = results["ensemble"]
    results["ensemble"] = (ens[0], ens[1], [round(100 * average_precision_score(y[va], ens[1][va]), 2) for _, va in folds], 0)
    for name, r in results.items():
        print(f"    {name:10s} AP {100 * average_precision_score(y, r[1]):5.1f}   top-1% precision {top1_precision(y, r[1]):.3f}", flush=True)

    print("3/5 ensemble + two-stage (nested) on grouped folds ...", flush=True)
    results["ensemble + two-stage"] = ((ENSEMBLE, True),) + cross_validate(ENSEMBLE, True, F, cols, y, groups, folds)
    r = results["ensemble + two-stage"]
    print(f"    {'ens+2stage':10s} AP {100 * average_precision_score(y, r[1]):5.1f}   top-1% precision {top1_precision(y, r[1]):.3f}  [{r[3]}s]", flush=True)

    chosen = max(results, key=lambda k: (round(top1_precision(y, results[k][1]), 3), average_precision_score(y, results[k][1])))
    (members, two_stage), oof, fold_ap, sec = results[chosen]
    g = summarise(y, oof, fold_ap or [0.0], sec, difficulty)
    print(f"    chosen: {chosen}", flush=True)

    print("4/5 random folds for comparison (leaky) ...", flush=True)
    rfolds = list(StratifiedKFold(K, shuffle=True, random_state=SEED).split(F, y))
    r_oof, r_fap, r_sec = cross_validate(members, two_stage, F, cols, y, groups, rfolds)
    rr = summarise(y, r_oof, r_fap, r_sec, difficulty, g["threshold"])

    print("5/5 final fit on all labelled transactions, scoring the test data ...", flush=True)
    final = Pipeline(members, two_stage).fit(F, cols, y, groups)
    details(p, F).assign(score=np.round(oof, 6), label=y, family=meta.family.to_numpy(), difficulty=difficulty) \
        .to_parquet(OUT / "train_scores.parquet", index=False)
    pt = load_split(TEST_DIR)
    T = build_features(pt)
    missing = [c for c in cols if c not in T.columns]
    if missing:
        raise SystemExit(f"test features differ from training: {missing}")
    scores = np.clip(final.predict(T), 0, 1)
    details(pt, T).assign(score=np.round(scores, 6)).to_parquet(OUT / "test_scores.parquet", index=False)
    check = write_and_check(T.TRANSACTION_HASH.to_numpy(), scores, TEST_DIR)

    table = {k: {"ap": round(100 * average_precision_score(y, v[1]), 2), "top1_precision": round(top1_precision(y, v[1]), 4),
                 "fold_top1_precision": [round(top1_precision(y[va], v[1][va]), 3) for _, va in folds]}
             for k, v in results.items()}
    (OUT / "evaluation.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chosen": chosen, "selection": "top-1% precision on grouped out-of-fold scores (tie-break AP)",
        "candidates": table, "grouped": g, "random_leaky": rr,
        "leakage": {"grouped": leakage_report(folds, y, meta.scenario_id.to_numpy(), sender)},
        "features": cols, "submission": {k: check[k] for k in ["rows", "all_passed", "size_kb"]},
    }, indent=2))

    print("\n================ MAX-PRECISION MODEL SUMMARY ================")
    for k, v in table.items():
        print(f"   {k:22s} AP {v['ap']:5.1f}   top-1% precision {v['top1_precision']:.3f}   "
              f"per fold {v['fold_top1_precision']}{'   <- chosen' if k == chosen else ''}")
    print(f"chosen              : {chosen}")
    print(f"top 1% (site view)  : precision {g['top1_precision']:.3f}   recall {g['top1_recall']:.3f}")
    print(f"AP grouped / random : {g['ap']:.1f} / {rr['ap']:.1f} (random is leaky)")
    print(f"@ threshold {g['threshold']:.3f}   : accuracy {g['accuracy']:.3f}  precision {g['precision']:.3f}  "
          f"recall {g['recall']:.3f}  F1 {g['f1']:.3f}   ROC-AUC {g['roc_auc']:.3f}")
    print(f"by difficulty, top1%: {g['top1_recall_by_difficulty']}")
    print("submission checks   :")
    for c in check["checks"]:
        print(f"   {'PASS' if c['passed'] else 'FAIL'}  {c['check']}")
    print(f"=> {'READY TO UPLOAD' if check['all_passed'] else 'NOT READY'}: {check['file']}  ({(time.time() - t_start) / 60:.1f} min)")
    print("=============================================================")


if __name__ == "__main__":
    main()
