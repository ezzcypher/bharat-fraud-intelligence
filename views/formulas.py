"""13. Formula & Solution Explorer - problem → formula → real code → result → limits, for every phase."""
import json

import pandas as pd
import streamlit as st

from bfi9 import exporters, formulas as FX, ui

ORIGIN = {"existing": "Existing implementation (called live)", "historical": "Documented in a BFI v1 artefact", "new": "NEW in Phase 9"}


def render():
    ui.header("Formula & Solution Explorer", f"{len(FX.CATALOGUE)} formulas from Phases 1–9 · each linked to its real source")
    a, b, c = st.columns([2, 2, 1])
    q = a.text_input("Search", placeholder="precision, SHAP, CAR, prevalence…")
    cat = b.selectbox("Category", ["All"] + FX.CATEGORIES)
    org = c.selectbox("Origin", ["All", "existing", "historical", "new"])
    items = [f for f in FX.CATALOGUE if (cat == "All" or f["category"] == cat) and (org == "All" or f["origin"] == org)
             and (not q or q.lower() in (f["name"] + f["problem"] + f["source"]).lower())]
    if not items:
        return ui.unavailable("Formulas", "nothing matches the search.")
    f = next(x for x in FX.CATALOGUE if x["id"] == st.selectbox("Formula", [x["id"] for x in items], format_func=lambda i: next(x["name"] for x in FX.CATALOGUE if x["id"] == i)))
    st.markdown(f"### {f['name']}  \n<span class='bfi-tag'>{f['category']}</span> <span class='bfi-tag'>{ORIGIN[f['origin']]}</span>", unsafe_allow_html=True)
    l, r = st.columns([3, 2])
    with l:
        st.markdown(f"**A · Problem.** {f['problem']}\n\n**B · Why it is needed.** {f['why']}")
        st.markdown("**C · Notation**")
        st.latex(f["latex"])
        if f["symbols"]:
            st.markdown("**D · Symbols.** " + "; ".join(f"`{k}` = {v}" for k, v in f["symbols"].items()))
        st.markdown("**F · Python** (copy with the icon at the top-right of the block)")
        st.code(f["code"], language="python")
        st.markdown(f"**H · Dashboard use.** {f['dashboard']}\n\n**I · Limitations.** {f['limitations']}\n\n**J · Interview answer.** {f['interview']}\n\n**K · Source.** {f['source']}")
    with r:
        st.markdown("**E · Worked example** (educational inputs; changing them never touches the model or saved results)")
        key = f"fx_{f['id']}"
        if st.button("Reset example", key=f"reset_{key}"):
            for k in f["inputs"]:
                st.session_state.pop(f"{key}_{k}", None)
        vals = {k: st.number_input(k, value=float(v), key=f"{key}_{k}", format="%.6g") for k, v in f["inputs"].items()}
        try:
            out = f["run"](**vals)
            st.markdown("**G · Output**")
            st.code(json.dumps(out, default=lambda o: float(o) if hasattr(o, "__float__") else str(o), indent=1) if not isinstance(out, (int, float, str)) else repr(out))
        except Exception as e:
            st.error(f"{type(e).__name__}: {e}")
        if f.get("project"):
            pv = f["project"]()
            st.markdown(f"**Real project value (test split, model A):** {pv if pv is None else round(pv, 6)}")
    rec = pd.DataFrame(FX.export_records())
    a, b = st.columns(2)
    a.download_button("Download catalogue (CSV)", exporters.csv_bytes(rec), "formula_catalogue.csv", "text/csv")
    b.download_button("Download catalogue (JSON)", json.dumps(FX.export_records(), indent=1).encode(), "formula_catalogue.json", "application/json")
