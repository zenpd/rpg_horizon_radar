"""Ask Radar. Keyword rules answer first, over what the radar already holds, so those answers are
traceable. A question the rules cannot match goes to the small Azure model (llm_azure), which may
only use numbered evidence from the radar; every point must cite one, and uncited points are dropped.
Production: retrieval over stored signals, checked by the Fact-Checker agent before it is shown."""
from __future__ import annotations

import re

from . import rules
from .llm_azure import AZURE, AzureError
from .reference import REF
from .store import STORE

STOP = set("which what where when how does has have been that this with from about rival rivals company companies the and for are is in on of to its their doing".split())


def suggestions(co: str) -> list[str]:
    w = STORE.companies[co]
    return w["ask"]["try"] + [f'What has {w["rival"]} been doing?', "How is the opportunity score calculated?", "What risks is the radar watching?"]


def first_turn(co: str) -> dict:
    a = STORE.companies[co]["ask"]
    return {"question": a["q"], "lead": a["lead"], "points": a["pts"], "meaning": a["mean"], "confidence": a["conf"], "sources": a["src"]}


def answer(co: str, question: str) -> dict:
    q, w = question.lower(), STORE.companies[co]
    targets = [t for t in STORE.targets if co in t["desks"]]
    rival_names = [w["rival"], *w["fin"]["rivals"].keys()]
    hit = next((n for n in rival_names if n.lower() in q), None)
    if hit:
        if hit == w["rival"]:
            t0 = w["timeline"][0]
            return {"lead": f'Here\'s the latest the radar has tracked on {w["rival"]}:',
                    "points": [[f"{t0[0]} · {t0[1]}: {t0[2]}", 1], [w["analyst"], 2], [f'Customers say: {w["voc"][0][2]} {w["voc"][0][3]}', 3]],
                    "meaning": w["suggest"], "confidence": 78, "sources": [t0[3], "Voice of Customer tracker", "Analyst synthesis"]}
        r = w["fin"]["rivals"][hit]
        vs = co if w["fin"]["listed"] else "the sector index"
        return {"lead": f'On {hit} ({r["seg"]}) versus {vs}:',
                "points": [[f'1-year share price return: {rules.pct(r["ret"]["1Y"])}', 1], [r["why"], 2], [r["act"], 3]],
                "meaning": r["act"], "confidence": 74, "sources": ["Market & Financials Tracker", "Exchange price data"]}
    if re.search(r"\bscor(e|ing)\b|how.*(calculat|work)", q):
        s = max(targets, key=lambda t: t["score"]) if targets else STORE.targets[0]
        parts = " + ".join(f'{REF["TYPE_LABEL"][k].lower()} {REF["W"][k]}' for k in s["types"])
        return {"lead": "Every opportunity score is rule-based, never a black box:",
                "points": [["Each distinct signal type carries a fixed weight. For example, an insolvency filing is worth 35 and a leadership departure 20.", 1],
                           ["The weights for every distinct type touching a company are added up, then multiplied by a co-occurrence factor (1.0× for one type, up to 2.0× for four or more).", 2],
                           [f'For example, {s["name"]}: {parts} = {s["base"]}, × {s["m"]} → {s["score"]}.', 3],
                           ["Scores are capped at 100 and never use non-public information.", 1]],
                "meaning": "a higher score means more independent signal types point the same way at once, not that any single signal matters more.",
                "confidence": 95, "sources": ["Radar scoring rules (fixed, shown to every user)", "Signal weights table"]}
    if re.search(r"\brisks?\b", q):
        neg = next((v for v in w["voc"] if v[0] == "crit"), w["voc"][0])
        pts = [[f"{neg[2]} {neg[3]}", 1]]
        if targets:
            t = max(targets, key=lambda x: x["score"])
            b = rules.make_brief(t)
            pts.append([f'On {t["name"]}: {b["cons"][0]}', 2])
            if b["flags"][0] != "None found in public sources":
                pts.append([f'Red flag on {t["name"]}: {b["flags"][0]}', 3])
        return {"lead": f"The main risks the radar is watching around {co} right now:", "points": pts,
                "meaning": "none of this is confirmed by diligence. Treat it as a prompt to look closer, not a verdict.", "confidence": 70,
                "sources": ["Voice of Customer tracker", "Public-signal pattern matching (no non-public information)"]}
    tgt = next((t for t in STORE.targets if t["name"].lower() in q or t["name"].split(" ")[0].lower() in q), None)
    if tgt:
        s0 = tgt["signals"][0]
        return {"lead": f'{tgt["name"]} ({tgt["category"]}, {tgt["geo"]}): opportunity score {tgt["score"]} of 100.',
                "points": [[tgt["business"], 1], [f"{s0[1]} · {s0[2]}", 2], [f'Routed to {", ".join(tgt["desks"])}.', 3]],
                "meaning": tgt["title"] + ".", "confidence": 82, "sources": [s0[3], "Radar scoring rules"]}
    words = [x for x in re.sub(r"[^a-z0-9\s]", " ", q).split() if len(x) > 3 and x not in STOP]
    if words:
        best, best_score = None, 0
        for t in w["timeline"]:
            hay = (t[1] + " " + t[2]).lower()
            sc = sum(1 for x in words if x in hay)
            if sc > best_score:
                best, best_score = t, sc
        if best:
            return {"lead": f'Closest match from what the radar has tracked on {w["rival"]}:',
                    "points": [[f"{best[0]} · {best[1]}: {best[2]}", 1], [w["analyst"], 2]],
                    "meaning": w["suggest"], "confidence": 62, "sources": [best[3], "Analyst synthesis"]}
    return llm_answer(co, question) or {"fallback": True, "suggestions": suggestions(co)}


