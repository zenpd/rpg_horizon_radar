"""SWOT Analyst agent. Reads one RPG company's evidence (its own record, the rival's signals and the
deal targets on its desk), asks an LLM for a SWOT with TOWS moves, checks the draft against the same
rules the screens rely on, and sends any problems back for a revision. A draft that passes replaces
the mock SWOT in the store; one that never passes leaves the current SWOT untouched.

Runs as a background job (202 + polling), like the deep dive. The model comes from the repo's
shared routes (llm_chat.py): Groq gpt-oss-120b at low reasoning effort, then NVIDIA Nemotron,
then Azure OpenAI. It never changes a signal score — scoring stays rule-based."""
from __future__ import annotations

import itertools
import json
import re
import threading
from datetime import datetime

from . import evidence as ev
from . import persistence, post_acquisition
from .bridge import CO_TO_CODE
from .reference import REF
from .store import STORE

MAX_ROUNDS = 3  # first draft plus up to two revisions

SYSTEM = """You are the SWOT Analyst for RPG Horizon Radar, the competitive intelligence and M&A radar of the RPG Group.

For one RPG company you write its SWOT and the TOWS moves that follow from it, from a numbered list of evidence. Each evidence item has an id (E1, E2 ...), the case it belongs to, a date, a source and whether it is live data or demo data.
- Strengths and weaknesses describe the RPG company itself. Start from the strategy team's list (evidence from "Strategy team list"); keep an item unless other evidence contradicts it, and add one only when the evidence clearly supports it.
- Opportunities and threats come from the rest of the evidence: the rival's moves, what customers say about the rival, market facts and the deal targets on this company's desk.
- Evidence that starts "Customers on <rival>'s products" is about the RIVAL's products, not the RPG company's. A complaint about the rival is an opening for the RPG company (an opportunity), never a weakness or threat of the RPG company.
- Live evidence is real, recent public data about the named rival. Prefer it over demo data when both bear on a point.
- Every SWOT item lists the ids of the evidence it rests on (at least one), and gives its reasoning: one or two sentences on how that evidence leads to the item.
- Link an opportunity or threat to a case only when its evidence belongs to that case: t_<company> for the rival, d_<target> for that deal target. Otherwise use null. A move's case is the case its opportunity or threat comes from.
- Score every opportunity and threat for impact and urgency, each 0-100, from the evidence alone. Above 50 on both means act now. Never change a score to satisfy a rule, and do not mention the rules in any reasoning.
- A move is recommended only when it links at least one strength or weakness to at least one opportunity or threat. Its type names the pair it uses: SO, WO, ST or WT. Every move points to one case, and no case is used by two moves.
- Every item that scores above 50 on both impact and urgency must be used by at least one move.
- Each move's why is one or two sentences on why it matters now, citing the specific evidence (who did what, when, how much).
- Weigh a deal target's red flags (rating cuts, auditor exits, promoter pledges, governance issues, insolvency) against its fit. A target whose risks outweigh the fit goes in set_aside, not in a move.
- A deal target that is on the desk but does not earn a move goes in set_aside, with a one-sentence reason.

Refer to SWOT items by position: S1, S2 ... W1 ... O1 ... T1, in the order you list them. Use those ids only in a move's uses, and evidence ids only in evidence lists; never write any id, score or case id inside a text, reasoning or why field.
Write short, plain sentences a busy strategy head can scan. Use only the evidence given; do not invent facts, numbers or names."""


