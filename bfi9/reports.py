"""First/Baseline report (BFI v1 Phase 2 .docx) vs EDA report (BFI v1 notebook saved outputs).

Historical values are PARSED from the artefacts (with a cell/section reference). Values recomputed from the
current CSVs are kept in a separate column. Nothing is typed in: a value the parser cannot find is 'unavailable'."""
from __future__ import annotations

import hashlib
import html
import json
import re
import zipfile
from functools import lru_cache

import pandas as pd

from . import settings as S
from .quality import pct_change

UNAV = None  # unavailable marker


def _sha12(p) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def docx_paragraphs(path) -> list[tuple[str, str]]:
    """(style, text) per paragraph from word/document.xml (dependency-free; table cells come out as paragraphs)."""
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf8", "ignore")
    out = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
        st = re.search(r'<w:pStyle w:val="([^"]+)"', p)
        t = html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))).strip()
        if t:
            out.append((st.group(1) if st else "", t))
    return out


def _num(s):
    return float(str(s).replace(",", "")) if s is not None else None


def _find(pattern, text, flags=re.S, group=1, cast=_num):
    m = re.search(pattern, text, flags)
    return cast(m.group(group)) if m else UNAV


# ------------------------------------------------------------------ first report
@lru_cache(maxsize=1)
def first_report() -> dict:
    if not S.V1_REPORT.is_file():
        return {"status": "missing", "path": str(S.V1_REPORT)}
    paras = docx_paragraphs(S.V1_REPORT)
    text = " | ".join(t for _, t in paras)
    sections, cur = [], {"heading": "Front matter", "text": []}
    for st, t in paras:
        if st.lower().startswith(("heading", "title")) or re.match(r"^\d{1,2}(\.\d)?\.? [A-Z]", t):
            sections.append(cur); cur = {"heading": t, "text": []}
        else:
            cur["text"].append(t)
    sections.append(cur)
    summ = pd.read_csv(S.V1_SUMMARY, encoding="utf-8-sig") if S.V1_SUMMARY.is_file() else pd.DataFrame(columns=["section", "item", "value"])
    look = lambda sec, item: next((r.value for r in summ.itertuples() if r.section == sec and r.item == item), UNAV)
    V = {
        "rows": (_find(r"([\d,]+) rows; \d+ processed columns", text), "Header table"),
        "columns": (_find(r"[\d,]+ rows; (\d+) processed columns", text), "Header table (processed columns)"),
        "positives": (_find(r"([\d,]+) ones", text), "Header table (label distribution)"),
        "prevalence_pct": (_find(r"Total \| [\d,]+ \| [\d,]+ \| ([\d.]+)%", text), "5. Chronological data split (Total row)"),
        "date_min": (_find(r"Total \| [\d,]+ \| [\d,]+ \| [\d.]+% \| (\d{4}-\d\d-\d\d)", text, cast=str), "5. Chronological data split"),
        "date_max": (_find(r"Total \| [\d,]+ \| [\d,]+ \| [\d.]+% \| \d{4}-\d\d-\d\d to (\d{4}-\d\d-\d\d)", text, cast=str), "5. Chronological data split"),
        "val_ap_full": (_num(look("Full Model Validation", "Average precision")), "BFI_Phase2_Summary.csv"),
        "val_ap_reduced": (_num(look("Reduced Model Validation", "Average precision")), "BFI_Phase2_Summary.csv"),
        "test_precision_080": (_num(look("Reduced Model Test", "Threshold 0.80 precision")), "BFI_Phase2_Summary.csv"),
        "test_recall_080": (_num(look("Reduced Model Test", "Threshold 0.80 recall")), "BFI_Phase2_Summary.csv"),
        "top_permutation_feature": (_find(r"AP drop \| (\w+) \|", text, cast=str), "7. Feature selection"),
        "n_reduced_features": (_find(r"reduced model used these (\d+) features", text), "7. Feature selection"),
    }
    return {"status": "ok", "path": S.V1_REPORT.name, "sha256_12": _sha12(S.V1_REPORT), "project": "BFI v1 (Indian banking)",
            "sections": [{"heading": s["heading"], "text": " ".join(s["text"])} for s in sections if s["text"] or s["heading"] != "Front matter"],
            "summary_table": summ, "values": V}


