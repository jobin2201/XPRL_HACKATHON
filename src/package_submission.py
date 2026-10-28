"""Build an upload folder (source_code.zip + predictions.csv) for any run in outputs/models/.

  python src/package_submission.py --run xgboost --name xgboost --command "python run_model.py --model xgboost"

Writes submissions/<name>/predictions.csv (copied from outputs/models/<run>/submission.csv, then checked
against the test data) and submissions/<name>/source_code.zip (code + README with the command + licence).
Nothing else is changed.
"""
import argparse
import json
import shutil
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "decode-and-detect-test-data"
SOURCES = ["run_model.py", "competition_max.py", "competition.py", "compare_quick.py", "tx_data.py",
           "tx_features.py", "tx_extra.py", "tx_patterns.py"]
REQUIREMENTS = ("# Python 3.11.17\npandas==3.1.0\npyarrow==26.0.0\nnumpy==2.4.6\nscikit-learn==1.9.1\n"
                "lightgbm==4.6.0\nxgboost==3.0.2\ncatboost==1.2.8\njoblib==1.6.0\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="folder name in outputs/models/")
    ap.add_argument("--name", required=True, help="folder name to create in submissions/")
    ap.add_argument("--command", required=True, help="exact command, run from src/, that produced the CSV")
    args = ap.parse_args()

    run = ROOT / "outputs" / "models" / args.run
    out = ROOT / "submissions" / args.name
    out.mkdir(parents=True, exist_ok=True)
    m = json.loads((run / "validation.json").read_text())

    csv = out / "predictions.csv"
    shutil.copy(run / "submission.csv", csv)
    back = pd.read_csv(csv, dtype={"TRANSACTION_HASH": str})
    want = set(pd.read_parquet(TEST_DIR / "transactions.parquet", columns=["TRANSACTION_HASH"]).TRANSACTION_HASH)
    ok = (csv.read_text().splitlines()[0] == "TRANSACTION_HASH,score" and len(back) == len(want) == 40_101
          and set(back.TRANSACTION_HASH) == want and not back.TRANSACTION_HASH.duplicated().any()
          and bool(back.score.between(0, 1).all()))

    readme = f"""# Decode & Detect - Code Gladiators ({args.name})

## Exact command that produced the predictions CSV
```
python -m pip install -r requirements.txt
cd src
{args.command}
```
Output: `outputs/models/{args.run}/submission.csv` (`TRANSACTION_HASH,score`, 40,101 rows).

Data layout expected next to `src/` (not included): `decode-and-detect-training-data/train/` (5 files incl.
labels.csv) and `decode-and-detect-test-data/` (4 files). Laptop CPU, no GPU, a few minutes. Python 3.11.17.

All features use only each split's own transactions, never labels, built identically for train and test.
Label metadata (family, difficulty, scenario_id, cohort_id) is never a model input.

## Validation (labelled training data, grouped 5-fold; not the test set)
| Measure | Value |
|---|---|
| 100 x Average Precision | {m.get('site_score_ap')} |
| Top-1% precision / recall | {m.get('top1_precision', 0):.1%} / {m.get('top1_recall', 0):.1%} |
| ROC-AUC | {m.get('roc_auc')} |
"""
    zpath = out / "source_code.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, allowZip64=False) as z:
        z.writestr("README.md", readme)
        z.writestr("requirements.txt", REQUIREMENTS)
        for f in ["LICENSE", "THIRD_PARTY.md"]:
            z.write(ROOT / f, f)
        for f in SOURCES:
            z.write(ROOT / "src" / f, f"src/{f}")
    print(f"{args.name:22s} predictions.csv {len(back):,} rows ({'ALL CHECKS PASSED' if ok else 'CHECK FAILED'}) · "
          f"source_code.zip {zpath.stat().st_size / 1024:.0f} KB · validation AP {m.get('site_score_ap')}")


if __name__ == "__main__":
    main()
