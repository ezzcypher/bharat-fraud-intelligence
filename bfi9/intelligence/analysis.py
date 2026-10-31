"""Evidence-grounded incident analysis (rule-based; no LLM; no tool execution from source text).

Every section separates (a) what the SOURCE says (quoted excerpt) from (b) GENERAL guidance for the category,
which is labelled as such. Nothing here claims a control would certainly have prevented an incident."""
from __future__ import annotations

import datetime as dt

GUIDE = {  # category -> (possible weaknesses, controls, AI techniques)
    "Business email compromise": (["inadequate payment-change verification", "weak email authentication"], ["independent callback for beneficiary changes", "dual approval of payments", "phishing-resistant MFA"],
                                  ["NLP on payment-change requests", "anomaly detection on beneficiary changes"]),
    "Phishing / credential theft": (["insufficient MFA", "low customer awareness"], ["phishing-resistant MFA", "login risk scoring", "customer education"], ["URL/email classifiers", "account-takeover behaviour models"]),
    "Account takeover": (["weak account recovery", "no device binding"], ["device and behavioural anomaly detection", "step-up authentication", "velocity limits"], ["behavioural biometrics", "sequence anomaly models"]),
    "Impersonation / deepfake": (["identity verification relying on voice/video alone"], ["out-of-band verification", "code words for high-value requests"], ["synthetic-media detection (limited reliability)"]),
    "Investment / stock-tip scam": (["insufficient market surveillance", "unregistered promoters"], ["investor warnings", "registration checks", "takedown of promotions"], ["NLP on promotions", "graph analysis of promoter networks"]),
    "Cryptocurrency investment scam": (["irreversible payments", "unregulated platforms"], ["payee warnings", "exchange-side risk scoring", "rapid freeze where lawful"], ["blockchain graph analytics", "risk scoring of withdrawals"]),
    "Market manipulation / securities fraud": (["insufficient market surveillance"], ["trade surveillance alerts", "disclosure enforcement"], ["anomaly detection on order books", "NLP on promotions"]),
    "Ponzi / pyramid scheme": (["delayed reporting", "unregistered offerings"], ["registration checks", "investor education"], ["network analysis of fund flows"]),
    "Payment-card fraud": (["weak transaction monitoring"], ["risk-based transaction scoring", "3-D Secure", "velocity rules"], ["supervised fraud classification (BFI v2 scope)"]),
    "Identity theft": (["weak identity verification"], ["document + liveness checks", "credit freezes"], ["document forgery detection", "synthetic-identity graph models"]),
    "Malware-enabled fraud": (["unpatched endpoints"], ["endpoint protection", "transaction signing"], ["malware detection", "session anomaly detection"]),
}
DEFAULT = (["not established from the source"], ["risk-based monitoring", "human review of high-risk cases", "information sharing"], ["similar-incident retrieval", "analyst decision support"])


def analyse(inc: dict) -> dict:
    """Sections A-F plus 'what this teaches BFI v2'. Marked AI-generated (rule-based)."""
    weak, controls, ai = GUIDE.get(inc["category"], DEFAULT)
    src = f"{inc['source_org']} ({inc.get('published') or 'date not reported'})"
    in_scope = inc["category"] in ("Payment-card fraud", "Account takeover", "Identity theft")
    return {
        "label": "AI-generated analysis (deterministic rules, no LLM). General guidance is not legal or incident-response advice.",
        "A_what_happened": f"Reported by {src}: “{inc['title']}”. Legal status per source wording: {inc['legal_status']}. Excerpt: “{inc['summary'][:240]}”",
        "B_how_it_worked": f"Source category cue: “{inc['original_terms']}” → {inc['category']}. Attack steps beyond the source text are NOT inferred.",
        "C_vulnerability": "Possible contributing weaknesses (not confirmed causes): " + "; ".join(weak),
        "D_prevention": "Relevant controls (general): " + "; ".join(controls) + ". Trade-offs: more friction and false positives, operating cost, privacy and accessibility impact.",
        "E_ai_help": "AI techniques that could help (data needed: labelled cases, device/session data, text): " + "; ".join(ai) + ". No technique would certainly have prevented this incident.",
        "F_actions_now": ["Contain: block/flag affected accounts or payees", "Preserve evidence and logs", "Communicate with affected customers/staff",
                          "Attempt payment recall and escalate", "Report to the regulator / law enforcement as required", "Medium term: add the controls above; long term: monitor and validate models"],
        "bfi_v2": {"comparable_pattern_in_model_scope": in_scope,
                   "statement": ("Card/transaction fraud is within BFI v2's training scope (IEEE-CIS card-not-present transactions) - a comparable transaction could be scored, "
                                 "but this incident's data is not in the dataset.") if in_scope else
                   ("Outside BFI v2's scope: the model classifies individual e-commerce transactions; it does not detect phishing, deepfakes, money laundering or market "
                    "manipulation. A new labelled dataset and model would be required."),
                   "data_needed": "transaction-level records with timestamps, device/session data and verified outcome labels",
                   "phase8_can_retrieve_similar": False},
        "sources": inc["source_urls"]}


def brief(incidents: list[dict], health: list[dict], title: str = "Global fraud intelligence brief") -> str:
    """Markdown brief: sources, dates and evidence classes preserved."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md = [f"# {title}", f"_Generated {now}. Incidents are deduplicated official-source reports; counts reflect reporting, not true fraud volume._", "",
          "## Source status", *[f"- {h['source']}: **{h['status']}** (last success {h['last_success'] or 'never'})" for h in health], "", "## Incidents"]
    for i in incidents:
        md += [f"### {i['title']}", f"- Published: {i.get('published') or 'not reported'} · Source: {i['source_org']} · Type: {i['source_type']}",
               f"- Category: {i['category']} (cue: “{i['original_terms']}”) · Legal status: {i['legal_status']} · Evidence: {i['evidence_quality']}",
               f"- Reported loss: {i['reported_loss'] if i['reported_loss'] is not None else 'Not reported'} {i['loss_currency'] if i['reported_loss'] is not None else ''} ({i['conversion_note']})",
               f"- Market linkage: {i['ticker_evidence']}", *[f"- Link: {u}" for u in i["source_urls"]], ""]
    return "\n".join(md)