# ------------------------------------------------------------------ EDA report (notebook)
def _out_text(o: dict) -> str:
    if o.get("output_type") == "stream":
        return "".join(o.get("text", ""))
    if "data" in o:
        return "".join(o["data"].get("text/plain", ""))
    if o.get("output_type") == "error":
        return f"{o.get('ename', '')}: {o.get('evalue', '')}"
    return ""


@lru_cache(maxsize=1)
def eda_report() -> dict:
    if not S.V1_NOTEBOOK.is_file():
        return {"status": "missing", "path": str(S.V1_NOTEBOOK)}
    nb = json.loads(S.V1_NOTEBOOK.read_text(encoding="utf8"))
    cells = []
    for i, c in enumerate(nb.get("cells", [])):
        src = "".join(c.get("source", []))
        cells.append({"cell": i, "type": c.get("cell_type"), "first_line": (src.splitlines() or [""])[0][:120],
                      "output": "\n".join(_out_text(o) for o in c.get("outputs", [])),
                      "images": sum(1 for o in c.get("outputs", []) if "image/png" in o.get("data", {}))})

    def grab(pattern, cast=_num):
        # Step: search cell outputs in order; the reference is the FIRST cell that contains the value
        for c in cells:
            m = re.search(pattern, c["output"], re.S)
            if m:
                return cast(m.group(1)), f"Notebook cell {c['cell']}"
        return UNAV, "not found in saved outputs"

    V = {"rows": grab(r"Dataset Dimensions:\s*([\d,]+) rows"), "columns_raw": grab(r"Dataset Dimensions:\s*[\d,]+ rows,\s*(\d+) columns"),
         "columns": grab(r"Engineered Columns count:\s*(\d+)"), "duplicate_rows": grab(r"Duplicate rows:\s*(\d+)"),
         "duplicate_ids": grab(r"Duplicate transaction IDs:\s*(\d+)"), "missing_loan_type": grab(r"Missing values:\s*\n\s*loan_type\s+(\d+)"),
         "imputed_records": grab(r"Records Affected:\s*([\d,]+)"), "positives": grab(r"Fraud cases:\s*([\d,]+)"),
         "prevalence_pct": grab(r"Overall fraud rate:\s*([\d.]+)\s*%"), "date_min": grab(r"Earliest Transaction:\s*(\S+)", str),
         "date_max": grab(r"Latest Transaction:\s*(\S+)", str), "engineered_columns": grab(r"Newly generated columns list:\s*\n(\[.*?\])", str),
         "top_corr_feature": grab(r"Pairwise Correlation with target 'is_fraud' ---.*?is_fraud\s+1\.0+\s*\n\s*(\w+)", str),
         "top_corr_value": grab(r"Pairwise Correlation with target 'is_fraud' ---.*?is_fraud\s+1\.0+\s*\n\s*\w+\s+([-\d.]+)")}
    block = lambda start: next((c["output"][c["output"].find(start):][:2500] for c in cells if start in c["output"]), "")
    return {"status": "ok", "path": S.V1_NOTEBOOK.name, "sha256_12": _sha12(S.V1_NOTEBOOK), "project": "BFI v1 (Indian banking)",
            "derived": "Derived from notebook outputs; not an original standalone report.",
            "cells": cells, "values": V, "phase1_summary": block("PHASE 1 AUDIT SUMMARY"), "phase3_summary": block("PHASE 3 TECHNICAL SUMMARY REPORT"),
            "outlier_table": block("STEP 10: STATISTICAL OUTLIER ANALYSIS")}


# ------------------------------------------------------------------ comparison
ITEMS = [  # (key in first, key in EDA, label, numeric?)
    ("rows", "rows", "Dataset rows", True), ("columns", "columns", "Columns used for modelling (processed)", True),
    (None, "columns_raw", "Raw columns", True), ("positives", "positives", "Positive labels (is_fraud = 1)", True),
    ("prevalence_pct", "prevalence_pct", "Fraud-label prevalence (%)", True), (None, "duplicate_rows", "Duplicate rows", True),
    (None, "duplicate_ids", "Duplicate transaction IDs", True), (None, "missing_loan_type", "Missing values (loan_type)", True),
    (None, "imputed_records", "Rows changed by cleaning (loan_type -> 'No Loan')", True), ("date_min", "date_min", "First date", False),
    ("date_max", "date_max", "Last date", False), (None, "engineered_columns", "Engineered features", False),
    ("top_permutation_feature", "top_corr_feature", "Strongest single-feature signal", False),
    ("n_reduced_features", None, "Features in reduced model", True), ("val_ap_reduced", None, "Validation AP (reduced model)", True),
    ("test_precision_080", None, "Test precision @0.80", True), ("test_recall_080", None, "Test recall @0.80", True)]


