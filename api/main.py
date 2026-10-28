"""FastAPI backend for the XRPL monitoring dashboard.

Reads the pipeline outputs in data/processed (features, scores, alerts, model_meta)
plus the raw transactions, and serves them to the Next.js frontend.

Run from the project root:
    python -m uvicorn api.main:app --reload --port 8000
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from detect import RULES, detect_rapid_forwarding, payments  # noqa: E402
from features import add_usd  # noqa: E402
from load_data import DATASET, PROCESSED_ROOT, dataset_dirs, load_all  # noqa: E402

DUST_USD = 1.0

app = FastAPI(title="XRPL Monitor API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["*"], allow_headers=["*"])

S: dict = {}  # in-memory state


def records(df: pd.DataFrame) -> list:
    """DataFrame -> JSON-safe records (NaN -> null, timestamps -> ISO)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def available_datasets() -> list[str]:
    """Datasets whose pipeline outputs exist in data/processed/<name> (the old synthetic sample is not offered)."""
    out = []
    if PROCESSED_ROOT.exists():
        out += sorted(p.name for p in PROCESSED_ROOT.iterdir() if p.is_dir() and (p / "scores.parquet").exists())
    return out


def time_buckets(ts: pd.Series) -> tuple[pd.Series, str]:
    """Bucket timestamps at a resolution that suits the data's span (minutes for a short Mainnet range, days for a month)."""
    span = ts.max() - ts.min() if len(ts) else pd.Timedelta(0)
    if span <= pd.Timedelta(hours=3):
        return ts.dt.floor("min").dt.strftime("%Y-%m-%dT%H:%M"), "minute"
    if span <= pd.Timedelta(days=3):
        return ts.dt.floor("h").dt.strftime("%Y-%m-%dT%H:00"), "hour"
    return ts.dt.strftime("%Y-%m-%d"), "day"


def load_state(name: str | None = None):
    name, raw, proc = dataset_dirs(name or S.get("dataset") or DATASET)
    if not (proc / "scores.parquet").exists():
        raise FileNotFoundError(f"No pipeline outputs for dataset '{name}' in {proc}. Run features.py and detect.py first.")
    data = load_all(raw)
    tx = add_usd(data["transactions"], data["market_rates"])
    tx["amount_usd"] = tx["amount_usd"].round(2)
    tx["failed"] = tx["result"] != "tesSUCCESS"
    tx = tx.sort_values("timestamp", ascending=False).reset_index(drop=True)

    scores = pd.read_parquet(proc / "scores.parquet")
    feats = pd.read_parquet(proc / "features.parquet")
    alerts = json.loads((proc / "alerts.json").read_text())
    meta = json.loads((proc / "model_meta.json").read_text())
    status_file = proc / "case_status.json"
    status = json.loads(status_file.read_text()) if status_file.exists() else {}

    scores["rules"] = scores["account"].map(lambda a: sorted(alerts.get(a, {}).get("rules", {}).keys()))
    summary = feats[["account", "n_sent", "n_received", "usd_sent_total", "usd_received_total",
                     "n_unique_dest", "n_unique_src"]]
    accounts = scores.merge(summary, on="account", how="left")

    pay = payments(tx)
    fwd = detect_rapid_forwarding(pay)
    peel_edges = set(zip(fwd.src, fwd.acct)) | set(zip(fwd.acct, fwd.dst))

    edges = (pay.groupby(["account", "destination"])
                .agg(count=("tx_hash", "size"), usd=("amount_usd", "sum"),
                     first=("timestamp", "min"), last=("timestamp", "max"))
                .reset_index())

    S.clear()
    S.update(dataset=name, status_file=status_file, tx=tx, scores=scores, accounts=accounts, alerts=alerts,
             meta=meta, status=status, feats=feats.set_index("account"), pay=pay, edges=edges, peel_edges=peel_edges,
             loaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))


@app.on_event("startup")
def _startup():
    try:
        load_state()
    except FileNotFoundError:  # e.g. XRPL_DATASET points at a dataset that hasn't been built: fall back to the official split
        load_state("official")


