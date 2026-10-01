"""Turns stored records into the shapes the screens need."""
from __future__ import annotations

from . import evidence as ev
from . import rules
from .reference import REF
from .store import COMPANIES_ORDER, STORE

MON = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
THREAT_PRIO = {"High": 85, "Medium": 60, "Low": 35}


def dnum(d: str) -> int:
    a, b = d.split(" ")
    return MON.get(b, 0) * 100 + int(a)


def threat_level(c: dict) -> str:
    return c["ws"]["threat"][1].replace("Threat: ", "")


def priority(c: dict) -> int:
    return c["target"]["score"] if c["kind"] == "deal" else THREAT_PRIO.get(threat_level(c), 50)


def in_scope(c: dict, scope: str) -> bool:
    return scope == "All" or scope in c["cos"]


STATUS = {"deep": "Deep dive running", "decide": "In the book · awaiting decision", "act": "In follow-up"}


def summary(c: dict) -> dict:
    s = {"id": c["id"], "kind": c["kind"], "who": STORE.who(c), "title": c["title"], "company": c["co"], "companies": c["cos"],
         "stage": c["stage"], "in_book": c["in_book"], "owner": c["owner"], "outcome": c["outcome"], "date": c["date"],
         "status_label": STATUS.get(c["stage"], c["outcome"] or ("Closed" if c["stage"] == "closed" else ""))}
    if c["kind"] == "deal":
        t = c["target"]
        s.update(score=t["score"], chips=[REF["TYPE_LABEL"][k] for k in t["types"]])
    else:
        s.update(threat=threat_level(c), threat_class=c["ws"]["threat"][0], chips=[x[1] for x in c["ws"]["timeline"][:3]])
    return s


def quick_look(c: dict) -> dict:
    if c["kind"] == "deal":
        t = c["target"]
        th = next((x for x in STORE.theses if x["desk"] == c["co"]), None)
        return {"story": t["story"],
                "signals": [{"date": s[1], "label": REF["TYPE_LABEL"][s[0]], "text": s[2], "source": s[3]} for s in t["signals"]],
                "score": {"parts": [[REF["TYPE_LABEL"][k].lower(), REF["W"][k]] for k in t["types"]], "base": t["base"], "m": t["m"],
                          "capped": t["raw"] > 100, "score": t["score"], "n_types": len(t["types"])},
                "thesis": {"company": c["co"], **rules.thesis_match(th, t)} if th else None,
                "owners": t["owners"], "bidders": t["bidders"]}
    w = c["ws"]
    return {"analyst": w["analyst"], "timeline": [{"date": x[0], "label": x[1], "text": x[2], "source": x[3]} for x in w["timeline"]],
            "spark": w["spark"], "voc_top": {"sentiment": w["voc"][0][1], "topic": w["voc"][0][2], "text": w["voc"][0][3]}}


def case_detail(c: dict) -> dict:
    return {**summary(c), "quick": quick_look(c), "recommended_by": STORE.rec_for_case(c["id"])}


def rec_card(r: dict) -> dict:
    c = STORE.cases[r["case_id"]]
    return {**r, "tows": REF["TOWS"][r["type"]], "uses_text": {u: STORE.swot_item(r["co"], u) for u in r["uses"]}, "case": case_detail(c)}


def positions(co: str) -> list[dict]:
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


def swot_view(co: str) -> dict:
    s, src = STORE.swot[co], STORE.swot_source[co]
    detail = STORE.swot_detail.get(co) if src["by"] == "agent" else None
    detail = detail or ev.demo_detail(co)
    d = lambda q, i: detail[q][i] if i < len(detail[q]) else {"reasoning": None, "sources": []}
    return {"company": co,
            "S": [{"id": f"S{i + 1}", "text": x, **d("S", i)} for i, x in enumerate(s["S"])],
            "W": [{"id": f"W{i + 1}", "text": x, **d("W", i)} for i, x in enumerate(s["W"])],
            "O": [{"id": f"O{i + 1}", "text": x[0], "case_id": x[1], **d("O", i)} for i, x in enumerate(s["O"])],
            "T": [{"id": f"T{i + 1}", "text": x[0], "case_id": x[1], **d("T", i)} for i, x in enumerate(s["T"])],
            "moves": len(s["rec"]), "set_aside": len(s["skip"]), "source": src, "method": method(co)}


