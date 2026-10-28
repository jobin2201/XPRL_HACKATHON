"""Pick a model, see its honest validation numbers, and get a submission for it.

  python src/run_model.py --model xgboost
  python src/run_model.py --model lightgbm
  python src/run_model.py --model catboost
  python src/run_model.py --model ensemble              (average of all three)
  python src/run_model.py --model xgboost --two-stage   (adds neighbour scores; slower, usually +1-2 AP)

What it does
  1. Loads the cached features (built once by compare_quick.py / this script; ~1 min the first time).
  2. 5-fold GROUPED validation (a planted scenario never sits in both training and checking), prints:
     Average Precision (the site score), top-1% precision/recall (the site's precision/recall),
     ROC-AUC, and accuracy/precision/recall/F1 at the best-F1 threshold.
  3. Trains on all labelled transactions, scores the 40,101 test transactions,
     writes outputs/models/<name>/submission.csv and checks it.
Nothing else is overwritten: outputs/competition/submission.csv stays as it is.

  --dashboard   also writes what the dashboard's Transaction Scoring tab reads (in the same run folder):
                train_scores.parquet (out-of-fold score per training payment), evaluation.json
                (folds, leakage, random-vs-grouped results, feature importance), submission_check.json,
                test_explanations.parquet (top features behind each test score, LightGBM SHAP contributions)
                and isolation_forest.json (unsupervised baseline on the same features).
                Adds a random-fold run for the leakage comparison (about +1 min for single-stage).
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, average_precision_score, f1_score, precision_recall_curve,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

from compare_quick import load_features
from competition import TRAIN_DIR, details, leakage_report
from competition_max import MODELS, Pipeline
from tx_data import LABEL_META, load_split
from tx_extra import GROUPS, extra_features
from tx_features import build_features, feature_columns

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "decode-and-detect-test-data"
CACHE = ROOT / "outputs" / "compare"
SEED, K = 0, 5


def test_features():
    cache = CACHE / "test_features_v2.parquet"
    if cache.exists():
        return pd.read_parquet(cache), pd.read_parquet(CACHE / "test_payments_v2.parquet")
    pt = load_split(TEST_DIR)
    T = build_features(pt)
    T.to_parquet(cache, index=False)
    pt.to_parquet(CACHE / "test_payments_v2.parquet", index=False)
    return T, pt


def top_k_mask(p, share=0.01):
    """Exactly ceil(1%) highest scores (ties broken by position), unlike p >= quantile which can select more."""
    k = max(1, int(np.ceil(share * len(p))))
    mask = np.zeros(len(p), dtype=bool)
    mask[np.argsort(-p, kind="stable")[:k]] = True
    return mask


def with_extras(F, split, groups):
    """Add optional feature groups (cached per split and group)."""
    parts = [F]
    for g in groups:
        cache = CACHE / f"{split}_extra_{g}_v2.parquet"
        if cache.exists():
            E = pd.read_parquet(cache)
        else:
            E = extra_features(F, [g])
            E.to_parquet(cache, index=False)
        parts.append(E.set_axis(F.index))
    return pd.concat(parts, axis=1)


def report(y, p, difficulty):
    prec, rec, thr = precision_recall_curve(y, p)
    f1s = 2 * prec[:-1] * rec[:-1] / np.maximum(prec[:-1] + rec[:-1], 1e-12)
    t = float(thr[np.argmax(f1s)])
    top = top_k_mask(p)
    return {
        "site_score_ap": round(100 * average_precision_score(y, p), 1),
        "top1_precision": round(float(y[top].mean()), 3),
        "top1_recall": round(float(y[top].sum() / y.sum()), 3),
        "roc_auc": round(roc_auc_score(y, p), 3),
        "threshold": round(t, 3),
        "accuracy": round(accuracy_score(y, p >= t), 4),
        "precision": round(precision_score(y, p >= t), 3),
        "recall": round(recall_score(y, p >= t), 3),
        "f1": round(f1_score(y, p >= t), 3),
        "caught_in_top1": {d: f"{int((top & (difficulty == d)).sum())}/{int((difficulty == d).sum())}" for d in ["easy", "medium", "hard"]},
    }


def cv_summary(y, p, fold_ap, difficulty, seconds, threshold):
    """One validation result in the format the dashboard reads (top 1% = exact top-k)."""
    top = top_k_mask(p)
    pred = p >= threshold
    return {
        "ap": round(100 * average_precision_score(y, p), 2), "fold_ap": fold_ap,
        "fold_ap_mean": round(float(np.mean(fold_ap)), 2), "fold_ap_std": round(float(np.std(fold_ap)), 2),
        "roc_auc": round(roc_auc_score(y, p), 4),
        "top1_precision": round(float(y[top].mean()), 4), "top1_recall": round(float(y[top].sum() / y.sum()), 4),
        "threshold": round(threshold, 4),
        # the dashboard's column names; values use the best-F1 threshold chosen on grouped folds
        "accuracy_at_0_5": round(accuracy_score(y, pred), 4),
        "precision_at_0_5": round(precision_score(y, pred, zero_division=0), 4),
        "recall_at_0_5": round(recall_score(y, pred), 4),
        "top1_recall_by_difficulty": {d: f"{int((top & (difficulty == d)).sum())}/{int((difficulty == d).sum())}"
                                      for d in ["easy", "medium", "hard"]},
        "seconds": seconds,
    }


def write_dashboard_files(out, name, args, F, cols, y, groups, diff, folds, oof, fold_ap, final, T, csv_path, m, t0):
    from datetime import datetime, timezone
    members = list(MODELS) if args.model == "ensemble" else [args.model]
    # random folds, only to show how optimistic they are (leaky: scenarios split across folds)
    rfolds = list(StratifiedKFold(K, shuffle=True, random_state=SEED).split(F, y))
    r_oof, r_ap, ts = np.zeros(len(y)), [], time.time()
    for tr, va in rfolds:
        pipe = Pipeline(members, args.two_stage).fit(F.iloc[tr], cols, y[tr], groups[tr])
        r_oof[va] = (pipe.predict(F, train_rows=tr, train_scores=pipe.train_oof)[va] if args.two_stage
                     else pipe.predict(F.iloc[va]))
        r_ap.append(round(100 * average_precision_score(y[va], r_oof[va]), 2))
    g = cv_summary(y, oof, fold_ap, diff, round(time.time() - t0, 1), m["threshold"])
    r = cv_summary(y, r_oof, r_ap, diff, round(time.time() - ts, 1), m["threshold"])

    # training scores with readable details (out-of-fold, grouped folds)
    p = load_split(TRAIN_DIR)
    fam = pd.read_csv(TRAIN_DIR / "labels.csv", usecols=["TRANSACTION_HASH", "family"]).set_index("TRANSACTION_HASH").family
    details(p, F).assign(score=np.round(oof, 6), label=y, family=fam.loc[F.TRANSACTION_HASH].to_numpy(),
                         difficulty=diff).to_parquet(out / "train_scores.parquet", index=False)

    meta = p.set_index("TRANSACTION_HASH").loc[F.TRANSACTION_HASH]
    leak = {k: leakage_report(f, y, meta.scenario_id.to_numpy(), meta.sender.to_numpy())
            for k, f in {"grouped": folds, "random": rfolds}.items()}

    first = final.stage1[0]
    gains = first.booster_.feature_importance("gain") if hasattr(first, "booster_") else first.feature_importances_
    importance = [{"feature": c, "gain": round(float(v), 1)} for c, v in sorted(zip(cols, gains), key=lambda t: -t[1])]

    back = pd.read_csv(csv_path, dtype={"TRANSACTION_HASH": str})
    want = pd.read_parquet(TEST_DIR / "transactions.parquet", columns=["TRANSACTION_HASH"]).TRANSACTION_HASH
    checks = [
        ("Header is exactly TRANSACTION_HASH,score", csv_path.read_text().splitlines()[0] == "TRANSACTION_HASH,score"),
        (f"Row count equals test transactions ({len(want):,})", len(back) == len(want)),
        ("Every hash appears exactly once", not back.TRANSACTION_HASH.duplicated().any()),
        ("No test transaction is missing", set(want) <= set(back.TRANSACTION_HASH)),
        ("No extra hashes", set(back.TRANSACTION_HASH) <= set(want)),
        ("No empty scores", not back.score.isna().any()),
        ("Scores are between 0 and 1", bool(back.score.between(0, 1).all())),
        ("File is under 12 MiB", csv_path.stat().st_size <= 12 * 1024 * 1024),
        ("Scores are spread out (more than 1,000 distinct values)", back.score.nunique() > 1000),
    ]
    sub = {"file": str(csv_path), "rows": int(len(back)), "expected_rows": int(len(want)),
           "size_kb": round(csv_path.stat().st_size / 1024, 1), "distinct_scores": int(back.score.nunique()),
           "score_min": float(back.score.min()), "score_max": float(back.score.max()),
           "checks": [{"check": c, "passed": bool(ok)} for c, ok in checks], "all_passed": all(ok for _, ok in checks)}
    (out / "submission_check.json").write_text(json.dumps(sub, indent=2))

    evaluation = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "final_model": args.model, "final_pipeline": name,
        "train": {"rows": int(len(F)), "suspicious": int(y.sum()), "features": cols},
        "test": {"rows": int(len(T)), "folder": str(TEST_DIR)},
        "fold_method": {
            "random": "StratifiedKFold(5, shuffle=True, random_state=0): rows assigned at random (shown for comparison only).",
            "grouped": "StratifiedGroupKFold(5, shuffle=True, random_state=0): group = scenario_id when present, "
                       "else the sender wallet. No scenario is split across folds.",
            "out_of_fold": "Every score comes from a model that never saw that row; AP is computed on the pooled "
                           "out-of-fold scores.",
            "feature_note": "Features are computed from each split's own transactions without labels, identically "
                            "for train and test.",
        },
        "leakage": leak,
        "results": {"grouped": {args.model: g}, "random": {args.model: r}},
        "headline": {"random_ap": r["ap"], "grouped_ap": g["ap"], "optimism": round(r["ap"] - g["ap"], 2)},
        "feature_importance": importance,
        "submission": {k: sub[k] for k in ["rows", "all_passed", "size_kb"]},
    }
    (out / "evaluation.json").write_text(json.dumps(evaluation, indent=2))

    # why each test payment scored as it did: top 5 positive SHAP contributions (stage 1 LightGBM)
    if hasattr(first, "booster_") and not args.two_stage:
        contrib = first.booster_.predict(T[cols], pred_contrib=True)
        vals = T[cols].to_numpy(float)
        top = np.argsort(-contrib[:, :-1], axis=1)[:, :5]
        reasons = [json.dumps([{"feature": cols[j], "value": round(float(vals[i, j]), 4),
                                "contribution": round(float(contrib[i, j]), 4)} for j in top[i] if contrib[i, j] > 0])
                   for i in range(len(T))]
        pd.DataFrame({"TRANSACTION_HASH": T.TRANSACTION_HASH.to_numpy(), "reasons": reasons,
                      "base_value": np.round(contrib[:, -1], 4)}).to_parquet(out / "test_explanations.parquet", index=False)

    # unsupervised baseline on the same features (no labels used to fit)
    from sklearn.ensemble import IsolationForest
    iso = IsolationForest(n_estimators=300, random_state=SEED, n_jobs=-1).fit(F[cols])
    anomaly = -iso.score_samples(F[cols])
    itop = top_k_mask(anomaly)
    (out / "isolation_forest.json").write_text(json.dumps({
        "site_score_ap": round(100 * average_precision_score(y, anomaly), 2),
        "top1_precision": round(float(y[itop].mean()), 4), "top1_recall": round(float(y[itop].sum() / y.sum()), 4),
        "roc_auc": round(roc_auc_score(y, anomaly), 4),
        "caught_in_top1": {d: f"{int((itop & (diff == d)).sum())}/{int((diff == d).sum())}" for d in ["easy", "medium", "hard"]},
        "note": "IsolationForest(n_estimators=300) on the v2 training features, labels not used. Scored on all training rows.",
    }, indent=2))
    print(f"   dashboard files written to {out}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=[*MODELS, "ensemble"], default="xgboost")
    ap.add_argument("--two-stage", action="store_true")
    ap.add_argument("--dashboard", action="store_true",
                    help="also write the files the dashboard's Transaction Scoring tab reads")
    ap.add_argument("--extra", nargs="*", default=[], choices=list(GROUPS),
                    help="optional feature groups: ratios activity patterns")
    args = ap.parse_args()
    members = list(MODELS) if args.model == "ensemble" else [args.model]
    name = args.model + ("_two_stage" if args.two_stage else "") + "".join(f"_{g}" for g in sorted(args.extra))
    out = ROOT / "outputs" / "models" / name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    F = with_extras(load_features(), "train", sorted(args.extra))
    y, groups, diff = F["__y"].to_numpy(), F["__group"].to_numpy(), F["__difficulty"].to_numpy()
    cols = [c for c in feature_columns(F) if not c.startswith("__") and F[c].nunique() > 1]
    assert not set(cols) & set(LABEL_META + ["is_suspicious"])
    folds = list(StratifiedGroupKFold(K, shuffle=True, random_state=SEED).split(F, y, groups))
    print(f"model: {name} · {len(F):,} training transactions · {len(cols)} features", flush=True)

    oof, fold_prec, fold_ap = np.zeros(len(y)), [], []
    for i, (tr, va) in enumerate(folds, 1):
        pipe = Pipeline(members, args.two_stage).fit(F.iloc[tr], cols, y[tr], groups[tr])
        oof[va] = (pipe.predict(F, train_rows=tr, train_scores=pipe.train_oof)[va] if args.two_stage
                   else pipe.predict(F.iloc[va]))
        fold_prec.append(round(float(y[va][top_k_mask(oof[va])].mean()), 3))
        fold_ap.append(round(100 * average_precision_score(y[va], oof[va]), 1))
        print(f"   fold {i}/5: AP {fold_ap[-1]:5.1f}  top-1% precision {fold_prec[-1]:.3f}", flush=True)
    m = report(y, oof, diff)
    m["top1_precision_per_fold"] = fold_prec
    m["ap_per_fold"] = fold_ap
    m["extra_groups"] = sorted(args.extra)

    print("training on all data and scoring the test set ...", flush=True)
    final = Pipeline(members, args.two_stage).fit(F, cols, y, groups)
    T, pt = test_features()
    T = with_extras(T, "test", sorted(args.extra))
    scores = np.clip(final.predict(T), 0, 1)
    sub = pd.DataFrame({"TRANSACTION_HASH": T.TRANSACTION_HASH.to_numpy(), "score": np.round(scores, 8)})
    path = out / "submission.csv"
    sub.to_csv(path, index=False, lineterminator="\n")
    details(pt, T).assign(score=np.round(scores, 6)).to_parquet(out / "test_scores.parquet", index=False)

    back = pd.read_csv(path, dtype={"TRANSACTION_HASH": str})
    want = set(pd.read_parquet(TEST_DIR / "transactions.parquet", columns=["TRANSACTION_HASH"]).TRANSACTION_HASH)
    ok = (path.read_text().splitlines()[0] == "TRANSACTION_HASH,score" and len(back) == len(want) == 40_101
          and set(back.TRANSACTION_HASH) == want and not back.TRANSACTION_HASH.duplicated().any()
          and back.score.between(0, 1).all())
    m["submission"] = {"file": str(path), "rows": int(len(back)), "all_checks_passed": bool(ok)}
    (out / "validation.json").write_text(json.dumps(m, indent=2))
    if args.dashboard:
        print("writing dashboard files (random-fold comparison, leakage, training scores) ...", flush=True)
        write_dashboard_files(out, name, args, F, cols, y, groups, diff, folds, oof, fold_ap, final, T, path, m, t0)

    print(f"\n================ {name.upper()} ================")
    print(f"Site score (100 x AP)     : {m['site_score_ap']}   per fold {fold_ap}")
    print(f"Top-1% precision / recall : {m['top1_precision']:.1%} / {m['top1_recall']:.1%}   (what the site shows)")
    print(f"   per fold precision     : {fold_prec}")
    print(f"Caught in top 1%          : {m['caught_in_top1']}")
    print(f"ROC-AUC                   : {m['roc_auc']}")
    print(f"At best-F1 threshold {m['threshold']}: accuracy {m['accuracy']:.2%}  precision {m['precision']:.1%}  "
          f"recall {m['recall']:.1%}  F1 {m['f1']:.3f}")
    print(f"Submission                : {path}  ({'ALL CHECKS PASSED' if ok else 'CHECK FAILED'})")
    print(f"Time                      : {(time.time() - t0) / 60:.1f} min")
    print("(validation numbers are measured on labelled training data; the site measures the test set)")


if __name__ == "__main__":
    main()
