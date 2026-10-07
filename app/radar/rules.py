"""Fixed, explainable rules for the radar screens: thesis criteria and watch rules. No LLM and no non-public data in here. Scores come from
services/scoring.py, the same rules the signal pipeline uses."""
from __future__ import annotations

import re

from db.seed import SUBSIDIARIES

# The sectors the RPG companies work in — the taxonomy watched companies are routed by.
SECTORS: list[str] = list(dict.fromkeys(s for sub in SUBSIDIARIES for s in sub["sectors"]))
SECTOR_LABEL: dict[str, str] = {
    "tyres": "Tyres", "mobility": "Mobility", "epc": "EPC", "materials-adjacent": "Materials (adjacent)",
    "it-services": "IT services", "ai-genai": "AI / GenAI", "bfsi-services": "BFSI services", "pharma": "Pharma",
    "api-manufacturing": "API manufacturing", "materials-engineering": "Materials engineering",
    "electrical-components": "Electrical components", "plantations": "Plantations", "agri-processing": "Agri-processing",
}
assert set(SECTOR_LABEL) == set(SECTORS), "label every subsidiary sector"
GEOS = ["India", "ASEAN", "Middle East", "US", "UK"]
OWNERSHIP = ["family", "promoter", "pe", "founder"]
METRIC_LABEL = {"score": "Opportunity score"}

THESIS_KEYWORDS = [
    (r"tyre|tire|rubber compound", "tyres"), (r"mobility|\bev\b|electric vehicle", "mobility"),
    (r"\bepc\b|substation|transmission", "epc"), (r"materials", "materials-engineering"),
    (r"it services|software|digital engineering", "it-services"), (r"\bai\b|genai|machine learning|analytics", "ai-genai"),
    (r"bfsi|bank|insurance", "bfsi-services"), (r"pharma|formulation", "pharma"), (r"\bapi\b|active pharmaceutical", "api-manufacturing"),
    (r"cable|heat-shrink|joint|electrical", "electrical-components"), (r"tea|estate|plantation|rubber plantation", "plantations"),
    (r"agri|food processing", "agri-processing"),
]


def parse_thesis(txt: str) -> dict:
    """Keyword rules for a plain-language thesis: the fallback when Azure OpenAI is not available.
    A thesis that names no known sector gets none; the reviewer picks before saving."""
    low, c = txt.lower(), {"sector": [], "geo": [], "rev": [0, 99999], "own": []}
    c["sector"] = list(dict.fromkeys(sec for pat, sec in THESIS_KEYWORDS if re.search(pat, low)))
    c["geo"] = [g for g in GEOS if g.lower() in low] or ["India"]
    m = re.search(r"(\d+)\s*(?:[–-]|to)\s*(\d+)", txt.replace(",", ""))
    if m:
        c["rev"] = sorted([int(m.group(1)), int(m.group(2))])
    for pat, o in [(r"family", "family"), (r"promoter", "promoter"), (r"\bpe\b|private equity", "pe"), (r"founder", "founder")]:
        if re.search(pat, low):
            c["own"].append(o)
    return c


def thesis_criteria(c: dict) -> list[str]:
    out = []
    if c.get("sector"):
        out.append("Sector: " + " / ".join(SECTOR_LABEL.get(s, s) for s in c["sector"]))
    out.append("Geography: " + " / ".join(c.get("geo") or ["India"]))
    lo, hi = c.get("rev") or [0, 99999]
    if hi < 99999:
        out.append(f"Revenue ₹{lo:,}–{hi:,} cr")
    if c.get("own"):
        out.append("Ownership: " + " / ".join(c["own"]))
    return out


def trigger_text(tr: dict) -> str:
    return f'{METRIC_LABEL[tr["metric"]]} {tr["op"]} {tr["val"]}'


def trigger_hits(tr: dict, companies: list[dict]) -> list[dict]:
    """Watched companies ({name, score, cos}) that meet the rule now."""
    out = []
    for c in companies:
        if tr["desk"] != "All" and tr["desk"] not in c["cos"]:
            continue
        if c["score"] is None:
            continue
        v = float(tr["val"])
        if (tr["op"] == "above" and c["score"] > v) or (tr["op"] == "below" and c["score"] < v):
            out.append(c)
    return out
