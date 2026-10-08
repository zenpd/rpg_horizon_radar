"""Turns stored records into the shapes the screens need. Every value here comes from the
database (watched companies, their public signals and rule-based scores, agent SWOTs) or from
what users did; a screen with nothing real to show says so instead."""
from __future__ import annotations

from .store import COMPANIES_ORDER, STORE, week_label

TOWS = {"SO": ["Strength × Opportunity", "Use a strength to seize an opportunity"],
        "WO": ["Weakness × Opportunity", "Use an opportunity to fix a weakness"],
        "ST": ["Strength × Threat", "Use a strength to blunt a threat"],
        "WT": ["Weakness × Threat", "Shore up a weakness a threat could exploit"]}
STATUS = {"open": "New", "shortlisted": "Shortlisted", "dismissed": "Archived"}


def type_label(t: str) -> str:
    return t.replace("_", " ")


def score_detail(types: list[str]) -> dict:
    """How the rule-based opportunity score is built (services/scoring.py), for the "i" next to it:
    each kind of move in the 90-day window adds its weight once, the sum is multiplied by how many
    kinds there are, and the result is capped at 100."""
    from services import scoring

    parts = [{"type": type_label(t), "weight": scoring.BASE_WEIGHTS.get(t, 0)} for t in sorted(set(types))]
    base, mult = sum(p["weight"] for p in parts), scoring._multiplier_for(len(parts))
    return {"parts": parts, "base": base, "kinds": len(parts), "multiplier": mult, "raw": round(base * mult, 1),
            "score": round(min(scoring.MAX_SCORE, base * mult)), "max": scoring.MAX_SCORE, "window_days": scoring.WINDOW_DAYS,
            "multipliers": {**{str(k): v for k, v in scoring.CO_OCCURRENCE_MULTIPLIER.items()}, "4+": scoring.CO_OCCURRENCE_MULTIPLIER_4_PLUS}}


def in_scope(c: dict, scope: str) -> bool:
    return scope == "All" or scope in c["cos"]


def _signal(x: dict) -> dict:
    return {"date": x["date"], "label": x["label"], "text": x["text"], "source": x["source"], "url": x.get("url")}


def acquirable(c: dict, co: str) -> dict:
    """Whether ``co`` could plausibly buy this company (services/company_size.fit), and whether it is an
    M&A signal for ``co``: a company at most half co's size, or a target from target discovery whose
    size is not known yet (shown as not verified). A competitor of unknown size is never one."""
    from services import company_size

    from .bridge import CO_TO_CODE

    f = company_size.fit(STORE.sizes.get(company_size.entity_key(c["entity_id"])), STORE.sizes.get(company_size.rpg_key(CO_TO_CODE[co])))
    return {**f, "signal": f["ok"] is True or (f["ok"] is None and c.get("role") == "target")}


def signal_for(c: dict) -> str | None:
    """The RPG company this company is an M&A signal for (the first that could buy it), or None."""
    return next((co for co in c["cos"] if acquirable(c, co)["signal"]), None)


def listing(c: dict) -> str | None:
    """The company's NSE symbol, when it has been matched to a listing."""
    return next((w["nse_symbol"] for ws in (STORE.live_meta.get("watch") or {}).values() for w in ws if w["id"] == c["entity_id"]), None)


def found_via(c: dict) -> str | None:
    """How the company came to be watched, when it was not by hand: "sector news" for the Sector Scout."""
    return next((w.get("found_via") for ws in (STORE.live_meta.get("watch") or {}).values() for w in ws if w["id"] == c["entity_id"]), None)


def summary(c: dict) -> dict:
    """An M&A signal card: the definite facts only."""
    rec = STORE.rec_for_case(c["id"])
    co = signal_for(c) or c["co"]
    return {"id": c["id"], "kind": c["kind"], "role": c.get("role", "competitor"), "who": c["who"], "title": c["title"],
            "company": co, "companies": c["cos"], "size": acquirable(c, co),
            "status": c["status"], "status_label": STATUS[c["status"]], "status_at": c["status_at"], "date": c["date"],
            "score": c["score"], "score_detail": score_detail(c["types"]) if c["score"] is not None else None, "chips": list(dict.fromkeys(s["label"] for s in c["signals"]))[:3], "signal_count": len(c["signals"]),
            # each tag's latest signal, so the card can link a tag to the article or filing behind it
            "chip_links": {lab: next(_signal(s) for s in c["signals"] if s["label"] == lab)
                           for lab in dict.fromkeys(s["label"] for s in c["signals"])},
            "listing": listing(c), "found_via": found_via(c), "recommended": {"type": rec["type"], "title": rec["title"], "co": rec["co"]} if rec else None}


def quick_look(c: dict) -> dict:
    return {"signals": [_signal(s) for s in c["signals"][:8]],
            "score": None if c["score"] is None else {"score": c["score"], "rationale": c["rationale"], "types": [type_label(t) for t in c["types"]]}}


def case_detail(c: dict) -> dict:
    return {**summary(c), "quick": quick_look(c), "recommended_by": STORE.rec_for_case(c["id"])}