ASK_SYSTEM = """You answer questions for the RPG Group strategy team in Ask Radar.
Use only the numbered evidence you are given. Every point must cite the number of the evidence it comes from.
If the evidence does not answer the question, return no points. Keep each point to one short, plain sentence.
lead: one line introducing the answer. meaning: what it means for the RPG company, starting in lower case.
confidence: 0-100, how well the evidence answers the question."""


def evidence_for(co: str) -> list[tuple[str, str]]:
    """(text, source) pairs the model may cite, numbered from 1 in the prompt."""
    w = STORE.companies[co]
    ev = [(f"{t[0]} · {w['rival']} · {t[1]}: {t[2]}", t[3]) for t in w["timeline"]]
    ev.append((f"Analyst read on {w['rival']}: {w['analyst']}", "Analyst synthesis"))
    ev += [(f"Customers on {w['rival']}: {v[1].lower()}, {v[2]} {v[3]} ({v[4]} mentions)", "Voice of Customer tracker") for v in w["voc"]]
    for t in STORE.targets:
        if co in t["desks"]:
            ev.append((f"{t['name']} ({t['category']}, {t['geo']}), opportunity score {t['score']}: {t['story']}", "Radar deal signals"))
    return ev


def llm_answer(co: str, question: str) -> dict | None:
    if not AZURE.available:
        return None
    ev = evidence_for(co)
    schema = {"type": "object", "additionalProperties": False, "required": ["lead", "points", "meaning", "confidence"],
              "properties": {"lead": {"type": "string"}, "meaning": {"type": "string"}, "confidence": {"type": "integer"},
                             "points": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["text", "evidence"],
                                                                   "properties": {"text": {"type": "string"}, "evidence": {"type": "integer"}}}}}}
    prompt = f"RPG company: {co}\nQuestion: {question}\n\nEvidence:\n" + "\n".join(f"[{i}] {t}" for i, (t, _) in enumerate(ev, 1))
    try:
        r = AZURE.complete_json(ASK_SYSTEM, prompt, schema, "ask_answer")
    except AzureError:
        return None
    cited = [p for p in r["points"] if 1 <= p["evidence"] <= len(ev)][:4]
    if not cited:
        return None
    srcs = list(dict.fromkeys(ev[p["evidence"] - 1][1] for p in cited))
    return {"lead": r["lead"], "points": [[p["text"], srcs.index(ev[p["evidence"] - 1][1]) + 1] for p in cited],
            "meaning": r["meaning"], "confidence": max(0, min(70, r["confidence"])),  # generated answers never outrank rule answers
            "sources": srcs, "generated_by": AZURE.deployment}
