"""Fixed, explainable rules: opportunity score, thesis fit, watch rules, financial health,
escalation brief, diligence questions, plans. No LLM and no non-public data in here."""
from __future__ import annotations

import math

from .reference import REF

W: dict[str, int] = REF["W"]
TYPE_LABEL: dict[str, str] = REF["TYPE_LABEL"]
SECTOR_LABEL: dict[str, str] = REF["SECTOR_LABEL"]
RATING_ORDER: list[str] = REF["RATING_ORDER"]
METRIC_LABEL: dict[str, str] = REF["METRIC_LABEL"]


def js_round(x: float) -> int:
    """Round half up, like JavaScript's Math.round (Python's round() is banker's rounding)."""
    return int(math.floor(x + 0.5))


def multiplier(n_types: int) -> float:
    """Co-occurrence multiplier: more independent signal types pointing the same way."""
    if n_types >= 4:
        return 2.0
    return {1: 1.0, 2: 1.3, 3: 1.6}.get(n_types, 1.0)


def score_of(signals: list[list]) -> dict:
    types: list[str] = []
    for s in signals:
        if s[0] not in types:
            types.append(s[0])
    base = sum(W[k] for k in types)
    m = multiplier(len(types))
    raw = base * m
    return {"types": types, "base": base, "m": m, "raw": raw, "score": min(100, js_round(raw))}


def thesis_match(th: dict, t: dict) -> dict:
    c = th["c"]
    checks: list[list] = [
        ["Sector: " + " / ".join(SECTOR_LABEL[s] for s in c["sector"]), t["sector"] in c["sector"]],
        ["Geography: " + " / ".join(c["geo"]), t["geo"] in c["geo"]],
    ]
    lo, hi = c["rev"]
    if hi < 99999:
        checks.append([f"Revenue ₹{lo:,}–{hi:,} cr", lo <= t["revenue"] <= hi])
    if c.get("own"):
        checks.append(["Ownership: " + " / ".join(c["own"]), t["ownership"] in c["own"]])
    if c.get("usfda"):
        checks.append(["USFDA-approved plant", bool(t.get("usfda"))])
    ok = sum(1 for x in checks if x[1])
    return {"checks": checks, "ok": ok, "total": len(checks), "pct": js_round(ok / len(checks) * 100)}


def trigger_text(tr: dict) -> str:
    if tr["metric"] == "insolvency":
        return "Insolvency filed"
    if tr["metric"] == "rivalstake":
        return "A rival builds a new stake"
    unit = "%" if tr["metric"] == "pledge" else ""
    return f'{METRIC_LABEL[tr["metric"]]} {tr["op"]} {tr["val"]}{unit}'


def trigger_hits(tr: dict, targets: list[dict], deals: list[list]) -> list[dict]:
    out = []
    for t in targets:
        if tr["desk"] != "All" and tr["desk"] not in t["desks"]:
            continue
        m = tr["metric"]
        hit = False
        if m == "score":
            hit = t["score"] > float(tr["val"])
        elif m == "pledge":
            hit = t["pledge"] > float(tr["val"])
        elif m == "rating":
            val = str(tr["val"]).upper()
            hit = t["rating"] != "–" and val in RATING_ORDER and RATING_ORDER.index(t["rating"]) < RATING_ORDER.index(val)
        elif m == "insolvency":
            hit = "insolvency_filed" in t["types"]
        elif m == "rivalstake":
            hit = any(d[2] == t["name"] and "SAST" in d[3] for d in deals)
        if hit:
            out.append(t)
    return out


def verdict_of(t: dict) -> list[str]:
    h = t["health"]
    last, fall = h["m"][4], h["m"][0] - h["m"][4]
    run = fall >= 4 or (h["aud"][0] == "bad" and "not yet filed" not in h["aud"][1])
    fund = h["de"] > 3 or (h["ic"] is not None and h["ic"] < 2) or t["pledge"] > 30
    if h.get("early"):
        return ["Early stage", "Revenue is growing fast and it has only just turned profitable. Too early to call it weak; it may need funding to keep growing."]
    if run and fund:
        return ["Badly run and badly funded", "Margins are falling and debt is heavy. A buyer would need to fix both the business and the balance sheet. Usually a turnaround or insolvency-process purchase."]
    if fund:
        return ["Badly funded, business is sound", "Margins are holding up, but debt or pledged shares are too high. The core business may be worth more to an owner with a stronger balance sheet."]
    if run:
        return ["Badly run, balance sheet is fine", "Debt is manageable, but margins are sliding or the auditor has raised concerns. A buyer would need to fix operations and governance."]
    _ = last
    return ["Healthy", "Stable margins and low debt. Any deal would come from the owner wanting to sell, not from distress."]


def health_block(t: dict) -> dict:
    h = t["health"]
    cagr = (math.pow(h["rev"][4] / h["rev"][0], 1 / 4) - 1) * 100
    fell = h["m"][0] - h["m"][4] >= 4
    checks = [
        [fell, f'Margin {"fell" if fell else "moved"} from {h["m"][0]}% to {h["m"][4]}% over 4 years'],
        [h["de"] > 3, f'Net debt is {h["de"]}× EBITDA' + (" (above 3× is stretched)" if h["de"] > 3 else "")],
        [h["ic"] is not None and h["ic"] < 2, "No borrowings" if h["ic"] is None else f'Profit covers interest {h["ic"]}×' + (" (below 2× is weak)" if h["ic"] < 2 else "")],
        [h["aud"][0] == "bad", h["aud"][1]],
    ]
    return {
        "verdict": verdict_of(t),
        "revenue": h["rev"], "margin": h["m"], "years": ["FY22", "FY23", "FY24", "FY25", "FY26"],
        "kv": [["Revenue FY26", f'₹{h["rev"][4]:,} cr'], ["4-year revenue growth", f'{"+" if cagr >= 0 else ""}{cagr:.1f}% a year'],
               ["EBITDA margin FY26", f'{h["m"][4]}%'], ["Net debt / EBITDA", f'{h["de"]}×'],
               ["Interest cover", "No debt" if h["ic"] is None else f'{h["ic"]}×'], ["Promoter pledge", f'{t["pledge"]}%']],
        "checks": [{"bad": b, "text": x} for b, x in checks],
    }


