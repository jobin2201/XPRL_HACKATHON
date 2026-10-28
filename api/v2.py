"""Dashboard API for the LightGBM v2 model (run_model.py --model lightgbm --extra ratios activity patterns --dashboard).

Endpoints (all under /api/v2):
  GET  /summary              validation metrics, test score distribution, activity over time, top suspicious payments
  GET  /transactions         ranked test payments with filters
  GET  /transactions/{hash}  one payment with its joined rows: transaction, transfer legs, block, market rate,
                             wallet context, score, and the reasons behind the score
  GET  /graph                wallet-to-wallet payment graph around a payment or a wallet
  GET  /models               every model we trained, side by side (v1, v2, v3, XGBoost, CatBoost, Isolation Forest...)
  GET  /datasets             what is in the training and test data (counts, labels, days, currencies, legs, amounts)
  POST /explain/{hash}       plain-English explanation (Groq LLM when GROQ_API_KEY is set in .env, built-in otherwise)

Reads only files on disk: outputs/models/<run>/, outputs/compare/test_payments_v2.parquet and the test data folder.
"""
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

ROOT = Path(__file__).resolve().parents[1]
RUN = os.environ.get("TXMODEL_RUN", "lightgbm_activity_patterns_ratios")
RUN_DIR = ROOT / "outputs" / "models" / RUN
MODELS_DIR = ROOT / "outputs" / "models"
TEST_DIR = ROOT / "decode-and-detect-test-data"
PAYMENTS = ROOT / "outputs" / "compare" / "test_payments_v2.parquet"
RUN_CMD = "python src/run_model.py --model lightgbm --extra ratios activity patterns --dashboard"

router = APIRouter(prefix="/api/v2")
_cache: dict = {}


# ------------------------------------------------------------------ .env (Groq key)
def _load_env():
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() and not os.environ.get(k.strip()):
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


_load_env()


# ------------------------------------------------------------------ data
def _cached(key, path: Path, loader):
    if not path.exists():
        raise HTTPException(404, f"{path.name} not found in {path.parent}. Run: {RUN_CMD}")
    mtime = path.stat().st_mtime
    hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    data = loader(path)
    _cache[key] = (mtime, data)
    return data


def _json(path: Path):
    return json.loads(path.read_text())


def validation():
    return _cached("validation", RUN_DIR / "validation.json", _json)


def threshold():
    return float(validation().get("threshold", 0.5))


def scores() -> pd.DataFrame:
    def load(path):
        df = pd.read_parquet(path).sort_values("score", ascending=False).reset_index(drop=True)
        df["rank"] = np.arange(1, len(df) + 1)
        df["top1"] = df["rank"] <= int(np.ceil(0.01 * len(df)))
        return df
    df = _cached("scores", RUN_DIR / "test_scores.parquet", load)
    df["flagged"] = df.score >= threshold()
    return df


def payments() -> pd.DataFrame:
    return _cached("payments", PAYMENTS, lambda p: pd.read_parquet(p).set_index("TRANSACTION_HASH"))


def explanations() -> pd.DataFrame | None:
    path = RUN_DIR / "test_explanations.parquet"
    return _cached("explanations", path, lambda p: pd.read_parquet(p).set_index("TRANSACTION_HASH")) if path.exists() else None


def raw_tables():
    if "raw" not in _cache:
        tx = pd.read_parquet(TEST_DIR / "transactions.parquet",
                             columns=["TRANSACTION_HASH", "TRANSACTION_TYPE", "TRANSACTION_RESULT", "FEE", "SEQUENCE",
                                      "DELIVERED_AMOUNT", "EXTRA_TRANSACTION_FIELDS"]).set_index("TRANSACTION_HASH")
        tr = pd.read_parquet(TEST_DIR / "transfers.parquet",
                             columns=["TRANSACTION_HASH", "TRANSFER_INDEX", "TRANSFER_TYPE", "FROM_ADDRESS", "TO_ADDRESS",
                                      "TOKEN_ADDRESS", "SYMBOL", "VALUE", "TIMESTAMP"])
        blocks = pd.read_parquet(TEST_DIR / "blocks.parquet",
                                 columns=["LEDGER_INDEX", "LEDGER_HASH", "DATETIME", "TOTAL_COINS", "PARENT_HASH"])
        blocks["LEDGER_INDEX"] = blocks.LEDGER_INDEX.astype("int64")
        rates = pd.read_csv(TEST_DIR / "market_rates.csv")
        lookup = dict(zip(zip(rates.TIMESTAMP.astype("int64"), rates.ASSET), rates.PRICE_MICRO_USD / 1e6))
        _cache["raw"] = (tx, tr.groupby("TRANSACTION_HASH"), blocks.set_index("LEDGER_INDEX"), lookup)
    return _cache["raw"]


