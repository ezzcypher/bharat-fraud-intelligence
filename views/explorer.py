"""3. Transaction Explorer - search, sort, paginate, select, export (labels only in evaluation mode)."""
import streamlit as st

from bfi9 import exporters, phase8, ui
from bfi9 import settings as S

from . import common

COLS = ["split", "day", "score", "decision", "risk_band", "amount_usd", "ProductCD", "card4", "card6", "P_emaildomain", "identity_present", "n_missing_inputs", "isFraud"]


def render():
    ui.header("Transaction Explorer", "Validation + test transactions scored by the frozen model · one row per TransactionID")
    if not common.require_v2():
        return
    d = common.filter_bar(common.frame())
    cols = [c for c in COLS if c in d]
    a, b, c = st.columns([2, 1, 1])
    sort = a.selectbox("Sort by", ["score", "TransactionID"] + [x for x in ("amount_usd", "day", "n_missing_inputs") if x in d])
    desc = b.toggle("Descending", True)
    size = c.selectbox("Rows per page", [25, 50, 100], 1)
    v = d.reset_index().sort_values(sort, ascending=not desc)
    pages = max(1, -(-len(v) // size))
    page = st.number_input(f"Page (1–{pages})", 1, pages, 1)
    view = v.iloc[(page - 1) * size: page * size][["TransactionID"] + cols]
    ev = st.dataframe(view, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                      column_config={"score": st.column_config.ProgressColumn("score", min_value=0, max_value=1, format="%.4f"),
                                     "amount_usd": st.column_config.NumberColumn("amount (USD)", format="%.2f")})
    st.caption("Lineage: TransactionID → Phase 4 stored score → frozen threshold → Phase 5 band; attributes from the Phase 8 validated feature store; "
               "identity flag from train_identity.csv. " + ("Labels hidden (investigation mode)." if S.MODE != "evaluation" else "Labels shown (evaluation mode)."))
    st.download_button("Download filtered rows (CSV)", exporters.csv_bytes(v[["TransactionID"] + cols]), "bfi_v2_filtered_transactions.csv", "text/csv")
    sel = ev.selection.rows if ev and hasattr(ev, "selection") else []
    if sel:
        tid = int(view.iloc[sel[0]]["TransactionID"])
        st.session_state["selected_tid"] = tid
        with st.container(border=True):
            st.markdown(f"**Transaction {tid}** · open *Transaction Investigation* for the explanation")
            st.json(phase8.transaction(tid), expanded=False)
