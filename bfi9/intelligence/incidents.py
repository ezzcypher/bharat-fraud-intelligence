"""Normalized incident schema, rule-based classification, geography relations, dedup and trends.

Unknowns stay 'Unknown'/'Not reported'. A country is linked to an incident only through an explicit phrase,
and each link records its RELATION (origin / victim / infrastructure / jurisdiction / reporter / mentioned)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

import pandas as pd

from ..quality import pct_change
from .sources import SOURCES, canonical_url

CATEGORIES = [  # (category, keyword regex) - first match wins; source wording is kept in `original_terms`
    ("Business email compromise", r"business email compromise|\bBEC\b"), ("Cryptocurrency investment scam", r"crypto(currency)?[^.]{0,40}(scam|fraud|scheme)|pig butchering"),
    ("Ponzi / pyramid scheme", r"ponzi|pyramid scheme"), ("Market manipulation / securities fraud", r"manipulat|pump.and.dump|insider trading|securities fraud|spoof"),
    ("Investment / stock-tip scam", r"investment (scam|fraud)|stock.tip|offering fraud|unregistered offering"), ("Romance / confidence scam", r"romance|confidence scam"),
    ("Recovery scam", r"recovery scam|fund recovery"), ("Fake trading platform", r"fake (trading|investment) (platform|app)|fraudulent trading platform"),
    ("Impersonation / deepfake", r"impersonat|deepfake|voice clon"), ("Phishing / credential theft", r"phishing|credential|smishing|vishing"),
    ("Account takeover", r"account takeover"), ("Identity theft", r"identity theft"), ("Payment-card fraud", r"card fraud|skimming|carding"),
    ("Malware-enabled fraud", r"malware|ransomware|trojan"), ("Insider-enabled crime", r"insider (threat|fraud)|employee embezzl|embezzl")]
LEGAL = [("convicted", r"\bconvicted\b|pleaded guilty|sentenced"), ("charged", r"\bcharg(e|es|ed|ing)\b|indicted|complaint against"),
         ("settled / ordered", r"\bsettle|\border(ed|s)?\b|penalt|barred|suspend"), ("warning / advisory", r"\bwarn|advisory|caution|alert"),
         ("alleged", r"\balleg")]
COUNTRIES = ["United States", "India", "United Kingdom", "China", "Hong Kong", "Singapore", "Nigeria", "Ghana", "Russia", "Ukraine", "Cambodia", "Myanmar",
             "Laos", "Thailand", "Philippines", "Malaysia", "Indonesia", "Vietnam", "United Arab Emirates", "Dubai", "Canada", "Mexico", "Brazil", "Germany", "France",
             "Spain", "Italy", "Netherlands", "Switzerland", "Australia", "Japan", "South Korea", "Israel", "Cyprus", "Turkey", "South Africa", "Pakistan",
             "Bangladesh", "Sri Lanka", "Nepal", "Ireland", "Belgium", "Poland", "Romania", "Bulgaria", "Estonia", "Latvia", "Lithuania", "Cayman Islands"]
ALIAS = {"U.S.": "United States", "US": "United States", "USA": "United States", "UK": "United Kingdom", "U.K.": "United Kingdom", "UAE": "United Arab Emirates",
         "Dubai": "United Arab Emirates"}
_C = "|".join(sorted([re.escape(c) for c in COUNTRIES + list(ALIAS)], key=len, reverse=True))
REL = [("origin", rf"(?:based in|operat\w* (?:from|out of)|run from|located in) (?:the )?({_C})"),
       ("victim", rf"(?:victims?|investors?|customers?|residents?|consumers?) (?:in|from|across) (?:the )?({_C})"),
       ("infrastructure", rf"(?:servers?|call cent(?:er|re)s?|bank accounts?|websites?) (?:in|hosted in|located in) (?:the )?({_C})")]
TICKER = re.compile(r"\((?:NYSE|NASDAQ|Nasdaq|NYSE American|NSE|BSE)\s*:\s*([A-Z][A-Z.\-]{0,9})\)")
MONEY = re.compile(r"(\$|USD|US\$|₹|Rs\.?|INR|£|€)\s?([\d,.]+)\s*(million|billion|crore|lakh)?", re.I)
MULT = {"million": 1e6, "billion": 1e9, "crore": 1e7, "lakh": 1e5, None: 1}
CUR = {"$": "USD", "usd": "USD", "us$": "USD", "₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR", "£": "GBP", "€": "EUR"}


ORG = re.compile(r"\b(Ltd|Limited|LLP|LLC|Inc|Corp|Corporation|Bank|Banks|Pvt|Private|Company|Co\.|Securities|Capital|Fund|Trust|Exchange|Broking|"
                 r"Finance|Holdings|Group|PLC|SA|AG|Services|Depository|Board|Ministry|Authority|Commission|Government|Association|Industries)\b", re.I)
TOK = r"(?:[A-Z][a-z]+|[A-Z]\.?)"                                    # 'Veena', 'R', 'R.' - not all-caps acronyms like 'KYC'
PERSON = re.compile(r"\b(?:Mr|Ms|Mrs|Shri|Smt|Dr|Kumari)\.?\s+" + TOK + r"(?:\s+" + TOK + r"){0,3}")
TRIG1 = re.compile(r"\b(filed by|against|issued to|in respect of|noticee)\s+(" + TOK + r"(?:\s+" + TOK + r"){0,4})")   # 1+ name tokens
TRIG2 = re.compile(r"\b(of)\s+(" + TOK + r"(?:\s+" + TOK + r"){1,4})")                                                  # 'of' needs 2+ tokens
GOV_ID = [(re.compile(r"\bPAN\s*[:#-]?\s*[A-Z]{5}[0-9]{4}[A-Z]\b"), "PAN: [redacted]"), (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "[ID redacted]"),
          (re.compile(r"\b(?:Aadhaar|UID)\s*(?:No\.?|number)?\s*[:#-]?\s*\d{4}\s?\d{4}\s?\d{4}\b", re.I), "Aadhaar: [redacted]")]


def redact_people(text: str) -> str:
    """Privacy-first heuristic: hide government ID numbers and names of (likely) private individuals in regulator text;
    organisations stay visible. Over-redaction is preferred to exposure. The official link keeps the original wording."""
    text = text or ""
    for rx, rep in GOV_ID:
        text = rx.sub(rep, text)
    text = PERSON.sub("[named individual]", text)
    keep = lambda m: m.group(0) if ORG.search(m.group(2)) else f"{m.group(1)} [named individual]"
    return TRIG2.sub(keep, TRIG1.sub(keep, text))


@dataclass
class Incident:
    incident_id: str
    title: str
    summary: str
    published: str | None
    incident_date: str = "Not reported"
    source_org: str = "Unknown"
    source_urls: list = field(default_factory=list)
    source_type: str = "other"
    jurisdiction: str = "Unknown"
    category: str = "Unclassified"
    original_terms: str = ""
    legal_status: str = "Not reported"
    reported_loss: float | None = None
    loss_currency: str = "Not reported"
    loss_normalized_usd: float | None = None
    conversion_note: str = "Not converted (no recorded exchange rate)"
    victims_reported: str = "Not reported"
    tickers: list = field(default_factory=list)
    ticker_evidence: str = "No verified public-market linkage"
    evidence_quality: str = "official source, single report"
    verification_status: str = "unverified (single source)"
    last_updated: str = ""


def classify(text: str) -> tuple[str, str]:
    for cat, rx in CATEGORIES:
        m = re.search(rx, text, re.I)
        if m:
            return cat, m.group(0)
    return "Unclassified", "no category keyword in title/excerpt"


def legal_status(text: str) -> str:
    return next((s for s, rx in LEGAL if re.search(rx, text, re.I)), "Not reported")


def geo_links(inc_id: str, text: str, jurisdiction: str) -> list[dict]:
    """Explicit-phrase relations only; plain mentions are 'mentioned (relation unverified)'."""
    canon = lambda c: ALIAS.get(c, c)
    links = [{"incident_id": inc_id, "country": jurisdiction, "relation": "jurisdiction", "evidence": "source organisation"}] if jurisdiction != "Unknown" else []
    typed = set()
    for rel, rx in REL:
        for m in re.finditer(rx, text, re.I):
            links.append({"incident_id": inc_id, "country": canon(m.group(1)), "relation": rel, "evidence": m.group(0)[:120]})
            typed.add(canon(m.group(1)))
    for m in re.finditer(rf"\b({_C})\b", text):
        c = canon(m.group(1))
        if c not in typed and c != jurisdiction:
            links.append({"incident_id": inc_id, "country": c, "relation": "mentioned (relation unverified)", "evidence": m.group(0)})
            typed.add(c)
    return links


def money(text: str) -> tuple[float | None, str]:
    m = MONEY.search(text)
    if not m:
        return None, "Not reported"
    try:
        v = float(m.group(2).replace(",", "").rstrip(".")) * MULT[(m.group(3) or "").lower() or None]
    except ValueError:
        return None, "Not reported"
    return v, CUR.get(m.group(1).lower().rstrip("."), CUR.get(m.group(1).lower(), m.group(1)))


def normalize(item: dict) -> tuple[Incident, list[dict]]:
    src = next((s for s in SOURCES if s["id"] == item["source_id"]), {})
    text = f"{item['title']}. {item.get('excerpt', '')}"
    iid = hashlib.sha1(canonical_url(item["url"]).encode()).hexdigest()[:12]
    cat, terms = classify(text)
    amt, cur = money(text)
    tick = TICKER.findall(text)
    inc = Incident(incident_id=iid, title=redact_people(item["title"]), summary=redact_people(item.get("excerpt", ""))[:300], published=item.get("published"),
                   source_org=src.get("org", "Unknown"), source_urls=[item["url"]], source_type=src.get("type", "other"),
                   jurisdiction=src.get("jurisdiction", "Unknown"), category=cat, original_terms=terms, legal_status=legal_status(text),
                   reported_loss=amt, loss_currency=cur, tickers=tick,
                   ticker_evidence=f"ticker printed in source text: {', '.join(tick)}" if tick else "No verified public-market linkage",
                   last_updated=item.get("retrieved_at", ""))
    return inc, geo_links(iid, text, inc.jurisdiction)


def _tokens(s: str) -> set:
    return set(re.findall(r"[a-z0-9]{3,}", s.lower()))


def dedupe(incs: list[Incident], threshold: float = 0.8) -> list[Incident]:
    """Same canonical URL, or title Jaccard >= threshold within 3 days -> one incident with all source URLs kept."""
    out: list[Incident] = []
    for i in sorted(incs, key=lambda x: x.published or ""):
        dup = None
        for o in out:
            same_url = bool(set(map(canonical_url, i.source_urls)) & set(map(canonical_url, o.source_urls)))
            ta, tb = _tokens(i.title), _tokens(o.title)
            sim = len(ta & tb) / len(ta | tb) if ta | tb else 0
            close = (i.published and o.published and abs(pd.Timestamp(i.published) - pd.Timestamp(o.published)).days <= 3)
            if same_url or (sim >= threshold and close):
                dup = o
                break
        if dup:
            dup.source_urls = sorted(set(dup.source_urls) | set(i.source_urls))
            if len({canonical_url(u).split('/')[2] for u in dup.source_urls}) > 1:
                dup.evidence_quality, dup.verification_status = "multiple independent sources", "corroborated by >1 source"
        else:
            out.append(i)
    return out


def build(items: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    pairs = [normalize(i) for i in items]
    incs = dedupe([p[0] for p in pairs])
    keep = {i.incident_id for i in incs}
    geo = pd.DataFrame([g for _, gl in pairs for g in gl if g["incident_id"] in keep],
                       columns=["incident_id", "country", "relation", "evidence"]).drop_duplicates()
    return pd.DataFrame([asdict(i) for i in incs]), geo


def trends(inc: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    """Deduplicated incident counts per period x category; % change is None from a zero baseline."""
    if inc.empty or inc["published"].isna().all():
        return pd.DataFrame(columns=["period", "category", "incidents", "pct_change"])
    d = inc.dropna(subset=["published"]).assign(period=lambda x: pd.to_datetime(x["published"], utc=True).dt.tz_localize(None).dt.to_period(freq).dt.start_time)
    t = d.groupby(["period", "category"]).size().rename("incidents").reset_index().sort_values("period")
    t["pct_change"] = t.groupby("category")["incidents"].transform(lambda s: [None] + [pct_change(a, b) for a, b in zip(s[:-1], s[1:])])
    return t


def emerging(inc: pd.DataFrame, min_incidents: int = 3, min_sources: int = 2) -> list[str]:
    """A category is 'emerging' only with >= min_incidents incidents from >= min_sources different organisations."""
    if inc.empty:
        return []
    g = inc.groupby("category").agg(n=("incident_id", "size"), orgs=("source_org", "nunique"))
    return [c for c, r in g.iterrows() if c != "Unclassified" and r.n >= min_incidents and r.orgs >= min_sources]