def method(co: str) -> dict:
    """How this SWOT was built, in plain words, for the details section."""
    src = STORE.swot_source[co]
    live = len(STORE.live.get(co, []))
    if src["by"] != "agent":
        return {"built_by": "demo", "summary": "Written by hand for the demo. Nobody derived these items from the evidence, so there is no reasoning; "
                "the sources shown are the demo records each item links to.",
                "live_signals_available": live, "steps": []}
    n = src.get("evidence", {})
    basis = (f"{n.get('live', 0)} live signals about {src.get('rival')}" if src.get("live_data")
             else f"the demo rival story (no live signals were available)") + f", {n.get('demo', 0)} demo records on the deal targets"         + f" and the strategy team's list of {n.get('team', 0)} strengths and weaknesses"
    return {"built_by": "agent", "model": src["model"], "at": src["at"], "rounds": src.get("rounds"), "live_signals_available": live,
            "summary": f"Built by the SWOT Analyst agent ({src['model']}) on {src['at']} from {basis}.",
            "steps": ["Every piece of evidence was numbered, with its source, date and whether it is live or demo data.",
                      "The agent wrote each strength, weakness, opportunity and threat, cited the evidence behind it and gave its reasoning.",
                      "It scored each opportunity and threat for impact and urgency (above 50 on both means act now).",
                      "It proposed moves, each linking a strength or weakness to an opportunity or threat, and set aside deal targets whose risks outweigh the fit.",
                      f"A rule check verified the draft: every item cites real evidence, every move links the two halves of the SWOT, every act-now item drives a move, and no case is used twice. "
                      f"It passed after {src.get('rounds', 1)} round{'s' if src.get('rounds', 1) != 1 else ''}."]}


def analyst_text(scope: str) -> str:
    if scope == "All":
        n = sum(len(STORE.recs_for(co)) for co in COMPANIES_ORDER)
        k = len(STORE.group_skips())
        return (f"Across the group, the radar found {n} moves that fit and set {k} aside. The strongest fits close a weakness: "
                "CEAT's supplier risk at Meridian, Zensar's GenAI gap through Northfield and RPG Life Sciences' missing USFDA plant at Veltrix.")
    r, k = STORE.recs_for(scope), len(STORE.swot[scope]["skip"])
    tail = f"; {k} other{' was' if k == 1 else 's were'} set aside" if k else ""
    return f"{STORE.companies[scope]['analyst']} Against {scope}'s strengths and weaknesses, {len(r)} move{'s fit' if len(r) > 1 else ' fits'} this week{tail}."


def feed(scope: str) -> list[dict]:
    items = []
    for c in STORE.cases.values():
        if not in_scope(c, scope):
            continue
        if c["kind"] == "deal":
            for s in c["target"]["signals"]:
                items.append({"date": s[1], "who": STORE.who(c), "label": REF["TYPE_LABEL"][s[0]], "text": s[2], "case_id": c["id"]})
        else:
            for t in c["ws"]["timeline"]:
                items.append({"date": t[0], "who": STORE.who(c), "label": t[1], "text": t[2], "case_id": c["id"]})
    for co in (COMPANIES_ORDER if scope == "All" else [scope]):
        for x in STORE.live.get(co, []):
            items.append({"date": x["date"], "who": x["company"], "label": f"Live · {x['label']}", "text": x["text"],
                          "case_id": f"t_{co}", "live": True, "source": x["source"], "url": x.get("url")})
    items.sort(key=lambda x: -dnum(x["date"]))
    return items


def home(scope: str) -> dict:
    cos = COMPANIES_ORDER if scope == "All" else [scope]
    recs = [rec_card(r) for co in cos for r in STORE.recs_for(co)]
    skips = STORE.group_skips() if scope == "All" else [{"co": scope, "case_id": cid, "why": why} for cid, why in STORE.swot[scope]["skip"]]
    for s in skips:
        s["who"] = STORE.who(STORE.cases[s["case_id"]])
    f = feed(scope)
    return {"scope": scope, "week": "Week 40", "analyst": analyst_text(scope), "recommended": recs, "set_aside": skips,
            "swot": None if scope == "All" else swot_view(scope), "positions": None if scope == "All" else positions(scope),
            "tiles": [swot_view(co) for co in COMPANIES_ORDER] if scope == "All" else None,
            "signals": f[:14], "signal_count": len(f)}


