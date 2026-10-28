# Decode & Detect – Code Gladiators submission

Suspicion score (0–1) for every test transaction, from a two-stage LightGBM model.

## Exact command that produced the predictions CSV

```
python -m pip install -r requirements.txt
python src/run_model.py --model lightgbm --two-stage
```

Output: `outputs/models/lightgbm_two_stage/submission.csv` (`TRANSACTION_HASH,score`, 40,101 rows).

### Data layout expected (data is not included in this ZIP)
```
decode-and-detect-training-data/train/   transactions.parquet, transfers.parquet, blocks.parquet, market_rates.csv, labels.csv
decode-and-detect-test-data/             transactions.parquet, transfers.parquet, blocks.parquet, market_rates.csv
```

### Hardware and time
Laptop CPU (Windows 11, multi-core), no GPU. About 4–5 minutes in total
(~1 min features per split, ~3 min validation + final training). Python 3.11.17.

## How it works
| File | Role |
|---|---|
| `src/tx_data.py` | Loads the five files and joins them into one row per transaction. Checks every join: no duplicated or dropped transaction, last transfer leg = delivered amount, block keys one-to-one, an hourly market rate for every amount. XRP drops and token units are never mixed. |
| `src/tx_features.py` | ~134 behavioural features from the split's own transactions (no labels): one-off wallet pairs, activity in 10 min–72 h windows, forwarding of similar amounts, multi-hop chains, cycles, wallet profiles, clusters of one-off payments, plus second-stage neighbour scores. |
| `src/competition_max.py` | Model definitions and the two-stage pipeline (stage 1 LightGBM; stage 2 LightGBM that also sees the out-of-fold scores of nearby payments sharing a wallet). |
| `src/run_model.py` | Grouped 5-fold validation, final training on all labelled data, test scoring, submission checks. |
| `src/compare_quick.py`, `src/competition.py` | Helpers used by run_model.py (feature cache, output columns, metrics). |

## Validation (measured on labelled training data, not on the test set)
Grouped 5-fold cross-validation: a planted scenario is never split between training and validation folds.
| Measure | Value |
|---|---|
| 100 × Average Precision | 56.9 |
| Top-1% precision / recall | 82.6% / 26.6% |
| ROC-AUC | 0.891 |

Label metadata (`family`, `difficulty`, `scenario_id`, `cohort_id`) is never a model input; `scenario_id`
is only used to keep scenarios inside one validation fold.
