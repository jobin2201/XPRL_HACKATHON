"""Train a suspicious-account classifier on the labelled accounts.

Reads data/processed/features.parquet + data/raw/labels.csv, reports validation
scores, then refits on all labelled data and saves models/model.joblib.
"""
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, average_precision_score, classification_report, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split

from load_data import MODELS, PROCESSED, RAW

LABEL_COL = "is_suspicious"
SEED = 42


def make_model():
    return RandomForestClassifier(n_estimators=400, min_samples_leaf=2, class_weight="balanced",
                                  random_state=SEED, n_jobs=-1)


def main():
    feats = pd.read_parquet(PROCESSED / "features.parquet")
    labels = pd.read_csv(RAW / "labels.csv")
    df = feats.merge(labels[["account", LABEL_COL]], on="account", how="inner")
    feature_cols = [c for c in feats.columns if c != "account"]
    X, y = df[feature_cols], df[LABEL_COL].astype(int)
    print(f"labelled accounts: {len(df)}  suspicious: {int(y.sum())}")

    X_tr, X_va, y_tr, y_va = train_test_split(X, y, test_size=0.25, stratify=y, random_state=SEED)
    model = make_model().fit(X_tr, y_tr)
    p = model.predict_proba(X_va)[:, 1]
    pred = (p >= 0.5).astype(int)
    print("\n================ ACCOUNT MODEL (dashboard) ================")
    print("model     : RandomForestClassifier(n_estimators=400, min_samples_leaf=2, class_weight=balanced)")
    print(f"check set : {len(y_va)} accounts, {int(y_va.sum())} suspicious (25% held back from training)")
    print(f"accuracy  : {accuracy_score(y_va, pred):.3f}")
    print(f"precision : {precision_score(y_va, pred, zero_division=0):.3f}   (of accounts flagged, share truly suspicious)")
    print(f"recall    : {recall_score(y_va, pred, zero_division=0):.3f}   (of suspicious accounts, share caught)")
    print(f"F1        : {f1_score(y_va, pred, zero_division=0):.3f}")
    print(f"ROC-AUC   : {roc_auc_score(y_va, p):.3f}   PR-AUC: {average_precision_score(y_va, p):.3f}")
    print("===========================================================\n")
    print(classification_report(y_va, pred, digits=3, zero_division=0))

    model = make_model().fit(X, y)  # refit on every labelled account
    imp = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print("top features:\n" + imp.head(10).round(3).to_string())

    MODELS.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": feature_cols}, MODELS / "model.joblib")
    print(f"saved -> {MODELS / 'model.joblib'}")


if __name__ == "__main__":
    main()
