"""Decode & Detect: train, verify and submit the per-transaction LightGBM model (v2).

What changed from v1 (backup: competition_v1_backup.py, tx_features_v1_backup.py)
  * Own loader with checked joins of all five files (tx_data.py), no dependency on payments.py.
  * ~130 features (tx_features.py): one-off wallet pairs, 10m-72h activity windows, money chains,
    cycles, wallet profiles, clusters of one-off payments with similar amounts.
  * Optional second stage: each payment also sees the out-of-fold scores of nearby payments that
    share a wallet (suspicious payments come in groups). Computed nested, so it cannot leak.

Validation
  grouped - StratifiedGroupKFold(5): group = scenario_id, else sender wallet. Honest; used to choose.
  random  - StratifiedKFold(5): shown for comparison only (leaks scenarios across folds).

Outputs (outputs/competition/): evaluation.json, train_scores.parquet, test_scores.parquet,
submission.csv (exactly TRANSACTION_HASH,score), submission_check.json, run_log.txt

Run:  python src/competition.py
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, average_precision_score, f1_score, precision_recall_curve,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

from tx_data import LABEL_META, load_split
from tx_features import build_features, feature_columns, neighbour_score_features

ROOT = Path(__file__).resolve().parents[1]
TRAIN_DIR = ROOT / "decode-and-detect-training-data" / "train"
TEST_DIR = ROOT / "decode-and-detect-test-data"
OUT = ROOT / "outputs" / "competition"
SEED, K = 0, 5
MAX_BYTES, MAX_ROWS = 12 * 1024 * 1024, 100_000
MODEL_NAME = "lightgbm"

CONFIGS = {
    "lightgbm_a": dict(n_estimators=800, learning_rate=0.03, num_leaves=31, min_child_samples=20,
                       subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=1.0),
    "lightgbm_b": dict(n_estimators=1500, learning_rate=0.02, num_leaves=15, min_child_samples=40,
                       subsample=0.8, subsample_freq=1, colsample_bytree=0.5, reg_lambda=5.0),
}


def make_model(config):
    return lgb.LGBMClassifier(**CONFIGS[config], random_state=SEED, n_jobs=-1, verbose=-1)


# ------------------------------------------------------------------ pipeline
class Pipeline:
    """LightGBM, optionally with a second stage on neighbour scores (nested out-of-fold)."""

    def __init__(self, config, two_stage):
        self.config, self.two_stage = config, two_stage

    def fit(self, F, cols, y, groups):
        self.cols = cols
        self.stage1 = make_model(self.config).fit(F[cols], y)
        if self.two_stage:
            oof = np.zeros(len(y))
            inner = StratifiedGroupKFold(K, shuffle=True, random_state=SEED + 1)
            for tr, va in inner.split(F, y, groups):
                oof[va] = make_model(self.config).fit(F[cols].iloc[tr], y[tr]).predict_proba(F[cols].iloc[va])[:, 1]
            self.train_oof = oof
            X2 = pd.concat([F[cols], neighbour_score_features(F, oof)], axis=1)
            self.cols2 = list(X2.columns)
            self.stage2 = make_model(self.config).fit(X2, y)
        return self

    def predict(self, F, train_rows=None, train_scores=None):
        s1 = self.stage1.predict_proba(F[self.cols])[:, 1]
        if not self.two_stage:
            return s1
        if train_rows is not None:          # cross-validation: training rows keep their out-of-fold scores
            s1 = s1.copy()
            s1[train_rows] = train_scores
        X2 = pd.concat([F[self.cols], neighbour_score_features(F, s1)], axis=1)[self.cols2]
        return self.stage2.predict_proba(X2)[:, 1]


def cross_validate(config, two_stage, F, cols, y, groups, folds):
    oof, fold_ap, t0 = np.zeros(len(y)), [], time.time()
    for tr, va in folds:
        pipe = Pipeline(config, two_stage).fit(F.iloc[tr], cols, y[tr], groups[tr])
        if two_stage:
            oof[va] = pipe.predict(F, train_rows=tr, train_scores=pipe.train_oof)[va]
        else:
            oof[va] = pipe.predict(F.iloc[va])
        fold_ap.append(round(100 * average_precision_score(y[va], oof[va]), 2))
    return oof, fold_ap, round(time.time() - t0, 1)


# ------------------------------------------------------------------ metrics, folds, leakage
def summarise(y, p, fold_ap, seconds, difficulty, threshold=None):
    prec, rec, thr = precision_recall_curve(y, p)
    f1s = 2 * prec[:-1] * rec[:-1] / np.maximum(prec[:-1] + rec[:-1], 1e-12)
    threshold = float(thr[np.argmax(f1s)]) if threshold is None else threshold
    pred = p >= threshold
    top = p >= np.quantile(p, 0.99)
    return {
        "ap": round(100 * average_precision_score(y, p), 2),
        "fold_ap": fold_ap, "fold_ap_mean": round(float(np.mean(fold_ap)), 2), "fold_ap_std": round(float(np.std(fold_ap)), 2),
        "roc_auc": round(roc_auc_score(y, p), 4),
        "top1_precision": round(float(y[top].mean()), 4), "top1_recall": round(float(y[top].sum() / y.sum()), 4),
        "threshold": round(threshold, 4),
        "accuracy": round(accuracy_score(y, pred), 4), "precision": round(precision_score(y, pred, zero_division=0), 4),
        "recall": round(recall_score(y, pred), 4), "f1": round(f1_score(y, pred), 4),
        # names kept for the dashboard (these use the max-F1 threshold, not 0.5)
        "accuracy_at_0_5": round(accuracy_score(y, pred), 4), "precision_at_0_5": round(precision_score(y, pred, zero_division=0), 4),
        "recall_at_0_5": round(recall_score(y, pred), 4),
        "top1_recall_by_difficulty": {d: f"{int((top & (difficulty == d)).sum())}/{int((difficulty == d).sum())}"
                                      for d in ["easy", "medium", "hard"]},
        "seconds": seconds,
    }


def leakage_report(folds, y, scenario, sender):
    fold_of = np.empty(len(y), dtype=int)
    for i, (_, va) in enumerate(folds):
        fold_of[va] = i
    d = pd.DataFrame({"fold": fold_of, "y": y, "scenario": scenario})
    sus = d[(d.y == 1) & d.scenario.notna()]
    per = sus.groupby("scenario").fold.nunique()
    split = per[per > 1].index
    overlap = [float(np.isin(sender[va], list(set(sender[tr]))).mean()) for tr, va in folds]
    return {
        "fold_sizes": [int(len(va)) for _, va in folds], "fold_suspicious": [int(y[va].sum()) for _, va in folds],
        "suspicious_scenarios": int(len(per)), "scenarios_split_across_folds": int(len(split)),
        "suspicious_rows_whose_scenario_is_also_in_training": int(sus.scenario.isin(split).sum()),
        "suspicious_rows": int(len(sus)),
        "share_of_check_rows_whose_sender_is_in_training": round(float(np.mean(overlap)), 4),
    }


# ------------------------------------------------------------------ outputs
def details(p, F):
    d = p.set_index("TRANSACTION_HASH").loc[F.TRANSACTION_HASH]
    return pd.DataFrame({
        "TRANSACTION_HASH": F.TRANSACTION_HASH.to_numpy(),
        "time": pd.to_datetime(d.ts.to_numpy(), unit="s", utc=True),
        "from": d.sender.to_numpy(), "to": d.receiver.to_numpy(),
        "usd": d.usd.round(2).to_numpy(), "legs": d.n_legs.astype(int).to_numpy(),
        "conversion": d.is_conversion.astype(bool).to_numpy(),
    })


def write_and_check_submission(hashes, scores, test_dir):
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


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", type=Path, default=TEST_DIR)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    print("1/6 loading + joining the training files, building features ...", flush=True)
    p = load_split(TRAIN_DIR)
    F = build_features(p)
    meta = p.set_index("TRANSACTION_HASH").loc[F.TRANSACTION_HASH]
    y = meta.is_suspicious.astype(int).to_numpy()
    difficulty, scenario, sender = meta.difficulty.to_numpy(), meta.scenario_id.to_numpy(), meta.sender.to_numpy()
    groups = np.where(meta.scenario_id.notna(), "scenario:" + meta.scenario_id.astype(str), "sender:" + sender)
    cols = [c for c in feature_columns(F) if F[c].nunique() > 1]
    assert not set(cols) & set(LABEL_META + ["is_suspicious"]), "label information leaked into features"
    print(f"    {len(F):,} transactions, {int(y.sum()):,} suspicious, {len(cols)} features", flush=True)

    print("2/6 folds and leakage check ...", flush=True)
    folds = {"grouped": list(StratifiedGroupKFold(K, shuffle=True, random_state=SEED).split(F, y, groups)),
             "random": list(StratifiedKFold(K, shuffle=True, random_state=SEED).split(F, y))}
    leakage = {s: leakage_report(f, y, scenario, sender) for s, f in folds.items()}
    for s, r in leakage.items():
        print(f"    {s:8s}: {r['scenarios_split_across_folds']}/{r['suspicious_scenarios']} scenarios split across folds", flush=True)

    print("3/6 LightGBM configurations on grouped folds ...", flush=True)
    candidates = {}
    for config in CONFIGS:
        oof, fap, sec = cross_validate(config, False, F, cols, y, groups, folds["grouped"])
        candidates[(config, False)] = (oof, fap, sec)
        print(f"    {config} single-stage   AP {100 * average_precision_score(y, oof):5.1f}  [{sec}s]", flush=True)
    best_cfg = max(CONFIGS, key=lambda c: average_precision_score(y, candidates[(c, False)][0]))

    print(f"4/6 two-stage ({best_cfg} + neighbour scores, nested) on grouped folds ...", flush=True)
    oof, fap, sec = cross_validate(best_cfg, True, F, cols, y, groups, folds["grouped"])
    candidates[(best_cfg, True)] = (oof, fap, sec)
    print(f"    {best_cfg} two-stage      AP {100 * average_precision_score(y, oof):5.1f}  [{sec}s]", flush=True)

    chosen = max(candidates, key=lambda k: average_precision_score(y, candidates[k][0]))
    config, two_stage = chosen
    g_oof, g_fap, g_sec = candidates[chosen]
    g = summarise(y, g_oof, g_fap, g_sec, difficulty)
    print(f"    chosen: {config} {'two-stage' if two_stage else 'single-stage'}", flush=True)

    print("5/6 random folds for comparison (leaky) ...", flush=True)
    r_oof, r_fap, r_sec = cross_validate(config, two_stage, F, cols, y, groups, folds["random"])
    r = summarise(y, r_oof, r_fap, r_sec, difficulty, g["threshold"])

    print("6/6 final fit on all labelled transactions, scoring the test data ...", flush=True)
    final = Pipeline(config, two_stage).fit(F, cols, y, groups)
    importance = sorted(zip(cols, final.stage1.booster_.feature_importance("gain")), key=lambda t: -t[1])
    details(p, F).assign(score=np.round(g_oof, 6), label=y, family=meta.family.to_numpy(), difficulty=difficulty) \
        .to_parquet(OUT / "train_scores.parquet", index=False)

    pt = load_split(args.test)
    T = build_features(pt)
    missing = [c for c in cols if c not in T.columns]
    if missing:
        raise SystemExit(f"test features differ from training: {missing}")
    test_scores = np.clip(final.predict(T), 0, 1)
    details(pt, T).assign(score=np.round(test_scores, 6)).to_parquet(OUT / "test_scores.parquet", index=False)
    check = write_and_check_submission(T.TRANSACTION_HASH.to_numpy(), test_scores, args.test)

    label = f"{config}{' + two-stage' if two_stage else ''}"
    all_results = {f"{c}{' + two-stage' if ts else ''}": round(100 * average_precision_score(y, v[0]), 2)
                   for (c, ts), v in candidates.items()}
    evaluation = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "final_model": MODEL_NAME, "final_pipeline": label, "candidates_grouped_ap": all_results,
        "train": {"rows": int(len(F)), "suspicious": int(y.sum()), "features": cols},
        "test": {"rows": int(len(T)), "folder": str(args.test)},
        "fold_method": {
            "random": "StratifiedKFold(5, shuffle=True, random_state=0): rows assigned at random, keeping 3.1% suspicious in each fold.",
            "grouped": "StratifiedGroupKFold(5, shuffle=True, random_state=0): group = scenario_id when present, else the sender account. "
                       "No scenario is split across folds.",
            "out_of_fold": "Every score is predicted by a model that never saw that row; AP is computed on the pooled out-of-fold scores. "
                           "Two-stage neighbour scores are themselves out-of-fold (nested), so they cannot carry a row's own label.",
            "feature_note": "Features are computed from all transactions in the split (counts, timing, flows) without labels. "
                            "The test split gets the same treatment from its own transactions.",
        },
        "leakage": leakage,
        "results": {"grouped": {MODEL_NAME: g}, "random": {MODEL_NAME: r}},
        "headline": {"random_ap": r["ap"], "grouped_ap": g["ap"], "optimism": round(r["ap"] - g["ap"], 2)},
        "feature_importance": [{"feature": c, "gain": round(float(v), 1)} for c, v in importance],
        "submission": {k: check[k] for k in ["rows", "all_passed", "size_kb"]},
    }
    (OUT / "evaluation.json").write_text(json.dumps(evaluation, indent=2))

    print("\n================= TRANSACTION MODEL SUMMARY =================")
    print(f"pipeline            : LightGBM ({label}), {len(cols)} features")
    print(f"all candidates (AP) : {all_results}")
    print(f"AP grouped folds    : {g['ap']:.1f}   (honest; v1 was 39.9 here and scored 44.7 on the site)")
    print(f"AP random folds     : {r['ap']:.1f}   (leaky, comparison only)")
    print(f"ROC-AUC             : {g['roc_auc']:.3f}")
    print(f"top 1% (site view)  : precision {g['top1_precision']:.3f}   recall {g['top1_recall']:.3f}")
    print(f"@ threshold {g['threshold']:.3f}   : accuracy {g['accuracy']:.3f}  precision {g['precision']:.3f}  "
          f"recall {g['recall']:.3f}  F1 {g['f1']:.3f}")
    print(f"by difficulty, top1%: {g['top1_recall_by_difficulty']}")
    print("submission checks   :")
    for c in check["checks"]:
        print(f"   {'PASS' if c['passed'] else 'FAIL'}  {c['check']}")
    print(f"=> {'READY TO UPLOAD' if check['all_passed'] else 'NOT READY'}: {check['file']}  ({(time.time() - t_start) / 60:.1f} min)")
    print("=============================================================")


if __name__ == "__main__":
    main()