# ---------- detailed overview (one book page) ----------
def overview(c: dict) -> dict:
    base = {"id": c["id"], "kind": c["kind"], "title": c["title"], "who": STORE.who(c), "company": c["co"], "written": c["ov_date"],
            "stage": c["stage"], "owner": c["owner"], "approved": c["approved"], "outcome": c["outcome"],
            "owners": rules.owners_for(c), "plan": rules.plan_for(c)}
    r = STORE.rec_for_case(c["id"])
    if r:
        base["why"] = {"company": r["co"], "title": r["title"], "uses": [{"id": u, "text": STORE.swot_item(r["co"], u)} for u in r["uses"]]}
    if c["kind"] == "deal":
        t, sc = c["target"], c["target"]["scenario"]
        b = rules.make_brief(t)
        th = next((x for x in STORE.theses if x["desk"] == c["co"]), None)
        rec = sc["a"]["opts"][0]
        base.update(
            recommendation={"title": rec[0], "text": rec[1], "decision": f'approve a formal evaluation of {t["name"]}, name an owner and release a diligence budget.', "confidence": sc["conf"]},
            glance=[["Opportunity score", f'{t["score"]} of 100'], ["Financial health", rules.verdict_of(t)[0]],
                    ["Rival interest", sc["rival"] if t["bidders"] else "None seen"], ["Deal complexity", b["complexity"]],
                    ["Competition-law check", b["cci"]], ["Urgency", "High · a rival is moving" if t["bidders"] else "Normal"]],
            story=t["story"], signals=quick_look(c)["signals"], impact=sc["a"]["hit"], pros=b["pros"],
            thesis=rules.thesis_match(th, t)["checks"] if th else [], health=rules.health_block(t),
            scenario={"rival": sc["rival"], "rival_first": sc["a"]["play"], "we_buy": sc["b"]["react"], "basis": sc["basis"]},
            graph={"name": t["name"], "score": t["score"], "owners": t["owners"], "directors": t["directors"], "subs": t["subs"]},
            risks=b["cons"] + sc["b"]["risk"], flags=b["flags"], questions=rules.diligence_questions(t),
            sources=list(dict.fromkeys(s[3] for s in t["signals"])) + ["MCA filings (paid)", "SAST disclosures", "CCI orders", "deal databases"])
    else:
        w, co = c["ws"], c["co"]
        rec = next((o for o in w["war"]["opts"] if o[0] == "rec"), w["war"]["opts"][0])
        f = w["fin"]
        rv = f["rivals"].get(w["rival"])
        market = None
        if rv:
            market = {"rival_return": rv["ret"]["1Y"], "base_return": f["base"]["ret"]["1Y"], "base_name": co if f["listed"] else "the listed sector index",
                      "why": rv["why"], "act": rv["act"]}
        base.update(
            recommendation={"title": rec[1], "text": rec[2], "decision": "approve the response plan and name an owner.", "confidence": w["war"]["conf"]},
            glance=[["Threat level", threat_level(c)], ["Rival", w["rival"]], ["Signals in 60 days", str(len(w["timeline"]))],
                    ["Customer mentions · 30 days", str(sum(v[4] for v in w["voc"]))]],
            timeline=quick_look(c)["timeline"], analyst=w["analyst"], suggest=w["suggest"], market=market,
            voc=[{"sentiment": v[1], "topic": v[2], "text": v[3], "mentions": v[4]} for v in w["voc"]], opening=w["opening"],
            scenario={"question": w["war"]["q"], "play": w["war"]["play"], "basis": w["war"]["basis"]},
            options=[{"recommended": o[0] == "rec", "title": o[1], "text": o[2], "impact": o[3], "cost": o[4], "risk": o[5]} for o in w["war"]["opts"]],
            sources=w["ask"]["src"] + ["exchange price data"])
    return base


def follow_up(c: dict) -> dict:
    return {**summary(c), "approved": c["approved"], "plan": c["plan"], "updates": c["updates"], "watching": rules.watch_for(c)}


# ---------- competitors ----------
def roster(co: str) -> list[dict]:
    w, f = STORE.companies[co], STORE.companies[co]["fin"]
    out = [{"name": w["rival"], "segment": w["seg"], "watch": "Deep", "threat": w["threat"], "signals_30d": len(w["timeline"]) + len(w["voc"]),
            "latest_move": f'{w["timeline"][0][1]}: {w["timeline"][0][2]}', "primary": True, "timeline": w["timeline"], "voc": w["voc"],
            "analyst": w["analyst"], "suggest": w["suggest"], "spark": w["spark"], "tone": w["tone"], "case_id": "t_" + co}]
    for n, r in f["rivals"].items():
        if n == w["rival"]:
            continue
        out.append({"name": n, "segment": r["seg"], "watch": "Deep" if co + n in STORE.followed else "Standard", "threat": ["watch", "Threat: Medium"],
                    "signals_30d": 2, "latest_move": r["ev"][1], "why": r["why"], "act": r["act"], "primary": False})
    for x in w["extra_rivals"]:
        out.append({"name": x["name"], "segment": x["segment"], "watch": "Deep" if co + x["name"] in STORE.followed else "Light",
                    "threat": ["watch", "Threat: Low"], "signals_30d": 1, "latest_move": x["latest_move"], "primary": False})
    return out
