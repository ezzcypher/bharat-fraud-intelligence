"""Exports: CSV (no index column), Markdown, standalone HTML. Every report carries source, scope and timestamp.
PDF: produced from the HTML by the browser's print dialog (no extra PDF dependency is installed - documented)."""
from __future__ import annotations

import datetime as dt
import html
import re

import pandas as pd

from . import settings as S

LABEL_COLS = {"isFraud", "observed_dataset_label", "label", "outcome"}


def _guard(df: pd.DataFrame) -> pd.DataFrame:
    """Investigation-mode exports never contain labels, whatever the caller passed."""
    return df if S.MODE == "evaluation" else df.drop(columns=[c for c in df.columns if c in LABEL_COLS])


def csv_bytes(df: pd.DataFrame) -> bytes:
    return _guard(df).to_csv(index=False).encode("utf-8")


def stamp() -> str:
    return f"Generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M UTC} · BFI v2 Phase 9 · mode: {S.MODE}"


def redact(text: str) -> str:
    """Strip label sentences in investigation mode and anything that looks like a secret."""
    text = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+", r"\1: [REDACTED]", text)
    if S.MODE != "evaluation":
        text = re.sub(r"(?i)[^\n.]*\b(isFraud|observed dataset label)\b[^\n.]*[.\n]?", "", text)
    return text


def markdown_report(title: str, sections: list[tuple[str, str]], sources: list[str], scope: str) -> str:
    md = [f"# {title}", "", f"_{stamp()}_", f"**Scope:** {scope}", ""]
    for h, body in sections:
        md += [f"## {h}", body, ""]
    md += ["## Sources", *[f"- {s}" for s in sources], "",
           "> Model outputs are uncalibrated scores from an offline research model. A prediction is not confirmed fraud. Illustrative costs are not real money."]
    return redact("\n".join(md))


def html_report(md_text: str, title: str) -> str:
    """Self-contained HTML (print to PDF from the browser)."""
    body = []
    for line in md_text.splitlines():
        e = html.escape(line)
        body.append(f"<h1>{e[2:]}</h1>" if line.startswith("# ") else f"<h2>{e[3:]}</h2>" if line.startswith("## ")
                    else f"<li>{e[2:]}</li>" if line.startswith("- ") else f"<p>{e}</p>" if line.strip() else "")
    css = "body{font-family:system-ui,sans-serif;max-width:860px;margin:32px auto;color:#14161a;line-height:1.5}h1{font-size:22px}h2{font-size:16px;margin-top:22px;border-bottom:1px solid #e3e5ea}p,li{font-size:13px}"
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{css}</style></head><body>{''.join(body)}</body></html>"


def table_md(df: pd.DataFrame, max_rows: int = 40) -> str:
    d = _guard(df).head(max_rows)
    try:
        return d.to_markdown(index=False)          # needs 'tabulate'
    except ImportError:
        return "```\n" + d.to_string(index=False) + "\n```"
