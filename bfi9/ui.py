"""Design tokens, theme switching and reusable UI pieces (KPI card with evidence, states, chips).

Theme: one session value ('light'|'dark') drives (1) Streamlit's native theme options, synced at runtime,
(2) CSS variables for our components, (3) the Plotly template (charts.template()). Risk is never colour-only:
every band carries a text label and a shape glyph."""
from __future__ import annotations

import html

import streamlit as st

# Step 1: tokens (status colours from the validated reference palette; text never wears a series colour).
TOKENS = {
    # warm white / charcoal / slate with a restrained emerald accent; dark = deep charcoal (own steps, not an inversion)
    "light": {"bg": "#f7f6f2", "surface": "#ffffff", "surface2": "#f1f0eb", "border": "#e4e2db", "text": "#1d2024", "muted": "#5c626b",
              "accent": "#0f7b5f", "chart": "#fdfdfb", "grid": "#ebeae5"},
    "dark": {"bg": "#121314", "surface": "#191a1c", "surface2": "#212225", "border": "#2c2e32", "text": "#ecebe7", "muted": "#a2a6ad",
             "accent": "#34b38a", "chart": "#191a1c", "grid": "#2a2c30"},
}


STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
BAND = {"Low": ("good", "●"), "Medium": ("warning", "▲"), "High": ("serious", "◆"), "Critical": ("critical", "■")}
EVIDENCE = {"measured": "Measured from project data", "derived": "Derived by formula from measured values", "assumed": "Assumption",
            "illustrative": "Illustrative (not a real-world value)", "unknown": "Unknown / not available", "exploratory": "Exploratory sensitivity"}


def theme() -> str:
    return st.session_state.get("theme", "light")


def sync_native_theme() -> None:
    """Make Streamlit's own widgets follow the toggle (process-wide option; single-user Colab app)."""
    t = TOKENS[theme()]
    want = {"theme.base": theme(), "theme.backgroundColor": t["bg"], "theme.secondaryBackgroundColor": t["surface2"],
            "theme.textColor": t["text"], "theme.primaryColor": t["accent"]}
    changed = False
    for k, v in want.items():
        if st._config.get_option(k) != v:
            st._config.set_option(k, v)
            changed = True
    if changed:
        st.rerun()  # one extra run so the browser receives the new theme; next run finds options equal (no loop)


def inject_css() -> None:
    t = TOKENS[theme()]
    st.markdown(f"""<style>
:root {{ --bg:{t['bg']}; --surface:{t['surface']}; --surface2:{t['surface2']}; --border:{t['border']}; --text:{t['text']}; --muted:{t['muted']}; --accent:{t['accent']}; }}
html, body, .stApp, button, input, textarea, select {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
.stApp {{ background: var(--bg); color: var(--text); }}
section[data-testid="stSidebar"] {{ background: var(--surface); border-right: 1px solid var(--border); }}
[data-testid="stSidebarNavLink"] {{ border-radius: 8px; transition: background .12s ease; }}
[data-testid="stSidebarNavLink"][aria-current="page"] {{ background: var(--surface2); box-shadow: inset 2px 0 0 var(--accent); }}
.block-container {{ padding-top: 2.6rem; padding-bottom: 3rem; max-width: 1360px; }}
h1, h2, h3, h4, h5 {{ letter-spacing: -.01em; }}
h5 {{ font-size: .95rem; font-weight: 600; color: var(--text); margin-top: .6rem; }}
*:focus-visible {{ outline: 2px solid var(--accent) !important; outline-offset: 2px; border-radius: 6px; }}
.bfi-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; height: 100%; transition: border-color .15s ease; }}
.bfi-card:hover {{ border-color: var(--muted); }}
.bfi-k-label {{ font-size: .76rem; color: var(--muted); letter-spacing: .02em; min-height: 1.1rem; overflow-wrap: anywhere; }}
.bfi-k-value {{ font-size: 1.35rem; font-weight: 600; color: var(--text); margin: 2px 0; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; line-height: 1.25; }}
.bfi-k-foot {{ font-size: .72rem; color: var(--muted); }}
.bfi-tag {{ display:inline-block; font-size:.66rem; padding:0 6px; margin-right:4px; border-radius:999px; border:1px solid var(--border); color:var(--muted); background:var(--surface2); }}
.bfi-chip {{ display:inline-block; font-size:.74rem; padding:2px 9px; margin:2px 4px 2px 0; border-radius:999px; background:var(--surface2); border:1px solid var(--border); color:var(--text); }}
.bfi-def {{ margin-top:6px; font-size:.72rem; color:var(--muted); }}
.bfi-def summary {{ cursor:pointer; list-style:none; border-radius:4px; }}
.bfi-def summary::-webkit-details-marker {{ display:none; }}
.bfi-def div {{ margin-top:4px; color:var(--text); line-height:1.35; }}
.bfi-band {{ font-weight:600; font-size:.8rem; }}
.bfi-note {{ border-left: 3px solid var(--accent); background: var(--surface); padding: 8px 12px; border-radius: 0 8px 8px 0; color: var(--text); font-size:.88rem; }}
.bfi-warn {{ border-left: 3px solid {STATUS['serious']}; background: var(--surface); padding: 8px 12px; border-radius: 0 8px 8px 0; color: var(--text); font-size:.88rem; }}
.bfi-title {{ font-size:1.4rem; font-weight:650; color:var(--text); margin-bottom:0; letter-spacing:-.015em; }}
.bfi-sub {{ color: var(--muted); font-size:.88rem; margin-top:2px; margin-bottom:.4rem; }}
.bfi-badge {{ display:inline-block; font-size:.7rem; font-weight:650; letter-spacing:.06em; padding:2px 8px; border-radius:6px; border:1px solid; margin:2px 0 6px; }}
.bfi-badge.demo {{ color:{STATUS['warning'] if theme() == 'dark' else '#8a5a00'}; border-color:{STATUS['warning']}; background:transparent; }}
.bfi-badge.info {{ color:var(--muted); border-color:var(--border); }}
.bfi-pill {{ display:inline-block; font-size:.78rem; font-weight:600; padding:3px 10px; border-radius:999px; border:1px solid var(--border); background:var(--surface2); color:var(--text); }}
[data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {{ border-radius: 10px; }}
div[data-testid="stForm"] {{ border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }}
@media (max-width: 1100px) {{ .bfi-k-value {{ font-size: 1.15rem; }} .block-container {{ padding-left: 1.2rem; padding-right: 1.2rem; }} }}
</style>""", unsafe_allow_html=True)


