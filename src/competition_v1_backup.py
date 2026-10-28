"""Decode & Detect: train, verify and submit the per-transaction LightGBM model.

Steps
  1. Build features for train/ (features use the split's own transactions only, never labels).
  2. Make two sets of 5 folds on the SAME rows:
       random  - StratifiedKFold (the original check)
       grouped - StratifiedGroupKFold: a scenario never spans two folds; rows without a
                 scenario are grouped by sender account. This is the honest estimate.
     and measure leakage for each (scenarios split across folds, senders shared across folds).
  3. Cross-validate LightGBM on both fold sets with out-of-fold Average Precision (the site's metric).
  4. Fit LightGBM on all labelled rows, score the test data.
  5. Write submission.csv (exactly TRANSACTION_HASH,score) and validate it against the test files.

Outputs (outputs/competition/):
  evaluation.json         folds, leakage, cross-validation results, feature importance
  train_scores.parquet    out-of-fold scores for every training transaction (grouped folds)
  test_scores.parquet     test scores with transaction details (for the dashboard)
  submission.csv          upload this file
  submission_check.json   result of every submission check

Run:
  python src/competition.py                     # full run (about 1 minute)
  python src/competition.py --test path/to/test-data
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, average_precision_score, precision_score, recall_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

from tx_features import DATA, ROOT, TEST_DATA, load_split, make_features

OUT = ROOT / "outputs" / "competition"
SEED, K = 0, 5
MAX_BYTES, MAX_ROWS = 12 * 1024 * 1024, 100_000  # site limits

MODEL_NAME = "lightgbm"


def make_model():
    return lgb.LGBMClassifier(
        n_estimators=600, learning_rate=0.03, num_leaves=31, min_child_samples=20, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, reg_lambda=1.0, random_state=SEED, n_jobs=-1, verbose=-1)


# ------------------------------------------------------------------ folds and leakage
def make_folds(y, groups):
    idx = np.zeros(len(y))
    return {
        "random": list(StratifiedKFold(K, shuffle=True, random_state=SEED).split(idx, y)),
        "grouped": list(StratifiedGroupKFold(K, shuffle=True, random_state=SEED).split(idx, y, groups)),
    }


def leakage_report(folds, y, scenario, sender):
    fold_of = np.empty(len(y), dtype=int)
    for i, (_, va) in enumerate(folds):
        fold_of[va] = i
    d = pd.DataFrame({"fold": fold_of, "y": y, "scenario": scenario, "sender": sender})
    sus = d[(d.y == 1) & d.scenario.notna()]
    folds_per_scenario = sus.groupby("scenario").fold.nunique()
    split = folds_per_scenario[folds_per_scenario > 1].index
    sender_overlap = []
    for tr, va in folds:
        seen = set(sender[tr])
        sender_overlap.append(float(np.isin(sender[va], list(seen)).mean()))
    return {
        "fold_sizes": [int(len(va)) for _, va in folds],
        "fold_suspicious": [int(y[va].sum()) for _, va in folds],
        "suspicious_scenarios": int(len(folds_per_scenario)),
        "scenarios_split_across_folds": int(len(split)),
        "suspicious_rows_whose_scenario_is_also_in_training": int(sus.scenario.isin(split).sum()),
        "suspicious_rows": int(len(sus)),
        "share_of_check_rows_whose_sender_is_in_training": round(float(np.mean(sender_overlap)), 4),
    }


# ------------------------------------------------------------------ evaluation
def top1(y, p):
    top = p >= np.quantile(p, 0.99)
    return float(y[top].mean()), float(y[top].sum() / y.sum())


def cross_validate(X, y, folds, difficulty):
    oof, fold_ap, t0 = np.zeros(len(y)), [], time.time()
    for tr, va in folds:
        model = make_model().fit(X.iloc[tr], y[tr])
        oof[va] = model.predict_proba(X.iloc[va])[:, 1]
        fold_ap.append(round(100 * average_precision_score(y[va], oof[va]), 2))
    prec1, rec1 = top1(y, oof)
    top = oof >= np.quantile(oof, 0.99)
    return oof, {
        "ap": round(100 * average_precision_score(y, oof), 2),  # pooled out-of-fold predictions
        "fold_ap": fold_ap,
        "fold_ap_mean": round(float(np.mean(fold_ap)), 2),
        "fold_ap_std": round(float(np.std(fold_ap)), 2),
        "top1_precision": round(prec1, 4),
        "top1_recall": round(rec1, 4),
        "accuracy_at_0_5": round(accuracy_score(y, oof >= 0.5), 4),
        "precision_at_0_5": round(precision_score(y, oof >= 0.5, zero_division=0), 4),
        "recall_at_0_5": round(recall_score(y, oof >= 0.5), 4),
        "top1_recall_by_difficulty": {
            d: f"{int((top & (difficulty == d)).sum())}/{int((difficulty == d).sum())}" for d in ["easy", "medium", "hard"]},
        "seconds": round(time.time() - t0, 1),
    }


# ------------------------------------------------------------------ submission
def write_and_check_submission(test_features, scores, test_dir: Path):
    sub = pd.DataFrame({"TRANSACTION_HASH": test_features.TRANSACTION_HASH.to_numpy(), "score": np.round(scores, 6)})
    path = OUT / "submission.csv"
    sub.to_csv(path, index=False)

    back = pd.read_csv(path)
    expected = pd.read_parquet(test_dir / "transactions.parquet", columns=["TRANSACTION_HASH"]).TRANSACTION_HASH
    got = set(back.TRANSACTION_HASH)
    checks = [
        ("Columns are exactly TRANSACTION_HASH,score", list(back.columns) == ["TRANSACTION_HASH", "score"]),
        (f"Row count equals test transactions ({len(expected):,})", len(back) == len(expected)),
        ("Every hash appears exactly once", not back.TRANSACTION_HASH.duplicated().any()),
        ("No test transaction is missing", set(expected) <= got),
        ("No extra hashes", got <= set(expected)),
        ("No empty scores", not back.score.isna().any()),
        ("Scores are between 0 and 1", bool(back.score.between(0, 1).all())),
        (f"At most {MAX_ROWS:,} rows", len(back) <= MAX_ROWS),
        ("File is under 12 MiB", path.stat().st_size <= MAX_BYTES),
        ("Scores are spread out (more than 1,000 distinct values)", back.score.nunique() > 1000),
    ]
    report = {
        "file": str(path),
        "rows": int(len(back)),
        "expected_rows": int(len(expected)),
        "size_kb": round(path.stat().st_size / 1024, 1),
        "distinct_scores": int(back.score.nunique()),
        "score_min": float(back.score.min()), "score_max": float(back.score.max()),
        "checks": [{"check": c, "passed": bool(ok)} for c, ok in checks],
        "all_passed": all(ok for _, ok in checks),
    }
    (OUT / "submission_check.json").write_text(json.dumps(report, indent=2))
    return report


def details(raw, feats):
    """Readable columns for the dashboard, in the order of the feature table."""
    d = raw.set_index("TRANSACTION_HASH").loc[feats.TRANSACTION_HASH]
    return pd.DataFrame({
        "TRANSACTION_HASH": feats.TRANSACTION_HASH.to_numpy(),
        "time": pd.to_datetime(d.TIMESTAMP.astype("int64").to_numpy(), unit="s", utc=True),
        "from": d.FROM_ADDRESS.to_numpy(),
        "to": d.TO_ADDRESS.to_numpy(),
        "usd": d.VALUE.astype(float).round(2).to_numpy(),
        "legs": d.n_legs.fillna(0).astype(int).to_numpy(),
        "conversion": d.is_path.fillna(False).astype(bool).to_numpy(),
    })


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", type=Path, default=TEST_DATA)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    print("1/5 building training features ...")
    raw = load_split(DATA / "train")
    labels = pd.read_csv(DATA / "train" / "labels.csv")
    F = make_features(raw).merge(labels, on="TRANSACTION_HASH", validate="one_to_one")
    meta_cols = ["TRANSACTION_HASH", "is_suspicious", "family", "difficulty", "scenario_id", "cohort_id"]
    X = F.drop(columns=meta_cols)
    y = F.is_suspicious.to_numpy()
    sender = raw.set_index("TRANSACTION_HASH").loc[F.TRANSACTION_HASH].FROM_ADDRESS.to_numpy()
    scenario = F.scenario_id.to_numpy()
    groups = np.where(F.scenario_id.notna(), "scenario:" + F.scenario_id.astype(str), "sender:" + sender)
    difficulty = F.difficulty.to_numpy()
    print(f"    {len(F):,} transactions, {int(y.sum()):,} suspicious, {X.shape[1]} features")

    print("2/5 making folds and checking leakage ...")
    folds = make_folds(y, groups)
    leakage = {s: leakage_report(f, y, scenario, sender) for s, f in folds.items()}
    for s, r in leakage.items():
        print(f"    {s:8s}: {r['scenarios_split_across_folds']}/{r['suspicious_scenarios']} scenarios split across folds, "
              f"{r['share_of_check_rows_whose_sender_is_in_training']:.0%} of check rows have a sender seen in training")

    print("3/5 cross-validating LightGBM on both fold sets (out-of-fold Average Precision) ...")
    results, oof_final = {s: {} for s in folds}, None
    for s, f in folds.items():
        oof, res = cross_validate(X, y, f, difficulty)
        results[s][MODEL_NAME] = res
        if s == "grouped":
            oof_final = oof
        print(f"    {s:8s} {MODEL_NAME:10s} AP {res['ap']:5.1f}  (folds {res['fold_ap_mean']:.1f} ± {res['fold_ap_std']:.1f})  "
              f"top1% P {res['top1_precision']:.3f} R {res['top1_recall']:.3f}  [{res['seconds']}s]")

    print(f"4/5 training final LightGBM on all {len(F):,} labelled transactions ...")
    final = make_model().fit(X, y)
    gain = final.booster_.feature_importance("gain")
    importance = [{"feature": c, "gain": round(float(g), 1)}
                  for c, g in sorted(zip(X.columns, gain), key=lambda t: -t[1])]

    train_scores = details(raw, F).assign(
        score=np.round(oof_final, 6), label=y, family=F.family.to_numpy(), difficulty=difficulty)
    train_scores.to_parquet(OUT / "train_scores.parquet", index=False)

    print(f"5/5 scoring test data in {args.test} and validating the submission ...")
    test_raw = load_split(args.test)
    T = make_features(test_raw)
    test_scores = final.predict_proba(T.reindex(columns=X.columns, fill_value=0.0))[:, 1]
    details(test_raw, T).assign(score=np.round(test_scores, 6)).to_parquet(OUT / "test_scores.parquet", index=False)
    check = write_and_check_submission(T, test_scores, args.test)

    g = results["grouped"][MODEL_NAME]
    r = results["random"][MODEL_NAME]
    evaluation = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "final_model": MODEL_NAME,
        "train": {"rows": int(len(F)), "suspicious": int(y.sum()), "features": list(X.columns)},
        "test": {"rows": int(len(T)), "folder": str(args.test)},
        "fold_method": {
            "random": "StratifiedKFold(5, shuffle=True, random_state=0): rows assigned at random, keeping 3.1% suspicious in each fold.",
            "grouped": "StratifiedGroupKFold(5, shuffle=True, random_state=0): group = scenario_id when present, else the sender account. "
                       "No scenario is split across folds.",
            "out_of_fold": "Every score is predicted by a model that never saw that row; AP is computed on the pooled out-of-fold scores.",
            "feature_note": "Features are computed from all transactions in the split (counts, timing, flows) without labels. "
                            "The test split gets the same treatment from its own transactions, so this is not label leakage.",
        },
        "leakage": leakage,
        "results": results,
        "headline": {"random_ap": r["ap"], "grouped_ap": g["ap"], "optimism": round(r["ap"] - g["ap"], 2)},
        "feature_importance": importance,
        "submission": {k: check[k] for k in ["rows", "all_passed", "size_kb"]},
    }
    (OUT / "evaluation.json").write_text(json.dumps(evaluation, indent=2))

    print("\n================= TRANSACTION MODEL SUMMARY =================")
    print(f"final model         : LightGBM")
    print(f"AP random folds     : {r['ap']:.1f}   (original method, optimistic)")
    print(f"AP grouped folds    : {g['ap']:.1f}   (honest: unseen scenarios)  <- expect the site score near this")
    print(f"accuracy @0.5       : {g['accuracy_at_0_5']:.3f}   precision {g['precision_at_0_5']:.3f}   recall {g['recall_at_0_5']:.3f}")
    print(f"top 1% (site view)  : precision {g['top1_precision']:.3f}   recall {g['top1_recall']:.3f}")
    print(f"by difficulty, top1%: {g['top1_recall_by_difficulty']}")
    print("submission checks   :")
    for c in check["checks"]:
        print(f"   {'PASS' if c['passed'] else 'FAIL'}  {c['check']}")
    print(f"=> {'READY TO UPLOAD' if check['all_passed'] else 'NOT READY'}: {check['file']}")
    print("=============================================================")


if __name__ == "__main__":
    main()