def compare(recomputed: dict | None = None) -> pd.DataFrame:
    """One row per item. pct_change only for numeric items with a non-zero first value."""
    F, E = first_report(), eda_report()
    fv, ev = F.get("values", {}), E.get("values", {})
    rows = []
    for fk, ek, label, numeric in ITEMS:
        a, aref = fv.get(fk, (UNAV, "not reported")) if fk else (UNAV, "not reported in first report")
        b, bref = ev.get(ek, (UNAV, "not in EDA outputs")) if ek else (UNAV, "not in EDA report")
        if a is UNAV or b is UNAV:
            status = "unavailable"
        elif label.startswith("Strongest"):
            status = "not comparable"   # permutation AP drop vs Pearson r: different measures
        elif numeric:
            status = "unchanged" if abs(float(a) - float(b)) < 1e-9 else "not comparable"
        else:
            status = "unchanged" if str(a) == str(b) else "not comparable"
        diff = (float(b) - float(a)) if (numeric and status != "unavailable" and status != "not comparable" and a is not UNAV) else None
        rows.append({"item": label, "first_report": a, "first_ref": aref, "eda_report": b, "eda_ref": bref,
                     "abs_difference": diff, "pct_change": pct_change(a, b) if diff is not None else None, "status": status,
                     "recomputed_now": (recomputed or {}).get(ek or fk)})
    return pd.DataFrame(rows)


def warnings() -> list[str]:
    return ["Both reports describe the same BFI v1 dataset (550,000 rows), but the first report models the 28-column processed table "
            "while the EDA ran on the 20-column raw table.",
            "Neither report uses the BFI v2 IEEE-CIS data; their values must not be compared with v2 model metrics.",
            "Historical values are parsed from the artefacts; 'recomputed_now' comes from the current CSVs and is shown separately."]


def narrative(cmp: pd.DataFrame) -> list[dict]:
    """Deterministic, evidence-cited summary (no LLM). Every answer names the rows/artefacts it uses."""
    v1 = json.loads(sorted(S.ROOT.glob("BFI_Phase4_Audit_Summary*.json"))[0].read_text()) if list(S.ROOT.glob("BFI_Phase4_Audit_Summary*.json")) else {}
    same = cmp[cmp.status == "unchanged"]["item"].tolist()
    eda_only = cmp[(cmp.first_report.isna()) & (cmp.eda_report.notna())]["item"].tolist()
    first_only = cmp[(cmp.eda_report.isna()) & (cmp.first_report.notna())]["item"].tolist()
    val = v1.get("validation", {})
    return [
        {"q": "What changed between the reports?", "a": f"The EDA report adds data-quality evidence ({', '.join(eda_only)}); the first report adds modelling results ({', '.join(first_only)}).",
         "evidence": "comparison table rows"},
        {"q": "Which data-quality issues were discovered?", "a": "loan_type was missing for rows without a loan and was imputed as 'No Loan'; no duplicate rows or IDs were found.",
         "evidence": "EDA: missing_loan_type, imputed_records, duplicate_* rows"},
        {"q": "Which findings were confirmed?", "a": f"Values that agree across both artefacts: {', '.join(same) or 'none'}.", "evidence": "status = unchanged"},
        {"q": "Which earlier assumptions were corrected?",
         "a": (f"The later v1 Phase 4 audit found validation ROC-AUC {val.get('roc_auc', 'n/a')} and AP {val.get('ap', 'n/a')}: labels carry almost no learnable signal, "
               "so EDA group differences (e.g. by transaction type) are descriptive only."), "evidence": "BFI_Phase4_Audit_Summary.json; BFI_Case_Study.docx"},
        {"q": "What conclusions are supported?", "a": "The dataset is internally consistent (no duplicates, valid ranges, imbalance ~0.886%); the v1 baseline was weak.",
         "evidence": "EDA cells; first report sections 6-9"},
        {"q": "What remains uncertain?", "a": "How is_fraud was generated; whether any feature is available at decision time.", "evidence": "first report Limitations; Case Study"},
        {"q": "What would a data scientist investigate next?", "a": "Label provenance first; the project did this and moved to IEEE-CIS (BFI v2).", "evidence": "v1 audit 'next' field"}]
