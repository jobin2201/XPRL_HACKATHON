<div align="center">

# 🔎 Ledgerwatch

### Finding money-laundering patterns in XRP Ledger payments

**Decode & Detect hackathon · Team Code Gladiators**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![LightGBM](https://img.shields.io/badge/Model-LightGBM%204.6-2a78d6)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Dashboard-Next.js%2016-000000?logo=nextdotjs&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/jobin2201/XPRL_HACKATHON/blob/main/LICENSE)

</div>

---

## 📌 What this project does

A week of payments on a (synthetic) XRP Ledger hides **planted money-laundering patterns**: fan-outs, cycles,
relay chains, layering and more. Ledgerwatch gives **every transaction a suspicion score from 0 to 1** so the
suspicious ones rise to the top of an investigator's review list.

| | Part | What it does |
|---|---|---|
| 🧠 | **Detection pipeline** (`src/`) | Joins the raw ledger files into one row per payment, builds ~190 behavioural features (activity bursts, fast forwarding, chains, cycles, one-off wallet pairs) and trains a LightGBM model |
| 📊 | **Investigation dashboard** (`api/` + `frontend/`) | A FastAPI backend and a Next.js website to browse the scored payments, see *why* each one was flagged, explore the money-flow graph and compare models |

```
 raw payments ──► join & value in USD ──► behavioural features ──► LightGBM ──► score 0–1 per payment
                                                                        │
                                                                        └──► dashboard: rank · explain · graph
```

## 🤖 Model

**LightGBM v2** (LightGBM + ratio, activity and pattern features): it gave the best validation score of every
model we tried (XGBoost, CatBoost, logistic regression, Isolation Forest), runs in minutes on a laptop CPU and
can show which features drove each score.

---

## 🚀 How to run

### Requirements

- **Python 3.11** and **Node.js 20+**
- The competition data (not included, the organisers' licence does not allow redistribution):

```
XPRL_HACKATHON/
├── decode-and-detect-training-data/train/   transactions.parquet · transfers.parquet · blocks.parquet · market_rates.csv · labels.csv
└── decode-and-detect-test-data/             transactions.parquet · transfers.parquet · blocks.parquet · market_rates.csv
```

### 1️⃣ Install

```powershell
python -m pip install -r requirements.txt
python -m pip install xgboost catboost      # imported by the shared model module
cd frontend; npm install; cd ..
```

### 2️⃣ Train the model and score the test data

```powershell
python src/run_model.py --model lightgbm --extra ratios activity patterns --dashboard
```

➡️ Writes `outputs/models/lightgbm_activity_patterns_ratios/submission.csv` (`TRANSACTION_HASH,score`, 40,101 rows)
plus the files the dashboard reads.

### 3️⃣ Start the dashboard

**One click (Windows):**

```powershell
.\run_dashboard.ps1
```

It builds any missing model files, then opens the API and the website in two windows.
The script uses the conda env path `F:\ana\envs\xrpl_env\python.exe`; change `$py` at the top if yours differs.

**Or by hand:**

```powershell
# terminal 1 – API
$env:TXMODEL_RUN = "lightgbm_activity_patterns_ratios"
python -m uvicorn api.main:app --port 8000

# terminal 2 – website
cd frontend
npm run dev
```

| Open | URL |
|---|---|
| 🖥️ Dashboard | http://localhost:3000 |
| 📘 API docs | http://127.0.0.1:8000/docs |

### Dashboard pages

| Page | What you see |
|---|---|
| 01 · **Dashboard** | Headline metrics, score distribution, activity over time, top suspicious payments |
| 02 · **Transactions** | Ranked, filterable list; open a payment to see its legs, block, rate, wallet context and the top reasons behind its score |
| 03 · **Network graph** | Wallet-to-wallet money flow around a payment or wallet |
| 04 · **Models** | Every model trained, side by side |
| 05 · **Validation** | Validation folds, leakage checks, feature importance, submission checks |

---

## 🗂️ Project structure

```
XPRL_HACKATHON/
│
├── src/                              🧠 detection pipeline
│   ├── tx_data.py                    load + join the 5 files → 1 row per payment (checked joins, USD values)
│   ├── tx_features.py                ~134 behavioural features
│   ├── tx_extra.py                   extra groups: ratios · activity · patterns
│   ├── tx_patterns.py                pattern structure and pace around one-off payments
│   ├── competition_max.py            model definitions (LightGBM / XGBoost / CatBoost)
│   ├── run_model.py                  ⭐ main entry: validate → train → score test → check CSV
│   ├── competition.py                shared helpers (metrics, leakage report)
│   ├── compare_quick.py              feature cache + quick model comparison
│   ├── lgbm_v3.py                    self-contained v3 pipeline (writes submission_v3/)
│   ├── package_submission.py         builds predictions.csv + source_code.zip for upload
│   ├── ex1…ex4_*.py, xrpl_common.py  exercises on real XRPL Mainnet data (public JSON-RPC, cached)
│   └── make_sample_data.py, features.py, train.py, predict.py, detect.py
│                                     early account-level prototype (random forest + rules + Isolation Forest)
│
├── api/                              ⚙️ FastAPI backend
│   ├── main.py                       app, dataset/account endpoints, mounts v2
│   └── v2.py                         /api/v2: summary, transactions, graph, models, datasets, explain
│
├── frontend/                         📊 Next.js 16 + TypeScript + Tailwind dashboard
│   ├── app/                          pages: dashboard · flagged · graph · models · scoring · cases …
│   ├── components/                   charts (Recharts), network graph (d3-force), layout
│   └── lib/                          API client and formatting helpers
│
├── docs/                             project report (PDF)
├── outputs/                          generated: model runs, submissions, caches (git-ignored)
├── run_dashboard.ps1                 one-click start (Windows)
├── requirements.txt                  Python dependencies
├── SUBMISSION_README.md              README shipped inside the submission ZIP
├── THIRD_PARTY.md                    libraries, data and AI assistance used
└── LICENSE                           MIT
```

---

## 📄 License

Released under the **[MIT License](https://github.com/jobin2201/XPRL_HACKATHON/blob/main/LICENSE)** · © 2026 Code Gladiators.
See [`LICENSE`](LICENSE) in this repository.

A detailed write-up is in [`docs/Ledgerwatch_Project_Report.pdf`](docs/Ledgerwatch_Project_Report.pdf).
