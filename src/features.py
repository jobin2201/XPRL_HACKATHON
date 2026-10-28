"""Turn raw transactions into one row of behavioural features per account.

Output: data/processed/features.parquet
"""
import numpy as np
import pandas as pd

from load_data import PROCESSED, load_all

STRUCTURING_LOW, STRUCTURING_HIGH = 9000, 10000  # USD band just under a reporting threshold
NIGHT_HOURS = range(0, 5)


def add_usd(tx: pd.DataFrame, rates: pd.DataFrame | None) -> pd.DataFrame:
    tx = tx.copy()
    if "amount_usd" in tx and tx["amount_usd"].notna().all():  # already priced (official data: hourly rates)
        return tx
    if rates is None:
        tx["amount_usd"] = tx["amount"]
        return tx
    r = rates.copy()
    r["date"] = pd.to_datetime(r["date"]).dt.date
    tx["date"] = tx["timestamp"].dt.date
    tx = tx.merge(r, on=["date", "currency"], how="left")
    # fall back to the currency's average rate for days missing from the table;
    # currencies with no rate at all (e.g. unvetted Mainnet tokens) are left unpriced at 0 USD
    avg = rates.groupby("currency")["usd_rate"].mean()
    tx["usd_rate"] = tx["usd_rate"].fillna(tx["currency"].map(avg)).fillna(0.0)
    tx["amount_usd"] = tx["amount"] * tx["usd_rate"]
    return tx.drop(columns=["date"])


def sender_features(tx: pd.DataFrame) -> pd.DataFrame:
    tx = tx.copy()
    tx["is_payment"] = tx["tx_type"] == "Payment"
    tx["failed"] = tx["result"] != "tesSUCCESS"
    tx["night"] = tx["timestamp"].dt.hour.isin(NIGHT_HOURS)
    tx["near_threshold"] = tx["amount_usd"].between(STRUCTURING_LOW, STRUCTURING_HIGH, inclusive="left")
    tx["has_tag"] = tx["destination_tag"].notna()
    tx["day"] = tx["timestamp"].dt.floor("D")
    tx["hour"] = tx["timestamp"].dt.floor("h")

    g = tx.groupby("account")
    f = pd.DataFrame({
        "n_sent": g.size(),
        "n_payments_sent": g["is_payment"].sum(),
        "n_tx_types": g["tx_type"].nunique(),
        "usd_sent_total": g["amount_usd"].sum(),
        "usd_sent_mean": g["amount_usd"].mean(),
        "usd_sent_max": g["amount_usd"].max(),
        "usd_sent_std": g["amount_usd"].std(),
        "n_unique_dest": g["destination"].nunique(),
        "frac_failed": g["failed"].mean(),
        "frac_night": g["night"].mean(),
        "frac_near_threshold": g["near_threshold"].mean(),
        "frac_dest_tag": g["has_tag"].mean(),
        "fee_mean": g["fee"].mean(),
        "fee_max": g["fee"].max(),
        "active_days": g["day"].nunique(),
        "max_tx_per_hour": tx.groupby(["account", "hour"]).size().groupby("account").max(),
    })
    gaps = tx.sort_values("timestamp").groupby("account")["timestamp"].diff().dt.total_seconds()
    f["median_gap_sec"] = gaps.groupby(tx["account"]).median()
    f["tx_per_active_day"] = f["n_sent"] / f["active_days"]
    f["dest_per_payment"] = f["n_unique_dest"] / f["n_payments_sent"].replace(0, np.nan)
    return f


def receiver_features(tx: pd.DataFrame) -> pd.DataFrame:
    pay = tx[(tx["tx_type"] == "Payment") & tx["destination"].notna()]
    g = pay.groupby("destination")
    f = pd.DataFrame({
        "n_received": g.size(),
        "usd_received_total": g["amount_usd"].sum(),
        "n_unique_src": g["account"].nunique(),
    })
    f.index.name = "account"
    return f


def round_trip_features(tx: pd.DataFrame) -> pd.Series:
    """Number of counterparties an account both sends to and receives from."""
    pay = tx[(tx["tx_type"] == "Payment") & tx["destination"].notna()]
    edges = pay[["account", "destination"]].drop_duplicates()
    rev = edges.rename(columns={"account": "destination", "destination": "account"})
    both = edges.merge(rev, on=["account", "destination"])
    return both.groupby("account").size().rename("n_round_trip_partners")


def transfer_features(transfers: pd.DataFrame | None) -> pd.DataFrame | None:
    if transfers is None:
        return None
    hops = transfers.groupby("tx_hash")["hop"].transform("max")
    multi = transfers.assign(multi_hop=hops > 0)
    g = multi.groupby("from_account")
    f = pd.DataFrame({"n_transfer_hops_out": g.size(), "frac_multi_hop_out": g["multi_hop"].mean()})
    f.index.name = "account"
    return f


def build_features(data: dict) -> pd.DataFrame:
    tx = add_usd(data["transactions"], data["market_rates"])
    parts = [sender_features(tx), receiver_features(tx), round_trip_features(tx),
             transfer_features(data["transfers"])]
    feats = pd.concat([p for p in parts if p is not None], axis=1)
    feats.index.name = "account"
    feats = feats.fillna(0.0)
    feats["in_out_usd_ratio"] = feats["usd_received_total"] / (feats["usd_sent_total"] + 1.0)
    # pass-through: share of value both received and sent on (1 = everything forwarded); 0 when one side is empty
    lo = feats[["usd_received_total", "usd_sent_total"]].min(axis=1)
    hi = feats[["usd_received_total", "usd_sent_total"]].max(axis=1)
    feats["pass_through_ratio"] = (lo / hi.replace(0, np.nan)).fillna(0.0)
    return feats.reset_index()


def main():
    feats = build_features(load_all())
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out = PROCESSED / "features.parquet"
    feats.to_parquet(out, index=False)
    print(f"{len(feats):,} accounts x {feats.shape[1] - 1} features -> {out}")


if __name__ == "__main__":
    main()
