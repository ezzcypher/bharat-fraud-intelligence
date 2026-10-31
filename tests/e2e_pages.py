"""Headless render of every page with Streamlit AppTest (no browser needed). Writes one runner script per page."""
import json
import sys
import tempfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1]
PAGES = ["overview", "risk", "explorer", "investigation", "performance", "explain", "costs", "forecasting", "eda", "reports_page", "analyst", "intel", "formulas", "audit"]
RUNNER = """import sys; sys.path.insert(0, {app!r}); sys.path.insert(0, {app!r} + '/tests')
import conftest  # applies the sandbox-only override when (and only when) BFI_DEV_P5_SHA is set
import streamlit as st
from bfi9 import ui
st.session_state.setdefault('theme', {theme!r}); ui.inject_css()
from views import {page}
{page}.render()
"""


def run(theme="light", timeout=600):
    out, tmp = [], Path(tempfile.mkdtemp())
    for p in PAGES:
        f = tmp / f"run_{p}.py"
        f.write_text(RUNNER.format(app=str(APP), theme=theme, page=p))
        at = AppTest.from_file(str(f), default_timeout=timeout).run()
        exc = [e.value for e in at.exception]
        out.append({"page": p, "theme": theme, "status": "PASS" if not exc else "FAIL", "exceptions": exc[:2], "elements": len(list(at.main))})
    return out


if __name__ == "__main__":
    res = run("light") + run("dark")
    print("E2E_RESULTS", json.dumps(res))
    sys.exit(0 if all(r["status"] == "PASS" for r in res) else 1)