def records(df: pd.DataFrame) -> list:
    return json.loads(df.to_json(orient="records", date_format="iso"))


# ------------------------------------------------------------------ plain-language reasons
_W = r"(\d+m|\d+h)"
_RULES = [
    (r"^pair_n$", lambda v: f"this sender paid this receiver {v:.0f} time(s) in the week" + (" (a one-off pair)" if v <= 1 else "")),
    (r"^pair_first$", lambda v: "first ever payment between these two wallets" if v else "a repeat payment between these wallets"),
    (r"^pair_k$", lambda v: f"payment number {v + 1:.0f} between this pair"),
    (rf"^pace{_W}_gap_prev$", lambda v, w: f"the previous one-off payment on these wallets was {v:.1f} min earlier (window {w})"),
    (rf"^pace{_W}_gap_next$", lambda v, w: f"the next one-off payment on these wallets came {v:.1f} min later (window {w})"),
    (rf"^pace{_W}_pat_n$", lambda v, w: f"{v:.0f} linked one-off payments around it within ±{w}"),
    (rf"^pace{_W}_pat_gap_med$", lambda v, w: f"those linked payments are {v:.1f} min apart (median, ±{w})"),
    (rf"^pace{_W}_pat_wallets$", lambda v, w: f"{v:.0f} wallets involved in the local pattern (±{w})"),
    (rf"^pace{_W}_pat_span$", lambda v, w: f"the local pattern spans {v:.0f} min (±{w})"),
    (rf"^pace{_W}_pat_gap_max$", lambda v, w: f"largest gap inside the local pattern {v:.1f} min (±{w})"),
    (rf"^pace{_W}_pat_rank$", lambda v, w: f"position {v:.0%} of the way through its local pattern"),
    (rf"^oneoff_closed_{_W}$", lambda v, w: f"{v:.0f} one-off payments link the surrounding wallets to each other (±{w})"),
    (rf"^oneoff_closed_ratio_{_W}$", lambda v, w: f"neighbouring wallets are tightly interlinked (ratio {v:.2f}, ±{w})"),
    (rf"^oneoff_squares_{_W}$", lambda v, w: f"{v:.0f} closed sender/receiver squares (bipartite pattern, ±{w})"),
    (rf"^oneoff_n_nb_{_W}$", lambda v, w: f"{v:.0f} wallets dealt with these two via one-off payments (±{w})"),
    (rf"^oneoff_path2_{_W}$", lambda v, w: f"{v:.0f} one-off payments flow in just before / out just after (±{w})"),
    (rf"^s_out_{_W}$", lambda v, w: f"the sender made {v:.0f} payments within ±{w}"),
    (rf"^r_in_{_W}$", lambda v, w: f"the receiver got {v:.0f} payments within ±{w}"),
    (rf"^s_in_before_{_W}$", lambda v, w: f"the sender received {v:.0f} payments in the {w} before"),
    (rf"^r_out_after_{_W}$", lambda v, w: f"the receiver sent {v:.0f} payments in the {w} after"),
    (rf"^r_fwd_ratio_{_W}$", lambda v, w: f"the receiver passed on {v:.1f}× this amount within {w}"),
    (rf"^s_funded_ratio_{_W}$", lambda v, w: f"the sender had received {v:.1f}× this amount in the {w} before"),
    (rf"^s_out_cp_{_W}$", lambda v, w: f"the sender paid {v:.0f} different wallets within ±{w}"),
    (rf"^r_in_cp_{_W}$", lambda v, w: f"the receiver was paid by {v:.0f} different wallets within ±{w}"),
    (r"^r_fwd_gap_min_(tight|loose)$", lambda v, w: f"the receiver forwarded a similar amount after {v:.0f} min"),
    (r"^s_funded_gap_min_(tight|loose)$", lambda v, w: f"the sender was funded with a similar amount {v:.0f} min before"),
    (r"^chain_(fwd|bwd|total)_(6h|72h)$", lambda v: f"a similar amount kept moving through {v:.0f} hop(s)"),
    (r"^cycle_hops_48h$", lambda v: f"money returned to the sender after {v:.0f} hop(s)" if v else "no cycle back to the sender"),
    (r"^network_activity_2h_rel$", lambda v: f"network activity around this time is {v:.2f}× normal"),
    (r"^log_usd$", lambda v: f"amount about ${np.expm1(v):,.2f}"),
    (rf"^rare_cluster_tx_{_W}$", lambda v, w: f"cluster of {v:.0f} one-off payments around it (±{w})"),
    (rf"^rare_similar_(1hop|2hop)_{_W}$", lambda v, h, w: f"{v:.0f} nearby one-off payments of a similar amount ({h}, ±{w})"),
    (rf"^(s|r)_rare_{_W}$", lambda v, who, w: f"the {'sender' if who == 's' else 'receiver'} had {v:.0f} one-off payments within ±{w}"),
    (rf"^two_hop_activity_{_W}$", lambda v, w: f"{v:.0f} payments in the 2-hop neighbourhood within ±{w}"),
    (r"_rate_change_", lambda v: f"activity {np.exp(v):.1f}× the wallet's usual rate"),
    (r"^log_amt_vs_", lambda v: f"amount {np.exp(v):.1f}× the wallet's usual amount"),
]