def _schema(case_ids: list[str], evidence_ids: list[str]) -> dict:
    case = {"type": "string", "enum": case_ids}
    cites = {"type": "array", "items": {"type": "string", "enum": evidence_ids}}
    internal = {"type": "object", "additionalProperties": False, "required": ["text", "evidence", "reasoning"],
                "properties": {"text": {"type": "string"}, "evidence": cites, "reasoning": {"type": "string"}}}
    external = {"type": "object", "additionalProperties": False, "required": ["text", "case_id", "impact", "urgency", "evidence", "reasoning"],
                "properties": {"text": {"type": "string"}, "case_id": {"anyOf": [case, {"type": "null"}]},
                               "impact": {"type": "integer"}, "urgency": {"type": "integer"}, "evidence": cites, "reasoning": {"type": "string"}}}
    move = {"type": "object", "additionalProperties": False, "required": ["type", "title", "uses", "case_id", "why"],
            "properties": {"type": {"type": "string", "enum": list(REF["TOWS"])}, "title": {"type": "string"},
                           "uses": {"type": "array", "items": {"type": "string"}}, "case_id": case, "why": {"type": "string"}}}
    skip = {"type": "object", "additionalProperties": False, "required": ["case_id", "why"],
            "properties": {"case_id": case, "why": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False,
            "required": ["strengths", "weaknesses", "opportunities", "threats", "moves", "set_aside"],
            "properties": {"strengths": {"type": "array", "items": internal}, "weaknesses": {"type": "array", "items": internal},
                           "opportunities": {"type": "array", "items": external}, "threats": {"type": "array", "items": external},
                           "moves": {"type": "array", "items": move}, "set_aside": {"type": "array", "items": skip}}}


# ---------- evidence ----------
def candidate_cases(co: str) -> list[str]:
    return [c["id"] for c in STORE.cases.values() if (c["kind"] == "deal" and co in c["cos"]) or c["id"] == f"t_{co}"]


def evidence(co: str) -> dict:
    """What the agent reads. The numbered items come from evidence.registry."""
    reg = ev.registry(co)
    targets = [{"case_id": c["id"], "name": c["target"]["name"], "headline": c["target"]["title"]}
               for c in STORE.cases.values() if c["kind"] == "deal" and co in c["cos"]]
    return {"company": co, "segment": STORE.companies[co]["seg"],
            "rival": {"case_id": f"t_{co}", "name": ev.rival_name(co), "live_data": ev.uses_live(co)},
            "deal_targets": targets,
            "evidence": [{"id": x["id"], "case_id": x["case_id"], "date": x["date"], "source": x["source"],
                          "origin": x["origin"], "text": x["text"]} for x in reg]}


# ---------- checks ----------
def check(draft: dict, co: str, evidence_ids: set[str] | None = None) -> list[str]:
    """The rules the Home screen depends on. Returns problems; empty means the draft can be used."""
    errs: list[str] = []
    cand = set(candidate_cases(co))
    ids = evidence_ids if evidence_ids is not None else {x["id"] for x in ev.registry(co)}
    keys = {"S": "strengths", "W": "weaknesses", "O": "opportunities", "T": "threats"}
    counts = {q: len(draft[k]) for q, k in keys.items()}
    for q, (lo, hi) in {"S": (2, 5), "W": (2, 5), "O": (1, 6), "T": (1, 6)}.items():
        if not lo <= counts[q] <= hi:
            errs.append(f"List {lo}-{hi} items under {q}; you listed {counts[q]}.")
    refs = {f"{q}{i + 1}" for q, n in counts.items() for i in range(n)}
    for q, key in keys.items():
        for i, x in enumerate(draft[key]):
            if not x["evidence"]:
                errs.append(f"{q}{i + 1} cites no evidence; list the evidence ids it rests on.")
            bad = [e for e in x["evidence"] if e not in ids]
            if bad:
                errs.append(f"{q}{i + 1} cites {', '.join(bad)}, which are not in the evidence list.")
            if not x["reasoning"].strip():
                errs.append(f"{q}{i + 1} has no reasoning.")
    for q, key in (("O", "opportunities"), ("T", "threats")):
        for i, x in enumerate(draft[key]):
            if not (0 <= x["impact"] <= 100 and 0 <= x["urgency"] <= 100):
                errs.append(f"{q}{i + 1}: impact and urgency must be between 0 and 100.")
            if x["case_id"] is not None and x["case_id"] not in cand:
                errs.append(f"{q}{i + 1}: case_id {x['case_id']} is not on {co}'s desk.")
    moves = draft["moves"]
    if not 1 <= len(moves) <= 4:
        errs.append(f"Recommend 1-4 moves; you recommended {len(moves)}.")
    used: set[str] = set()
    seen: set[str] = set()
    for m in moves:
        name = f"Move '{m['title']}'"
        bad = [u for u in m["uses"] if u not in refs]
        if bad:
            errs.append(f"{name} uses {', '.join(bad)}, which do not exist.")
        quads = {u[0] for u in m["uses"] if u in refs}
        if not quads & {"S", "W"} or not quads & {"O", "T"}:
            errs.append(f"{name} must use at least one strength or weakness and at least one opportunity or threat.")
        for letter in m["type"]:
            if letter not in quads:
                errs.append(f"{name} is type {m['type']} but uses no {letter} item.")
        if m["case_id"] not in cand:
            errs.append(f"{name}: case_id {m['case_id']} is not on {co}'s desk.")
        if m["case_id"] in seen:
            errs.append(f"{name}: case {m['case_id']} is already used by another move.")
        seen.add(m["case_id"])
        used |= set(m["uses"])
    for q, key in (("O", "opportunities"), ("T", "threats")):
        for i, x in enumerate(draft[key]):
            if x["impact"] > 50 and x["urgency"] > 50 and f"{q}{i + 1}" not in used:
                errs.append(f"{q}{i + 1} scores above 50 on impact and urgency, so a move must use it. Add or extend a move; do not change the scores to get past this rule.")
    texts = [t for k in keys.values() for x in draft[k] for t in (x["text"], x["reasoning"])] \
        + [t for m in moves for t in (m["title"], m["why"])] + [s["why"] for s in draft["set_aside"]]
    leaked = sorted({ref for t in texts for ref in re.findall(r"\b(?:[SWOT][1-9]|E\d{1,3})\b", t)})
    if leaked:
        errs.append(f"Text fields mention ids ({', '.join(leaked)}). Write plain sentences; ids belong only in uses and evidence lists.")
    for s in draft["set_aside"]:
        if s["case_id"] in seen:
            errs.append(f"Set-aside case {s['case_id']} is also recommended; pick one.")
        if s["case_id"] not in cand:
            errs.append(f"Set-aside case {s['case_id']} is not on {co}'s desk.")
    return errs


def to_store(draft: dict, reg: list[dict]) -> tuple[dict, dict, dict]:
    """Agent draft -> the compact shapes swot.json uses, plus each item's reasoning and sources."""
    swot = {"S": [x["text"] for x in draft["strengths"]], "W": [x["text"] for x in draft["weaknesses"]],
            "O": [[x["text"], x["case_id"]] for x in draft["opportunities"]],
            "T": [[x["text"], x["case_id"]] for x in draft["threats"]],
            "rec": [[m["type"], m["title"], m["uses"], m["case_id"], m["why"]] for m in draft["moves"]],
            "skip": [[s["case_id"], s["why"]] for s in draft["set_aside"]]}
    pos = {"O": [[x["impact"], x["urgency"]] for x in draft["opportunities"]],
           "T": [[x["impact"], x["urgency"]] for x in draft["threats"]]}
    by_id = {x["id"]: x for x in reg}
    detail = {q: [{"reasoning": x["reasoning"], "sources": ev.cite([by_id[e] for e in dict.fromkeys(x["evidence"]) if e in by_id])}
                  for x in draft[k]]
              for q, k in (("S", "strengths"), ("W", "weaknesses"), ("O", "opportunities"), ("T", "threats"))}
    return swot, pos, detail


# ---------- drafters: one model call each; the loop below is provider-neutral ----------
class AgentError(Exception):
    pass


def default_drafter():
    """The repo's shared LLM routes (Groq, then NVIDIA, then Azure OpenAI); see llm_chat.py."""
    from .llm_chat import ChatDrafter, ChatError

    try:
        return ChatDrafter()
    except ChatError as e:
        raise AgentError(str(e))


# ---------- the agent loop ----------
def run(co: str, drafter=None, on_round=None) -> dict:
    """Draft, check, revise. Returns {draft, registry, rounds} or raises AgentError."""
    from .llm_chat import ChatError

    drafter = drafter or default_drafter()
    reg = ev.registry(co)
    ids = [x["id"] for x in reg]
    schema = _schema(candidate_cases(co), ids)
    messages = [{"role": "user", "content": "Write the SWOT and moves for this RPG company from this evidence.\n\n"
                 + json.dumps(evidence(co), indent=1, ensure_ascii=False)}]
    errs: list[str] = []
    for rnd in range(1, MAX_ROUNDS + 1):
        if on_round:
            on_round(rnd)
        try:
            text, reply = drafter.draft(SYSTEM, messages, schema)
        except ChatError as e:
            raise AgentError(str(e))
        try:
            draft = json.loads(text)
            errs = check(draft, co, set(ids))
        except json.JSONDecodeError as e:
            errs = [f"The reply was not valid JSON ({e.msg} at character {e.pos}). Return only the JSON object."]
        except KeyError as e:
            errs = [f"The reply is missing the field {e}. Return the JSON object with every field."]
        except (TypeError, AttributeError):
            errs = ["A field in the reply has the wrong type. Follow the schema exactly."]
        if not errs:
            return {"draft": draft, "registry": reg, "rounds": rnd}
        messages += [reply, {"role": "user", "content": "The draft breaks these rules. Fix them and return the full SWOT again.\n- " + "\n- ".join(errs)}]
    raise AgentError(f"The draft still broke {len(errs)} rule(s) after {MAX_ROUNDS} rounds: " + " ".join(errs[:3]))


# ---------- background jobs ----------
_ids = itertools.count(1)
JOBS: dict[str, dict] = {}


def _reproject_approved_cases(co: str) -> None:
    """A fresh SWOT may newly cite a deal case that was already approved before this rebuild —
    the one scenario views.overview()'s "rebuild to capture this" hint points at. Keep every
    already-approved deal case on this company's desk in sync with the SWOT that now exists,
    not just the one the hint was shown for."""
    for c in list(STORE.cases.values()):
        if c["kind"] == "deal" and co in c["cos"] and c["stage"] in ("act", "closed"):
            projection = post_acquisition.project(co, c["id"])
            if projection:
                STORE.post_acq_swot[(co, c["id"])] = projection
                persistence.save_post_acquisition(CO_TO_CODE[co], c["id"], projection)


def start(co: str, user: str, drafter=None) -> dict:
    running = next((j for j in JOBS.values() if j["company"] == co and j["status"] == "running"), None)
    if running:
        return running
    jid = f"swot_{next(_ids)}"
    job = {"id": jid, "company": co, "status": "running", "round": 0, "max_rounds": MAX_ROUNDS, "error": None,
           "started": datetime.now().strftime("%d %b %H:%M")}
    JOBS[jid] = job

    def work():
        nonlocal drafter
        try:
            drafter = drafter or default_drafter()
            out = run(co, drafter, on_round=lambda r: job.update(round=r))
            STORE.swot[co], STORE.positions[co], STORE.swot_detail[co] = to_store(out["draft"], out["registry"])
            origins = [x["origin"] for x in out["registry"]]
            STORE.swot_source[co] = {"by": "agent", "model": drafter.model, "at": datetime.now().strftime("%d %b %H:%M"),
                                     "rounds": out["rounds"], "live_data": ev.uses_live(co), "rival": ev.rival_name(co),
                                     "evidence": {o: origins.count(o) for o in ("live", "demo", "team")}}
            STORE.save_agent_swot(co)
            _reproject_approved_cases(co)
            STORE.audit(user, "swot_rebuild", co)
            job["status"] = "completed"
        except AgentError as e:
            job.update(status="failed", error=str(e))
        except Exception as e:  # keep the job pollable whatever happens
            job.update(status="failed", error=f"Unexpected error: {e}")

    threading.Thread(target=work, daemon=True).start()
    return job
