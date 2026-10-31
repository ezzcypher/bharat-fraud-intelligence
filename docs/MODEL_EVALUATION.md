# Model evaluation (historical, frozen)

> **These are historical results.** They were produced in the project's Google Colab runtime from the frozen Phase 4
> model and its stored predictions. They are **not** re-measured by this repository's CI, because the model, the stored
> predictions and the IEEE-CIS data are not redistributed (see [DATA_PIPELINE.md](DATA_PIPELINE.md)).

## What was evaluated

| Item | Value | Source |
|---|---|---|
| Dataset | IEEE-CIS Fraud Detection (Kaggle): `train_transaction` 590,540 × 394 and `train_identity` 144,233 × 41 | Phase 4 |
| Labels | `isFraud`, chargeback-derived (not confirmed investigation outcomes) | Dataset documentation |
| Split | Day-based chronological split (train / validation / test) on the relative day `TransactionDT // 86400` | Phase 4 `BFI_v2_splits.csv` |
| Model | LightGBM (`LGBMClassifier`), "model A", 431 features of which 32 categorical | Phase 4 `BFI_v2_model_config.json` |
| Decision threshold | **0.12379763346033115**, chosen on validation (best recall at precision ≥ 0.50 over the last 14 days of validation) | Phase 4 config; read at runtime, never typed into code |
| Decision rule | alert ⇔ score ≥ threshold | Phase 7 |

The model, split, labels, threshold and stored predictions are **frozen**. Nothing in this repository retrains, retunes,
recalibrates or re-thresholds the model.

## Test-split results (model A, frozen threshold)

| Metric | Value |
|---|---|
| Test transactions | 92,427 (TP + FP + TN + FN) |
| Prevalence (label rate) | 3.48 % (0.03476256937907754) |
| True positives (TP) | 1,713 |
| False positives (FP) | 1,782 |
| True negatives (TN) | 87,432 |
| False negatives (FN) | 1,500 |
| Precision | 0.4901 (0.4901287553648069) |
| Recall | 0.5331 (0.5331465919701214) |
| F1 | 0.5107 |
| Specificity | 0.9800 |
| False-positive rate | 0.0200 |
| Balanced accuracy | 0.7566 |
| Accuracy | 0.9645 (not meaningful at 3.5 % prevalence; shown for completeness) |
| Alert rate | 3.78 % |
| Average precision (PR-AUC) | 0.5506 (0.5506197344626254) |
| ROC-AUC | 0.9052 (0.9051527755720846) |
| Illustrative baseline cost | 165,900 CU (**illustrative cost units, not money**) |

In plain words: at the frozen threshold, about **half of the alerts** carry the fraud label, and the model flags about
**53 % of the labelled-fraud transactions** in the test period, while alerting on about 2 % of non-fraud transactions.

## Provenance chain

1. **Phase 4** stored the test predictions (`BFI_v2_FINAL_test_preds.csv`) and the threshold (`BFI_v2_model_config.json`).
2. **Phase 7** computed the metrics with its `metrics_engine` and released them in `outputs/metrics.json` and the cost
   scenarios in `cost_scenarios.csv`.
3. **Phase 9** recomputed every value above through the Phase 8 bridge (`bfi9/phase8.py` → Phase 7 `metrics_engine`) and
   compared it with the Phase 7 release: **17 of 17 values identical (absolute difference 0)**. The comparison table is
   [`docs/evidence/model_metrics_phase7_vs_recomputed.csv`](evidence/model_metrics_phase7_vs_recomputed.csv).
4. On **2026-10-31** the confusion counts, precision, recall, AP and ROC-AUC were recomputed again in the final release
   runtime and matched the same values.

## How to read these numbers responsibly

- **Scores are uncalibrated risk scores, not probabilities.** A score of 0.3 does not mean a 30 % chance of fraud.
- **An alert is a review signal, never confirmed fraud.** Labels are chargeback-derived.
- **The test split has been used.** Any further threshold exploration in the app runs on the **validation** split only and
  is labelled exploratory (in-sample for the threshold choice, so optimistic).
- **Feature availability is unverified.** 68.08 % of total mean |SHAP| sits on C/D/M/V/dist feature families whose
  availability at decision time is not documented by the dataset. Real-world performance could be lower.
- **No calendar dates exist.** `TransactionDT` is seconds from an undisclosed reference; only relative days are used.
- **Costs are illustrative.** No measured business costs exist; the cost simulator uses labelled assumptions.
- **Single dataset, single period.** No external validation set, no drift monitoring on live data.
- **Phase 6 v1.1 and Phase 7 folders are RECONSTRUCTED from hash-verified files**, not the original release archives (see
  [LIMITATIONS.md](LIMITATIONS.md)). The metrics engine and stored outputs used here are among the verified files.

## Test evidence (from the private Colab runtime, 2026-10-31)

| Suite | Result |
|---|---|
| Phase 9 application suite (full environment with licensed artifacts) | 126 tests: 125 passed, 1 failed (`test_01_protected_hashes_unchanged`: a pre-existing runtime-file hash check, identical on the untouched original release) |
| Headless end-to-end page renders | 28 / 28 passed |
| Phase 8 suite | 65 passed, 1 failed |
| Phase 7 (reconstructed) suite | 48 passed, 2 failed (release-validation tests that need the lost original files) |
| Phase 6 v1.1 (reconstructed) suite | 49 passed, 1 failed, 2 skipped |
| Phase 6 v1.0 suite | 18 passed, 1 skipped |
| Phase 5 suite | 12 / 12 passed |

## Tests of the code published in this repository (2026-10-31 UTC)

| Run | Environment | Result |
|---|---|---|
| Full suite, no deselection | Private Colab runtime with the licensed artifacts (`BFI_ROOT=/content`) | 132 tests: **131 passed, 1 skipped, 0 failed**. The skip is `test_01_protected_hashes_unchanged`, which needs the private Stage 1 hash baseline that is not published. |
| CI mode (`BFI_PUBLIC_CI=1`) | Fresh virtualenv, pinned requirements installed from PyPI, no licensed data | 132 collected: **93 passed, 2 skipped, 37 deselected, 0 failed**; pipeline smoke run on the synthetic example: OK |

The 37 deselected tests all failed in a clean copy only because the private bundle is absent; each one and its failure
reason is listed in [`package_meta/CI_DESELECTED_TESTS.csv`](../package_meta/CI_DESELECTED_TESTS.csv). The 2 skips in CI
mode are tests that skip themselves when the private baseline or reconstruction record is absent.

What GitHub Actions runs is described in the README section *Testing and CI*.