def make_brief(t: dict) -> dict:
    ty = t["types"]
    pros, cons, flags = [], [], []
    if any(k in ty for k in ["credit_downgrade", "delayed_filing", "insolvency_filed", "pledge_rising"]):
        pros.append("Possible distress-driven opening. The owners may be open to talks.")
    if "succession_risk" in ty:
        pros.append("Succession gap may make the family open to a sale.")
    if "pe_exit_window" in ty or "divestment_signal" in ty:
        pros.append("Owner is likely looking for an exit or buyer.")
    if "patent_shift" in ty or "press_opportunity" in ty:
        pros.append("Growing capability that fills a gap for " + ", ".join(t["desks"]) + ".")
    pros.append("Found through public sources ahead of wide market awareness.")
    cons.append("Not confirmed by diligence. These are patterns in public data, not verified financials.")
    if len(t["desks"]) > 1:
        cons.append("Relevant to several RPG companies. Agree which one would own it.")
    if t["bidders"]:
        cons.append("Rival interest detected. Timing may be tight.")
    if "insolvency_filed" in ty:
        cons.append("In an insolvency process. Any bid goes through the resolution process.")
    if "auditor_resigned" in ty:
        flags.append("Auditor resigned")
    if t["pledge"] > 30:
        flags.append(f'Promoter pledge {t["pledge"]}%')
    if "delayed_filing" in ty:
        flags.append("Late filing")
    if t["rating"] == "D" or "credit_downgrade" in ty:
        flags.append(f'Rating {t["rating"]}')
    if "insolvency_filed" in ty:
        flags.append("Insolvency case open")
    if not flags:
        flags.append("None found in public sources")
    complexity = "High" if (t["geo"] != "India" or len(t["desks"]) > 1) else ("Medium" if t["listed"] else "Low")
    cci = "Check needed with Legal" if t["revenue"] > 1000 else "Likely not needed · confirm"
    return {"pros": pros, "cons": cons, "flags": flags, "complexity": complexity, "cci": cci}


QUESTIONS = {
    "delayed_filing": "Why were the accounts filed late, and is there a dispute with the auditor?",
    "auditor_resigned": "Which records did the auditor say it could not access?",
    "credit_downgrade": "Which loans drove the rating cut, and when are they due?",
    "pledge_rising": "Who holds the pledged shares, and at what price could lenders sell them?",
    "insolvency_filed": "What is the timeline of the resolution process, and who are the main creditors?",
    "leadership_churn": "Why did senior leaders leave, and who runs the business today?",
    "succession_risk": "Who in the family or ownership group decides on a sale?",
    "pe_exit_window": "What return does the PE fund need, and is a sale process already running?",
    "divestment_signal": "Which services does it share with its parent, and how would they be separated?",
    "hiring_scaledown": "Are clients or projects being lost?",
    "press_distress": "How big are the penalties and delays on current projects?",
    "patent_shift": "Who owns the patents, and are key engineers tied in?",
    "press_opportunity": "What terms is the company offering new investors or partners?",
    "hiring_scaleup": "Can the team keep growing without losing quality?",
}


def diligence_questions(t: dict) -> list[str]:
    q = [QUESTIONS[k] for k in t["types"] if k in QUESTIONS]
    q.append("How much revenue comes from the top 5 customers, and are any of them our rivals?")
    return q[:5]


def plan_for(case: dict) -> list[dict]:
    r = ["Days 0–30", "Days 31–60", "Days 61–90"]
    if case["kind"] == "deal":
        opts = case["target"]["scenario"]["a"]["opts"]
        p = [{"when": r[i], "what": "Decide on a bid" if x[0] == "Escalate for evaluation" else x[0], "how": x[1]} for i, x in enumerate(opts[:3])]
        if len(p) < 3:
            p.append({"when": r[len(p)], "what": "Decide the next step", "how": "Formal bid, partnership or stop, based on diligence."})
        return p
    o = case["ws"]["war"]["opts"]
    return [{"when": r[0], "what": o[0][1], "how": o[0][2]}, {"when": r[1], "what": o[1][1], "how": o[1][2]},
            {"when": r[2], "what": "Review against the rival's moves", "how": f'Compare results with {case["ws"]["rival"]}\'s actual moves and adjust.'}]


def owners_for(case: dict) -> list[str]:
    co = case["co"]
    if case["kind"] == "deal":
        return [f"Head of Strategy, {co}", f"CFO, {co}", "Group M&A team"]
    return [f"Head of Strategy, {co}", f"Business head, {co}", f"Sales head, {co}"]


def watch_for(case: dict) -> list[str]:
    if case["kind"] == "deal":
        t = case["target"]
        r = t["scenario"]["rival"]
        return [f'Any new stake disclosure (SAST) in {t["name"]}', f'Rating change or late filing by {t["name"]}', f"Any deal move by {r}"]
    w = case["ws"]
    return [f'New product launches or plant filings by {w["rival"]}', f'{w["rival"]} price changes in {case["co"]}\'s markets',
            f'Customer complaints about {w["rival"]} (Voice of Customer)']


def pct(v: float) -> str:
    return f'{"+" if v >= 0 else ""}{v:.1f}%'