def account_status(a):
    return S["status"].get(a, {"status": "open", "note": "", "updated_at": None})


# ---------------------------------------------------------------- overview
@app.get("/api/health")
def health():
    return {"ok": True, "loaded_at": S.get("loaded_at"), "dataset": S.get("dataset")}


@app.post("/api/reload")
def reload():
    load_state()
    return {"ok": True, "loaded_at": S["loaded_at"], "dataset": S["dataset"]}


@app.get("/api/datasets")
def datasets():
    out = []
    for name in available_datasets():
        meta_file = dataset_dirs(name)[2] / "model_meta.json"
        meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
        out.append({"name": name, "n_accounts": meta.get("n_accounts"), "supervised": meta.get("supervised_available", True),
                    "generated_at": meta.get("generated_at"), "source": meta.get("source")})
    return {"current": S.get("dataset"), "datasets": out}


class DatasetIn(BaseModel):
    name: str


@app.post("/api/dataset")
def switch_dataset(body: DatasetIn):
    if body.name not in available_datasets():
        raise HTTPException(404, f"dataset '{body.name}' has no pipeline outputs")
    load_state(body.name)
    return {"ok": True, "dataset": S["dataset"], "loaded_at": S["loaded_at"]}


@app.get("/api/overview")
def overview():
    tx, acc, meta = S["tx"], S["accounts"], S["meta"]
    flagged = acc[acc.flagged]
    flagged_set = set(flagged.account)

    keys, granularity = time_buckets(tx.timestamp)
    daily = tx.assign(date=keys, flagged_tx=tx.account.isin(flagged_set) | tx.destination.isin(flagged_set))
    activity = (daily.groupby("date")
                     .agg(transactions=("tx_hash", "size"), flagged=("flagged_tx", "sum"),
                          failed=("failed", "sum"), usd=("amount_usd", "sum"))
                     .reset_index())
    activity["usd"] = activity["usd"].round(0)
    value_tx = payments(tx)  # value moved between different accounts (self-payments and failures excluded)

    bins = np.linspace(0, 1, 21)
    counts, _ = np.histogram(acc.risk_score, bins=bins)
    dist = [{"bin": f"{bins[i]:.2f}", "lo": round(bins[i], 2), "hi": round(bins[i + 1], 2), "count": int(c)}
            for i, c in enumerate(counts)]

    rule_counts = [{"id": k, "name": v["name"], "weight": v["weight"],
                    "count": int(sum(k in r for r in acc.rules))} for k, v in RULES.items()]
    rule_counts.sort(key=lambda r: -r["count"])

    top = acc.sort_values("risk_score", ascending=False).head(12)
    top = top.assign(status=top.account.map(lambda a: account_status(a)["status"]))

    recent = tx[tx.account.isin(flagged_set) | tx.destination.isin(flagged_set)].head(10)
    return {
        "kpis": {
            "transactions": int(len(tx)), "accounts": int(len(acc)), "flagged": int(len(flagged)),
            "critical": int((acc.tier == "critical").sum()), "high": int((acc.tier == "high").sum()),
            "usd_volume": round(float(value_tx.amount_usd.sum()), 0),
            "self_payments": int(((tx.tx_type == "Payment") & (tx.account == tx.destination)).sum()),
            "failed_rate": round(float(tx.failed.mean()), 4),
            "start": tx.timestamp.min().isoformat(), "end": tx.timestamp.max().isoformat(),
            "under_review": int(sum(v.get("status") == "review" for v in S["status"].values())),
        },
        "tiers": {t: int((acc.tier == t).sum()) for t in ["critical", "high", "medium", "low"]},
        "score_distribution": dist,
        "rule_counts": rule_counts,
        "activity": records(activity),
        "granularity": granularity,
        "dataset": S["dataset"],
        "supervised_available": meta.get("supervised_available", True),
        "source": meta.get("source"),
        "top_accounts": records(top[["account", "risk_score", "model_score", "anomaly_score", "rule_score",
                                     "tier", "rules", "usd_sent_total", "status"]]),
        "recent_flagged_tx": records(recent[["tx_hash", "timestamp", "tx_type", "account", "destination",
                                             "amount_usd", "currency", "result"]]),
        "model_version": meta["model_version"], "generated_at": meta["generated_at"],
    }


