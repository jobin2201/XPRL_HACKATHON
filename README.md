# Ledgerwatch: XRPL suspicious-activity detection

A Python detection pipeline plus a Next.js investigation dashboard for XRP Ledger accounts.

```
data/raw/          input files (currently a SYNTHETIC sample)
data/processed/    features, scores, alerts, model metadata, case decisions
src/               pipeline: make_sample_data, load_data, features, train, predict, detect
models/            trained random forest (model.joblib)
outputs/           predictions.csv
api/               FastAPI backend that serves the pipeline outputs
frontend/          Next.js 16 + TypeScript + Tailwind dashboard
```

## Quick start (Windows)

```powershell
cd F:\WORK\NEWPROJECTS\MPROJECTS\XPRL_HACKATHON
.\run_dashboard.ps1            # starts the API on :8000 and the website on :3000
```

Then open http://localhost:3000. If another app already uses port 3000 on 127.0.0.1,
open http://[::1]:3000 instead, or stop that app.

## Environment

Uses the existing conda env `xrpl_env` (`F:\ana\envs\xrpl_env`), which now also has FastAPI and uvicorn.

```powershell
F:\ana\envs\xrpl_env\python.exe -m pip install -r requirements.txt
cd frontend; npm install
```

## 1. Run the pipeline

```powershell
cd src
$py = "F:\ana\envs\xrpl_env\python.exe"
& $py make_sample_data.py   # ONLY for the synthetic sample; skip once you have the official files
& $py load_data.py          # print schema + preview of each file
& $py features.py           # -> data/processed/features.parquet
& $py train.py              # -> models/model.joblib (validation ROC-AUC / PR-AUC)
& $py predict.py            # -> outputs/predictions.csv (accounts not in labels.csv)
& $py detect.py             # -> scores.parquet, alerts.json, model_meta.json
```

`detect.py` is the explainable layer. It combines three detectors:

| Detector | What it is |
|---|---|
| Supervised | Random forest probability. Out-of-fold for labelled accounts, so there is no leakage. |
| Anomaly | Isolation Forest on log-scaled features, expressed as a percentile. |
| Rules | Nine typology rules: structuring, fan-out, fan-in, round-tripping, rapid forwarding / peel chains, failed probing, odd-hour activity, fee spikes and dust. Each one records its evidence and example transactions. |

The combined risk is `0.5 × model + 0.3 × rule_score/100 + 0.2 × anomaly`. An account is flagged
at risk ≥ 0.40 or with a rule score of 30 or more.

## 2. Run the website

```powershell
# terminal 1, from the project root
F:\ana\envs\xrpl_env\python.exe -m uvicorn api.main:app --port 8000

# terminal 2
cd frontend
npm run dev
```

After re-running the pipeline, restart the API or call `POST http://127.0.0.1:8000/api/reload`.

| Page | What it shows |
|---|---|
| 01 Overview | KPIs, activity over time, risk tiers, rule-trigger counts, score distribution, priority shortlist |
| 02 Investigations | Filterable and sortable queue with risk, rule and anomaly scores, plus expandable reasons |
| 03 Network Analysis | Force-directed money-flow graph with fan-out, fan-in, cycle and peel-chain highlights, click-to-inspect, and date and value filters |
| 04 Transaction Explorer | Hash and address search, failed and dust filters, incoming and outgoing history, transaction detail |
| 05 Case Details | Timeline, received vs sent, counterparties, rapid-forwarding evidence, rule-by-rule explanation, review / escalate / dismiss |
| 06 Model Insights | Metrics, model card, feature importance, supervised-vs-anomaly scatter, rank agreement, disagreements, limitations |

Analyst decisions are saved to `data/processed/case_status.json`.

## Data (data/raw)

The files there now are a **synthetic sample** made by `make_sample_data.py`, not the competition data.
When you receive the official files, delete the sample files and copy the originals in unchanged.
Adjust column names in `features.py` and `detect.py` if they differ, then re-run the pipeline.
Also delete `data/processed/sample_hidden_test_labels.csv`, which only exists for the sample.

| File | Sample columns |
|---|---|
| transactions.parquet | tx_hash, ledger_index, timestamp, tx_type, account, destination, amount, currency, fee, destination_tag, result |
| transfers.parquet | tx_hash, hop, from_account, to_account, amount, currency, timestamp |
| blocks.parquet | ledger_index, close_time, tx_count |
| market_rates.csv | date, currency, usd_rate |
| labels.csv | account, is_suspicious (labelled accounts only) |

The sample plants six typologies:
- structuring just under 10k USD
- fan-out bursts
- fan-in collectors
- night bursts with high fees and failures
- round-tripping inside a ring
- peel-chain pass-through mules

The scores are high because these patterns were planted on purpose. They say nothing about competition performance.

## Competition pipeline (official Decode & Detect data)

Uses `decode-and-detect-training-data/` (train + labels, validation) and scores **one row per transaction**.

```powershell
F:\ana\envs\xrpl_env\python.exe src/competition.py                  # check run on validation/
F:\ana\envs\xrpl_env\python.exe src/competition.py path\to\test-data  # real submission
```

Writes `outputs/competition/predictions_<split>.csv` (`TRANSACTION_HASH,score`). Runs in about 40 s on a laptop.
5-fold AP on train: starter logistic regression 31.4, gradient boosting 72.6 (gradient boosting is used).