def describe(feature: str, value: float) -> str:
    for pattern, fn in _RULES:
        m = re.search(pattern, feature)
        if m:
            try:
                return fn(value, *m.groups())
            except TypeError:
                return fn(value)
    words = feature.replace("_", " ").replace(" s ", " sender ").replace(" r ", " receiver ")
    words = re.sub(r"^s ", "sender ", re.sub(r"^r ", "receiver ", words))
    return f"{words} = {value:g}"


def reasons_for(h: str) -> list:
    ex = explanations()
    if ex is None or h not in ex.index:
        return []
    return [{**r, "text": describe(r["feature"], r["value"])} for r in json.loads(ex.loc[h, "reasons"])]


# ------------------------------------------------------------------ endpoints
@router.get("/summary")
def summary():
    v = validation()
    df = scores()
    edges = np.linspace(0, 1, 21)
    counts, _ = np.histogram(df.score, bins=edges)
    hist = [{"bin": f"{lo:.2f}", "lo": float(lo), "hi": float(hi), "count": int(c)}
            for lo, hi, c in zip(edges[:-1], edges[1:], counts)]
    hours = pd.to_datetime(df.time, utc=True).dt.floor("h").dt.strftime("%Y-%m-%dT%H:00")
    act = df.assign(h=hours).groupby("h").agg(transactions=("score", "size"), flagged=("flagged", "sum")).reset_index()
    ev_path = RUN_DIR / "evaluation.json"
    ev = _cached("evaluation", ev_path, _json) if ev_path.exists() else None
    return {
        "run": RUN,
        "command": RUN_CMD.replace(" --dashboard", ""),
        "validation": v,
        "threshold": threshold(),
        "test": {
            "rows": int(len(df)),
            "flagged": int(df.flagged.sum()),
            "top1_cutoff": float(df.loc[df.top1, "score"].min()),
            "top1_rows": int(df.top1.sum()),
            "usd_flagged": round(float(df.loc[df.flagged, "usd"].sum()), 2),
            "wallets_flagged": int(len(set(df.loc[df.flagged, "from"]) | set(df.loc[df.flagged, "to"]))),
        },
        "histogram": hist,
        "activity": [{"date": r.h, "transactions": int(r.transactions), "flagged": int(r.flagged)} for r in act.itertuples()],
        "top": records(df.head(10)[["TRANSACTION_HASH", "time", "from", "to", "usd", "legs", "score", "rank"]]),
        "importance": (ev or {}).get("feature_importance", [])[:15],
        "has_explanations": explanations() is not None,
        "llm": bool(os.environ.get("GROQ_API_KEY")),
    }


