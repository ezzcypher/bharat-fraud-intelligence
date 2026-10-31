# Phase 9: Metrics and Formulas

The authoritative list is `outputs/formula_explorer/formula_catalogue.{csv,json}`, generated from `bfi9/formulas.py`. It is also browsable on the **Formula & Solution Explorer** page.

Each entry has sections A–K:
- A: problem
- B: why it is needed
- C: notation
- D: symbols
- E: worked example
- F: Python
- G: output
- H: dashboard use
- I: limitations
- J: interview answer
- K: source

## Origins
| Origin | Meaning | Implementation rule |
|---|---|---|
| existing | Already implemented in Phases 4–8 | Called live through the Phase 8 bridge (`phase8.p7()` → Phase 7 `metrics_engine` / `cost_engine`). Never copied. |
| historical | Documented in a BFI v1 artefact (Phase 2 report, notebook) | Reproduced for teaching; source cited. |
| new | Introduced in Phase 9 | FDR, MCC, t-interval, returns / abnormal returns / CAR, forecasting baselines, MAE/MAPE, PSI, zero-safe % change. Tests compare each against a reference library (sklearn, scipy) or against the identity it must satisfy. |

## The project's authoritative formulas
**Decision rule:** alert ⇔ score ≥ t, with t = 0.12379763346033115. t is read from `BFI_v2_model_config.json`, never typed in.

**Cost model (Phase 7):**

Total = FP·C_FP + FN·C_FN + N_reviewed·C_review + TP_stopped·C_intervention

The simpler FP·C_FP + FN·C_FN appears only as a general illustration.

**Explanations:**
- f(x) = φ₀ + Σφⱼ on the LightGBM **log-odds** scale.
- score = σ(f(x)).
- Additivity is checked per explanation.

**Bayes check:** P(label | alert) = TPR·π / (TPR·π + FPR(1−π)). On the test split this equals precision exactly. A test asserts the equality.

## Verified project values (test split, model A)
These are recomputed through Phase 7 at runtime. Test 3 asserts they equal Phase 7 `metrics.json`.
- **Counts:** TP 1,713 · FP 1,782 · TN 87,432 · FN 1,500.
- **Threshold metrics:** precision 0.4901 · recall 0.5331 · F1 0.5107.
- **Ranking metrics:** AP 0.5506 · ROC-AUC 0.9052.
- **Illustrative baseline cost:** 165,900 CU (test 4 asserts it equals Phase 7 `cost_scenarios.csv`).
