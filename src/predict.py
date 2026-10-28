"""Score every account that is NOT in labels.csv and write outputs/predictions.csv.

Pass --all to score every account instead.
"""
import sys

import joblib
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from load_data import MODELS, OUTPUTS, PROCESSED, RAW


def main():
    bundle = joblib.load(MODELS / "model.joblib")
    model, cols = bundle["model"], bundle["features"]
    feats = pd.read_parquet(PROCESSED / "features.parquet")

    labels_path = RAW / "labels.csv"
    if "--all" not in sys.argv and labels_path.exists():
        known = set(pd.read_csv(labels_path)["account"])
        feats = feats[~feats["account"].isin(known)]

    X = feats.reindex(columns=cols, fill_value=0.0)
    preds = pd.DataFrame({"account": feats["account"].values,
                          "suspicious_score": model.predict_proba(X)[:, 1].round(6)})
    preds = preds.sort_values("suspicious_score", ascending=False)

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    preds.to_csv(OUTPUTS / "predictions.csv", index=False)
    print(f"scored {len(preds):,} accounts -> {OUTPUTS / 'predictions.csv'}")
    print(preds.head(10).to_string(index=False))

    # Accounts held back by import_official.py (never used in training).
    hidden = PROCESSED / "hidden_test_labels.csv"
    if hidden.exists():
        truth = preds.merge(pd.read_csv(hidden), on="account")
        if truth["is_suspicious"].nunique() == 2:
            print(f"\n[hidden test accounts] ROC-AUC: {roc_auc_score(truth.is_suspicious, truth.suspicious_score):.3f}"
                  f"   PR-AUC: {average_precision_score(truth.is_suspicious, truth.suspicious_score):.3f}")


if __name__ == "__main__":
    main()