@router.get("/transactions")
def transactions(q: str = "", flagged: bool = False, min_score: float = 0, wallet: str = "",
                 limit: int = Query(50, le=500), offset: int = 0):
    df = scores()
    if q:
        ql = q.strip()
        df = df[df.TRANSACTION_HASH.str.contains(ql, case=False, regex=False)
                | df["from"].str.contains(ql, case=False, regex=False) | df["to"].str.contains(ql, case=False, regex=False)]
    if wallet:
        df = df[(df["from"] == wallet) | (df["to"] == wallet)]
    if flagged:
        df = df[df.flagged]
    if min_score:
        df = df[df.score >= min_score]
    page = df.iloc[offset:offset + limit]
    return {"total": int(len(df)), "threshold": threshold(),
            "items": records(page[["TRANSACTION_HASH", "time", "from", "to", "usd", "legs", "conversion", "score", "rank",
                                   "flagged", "top1"]])}


@router.get("/transactions/{tx_hash}")
def transaction(tx_hash: str):
    df = scores()
    row = df[df.TRANSACTION_HASH == tx_hash]
    if row.empty:
        raise HTTPException(404, "unknown transaction")
    r = row.iloc[0]
    p = payments().loc[tx_hash]
    tx, transfers, blocks, rates = raw_tables()
    raw = tx.loc[tx_hash]
    hour = int(p.ts) // 3600 * 3600
    legs = transfers.get_group(tx_hash).sort_values("TRANSFER_INDEX")
    is_xrp = (legs.SYMBOL == "XRP") | legs.TOKEN_ADDRESS.str.startswith("0x1111")
    asset = np.where(is_xrp, "XRP", legs.TOKEN_ADDRESS + ":" + legs.SYMBOL)
    price = [rates.get((int(t) // 3600 * 3600, a)) for t, a in zip(legs.TIMESTAMP.astype("int64"), asset)]
    legs_out = [{"leg": int(l.TRANSFER_INDEX), "type": l.TRANSFER_TYPE, "from": l.FROM_ADDRESS, "to": l.TO_ADDRESS,
                 "asset": l.SYMBOL, "issuer": None if x else l.TOKEN_ADDRESS, "amount": float(l.VALUE),
                 "usd": None if pr is None else round(float(l.VALUE) * pr, 2)}
                for l, x, pr in zip(legs.itertuples(), is_xrp, price)]
    block = blocks.loc[int(p.ledger_index)]
    sender_tx = df[(df["from"] == r["from"]) | (df["to"] == r["from"])]
    receiver_tx = df[(df["from"] == r["to"]) | (df["to"] == r["to"])]
    return {
        "hash": tx_hash,
        "score": float(r.score), "rank": int(r["rank"]), "flagged": bool(r.flagged), "top1": bool(r.top1),
        "threshold": threshold(), "total": int(len(df)),
        "transaction": {
            "time": pd.Timestamp(int(p.ts), unit="s", tz="UTC").isoformat(), "type": raw.TRANSACTION_TYPE,
            "result": raw.TRANSACTION_RESULT, "sender": p.sender, "receiver": p.receiver,
            "delivered": f"{p.delivered_units:,.6f} {p.delivered_currency}", "usd": round(float(p.usd), 2),
            "source": f"{p.source_currency} (${float(p.source_usd):,.2f} spent)", "fee_xrp": float(raw.FEE),
            "sequence": int(raw.SEQUENCE), "ledger_index": int(p.ledger_index), "position_in_ledger": int(p.tx_index),
            "conversion": bool(p.is_conversion), "legs": int(p.n_legs),
        },
        "legs": legs_out,
        "block": {"ledger_index": int(p.ledger_index), "ledger_hash": p.ledger_hash, "close_time": str(block.DATETIME),
                  "parent_hash": block.PARENT_HASH, "total_coins": str(block.TOTAL_COINS)},
        "rate": {"asset": p.delivered_asset if p.delivered_asset == "XRP" else p.delivered_currency,
                 "hour": pd.Timestamp(hour, unit="s", tz="UTC").isoformat(),
                 "usd_per_unit": rates.get((hour, p.delivered_asset))},
        "wallets": {
            "sender": {"address": r["from"], "payments": int(len(sender_tx)), "flagged": int(sender_tx.flagged.sum())},
            "receiver": {"address": r["to"], "payments": int(len(receiver_tx)), "flagged": int(receiver_tx.flagged.sum())},
        },
        "reasons": reasons_for(tx_hash),
    }


@router.get("/graph")
def graph(tx: str = "", wallet: str = "", hours: float = Query(6, gt=0, le=168), max_edges: int = Query(160, le=600)):
    df = scores()
    if not tx and not wallet:
        tx = df.iloc[0].TRANSACTION_HASH
    t0 = pd.to_datetime(df.time, utc=True)
    if tx:
        row = df[df.TRANSACTION_HASH == tx]
        if row.empty:
            raise HTTPException(404, "unknown transaction")
        centre = {row.iloc[0]["from"], row.iloc[0]["to"]}
        when = pd.to_datetime(row.iloc[0].time, utc=True)
    else:
        centre = {wallet}
        mine = df[(df["from"] == wallet) | (df["to"] == wallet)]
        if mine.empty:
            raise HTTPException(404, "unknown wallet")
        when = pd.to_datetime(mine.iloc[0].time, utc=True)       # its highest-scoring payment
    win = df[(t0 >= when - pd.Timedelta(hours=hours)) & (t0 <= when + pd.Timedelta(hours=hours))]
    first = win[win["from"].isin(centre) | win["to"].isin(centre)]
    ring = set(first["from"]) | set(first["to"])
    sub = win[win["from"].isin(ring) & win["to"].isin(ring)].sort_values("score", ascending=False)
    edges = (sub.groupby(["from", "to"])
             .agg(count=("score", "size"), usd=("usd", "sum"), max_score=("score", "max"),
                  flagged=("flagged", "max"), top_tx=("TRANSACTION_HASH", "first"), first=("time", "min"))
             .reset_index().sort_values("max_score", ascending=False).head(max_edges))
    nodes = pd.unique(pd.concat([edges["from"], edges["to"]]))
    stats = []
    for n in nodes:
        e = edges[(edges["from"] == n) | (edges["to"] == n)]
        stats.append({"id": n, "centre": n in centre, "payments": int(e["count"].sum()),
                      "max_score": float(e.max_score.max()), "flagged": bool(e.flagged.any())})
    return {"centre": sorted(centre), "tx": tx or None, "window_hours": hours,
            "from": (when - pd.Timedelta(hours=hours)).isoformat(), "to": (when + pd.Timedelta(hours=hours)).isoformat(),
            "nodes": stats, "edges": records(edges), "threshold": threshold(),
            "payments_in_view": int(edges["count"].sum())}


# leaderboard results typed in by the team after each upload: outputs/site_results.json
SITE_FILE = ROOT / "outputs" / "site_results.json"


def site_results() -> dict:
    if not SITE_FILE.exists():
        return {}
    data = json.loads(SITE_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, dict)}

MODEL_LIST = [
    ("v1", "v1 LightGBM", "LightGBM", "44 features, first version", None),
    ("xgboost", "XGBoost", "XGBoost", "134 behavioural features", "xgboost"),
    ("catboost", "CatBoost", "CatBoost", "134 behavioural features", "catboost"),
    ("lightgbm", "LightGBM baseline", "LightGBM", "134 behavioural features", "lightgbm"),
    ("lightgbm_two_stage", "LightGBM two-stage (uploaded)", "LightGBM ×2", "134 features + neighbour scores", "lightgbm_two_stage"),
    ("v3", "v3 LightGBM two-stage + patterns", "LightGBM ×2", "181 features + neighbour scores", "lightgbm_two_stage_patterns"),
    ("v2", "v2 LightGBM (dashboard model)", "LightGBM", "191 features: base + ratios + activity + patterns", "lightgbm_activity_patterns_ratios"),
]
ABLATION = [("lightgbm", "Baseline"), ("lightgbm_ratios", "+ ratios"), ("lightgbm_activity", "+ activity change"),
            ("lightgbm_patterns", "+ patterns"), ("lightgbm_activity_patterns_ratios", "+ all three (v2)")]


@router.get("/models")
def models():
    SITE = site_results()
    out = []
    for key, name, algo, feats, folder in MODEL_LIST:
        m = {}
        if folder and (MODELS_DIR / folder / "validation.json").exists():
            m = _json(MODELS_DIR / folder / "validation.json")
        elif key == "v1" and (ROOT / "outputs" / "competition" / "evaluation.json").exists():
            e = _json(ROOT / "outputs" / "competition" / "evaluation.json")
            if e.get("train", {}).get("features") and len(e["train"]["features"]) <= 60:   # the original 44-feature run
                g = e["results"]["grouped"]["lightgbm"]
                m = {"site_score_ap": g["ap"], "top1_precision": g["top1_precision"], "top1_recall": g["top1_recall"],
                     "accuracy": g.get("accuracy_at_0_5"), "precision": g.get("precision_at_0_5"), "recall": g.get("recall_at_0_5")}
            else:
                m = {"site_score_ap": 39.9, "top1_precision": 0.716, "top1_recall": 0.23}
        out.append({"key": key, "name": name, "algorithm": algo, "features": feats, "selected": key == "v2",
                    "ap": m.get("site_score_ap"), "top1_precision": m.get("top1_precision"), "top1_recall": m.get("top1_recall"),
                    "roc_auc": m.get("roc_auc"), "accuracy": m.get("accuracy"), "precision": m.get("precision"),
                    "recall": m.get("recall"), "f1": m.get("f1"), "caught": m.get("caught_in_top1"),
                    "ap_per_fold": m.get("ap_per_fold"),
                    "site": SITE.get(key) if (SITE.get(key) or {}).get("score") is not None else None,
                    "upload_folder": (SITE.get(key) or {}).get("upload_folder")})
    iso = RUN_DIR / "isolation_forest.json"
    if iso.exists():
        i = _json(iso)
        out.append({"key": "isolation_forest", "name": "Isolation Forest", "algorithm": "Isolation Forest (unsupervised)",
                    "features": "191 v2 features, labels not used", "selected": False, "ap": i["site_score_ap"],
                    "top1_precision": i["top1_precision"], "top1_recall": i["top1_recall"], "roc_auc": i["roc_auc"],
                    "accuracy": None, "precision": None, "recall": None, "f1": None, "caught": i.get("caught_in_top1"),
                    "ap_per_fold": None, "site": None, "upload_folder": None})
    ablation = []
    for folder, label in ABLATION:
        f = MODELS_DIR / folder / "validation.json"
        if f.exists():
            m = _json(f)
            ablation.append({"label": label, "ap": m.get("site_score_ap"), "top1_precision": m.get("top1_precision")})
    return {"models": out, "ablation": ablation, "isolation_forest_ready": iso.exists(), "site_file": str(SITE_FILE)}


# ------------------------------------------------------------------ datasets
DATASET_CACHE = ROOT / "outputs" / "compare" / "dataset_stats.json"
TRAIN_DIR = ROOT / "decode-and-detect-training-data" / "train"
AMOUNT_BINS = [0, 1, 10, 100, 1_000, 10_000, float("inf")]
AMOUNT_LABELS = ["< $1", "$1–10", "$10–100", "$100–1k", "$1k–10k", "> $10k"]


def _split_stats(directory: Path, labelled: bool) -> dict:
    import pyarrow.parquet as pq
    from tx_data import load_split   # src/ is on the path (api/main.py)
    p = load_split(directory)
    files = {f: pq.ParquetFile(directory / f"{f}.parquet").metadata.num_rows for f in ("transactions", "transfers", "blocks")}
    files["market_rates"] = int(len(pd.read_csv(directory / "market_rates.csv")))
    if labelled:
        files["labels"] = int(len(pd.read_csv(directory / "labels.csv", usecols=["TRANSACTION_HASH"])))
    t = pd.to_datetime(p.ts, unit="s", utc=True)
    day = (t.dt.floor("D") - t.dt.floor("D").min()).dt.days + 1
    amounts = pd.cut(p.usd, AMOUNT_BINS, labels=AMOUNT_LABELS, right=False).value_counts().reindex(AMOUNT_LABELS).fillna(0)
    out = {
        "folder": str(directory.relative_to(ROOT)),
        "files": files,
        "payments": int(len(p)),
        "wallets": int(len(set(p.sender) | set(p.receiver))),
        "senders": int(p.sender.nunique()),
        "start": t.min().isoformat(), "end": t.max().isoformat(),
        "usd_total": round(float(p.usd.sum()), 2), "usd_median": round(float(p.usd.median()), 2),
        "conversion_share": round(float(p.is_conversion.mean()), 4),
        "per_day": [{"day": int(d), "payments": int(c)} for d, c in day.value_counts().sort_index().items()],
        "currencies": [{"currency": k, "payments": int(v)} for k, v in p.delivered_currency.value_counts().items()],
        "legs": [{"legs": int(k), "payments": int(v)} for k, v in p.n_legs.value_counts().sort_index().items()],
        "amounts": [{"band": k, "payments": int(v)} for k, v in amounts.items()],
    }
    if labelled:
        y = p.is_suspicious.astype(int)
        sus = p[y == 1]
        out["labels"] = {
            "normal": int((y == 0).sum()), "suspicious": int(y.sum()),
            "by_difficulty": [{"difficulty": k, "payments": int(v)} for k, v in sus.difficulty.value_counts().items()],
            "by_family": [{"family": k, "payments": int(v)} for k, v in sus.family.value_counts().items()],
            "look_alikes": int(((y == 0) & p.family.isin(["bipartite", "chain", "cycle", "fan_in", "fan_out", "fan_out_in",
                                                           "multi_stage", "random", "stack"])).sum()),
            "suspicious_per_day": [{"day": int(d), "payments": int(c)} for d, c in day[y == 1].value_counts().sort_index().items()],
        }
    return out


@router.get("/datasets")
def datasets():
    if DATASET_CACHE.exists():
        data = json.loads(DATASET_CACHE.read_text())
    else:
        data = {"train": _split_stats(TRAIN_DIR, True), "test": _split_stats(TEST_DIR, False)}
        DATASET_CACHE.write_text(json.dumps(data, indent=2))
    df = scores()
    data["test"]["flagged"] = int(df.flagged.sum())
    data["test"]["top1"] = int(df.top1.sum())
    return data


# ------------------------------------------------------------------ explanation
def _builtin_explanation(d: dict) -> str:
    t, rs = d["transaction"], d["reasons"]
    verdict = ("is flagged as suspicious" if d["flagged"] else "is not flagged") + \
              f" (score {d['score']:.3f}, rank {d['rank']:,} of {d['total']:,}; the flag threshold is {d['threshold']:.3f})."
    lines = [f"This payment of ${t['usd']:,.2f} from {t['sender'][:10]}… to {t['receiver'][:10]}… {verdict}"]
    if rs:
        lines.append("The biggest drivers of its score:")
        lines += [f"• {r['text']}" for r in rs]
    if d["top1"]:
        lines.append("It is in the top 1% of all test payments, the band an investigator would review first.")
    lines.append("A high score means the payment looks like the planted laundering patterns the model learned; it is a "
                 "ranking signal for review, not proof of wrongdoing.")
    return "\n".join(lines)


@router.post("/explain/{tx_hash}")
def explain(tx_hash: str):
    d = transaction(tx_hash)
    builtin = _builtin_explanation(d)
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        return {"source": "built-in", "text": builtin,
                "note": "Add GROQ_API_KEY to the .env file and restart the API to get an AI explanation."}
    facts = {"score": round(d["score"], 4), "rank": d["rank"], "of": d["total"], "flag_threshold": d["threshold"],
             "flagged": d["flagged"], "in_top_1_percent": d["top1"], "transaction": d["transaction"],
             "transfer_legs": d["legs"], "sender_context": d["wallets"]["sender"], "receiver_context": d["wallets"]["receiver"],
             "top_score_drivers": [{"what": r["text"], "contribution": r["contribution"]} for r in d["reasons"]]}
    body = {
        "model": os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b"),
        "temperature": 0.2,
        "max_tokens": 1200,
        "messages": [
            {"role": "system", "content": "You are an anti-money-laundering analyst explaining a machine-learning alert on "
                                          "a synthetic XRP Ledger dataset to a non-technical reviewer. Use only the facts "
                                          "given. In 4-6 short sentences: say whether it is flagged and how strongly, "
                                          "describe the money flow, explain the top drivers in plain English, and note "
                                          "that a score is a reason to review, not proof."},
            {"role": "user", "content": json.dumps(facts, default=str)},
        ],
    }
    # Groq serves an OpenAI-compatible chat completions endpoint
    req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "User-Agent": "xrpl-hackathon-dashboard/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            text = json.loads(resp.read())["choices"][0]["message"]["content"].strip()
        return {"source": f"Groq ({body['model']})", "text": text}
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
        detail = e.read().decode()[:300] if isinstance(e, urllib.error.HTTPError) else str(e)
        return {"source": "built-in", "text": builtin, "note": f"Groq request failed: {detail}"}