# ---------- This week ----------
def swot_view(co: str) -> dict | None:
    if co not in STORE.swot:
        return None
    s, src, detail = STORE.swot[co], STORE.swot_source[co], STORE.swot_detail.get(co, {})
    d = lambda q, i: detail[q][i] if i < len(detail.get(q, [])) else {"reasoning": None, "sources": []}
    return {"company": co,
            "S": [{"id": f"S{i + 1}", "text": x, **d("S", i)} for i, x in enumerate(s["S"])],
            "W": [{"id": f"W{i + 1}", "text": x, **d("W", i)} for i, x in enumerate(s["W"])],
            "O": [{"id": f"O{i + 1}", "text": x[0], "case_id": x[1], **d("O", i)} for i, x in enumerate(s["O"])],
            "T": [{"id": f"T{i + 1}", "text": x[0], "case_id": x[1], **d("T", i)} for i, x in enumerate(s["T"])],
            "moves": len(s["rec"]), "set_aside": len(s["skip"]), "source": src, "method": method(co)}


def method(co: str) -> dict:
    src = STORE.swot_source[co]
    rounds = src.get("rounds", 1)
    return {"built_by": "agent", "model": src["model"], "at": src["at"], "rounds": rounds,
            "live_signals_available": len(STORE.live.get(co, [])),
            "summary": f"Built by the SWOT Analyst agent ({src['model']}) on {src['at']} from {src.get('evidence', {}).get('self', 0)} "
                       f"public facts about {co}, {src.get('evidence', {}).get('daily', 0)} kept daily findings and "
                       f"{src.get('evidence', {}).get('live', 0)} signals on the companies it watches.",
            "steps": [f"Public facts about {co} were collected from the sources ticked in its SWOT parameters: quarterly results and "
                      "shareholding, web pages for each analysis factor, and recent news.",
                      "Judged on: " + (", ".join(src.get("factors") or []) or "every factor") + ".",
                      "Every piece of evidence was numbered, with its source and date.",
                      "The agent wrote each strength, weakness, opportunity and threat, cited the evidence behind it and gave its reasoning.",
                      "It scored each opportunity and threat for impact and urgency (above 50 on both means act now).",
                      "It proposed moves, each linking a strength or weakness to an opportunity or threat at a watched company.",
                      f"A rule check verified the draft. It passed after {rounds} round{'s' if rounds != 1 else ''}."]}


def swot_status(co: str) -> dict:
    """Why a company has no SWOT yet, in plain words."""
    if co in STORE.swot:
        return {"built": True, "message": None}
    r = STORE.research.get(co) or {}
    if r.get("facts"):
        return {"built": False, "message": f"No SWOT for {co} yet. {len(r['facts'])} public facts about {co} are ready; "
                "build the SWOT to have the SWOT Analyst write it."}
    return {"built": False, "message": f"No SWOT for {co} yet. Building it first collects public facts about {co} "
            "(quarterly results, shareholding, web and news), then the SWOT Analyst writes the SWOT from them."}


def positions(co: str) -> list[dict]:
    if co not in STORE.swot:
        return []
    recs = STORE.recs_for(co)
    used = {u for r in recs for u in r["uses"]}
    out = []
    for q in ["O", "T"]:
        for i, x in enumerate(STORE.swot[co][q]):
            pid = f"{q}{i + 1}"
            imp, urg = STORE.positions[co][q][i]
            mv = next((r["title"] for r in recs if pid in r["uses"]), None)
            out.append({"id": pid, "q": q, "text": x[0], "case_id": x[1], "impact": imp, "urgency": urg, "used": pid in used, "move": mv})
    return out


def rec_card(r: dict) -> dict:
    return {**r, "tows": TOWS[r["type"]], "uses_text": {u: STORE.swot_item(r["co"], u) for u in r["uses"]}, "case": case_detail(STORE.cases[r["case_id"]])}


def feed(scope: str) -> list[dict]:
    items = []
    for co in (COMPANIES_ORDER if scope == "All" else [scope]):
        for x in STORE.live.get(co, []):
            items.append({**_signal(x), "who": x["company"], "case_id": f"r{x['entity_id']}", "observed_at": x["observed_at"]})
    items = list({(i["case_id"], i["observed_at"], i["text"]): i for i in items}.values())  # one row when shared by two companies
    items.sort(key=lambda x: x["observed_at"], reverse=True)
    return items


def analyst_text(scope: str, cases: list[dict], n_signals: int) -> str:
    where = "across the group" if scope == "All" else f"for {scope}"
    if not cases:
        return (f"No watched company has public signals {where} yet. Signals appear once companies are on the watchlist "
                "(Find rivals, or Admin → Watchlist) and an ingestion run has fetched their filings and news.")
    top = max(cases, key=lambda c: c["score"] or 0)
    tail = f" The highest rule-based score is {top['who']} at {top['score']:.0f}." if top["score"] is not None else ""
    return f"{len(cases)} watched compan{'ies have' if len(cases) != 1 else 'y has'} {n_signals} public signals {where} in the last 120 days.{tail}"


