# Security and privacy

**Scope.** This is a single-user research/portfolio application. It is **not** production security: there are no user
accounts, and reviewer actions are gated by one shared code.

## Reporting a problem

If you find a security issue or personal data in this repository, please open a GitHub issue **without** including the
sensitive value itself, or contact the repository owner through their GitHub profile. Do not test against systems you do
not own.

## What the application does

| Area | Control |
|---|---|
| Complaint input | Validated per field with readable errors. Full card numbers are refused as references; only the last 4 characters of any reference are stored. Card/account-like digit runs and OTP/CVV/PIN/password values are removed from free text before storage. |
| Contact details | Optional, stored locally, shown masked, never exported. Exports also drop descriptions and notes. |
| Evidence uploads | PDF/PNG/JPG/TXT only, ≤ 5 MB, ≤ 3 per complaint; extension and magic-byte check; UTF-8 check for TXT; sanitised filename; resolved-path containment check; files are never executed or rendered as HTML. |
| Database | SQLite through `bfi9/store.py` with parameterised queries only (including IN-lists); foreign keys on. |
| Ingestion | Requires the full model schema, validates IDs, amounts and times per row, caps batch size (5,000), and records counts and rejection reasons only. |
| Reviewer actions | `BFI9_REVIEWER_CODE` read from the environment and compared with `hmac.compare_digest`. Without it, reviewer actions are disabled. |
| Deserialisation | No pickle/joblib loading of user input. The model is read through Phase 8's hash-verified links. |
| Logging | Diagnostics are redacted and contain no complaint text or personal data. |
| External calls | No LLM/API calls (Phase 8 LLM disabled). Complaints are never forwarded to police, banks, RBI or government systems. The Global Fraud Intelligence page fetches public regulator feeds only when you press refresh. |
| Network exposure | Streamlit with XSRF protection on and usage statistics off. On Colab the app is reached only through Colab's authenticated kernel proxy; no public tunnel (ngrok/cloudflared) is used or documented. |

## Configuration and secrets

- No secrets are needed to run the app. Every setting is an environment variable documented in `.env.example`
  (placeholders only). The app does not read a `.env` file; never commit one.
- `.gitignore` excludes `.env*` (except the example), keys, credential JSON files, `kaggle.json`, runtime databases,
  logs, evidence uploads, caches, archives and data/model artifact formats.

## Publication audit (how this repository was assembled)

The repository was built from a verified release archive by **selecting** files, never by uploading the whole project.

1. Every file in the source archive was listed with its size, type and a publication decision
   (`package_meta/PUBLICATION_AUDIT.csv`). Files not published are listed with the reason in
   `package_meta/EXCLUDED_FILES.csv` (no secret values are recorded in either file).
2. Excluded by rule: licensed IEEE-CIS data and anything row-level derived from it (feature store, stored predictions,
   column profiles with example values); model artifacts; BFI v1 datasets with undocumented licences; runtime databases,
   complaint/case records, evidence uploads, audit and diagnostic logs; caches and bytecode; archives (`.zip`); Colab
   restoration tooling; personal interview-preparation notes; historical build evidence that embeds runtime paths.
3. All published files were scanned **locally** (no online scanning service) for private keys, cloud/API/GitHub/Slack
   tokens, passwords and connection strings, e-mail addresses, phone numbers, card-like digit runs, Google Drive and
   private URLs, and absolute paths. Findings and their resolution are in `PUBLICATION_AUDIT.csv`.
4. The git history contains only the reviewed files (a fresh repository; no earlier history was imported).

If a credential is ever found in this repository, treat it as exposed: revoke/rotate it first, then remove it from the
history.
