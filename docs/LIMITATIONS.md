# Known limitations

Nothing here has been removed to make the project look better. If a limitation is fixed, it is moved to a "resolved"
note with evidence, not deleted.

## Status of the system

- **Not production-ready.** This is an offline research and portfolio dashboard. It was developed and demonstrated on
  Google Colab, which is a development host, not a production server.
- **No real-time data source.** No bank, UPI, card-network, payment-gateway or government feed is connected. *Live
  Monitoring* shows **DEMO DATA** (historical IEEE-CIS test rows replayed with a simulated arrival time) or rows ingested
  from a user-named, **unverified** source.
- **Complaints are local only.** Registering a complaint in this app is not a police, bank, RBI or government
  complaint. Nothing is forwarded anywhere.
- **Single shared reviewer code, no user accounts.** `BFI9_REVIEWER_CODE` gates reviewer actions in a single-user demo.
  It is not multi-user authentication or production access control.
- **Local persistence.** Events, cases, notes, evidence and diagnostics live in `outputs/runtime/` (SQLite + files). On
  Colab they are lost on a runtime reset unless `BFI9_OPS_DB` and the runtime folder are moved to durable storage that
  you configure and test.

## Model and data

- **Scores are uncalibrated risk scores**, not probabilities. Risk bands are provisional (Phase 5).
- **Labels are chargeback-derived** (IEEE-CIS `isFraud`), not confirmed investigation outcomes. An alert is a review
  signal, never confirmed fraud.
- **Feature availability:** 68.08 % of total mean |SHAP| sits on C/D/M/V/dist features whose decision-time availability
  is unverified.
- **The test set has been used.** Threshold exploration runs on validation only and is labelled exploratory.
- **Costs are illustrative units (CU).** No measured business costs exist.
- **No calendar time.** IEEE-CIS has only `TransactionDT` (seconds from an undisclosed reference), so trends and
  forecasts use relative days and are transaction-volume baselines, never fraud forecasts.
- **Label-based views:** in investigation mode, label-based metrics are shown for full splits only. Filtered label
  metrics need evaluation mode, which is a launch setting.
- **BFI v1 labels are near-random** (v1 audit: validation ROC-AUC 0.528). v1 appears only on the EDA and Report pages and
  is never joined with IEEE-CIS rows.

## Provenance of earlier phases

- **Phase 6 v1.1 and Phase 7 are RECONSTRUCTED — NOT ORIGINAL RELEASE.** Their original release archives were lost in a
  Colab runtime reset. The folders were rebuilt only from files whose SHA-256 equals the hash recorded by the genuine
  releases (Phase 6: 17 of 19 files; Phase 7: 29 of 46 files plus its genuine `manifest.json`).
- 64 recorded originals were searched by SHA-256 across every available file and archive: 17 have byte-identical
  content elsewhere, **47 are not recoverable** and were not recreated (Phase 6 `TEST_REPORT.md` and
  `REMEDIATION_LOG.md`; the Phase 7 notebook, 13 figures, 3 reports and `SHA256SUMS.txt`).
- Consequences: the original release checksums are not reproduced; release-validation tests fail in Phases 6 v1.1, 7,
  8 and 9 for that reason; release validation is incomplete. The dashboard uses only verified code and outputs.
- **Phase 5 v1.2 archive is missing.** The dashboard uses the verified v1.0 artifacts.
- **Phase 6 browser click-through test is still pending** from Phase 6.
- **The historical 310-file baseline is not verified** (no authoritative 310-row manifest exists).

## This public repository

- **Licensed data, the feature store and the model are not included.** Without the private artifact bundle, 10 pages
  (Executive Overview, Live Monitoring, Fraud & Risk Analytics, Transaction Explorer, Transaction Investigation, Feature
  Explainability, Model Performance, Cost & Decision Simulator, Forecasting & Scenarios, AI Fraud Analyst, plus the
  reproducibility tab of Data Sources & Audit) show "This page is unavailable" with the reason, and EDA & Data Quality
  says the BFI v1 data is absent. Register Complaint, Case Management, Formula & Solution Explorer, Report Comparison and
  Global Fraud Intelligence (after a feed refresh) render without it, as does the synthetic pipeline. This was checked by
  rendering every page headlessly in a clean copy of the repository.
- **CI does not re-measure the model.** It runs the tests that need no licensed artifacts; the deselected tests are listed
  with reasons in `package_meta/CI_DESELECTED_TESTS.csv`. Model metrics are historical (see
  [MODEL_EVALUATION.md](MODEL_EVALUATION.md)).
- **Screenshots** in `docs/screenshots/` were captured from the private Colab runtime (with the bundle present) and
  cropped to aggregate views; they contain no transaction-level rows.

## Other features

- **Global Fraud Intelligence coverage:** only providers with a verified machine-readable feed are connected: SEC (needs a
  declared User-Agent), FTC, RBI and SEBI. INTERPOL, IC3, CERT-In, I4C, Europol, FCA, ESMA and FinCEN are listed but not
  connected. FTC feed URLs returned HTTP 404 from Colab on 2026-10-30 and are shown as unavailable.
- **Intelligence counts reflect publishing activity, not fraud volume.** Classification and geography rules are
  keyword-based; ambiguous items stay "Unclassified" or "relation unverified". Analysis is rule-based and is not
  incident-response or legal advice.
- **Personal data in feeds:** government ID patterns and likely names of private individuals are redacted with
  heuristic rules that prefer over-redaction; unusual name formats can still slip through.
- **Market data:** Stooq end-of-day prices; tickers only when printed in the source text; event studies are single-event,
  association only, and flag confounding events within ±5 days.
- **LLM disabled.** The AI Fraud Analyst is deterministic (Phase 8 decision).
- **Theme:** Streamlit theme options are process-wide. The in-app dark-theme toggle was not verified in a real browser
  (headless page renders in both themes were).
- **PDF export:** HTML reports are printed to PDF from the browser; no PDF library is used.
- **Browser coverage:** headless Chromium at 990 px and 1440 px, light and dark. Real phones, other browsers and screen
  readers were not tested. One chart axis title (Explainability, "Importance share by availability status") is clipped
  at 990 px, as in the original release.
- **Viewing in Colab:** only through Colab's authenticated port proxy, with CORS on. No public tunnel is used or supported.