def home(scope: str) -> dict:
    cos = COMPANIES_ORDER if scope == "All" else [scope]
    recs = [rec_card(r) for co in cos for r in STORE.recs_for(co)]
    rec_ids = {r["case_id"] for r in recs}
    skips = [{**s, "who": STORE.cases[s["case_id"]]["who"]} for co in cos for s in STORE.skips_for(co) if s["case_id"] not in rec_ids]
    cases = [c for c in STORE.cases.values() if in_scope(c, scope)]
    watched = sorted((case_detail(c) for c in cases if c["id"] not in rec_ids), key=lambda c: -(c["score"] or 0))
    f = feed(scope)
    return {"scope": scope, "week": week_label(), "analyst": analyst_text(scope, cases, len(f)),
            "recommended": recs, "set_aside": skips, "watched": watched,
            "swot": None if scope == "All" else swot_view(scope), "swot_status": None if scope == "All" else swot_status(scope),
            "positions": None if scope == "All" else positions(scope),
            "tiles": [{"company": co, "swot": swot_view(co), "watched": sum(1 for c in cases if co in c["cos"]),
                       "signals": len(STORE.live.get(co, []))} for co in COMPANIES_ORDER] if scope == "All" else None,
            "signals": f[:14], "signal_count": len(f)}


# ---------- competitors ----------
def roster(co: str) -> list[dict]:
    """Every company on the watchlist for this RPG company, with its signals."""
    rivals = {r["id"]: r for r in STORE.rivals.get(co, [])}
    out = []
    for w in (STORE.live_meta.get("watch") or {}).get(co, []):
        if w["status"] == "dismissed":
            continue
        r = rivals.get(w["id"])
        latest = r["signals"][0] if r else None
        cid = f"r{w['id']}"
        from services import company_size

        from .bridge import CO_TO_CODE
        size = company_size.fit(STORE.sizes.get(company_size.entity_key(w["id"])), STORE.sizes.get(company_size.rpg_key(CO_TO_CODE[co])))
        out.append({"entity_id": w["id"], "name": w["name"], "status": w["status"], "role": w.get("role", "competitor"), "size": size,
                    "score": w["score"], "score_detail": score_detail(r["types"]) if r and w["score"] is not None else None,
                    "signals": len(r["signals"]) if r else 0,
                    "nse_symbol": w.get("nse_symbol"), "origin": w.get("origin"), "found_at": (w.get("found_at") or "")[:10] or None,
                    "signal_status": STORE.cases[cid]["status"] if cid in STORE.cases else None,
                    "latest_move": f"{latest['label']}: {latest['text']}" if latest else None, "latest_date": latest["date"] if latest else None,
                    "why": w["why"], "sources": w["sources"], "case_id": f"r{w['id']}" if f"r{w['id']}" in STORE.cases else None,
                    "timeline": [_signal(s) for s in r["signals"][:10]] if r else []})
    out.sort(key=lambda x: (x["status"] != "watching", -x["signals"], x["name"]))
    return out


def candidates(co: str) -> list[dict]:
    """Targets ``co`` could buy (at most half its size, or not sized yet) that have no public signals yet, so
    they are not M&A signals: found by target discovery, waiting for news, filings or results."""
    from services import company_size

    from .bridge import CO_TO_CODE
    signalled = {c["entity_id"] for c in STORE.cases.values() if c["signals"]}
    out = []
    for w in (STORE.live_meta.get("watch") or {}).get(co, []):
        if w["status"] != "watching" or w.get("role") != "target" or w["id"] in signalled:
            continue
        size = company_size.fit(STORE.sizes.get(company_size.entity_key(w["id"])), STORE.sizes.get(company_size.rpg_key(CO_TO_CODE[co])))
        if size["ok"] is False:
            continue
        out.append({"entity_id": w["id"], "name": w["name"], "size": size, "nse_symbol": w.get("nse_symbol"),
                    "why": w["why"], "sources": w["sources"], "found_at": (w.get("found_at") or "")[:10] or None,
                    "employees": w.get("employees"), "clients": w.get("clients"), "headquarters": w.get("headquarters")})
    out.sort(key=lambda x: (x["size"]["ok"] is not True, x["name"]))
    return out


def watched_companies() -> list[dict]:
    """Every watched company with a score, for watch rules."""
    return [{"case_id": c["id"], "name": c["who"], "score": c["score"], "cos": c["cos"]} for c in STORE.cases.values()]


DEAL_TYPES = {"deal_activity", "fund_raise", "stake_selldown"}


def deals(scope: str) -> list[dict]:
    """Deal-related public signals of watched companies: acquisitions, mergers, divestments, fund raises, stake sales."""
    out = [{**_signal(x), "company": x["company"], "type": type_label(x["signal_type"]), "case_id": f"r{x['entity_id']}",
            "for": co, "observed_at": x["observed_at"]}
           for co in (COMPANIES_ORDER if scope == "All" else [scope]) for x in STORE.live.get(co, []) if x["signal_type"] in DEAL_TYPES]
    out = list({(d["case_id"], d["observed_at"], d["text"]): d for d in out}.values())
    out.sort(key=lambda d: d["observed_at"], reverse=True)
    return out