# ---------------------------------------------------------------- accounts
SortKey = Literal["risk_score", "rule_score", "anomaly_score", "model_score", "usd_sent_total", "n_sent"]


@app.get("/api/accounts")
def list_accounts(q: str = "", tier: str = "", rule: str = "", flagged: bool | None = None,
                  status: str = "", sort: SortKey = "risk_score", order: Literal["asc", "desc"] = "desc",
                  limit: int = Query(50, le=500), offset: int = 0):
    df = S["accounts"]
    if q:
        df = df[df.account.str.contains(q, case=False, regex=False)]
    if tier:
        df = df[df.tier.isin(tier.split(","))]
    if rule:
        df = df[df.rules.map(lambda r: rule in r)]
    if flagged is not None:
        df = df[df.flagged == flagged]
    st = df.account.map(lambda a: account_status(a)["status"])
    df = df.assign(status=st)
    if status:
        df = df[df.status == status]
    df = df.sort_values(sort, ascending=(order == "asc"))
    page = df.iloc[offset: offset + limit]
    return {"total": int(len(df)), "items": records(page.drop(columns=["anomaly_raw"]))}


@app.get("/api/accounts/{account}")
def account_detail(account: str):
    acc = S["accounts"]
    row = acc[acc.account == account]
    if row.empty:
        raise HTTPException(404, "account not found")
    tx, pay = S["tx"], S["pay"]
    alerts = S["alerts"].get(account, {"rules": {}, "deviations": []})

    mine = tx[(tx.account == account) | (tx.destination == account)]
    mine = mine.assign(direction=np.where((mine.account == account) & (mine.destination == account), "self",
                                          np.where(mine.account == account, "out", "in")))

    p = pay[(pay.account == account) | (pay.destination == account)]
    keys, granularity = time_buckets(S["tx"].timestamp)  # same resolution as the overview
    p = p.assign(direction=np.where(p.account == account, "out", "in"), date=keys.reindex(p.index))
    timeline = (p.pivot_table(index="date", columns="direction", values="amount_usd", aggfunc="sum", fill_value=0)
                 .reindex(columns=["in", "out"], fill_value=0).round(2).reset_index())
    timeline.columns = ["date", "received_usd", "sent_usd"]
    counts = p.pivot_table(index="date", columns="direction", values="tx_hash", aggfunc="count", fill_value=0)
    counts = counts.reindex(columns=["in", "out"], fill_value=0)
    timeline["received_n"] = timeline.date.map(counts["in"]).fillna(0).astype(int)
    timeline["sent_n"] = timeline.date.map(counts["out"]).fillna(0).astype(int)

    cp = p.assign(counterparty=np.where(p.direction == "out", p.destination, p.account))
    cps = (cp.pivot_table(index="counterparty", columns="direction", values="amount_usd",
                          aggfunc=["sum", "count"], fill_value=0))
    cps.columns = [f"{a}_{b}" for a, b in cps.columns]
    cps = cps.reindex(columns=["sum_in", "sum_out", "count_in", "count_out"], fill_value=0)
    cps["total"] = cps.sum_in + cps.sum_out
    cps = cps.sort_values("total", ascending=False).head(15).round(2).reset_index()
    risk = S["accounts"].set_index("account")
    cps["risk_score"] = cps.counterparty.map(risk.risk_score)
    cps["flagged"] = cps.counterparty.map(risk.flagged).fillna(False)

    rules = []
    for rid, ev in alerts["rules"].items():
        rules.append({"id": rid, **RULES[rid], "evidence": ev})
    rules.sort(key=lambda r: -r["weight"])
    not_triggered = [{"id": k, **v} for k, v in RULES.items() if k not in alerts["rules"]]

    r = row.iloc[0]
    return {
        "account": account,
        "scores": records(row.drop(columns=["anomaly_raw"]))[0],
        "features": json.loads(S["feats"].loc[account].to_json()),
        "rules": rules, "rules_not_triggered": not_triggered,
        "deviations": alerts["deviations"],
        "timeline": records(timeline),
        "granularity": granularity,
        "counterparties": records(cps),
        "totals": {"received_usd": round(float(p[p.direction == "in"].amount_usd.sum()), 2),
                   "sent_usd": round(float(p[p.direction == "out"].amount_usd.sum()), 2),
                   "first_seen": mine.timestamp.min().isoformat() if len(mine) else None,
                   "last_seen": mine.timestamp.max().isoformat() if len(mine) else None,
                   "tx_count": int(len(mine))},
        "transactions": records(mine.head(200)[["tx_hash", "timestamp", "tx_type", "direction", "account",
                                                "destination", "amount", "currency", "amount_usd", "fee",
                                                "result", "destination_tag"]]),
        "status": account_status(account),
        "risk_formula": S["meta"]["risk_formula"],
        "tier": r.tier,
    }


