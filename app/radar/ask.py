"""Ask Radar. Keyword rules answer first, over the public signals of the companies this RPG
company watches and the scoring rules, so those answers are traceable. A question the rules cannot
match goes to the small Azure model (agents/llm_azure.py), which may only use the numbered evidence
(evidence.py); every point must cite one, and uncited points are dropped. Production: retrieval
over stored signals, checked by a Fact-Checker agent before it is shown (not built)."""
from __future__ import annotations

import re

from agents.llm_azure import AZURE, AzureError
from services import scoring

from .evidence import registry, rival_names
from .store import STORE

STOP = set("which what where when how does has have been that this with from about rival rivals company companies the and for are is in on of to its their doing".split())
RISK_TYPES = {"credit_downgrade", "delayed_filing", "legal_action", "auditor_change", "leadership_churn", "promoter_pledge",
              "earnings_decline", "stake_selldown", "share_price_slump", "hiring_scaledown", "press_distress"}
MEANING = "these are public signals on a watchlist company. Open the linked source before acting on any of them."


def suggestions(co: str) -> list[str]:
    return [*(f"What has {n} been doing?" for n in rival_names(co)[:3]),
            "How is the opportunity score calculated?", "What risks is the radar watching?"]


def _points(signals: list[dict], with_company: bool = False) -> tuple[list[list], list[str]]:
    """Points citing each signal's source, numbered into the de-duplicated source list."""
    srcs = list(dict.fromkeys(x["source"] for x in signals))
    who = (lambda x: f"{x['company']} · ") if with_company else (lambda x: "")
    return [[f"{who(x)}{x['date']} · {x['label']}: {x['text']}", srcs.index(x["source"]) + 1] for x in signals], srcs


def answer(co: str, question: str) -> dict:
    q, live = question.lower(), STORE.live.get(co) or []
    hit = next((r for r in STORE.rivals.get(co, []) if r["name"].lower() in q), None)
    if hit:
        pts, srcs = _points(hit["signals"][:3])
        return {"lead": f"Here's the latest the radar has from public sources on {hit['name']}:", "points": pts,
                "meaning": MEANING, "confidence": 80, "sources": srcs}
    if re.search(r"\bscor(e|ing)\b|how.*(calculat|work)", q):
        pts = [["Each distinct signal type carries a fixed weight. For example, a credit downgrade is worth "
                f"{scoring.BASE_WEIGHTS['credit_downgrade']} and leadership churn {scoring.BASE_WEIGHTS['leadership_churn']}.", 1],
               ["The weights of every distinct type seen in a 90-day window are added up, then multiplied by a co-occurrence factor "
                "(1.0× for one type, up to 2.0× for four or more).", 1],
               ["Scores are capped at 100 and use only public information.", 1]]
        scored = [r for r in STORE.rivals.get(co, []) if r["score"] is not None]
        if scored:
            top = max(scored, key=lambda r: r["score"])
            pts.insert(2, [f"For example, {top['rationale']}", 2])
        return {"lead": "Every opportunity score is rule-based, never a black box:", "points": pts,
                "meaning": "a higher score means more independent signal types point the same way at once, not that any single signal matters more.",
                "confidence": 95, "sources": ["Radar scoring rules (services/scoring.py)", *(["Score rationale for a watched company"] if scored else [])]}
    if re.search(r"\brisks?\b", q):
        risky = [x for x in live if x.get("signal_type") in RISK_TYPES][:3]
        if risky:
            pts, srcs = _points(risky, with_company=True)
            return {"lead": f"The latest distress signals among the companies {co} watches:", "points": pts,
                    "meaning": "none of this is confirmed by diligence. Treat it as a prompt to look closer, not a verdict.",
                    "confidence": 70, "sources": srcs}
    words = [x for x in re.sub(r"[^a-z0-9\s]", " ", q).split() if len(x) > 3 and x not in STOP]
    if words and live:
        best = max(live, key=lambda x: sum(1 for k in words if k in (x["label"] + " " + x["text"]).lower()))
        if any(k in (best["label"] + " " + best["text"]).lower() for k in words):
            pts, srcs = _points([best], with_company=True)
            return {"lead": "Closest match from the public signals the radar holds:", "points": pts,
                    "meaning": MEANING, "confidence": 62, "sources": srcs}
    return llm_answer(co, question) or {"fallback": True, "suggestions": suggestions(co)}


ASK_SYSTEM = """You answer questions for the RPG Group strategy team in Ask Radar.
Use only the numbered evidence you are given. Every point must cite the number of the evidence it comes from.
If the evidence does not answer the question, return no points. Keep each point to one short, plain sentence.
lead: one line introducing the answer. meaning: what it means for the RPG company, starting in lower case.
confidence: 0-100, how well the evidence answers the question."""


def evidence_for(co: str) -> list[tuple[str, str]]:
    """(text, source) pairs the model may cite, numbered from 1 in the prompt."""
    return [(f"{x['date']} · {x['text']}", x["source"]) for x in registry(co)]


def llm_answer(co: str, question: str) -> dict | None:
    ev = evidence_for(co)
    if not AZURE.available or not ev:
        return None
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
