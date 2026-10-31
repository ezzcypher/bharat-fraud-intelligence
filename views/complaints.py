"""Register Complaint - fraud complaint form with validation, masking and optional evidence upload (local storage only)."""
import datetime as dt

import streamlit as st

from bfi9 import cases, ui

from . import common


def render():
    ui.header("Register a Fraud Complaint", "Creates a tracked case in this BFI workspace · nothing is sent to any outside organisation")
    ui.note("<b>This is not an official complaint.</b> Registering here does not report the incident to the police, your bank, the RBI or any "
            "government portal, and nothing is forwarded automatically. To report cyber fraud in India use the National Cyber Crime "
            "Reporting Portal (cybercrime.gov.in) or helpline 1930, and contact your bank immediately.", warn=True)
    st.caption("Never enter a full card number, CVV, OTP, UPI PIN, password or net-banking login. Card/account-like numbers in the "
               "description are removed automatically. Stored locally in this Colab runtime; lost if the runtime is reset.")
    with st.form("complaint", clear_on_submit=False):
        a, b = st.columns(2)
        cat = a.selectbox("Complaint category *", cases.CATEGORIES, index=None, placeholder="Choose a category")
        amt = b.number_input("Approximate amount (INR, optional)", min_value=0.0, max_value=1e9, value=None, step=100.0, format="%.2f")
        a, b = st.columns(2)
        d = a.date_input("Incident date *", value=None, max_value=dt.date.today(), format="DD/MM/YYYY")
        t = b.time_input("Incident time (approx.) *", value=None, step=300)
        a, b = st.columns(2)
        ref = a.text_input("Payment / transaction reference (optional)", max_chars=40,
                           help="Bank or UPI transaction ID, or the last 4 card digits. Only the last 4 characters are stored.")
        contact = b.text_input("Contact e-mail or mobile (optional)", max_chars=120,
                               help="Only needed if a reviewer should reach you. Stored locally and shown masked; never exported.")
        desc = st.text_area("What happened? *", max_chars=2000, height=140, placeholder="When, how you were contacted, what was paid or taken, what you have done since…")
        files = st.file_uploader("Supporting evidence (optional · PDF, PNG, JPG, TXT · max 3 files, 5 MB each)", type=["pdf", "png", "jpg", "jpeg", "txt"],
                                 accept_multiple_files=True)
        ok = st.checkbox("I understand this registers a case in BFI only and is not an official police, bank or government complaint, "
                         "and that the information I provided is accurate to the best of my knowledge. *")
        go = st.form_submit_button("Submit complaint", type="primary")
    if not go:
        return
    when = dt.datetime.combine(d, t, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30))) if d and t else None  # entered in IST
    form = {"category": cat, "incident_utc": when.astimezone(dt.timezone.utc) if when else None, "amount": amt, "txn_ref": ref,
            "contact": contact, "description": desc, "consent": ok}
    try:
        cid = cases.create_complaint(form, [(f.name, f.getvalue()) for f in (files or [])])
    except cases.CaseError as e:
        st.error("**Please fix the following before submitting:**\n" + "\n".join(f"- **{k}:** {v}" for k, v in e.errors.items()))
        return
    except Exception as e:
        st.error(f"The complaint could not be saved ({type(e).__name__}). Nothing was stored. Reference {common.log_issue('complaint_save', e)}.")
        return
    c = cases.get(cid)
    st.success(f"Complaint registered · Case ID **{cid}** · status **{c['status']}** · submitted {c['created_utc']} UTC. "
               "Keep this ID to track the case in *Case Management*.")
    st.caption(f"Stored: category, incident time, amount, reference {c['txn_ref_masked'] or '—'}, contact {c['contact'] or '—'} (masked), "
               f"description, {len(c['evidence'])} evidence file(s).")