class StatusIn(BaseModel):
    status: Literal["open", "review", "dismissed", "escalated"]
    note: str = ""


@app.post("/api/accounts/{account}/status")
def set_status(account: str, body: StatusIn):
    if account not in set(S["accounts"].account):
        raise HTTPException(404, "account not found")
    S["status"][account] = {"status": body.status, "note": body.note,
                            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    S["status_file"].write_text(json.dumps(S["status"], indent=2))
    return S["status"][account]


# ---------------------------------------------------------------- transactions
@app.get("/api/transactions")
def list_transactions(q: str = "", account: str = "", direction: Literal["all", "in", "out"] = "all",
                      failed: bool = False, dust: bool = False, tx_type: str = "", min_usd: float = 0,
                      flagged_only: bool = False, limit: int = Query(50, le=500), offset: int = 0):
    tx = S["tx"]
    if q:
        ql = q.strip()
        tx = tx[tx.tx_hash.str.contains(ql, case=False, regex=False)
                | tx.account.str.contains(ql, case=False, regex=False)
                | tx.destination.fillna("").str.contains(ql, case=False, regex=False)]
    if account:
        if direction == "out":
            tx = tx[tx.account == account]
        elif direction == "in":
            tx = tx[tx.destination == account]
        else:
            tx = tx[(tx.account == account) | (tx.destination == account)]
    if failed:
        tx = tx[tx.failed]
    if dust:
        tx = tx[(tx.tx_type == "Payment") & (tx.amount_usd < DUST_USD)]
    if tx_type:
        tx = tx[tx.tx_type == tx_type]
    if min_usd:
        tx = tx[tx.amount_usd >= min_usd]
    if flagged_only:
        fs = set(S["accounts"][S["accounts"].flagged].account)
        tx = tx[tx.account.isin(fs) | tx.destination.isin(fs)]
    page = tx.iloc[offset: offset + limit]
    return {"total": int(len(tx)), "tx_types": sorted(S["tx"].tx_type.unique().tolist()),
            "items": records(page[["tx_hash", "ledger_index", "timestamp", "tx_type", "account", "destination",
                                   "amount", "currency", "amount_usd", "fee", "destination_tag", "result"]])}


@app.get("/api/transactions/{tx_hash}")
def tx_detail(tx_hash: str):
    t = S["tx"][S["tx"].tx_hash == tx_hash]
    if t.empty:
        raise HTTPException(404, "transaction not found")
    return records(t)[0]


# ---------------------------------------------------------------- network
@app.get("/api/network")
def network(account: str = "", depth: int = Query(1, ge=1, le=2), min_usd: float = 0,
            start: str = "", end: str = "", max_nodes: int = Query(150, le=400)):
    pay = S["pay"]
    if start:
        pay = pay[pay.timestamp >= pd.Timestamp(start, tz="UTC")]
    if end:
        pay = pay[pay.timestamp < pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)]
    if min_usd:
        pay = pay[pay.amount_usd >= min_usd]
    e = (pay.groupby(["account", "destination"])
            .agg(count=("tx_hash", "size"), usd=("amount_usd", "sum")).reset_index())

    acc = S["accounts"].set_index("account")
    if account:
        if account not in acc.index:
            raise HTTPException(404, "account not found")
        nodes = {account}
        frontier = {account}
        for _ in range(depth):
            nb = set(e[e.account.isin(frontier)].destination) | set(e[e.destination.isin(frontier)].account)
            frontier = nb - nodes
            nodes |= nb
    else:
        seeds = set(acc[acc.flagged].index)
        nodes = set(seeds)
        nb = e[e.account.isin(seeds) | e.destination.isin(seeds)]
        nodes |= set(nb.account) | set(nb.destination)

    # cap: always keep flagged nodes + the focus account, then the counterparties moving the most value
    if len(nodes) > max_nodes:
        core = {n for n in nodes if acc.at[n, "flagged"]} | ({account} if account else set())
        core = set(sorted(core, key=lambda n: -acc.at[n, "risk_score"])[:max_nodes])
        touch = e[e.account.isin(core) | e.destination.isin(core)]
        weight = pd.concat([touch.groupby("destination").usd.sum(), touch.groupby("account").usd.sum()])
        weight = weight.groupby(level=0).sum().drop(labels=list(core), errors="ignore")
        weight = weight[weight.index.isin(nodes)].sort_values(ascending=False)
        nodes = core | set(weight.head(max(0, max_nodes - len(core))).index)

    e = e[e.account.isin(nodes) & e.destination.isin(nodes)]
    if not account:  # in overview mode only keep edges touching a flagged account
        fs = set(acc[acc.flagged].index)
        e = e[e.account.isin(fs) | e.destination.isin(fs)]
        nodes = set(e.account) | set(e.destination)
    pairs = set(zip(e.account, e.destination))
    peel = S["peel_edges"]

    def patterns(a):
        rules = set(acc.at[a, "rules"])
        out = []
        if "fan_out" in rules: out.append("fan_out")
        if "fan_in" in rules: out.append("fan_in")
        if "round_trip" in rules: out.append("cycle")
        if "rapid_forward" in rules: out.append("peel_chain")
        return out

    node_list = [{"id": a, "risk_score": float(acc.at[a, "risk_score"]), "tier": acc.at[a, "tier"],
                  "flagged": bool(acc.at[a, "flagged"]), "rules": list(acc.at[a, "rules"]),
                  "patterns": patterns(a),
                  "usd_sent": round(float(acc.at[a, "usd_sent_total"]), 2),
                  "usd_received": round(float(acc.at[a, "usd_received_total"]), 2),
                  "focus": a == account} for a in nodes]
    edge_list = [{"source": s, "target": t, "count": int(c), "usd": round(float(u), 2),
                  "reciprocal": (t, s) in pairs, "peel": (s, t) in peel}
                 for s, t, c, u in e[["account", "destination", "count", "usd"]].itertuples(index=False)]
    return {"nodes": node_list, "edges": edge_list,
            "range": {"start": S["pay"].timestamp.min().strftime("%Y-%m-%d"),
                      "end": S["pay"].timestamp.max().strftime("%Y-%m-%d")}}


