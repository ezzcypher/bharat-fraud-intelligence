"""Source registry, RSS/Atom connectors and the on-disk cache for Global Fraud Intelligence.

Isolation: this package never imports model, Phase 4-8 or v1 data code. Retrieved text is UNTRUSTED data:
it is parsed, truncated and stored, never executed or used to choose tools."""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

from .. import settings as S

STORE = S.INTEL
UA = "BFI-v2-Phase9-research-dashboard (educational; low-volume RSS reader)"
MAX_BYTES = 3_000_000
EXCERPT = 300  # permitted short excerpt only; full articles are never copied

# Step 1: registry. 'connected' only where a machine-readable feed was verified on the provider's own page (Stage 7 research).
SOURCES = [
    {"id": "sec_press", "name": "SEC press releases", "org": "U.S. Securities and Exchange Commission", "jurisdiction": "United States",
     "type": "regulator notice", "url": "https://www.sec.gov/news/pressreleases.rss", "listed_on": "https://www.sec.gov/about/secrss.shtml",
     "terms": "U.S. government work. SEC fair-access policy requires a declared User-Agent with contact; set BFI9_SEC_USER_AGENT to enable.", "env": "BFI9_SEC_USER_AGENT"},
    {"id": "sec_litigation", "name": "SEC litigation releases", "org": "U.S. Securities and Exchange Commission", "jurisdiction": "United States",
     "type": "enforcement action", "url": "https://www.sec.gov/enforcement-litigation/litigation-releases/rss", "listed_on": "https://www.sec.gov/about/secrss.shtml",
     "terms": "As above (declared User-Agent required).", "env": "BFI9_SEC_USER_AGENT"},
    {"id": "ftc_consumer", "name": "FTC consumer-protection press releases", "org": "U.S. Federal Trade Commission", "jurisdiction": "United States",
     "type": "enforcement action", "url": "https://www.ftc.gov/feeds/press-release-consumer-protection.xml", "listed_on": "https://www.ftc.gov/news-events/stay-connected/ftc-rss-feeds",
     "terms": "Published for RSS readers; U.S. government work."},
    {"id": "rbi_press", "name": "RBI press releases", "org": "Reserve Bank of India", "jurisdiction": "India", "type": "regulator notice",
     "url": "https://www.rbi.org.in/pressreleases_rss.xml", "listed_on": "rbi.org.in RSS listing", "terms": "Official RSS; no redistribution terms stated - short excerpts + links only."},
    {"id": "sebi", "name": "SEBI press releases, circulars, orders", "org": "Securities and Exchange Board of India", "jurisdiction": "India", "type": "regulator notice",
     "url": "https://www.sebi.gov.in/sebirss.xml", "listed_on": "https://www.sebi.gov.in/rss.html", "terms": "Official RSS; no terms stated - short excerpts + links only."},
]
NOT_CONNECTED = [(n, "No machine-readable feed verified on the provider's site; not scraped (link-out only).") for n in
                 ("INTERPOL", "FBI IC3", "CERT-In", "I4C / MHA", "Europol", "UK FCA (email alerts only)", "ESMA", "FinCEN")]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _clean(text: str) -> str:
    """Strip tags/entities and collapse whitespace; result is plain inert text."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _date(s: str) -> str | None:
    for f in (lambda x: parsedate_to_datetime(x), lambda x: dt.datetime.fromisoformat(x.replace("Z", "+00:00")),
              lambda x: dt.datetime.strptime(x, "%d %b, %Y %z")):   # SEBI feed format, e.g. '30 Oct, 2026 +0530'
        try:
            d = f(s.strip())
            return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc).isoformat(timespec="seconds")
        except Exception:
            continue
    return None


def parse_feed(xml_bytes: bytes, source_id: str) -> list[dict]:
    """RSS 2.0 and Atom. Refuses DTD/entity declarations (entity-expansion attacks) and oversized payloads."""
    if len(xml_bytes) > MAX_BYTES:
        raise ValueError("feed too large")
    head = xml_bytes[:4096].decode("utf8", "ignore")
    if "<!DOCTYPE" in head.upper() or "<!ENTITY" in head.upper():
        raise ValueError("feed declares a DTD/entities; refused")
    root = ET.fromstring(xml_bytes)
    strip = lambda t: t.split("}", 1)[-1]
    items = []
    for el in root.iter():
        if strip(el.tag) not in ("item", "entry"):
            continue
        f = {strip(c.tag): c for c in el}
        link = f.get("link")
        href = (link.get("href") or (link.text or "")).strip() if link is not None else ""
        pub = next((f[k].text for k in ("pubDate", "published", "updated", "date") if k in f and f[k].text), None)
        items.append({"source_id": source_id, "title": _clean(f["title"].text if "title" in f else "")[:300], "url": href,
                      "published": _date(pub) if pub else None, "published_raw": (pub or "")[:60], "excerpt": _clean(next((f[k].text for k in ("description", "summary", "content") if k in f and f[k].text), ""))[:EXCERPT],
                      "retrieved_at": _now()})
    return [i for i in items if i["title"] and i["url"].startswith("http")]


def fetch(src: dict, timeout: int = 15) -> dict:
    """One polite GET per source. Returns {status, items|error}; never raises."""
    if src.get("env") and not os.environ.get(src["env"]):
        return {"status": "disabled", "error": f"set {src['env']} (provider requires a declared User-Agent)", "items": []}
    ua = os.environ.get(src["env"]) if src.get("env") else UA
    try:
        req = urllib.request.Request(src["url"], headers={"User-Agent": ua, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(MAX_BYTES + 1)
        return {"status": "live", "items": parse_feed(data, src["id"])}
    except Exception as e:
        return {"status": "unavailable", "error": f"{type(e).__name__}: {str(e)[:120]}", "items": []}


# ------------------------------------------------------------------ cache
def _jsonl(name: str) -> Path:
    STORE.mkdir(parents=True, exist_ok=True)
    return STORE / name


def read_jsonl(name: str) -> list[dict]:
    p = _jsonl(name)
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def append_jsonl(name: str, rows: list[dict]) -> None:
    with open(_jsonl(name), "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def item_key(i: dict) -> str:
    return hashlib.sha1(canonical_url(i["url"]).encode()).hexdigest()[:16]


def canonical_url(u: str) -> str:
    u = re.sub(r"[?#].*$", "", u.strip()).rstrip("/")
    return re.sub(r"^https?://(www\.)?", "https://", u.lower())


def items() -> list[dict]:
    """Latest stored version of each item (a re-fetch replaces an older parse of the same canonical URL)."""
    return list({item_key(i): i for i in read_jsonl("raw_items.jsonl")}.values())


def refresh(sources=None) -> list[dict]:
    """Fetch every connected source; store redacted items (latest parse wins), compact the store, log health per source."""
    from .incidents import redact_people   # local import: incidents imports this module
    stored = {item_key(i): i for i in read_jsonl("raw_items.jsonl")}
    log = []
    for s in sources or SOURCES:
        r = fetch(s)
        fresh = [{**i, "title": redact_people(i["title"]), "excerpt": redact_people(i["excerpt"])} for i in r["items"]]
        new = [i for i in fresh if item_key(i) not in stored]
        stored.update({item_key(i): i for i in fresh})
        log.append({"source_id": s["id"], "at": _now(), "status": r["status"], "items": len(r["items"]), "new": len(new), "error": r.get("error")})
    p = _jsonl("raw_items.jsonl")   # compaction: one (redacted, latest) record per item; older unredacted copies are overwritten
    p.write_text("".join(json.dumps({**i, "title": redact_people(i["title"]), "excerpt": redact_people(i.get("excerpt", ""))}) + "\n" for i in stored.values()))
    append_jsonl("refresh_log.jsonl", log)
    return log


def health(max_age_hours: float = 24) -> list[dict]:
    """live = fetched this session; cached = last success within max_age; stale = older; unavailable = never succeeded."""
    log = read_jsonl("refresh_log.jsonl")
    out = []
    for s in SOURCES:
        rows = [l for l in log if l["source_id"] == s["id"]]
        ok = [l for l in rows if l["status"] == "live"]
        last = rows[-1] if rows else None
        if not ok:
            status = "disabled" if last and last["status"] == "disabled" else "unavailable"
        else:
            age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ok[-1]["at"])).total_seconds() / 3600
            status = "cached" if age <= max_age_hours else "stale"
        out.append({"source": s["name"], "status": status, "last_success": ok[-1]["at"] if ok else None,
                    "last_attempt": last["at"] if last else None, "last_error": last.get("error") if last else "never refreshed", "url": s["url"]})
    return out