def header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="bfi-title">{html.escape(title)}</div><div class="bfi-sub">{html.escape(subtitle)}</div>', unsafe_allow_html=True)


def kpi(label: str, value, definition: str, source: str, scope: str, evidence: str = "measured", fmt: str = "{:,}", foot: str = "") -> None:
    """KPI card. Definition/source/scope sit in a native <details> disclosure (keyboard-accessible, no extra widget row)."""
    v = "—" if value is None else (fmt.format(value) if isinstance(value, (int, float)) else str(value))
    e = html.escape
    st.markdown(f'<div class="bfi-card"><div class="bfi-k-label">{e(label)}</div><div class="bfi-k-value">{e(v)}</div>'
                f'<div class="bfi-k-foot"><span class="bfi-tag" title="{e(EVIDENCE.get(evidence, evidence))}">{e(evidence)}</span> {e(foot or scope)}</div>'
                f'<details class="bfi-def"><summary>ⓘ definition</summary><div>{e(definition)}<br><b>Source:</b> {e(source)}<br><b>Scope:</b> {e(scope)}'
                f'<br><b>Evidence:</b> {e(EVIDENCE.get(evidence, evidence))}</div></details></div>', unsafe_allow_html=True)


def band_label(band: str) -> str:
    role, glyph = BAND.get(str(band), ("warning", "?"))
    return f'<span class="bfi-band" style="color:{STATUS[role]}">{glyph}</span> <span class="bfi-band">{html.escape(str(band))}</span>'


def chips(items: list[str]) -> None:
    st.markdown("".join(f'<span class="bfi-chip">{html.escape(c)}</span>' for c in items) or '<span class="bfi-chip">No filters</span>', unsafe_allow_html=True)


def note(text: str, warn: bool = False) -> None:
    st.markdown(f'<div class="{"bfi-warn" if warn else "bfi-note"}">{text}</div>', unsafe_allow_html=True)


def unavailable(what: str, why: str) -> None:
    st.info(f"**{what} is unavailable.** {why}", icon="ℹ️")


def restricted(why: str) -> None:
    st.warning(f"**Restricted in investigation mode.** {why}", icon="🔒")


def provenance_banner() -> None:
    """Shown on every page while a Phase 6/7 dependency is a reconstruction (marker file present in its folder)."""
    from bfi9 import provenance
    rec = [r for r in provenance.status() if r["reconstructed"]]
    if rec:
        st.warning(f"**{provenance.LABEL}:** " + "; ".join(f"{r['dependency']} ({len(r['missing_not_recreated'])} original artefacts missing, incl. the release ZIP)" for r in rec)
                   + ". Rebuilt only from files whose SHA-256 matches the original release records; release validation is incomplete. "
                   "Details: Data Sources & Audit → Dependency provenance.", icon="⚠️")


def esc(text) -> str:
    return html.escape(str(text))


def badge(text: str, kind: str = "info", title: str = "") -> None:
    """Text badge (never colour-only). kind 'demo' marks replayed/synthetic data everywhere it appears."""
    st.markdown(f'<span class="bfi-badge {kind}" title="{esc(title)}">{esc(text)}</span>'
                + (f' <span class="bfi-k-foot">{esc(title)}</span>' if title else ""), unsafe_allow_html=True)


PILL = {"Submitted": "○", "Under Review": "◐", "Awaiting Information": "◔", "Resolved": "●", "Closed": "■"}


def status_pill(status: str) -> str:
    return f'<span class="bfi-pill">{PILL.get(status, "•")} {esc(status)}</span>'