# ---------------------------------------------------------------- model insights
@app.get("/api/model")
def model_insights():
    acc, meta = S["accounts"], S["meta"]
    supervised = bool(meta.get("supervised_available", True))
    ranks = acc[["account", "model_score", "anomaly_score", "rule_score", "risk_score", "tier", "flagged", "label"]]
    score_cols = (["model_score"] if supervised else []) + ["anomaly_score", "rule_score", "risk_score"]
    corr = acc[score_cols].corr(method="spearman").round(3).fillna(0.0)

    def top(col, k=25):
        return set(acc.sort_values(col, ascending=False).head(k).account)

    k = 25
    overlap = {"k": k, "anomaly_vs_rules": len(top("anomaly_score") & top("rule_score"))}
    if supervised:
        overlap.update(model_vs_anomaly=len(top("model_score") & top("anomaly_score")),
                       model_vs_rules=len(top("model_score") & top("rule_score")),
                       all_three=len(top("model_score") & top("anomaly_score") & top("rule_score")))
    bins = np.linspace(0, 1, 21)
    sus = acc.label == 1
    a_all, _ = np.histogram(acc.anomaly_score, bins=bins)
    a_flag, _ = np.histogram(acc[acc.flagged].anomaly_score, bins=bins)
    anomaly_dist = [{"bin": f"{bins[i]:.2f}", "all": int(a_all[i]) - int(a_flag[i]), "flagged": int(a_flag[i])}
                    for i in range(len(a_all))]
    disagreements = acc[((acc.anomaly_score >= 0.9) & (acc.rule_score == 0)) |
                        ((acc.rule_score >= 30) & (acc.anomaly_score < 0.7))]
    return {**meta,
            "spearman": {c: corr[c].to_dict() for c in corr.columns},
            "overlap": overlap,
            "scatter": records(ranks),
            "anomaly_distribution": anomaly_dist,
            "disagreements": records(disagreements.sort_values("risk_score", ascending=False)
                                     [["account", "model_score", "anomaly_score", "rule_score", "risk_score", "rules"]].head(20)),
            "labelled_suspicious": int(sus.sum())}


