"""Open the dataset files. Missing optional files are returned as None.

Datasets live side by side so real data never overwrites the synthetic test set:
    official data/raw/official/   -> data/processed/official/  (default: the Decode & Detect training split)
    sample   data/raw/            -> data/processed/          (old synthetic sample, not used any more)
    mainnet  data/raw/mainnet/    -> data/processed/mainnet/
Choose one with the XRPL_DATASET environment variable, e.g.  $env:XRPL_DATASET = "mainnet"
Build the official dataset first with:  python src/import_official.py
"""
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw"
PROCESSED_ROOT = ROOT / "data" / "processed"
MODELS = ROOT / "models"  # the supervised model is trained on the labelled official split


def dataset_dirs(name: str | None = None) -> tuple[str, Path, Path]:
    name = (name or os.environ.get("XRPL_DATASET") or "official").strip().lower()
    if name == "sample":
        return name, RAW_ROOT, PROCESSED_ROOT
    return name, RAW_ROOT / name, PROCESSED_ROOT / name


DATASET, RAW, PROCESSED = dataset_dirs()
OUTPUTS = ROOT / "outputs" if DATASET == "sample" else ROOT / "outputs" / DATASET

FILES = {
    "transactions": "transactions.parquet",
    "transfers": "transfers.parquet",
    "blocks": "blocks.parquet",
    "market_rates": "market_rates.csv",
    "labels": "labels.csv",
}


def _read(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def load_all(raw_dir: Path = RAW) -> dict:
    data = {}
    for name, fname in FILES.items():
        path = raw_dir / fname
        data[name] = _read(path) if path.exists() else None
    if data["transactions"] is None:
        raise FileNotFoundError(f"{raw_dir / FILES['transactions']} is required. Run src/make_sample_data.py "
                                "or copy the official files into data/raw.")
    tx = data["transactions"]
    tx["timestamp"] = pd.to_datetime(tx["timestamp"], utc=True)
    return data


def summary(data: dict) -> None:
    for name, df in data.items():
        if df is None:
            print(f"\n== {name}: (missing)")
            continue
        print(f"\n== {name}: {len(df):,} rows x {df.shape[1]} cols")
        print(df.dtypes.to_string())
        print(df.head(3).to_string())


if __name__ == "__main__":
    summary(load_all())