# ---------------------------------------------------------------- transaction model (src/competition.py outputs)
# The dashboard shows the v2 model: run_model.py --model lightgbm --extra ratios activity patterns --dashboard
# (override with the TXMODEL_RUN environment variable to show another run folder in outputs/models/)
TX_RUN = os.environ.get("TXMODEL_RUN", "lightgbm_activity_patterns_ratios")
TX_OUT = ROOT / "outputs" / "models" / TX_RUN
_TX_CACHE: dict = {}


def _tx_file(name: str):
    """Read an output of competition.py, re-reading it only when the file changes."""
    path = TX_OUT / name
    if not path.exists():
        raise HTTPException(404, f"{name} not found in outputs/models/{TX_RUN}. Run: python src/run_model.py "
                                 "--model lightgbm --extra ratios activity patterns --dashboard")
    mtime = path.stat().st_mtime
    hit = _TX_CACHE.get(name)
    if hit and hit[0] == mtime:
        return hit[1]
    data = pd.read_parquet(path) if path.suffix == ".parquet" else json.loads(path.read_text())
    if isinstance(data, pd.DataFrame):
        data = data.sort_values("score", ascending=False).reset_index(drop=True)
        data["rank"] = np.arange(1, len(data) + 1)
    _TX_CACHE[name] = (mtime, data)
    return data


@app.get("/api/txmodel/evaluation")
def txmodel_evaluation():
    return _tx_file("evaluation.json")


@app.get("/api/txmodel/submission")
def txmodel_submission():
    return _tx_file("submission_check.json")


@app.get("/api/txmodel/scores")
def txmodel_scores(split: Literal["train", "test"] = "test", q: str = "", label: Literal["all", "suspicious", "normal"] = "all",
                   min_score: float = 0, sort: Literal["desc", "asc"] = "desc",
                   limit: int = Query(50, le=500), offset: int = 0):
    df = _tx_file(f"{split}_scores.parquet")
    if q:
        ql = q.strip()
        df = df[df.TRANSACTION_HASH.str.contains(ql, case=False, regex=False)
                | df["from"].str.contains(ql, case=False, regex=False)
                | df["to"].str.contains(ql, case=False, regex=False)]
    if split == "train" and label != "all":
        df = df[df.label == (1 if label == "suspicious" else 0)]
    if min_score:
        df = df[df.score >= min_score]
    if sort == "asc":
        df = df.iloc[::-1]
    page = df.iloc[offset: offset + limit]
    return {"total": int(len(df)), "items": records(page)}


# ---------------------------------------------------------------- v2 model dashboard (api/v2.py)
from api.v2 import router as v2_router  # noqa: E402

app.include_router(v2_router)
