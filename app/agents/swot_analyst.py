"""SWOT Analyst agent. Reads one RPG company's numbered evidence (radar/evidence.py), asks an LLM
for a SWOT with TOWS moves, checks the draft against the same rules the screens rely on, and sends
any problems back for a revision. A draft that passes becomes the company's SWOT; one that never
passes leaves the current SWOT untouched.

Strengths and weaknesses rest on public research on the RPG company itself
(services/company_research.py: results, shareholding, web and news); opportunities and threats on
that research, the signals of the companies it watches and the daily findings users kept. Which
evidence it reads, and the analysis factors it tags every item with, follow the company's SWOT
parameters (services/swot_settings.py). The scheduler rebuilds every SWOT weekly (build()). A job first refreshes the research
when it is missing or stale; with no research at all, missing_evidence() says so and the agent does
not run: it never writes a strength or weakness it cannot cite.

Runs as a background job (202 + polling). The model comes from the shared
routes (llm_routes.py): Groq gpt-oss-120b at low reasoning effort, then NVIDIA Nemotron, then
Azure OpenAI. It never changes a signal score — scoring stays rule-based."""
from __future__ import annotations

import itertools
import json
import re
import threading
from datetime import datetime

from agents.llm_routes import Drafter, LLMError
from radar import evidence as ev
from radar.store import STORE
from radar.views import TOWS
from shared.logger import get_logger
from services import company_research, swot_settings

MAX_ROUNDS = 3  # first draft plus up to two revisions

SYSTEM = """You are the SWOT Analyst for RPG Horizon Radar, the competitive intelligence and M&A radar of the RPG Group.

For one RPG company you write its SWOT and the TOWS moves that follow from it, from a numbered list of public evidence. Each evidence item has an id (E1, E2 ...), its origin, the case it belongs to (or null), a date and a source.
- Evidence with origin "self" is about the RPG company itself: its results, shareholding, business and news. Evidence with origin "live" is about a company it watches, and belongs to that company's case. Evidence with origin "daily" is a finding from recent news that the team kept.
- Tag every SWOT item with the one factor, from the factors given, that it is about. Cover each factor where the evidence supports it; skip a factor the evidence says nothing about rather than guess.
- Strengths and weaknesses describe the RPG company itself and rest only on "self" evidence: what it does well or badly today, shown by its results, market position, products, capacity, people or news.
- Opportunities and threats are outside the company: market and industry trends in the "self" and "daily" evidence, and the filings, results, deals and news of the companies it watches.
- Prefer concrete facts (figures, dates, names) to general claims, and say how recent they are. If the evidence on a point is thin or dated, say so in the reasoning rather than overstating it.
- Prefer the company's reported results, filings and its own announcements, then established news outlets. A single day's share-price move, a stock rating or a trading tip is not a strength, weakness, opportunity or threat.
- Use a figure only with the period it covers (quarter or year) exactly as the evidence states it; never relabel a quarter as a year. When two pieces of evidence disagree, use the company's reported results or the more recent one, or leave the point out.
- Every SWOT item lists the ids of the evidence it rests on (at least one), and gives its reasoning: one or two sentences on how that evidence leads to the item.
- Link an opportunity or threat to a case only when its evidence belongs to that case (the case id given with the evidence). Otherwise use null. A move's case is the case its opportunity or threat comes from.
- Score every opportunity and threat for impact and urgency, each 0-100, from the evidence alone. Above 50 on both means act now. Never change a score to satisfy a rule, and do not mention the rules in any reasoning.
- A move is recommended only when it links at least one strength or weakness to at least one opportunity or threat. Its type names the pair it uses: SO, WO, ST or WT. Every move points to one watched company's case, and no case is used by two moves. When the company watches no company with evidence, return no moves and an empty set_aside.
- When there are watched companies, every item that scores above 50 on both impact and urgency must be used by at least one move.
- Each move's why is one or two sentences on why it matters now, citing the specific evidence (who did what, when, how much).
- A watched company with evidence that does not earn a move goes in set_aside, with a one-sentence reason.

Refer to SWOT items by position: S1, S2 ... W1 ... O1 ... T1, in the order you list them. Use those ids only in a move's uses, and evidence ids only in evidence lists; never write any id, score or case id inside a text, reasoning or why field.
Write short, plain sentences a busy strategy head can scan. Use only the evidence given; do not invent facts, numbers or names."""


def _schema(case_ids: list[str], evidence_ids: list[str], factors: list[str]) -> dict:
    case = {"type": "string", "enum": case_ids} if case_ids else {"type": "string"}  # no cases: check() allows no moves
    cites = {"type": "array", "items": {"type": "string", "enum": evidence_ids}}
    factor = {"type": "string", "enum": factors}
    internal = {"type": "object", "additionalProperties": False, "required": ["text", "factor", "evidence", "reasoning"],
                "properties": {"text": {"type": "string"}, "factor": factor, "evidence": cites, "reasoning": {"type": "string"}}}
    external = {"type": "object", "additionalProperties": False, "required": ["text", "factor", "case_id", "impact", "urgency", "evidence", "reasoning"],
                "properties": {"text": {"type": "string"}, "factor": factor, "case_id": {"anyOf": [case, {"type": "null"}]},
                               "impact": {"type": "integer"}, "urgency": {"type": "integer"}, "evidence": cites, "reasoning": {"type": "string"}}}
    move = {"type": "object", "additionalProperties": False, "required": ["type", "title", "uses", "case_id", "why"],
            "properties": {"type": {"type": "string", "enum": list(TOWS)}, "title": {"type": "string"},
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
    return [c["id"] for c in STORE.cases.values() if co in c["cos"]]


def missing_evidence(co: str) -> str | None:
    """Why the agent cannot write this company's SWOT, or None when it can."""
    if not ev.research(co):
        errors = (STORE.research.get(co) or {}).get("errors") or []
        why = f" The last attempt failed: {'; '.join(errors[:2])}" if errors else ""
        return (f"No public research on {co} itself yet (results, shareholding, web and news), so the SWOT Analyst cannot write "
                f"its strengths and weaknesses. Research needs TAVILY_API_KEY, GNEWS_API_KEY or FINCRUX_API_KEY.{why}")
    return None


def factors(co: str) -> list[str]:
    """The labels of the analysis factors ticked in the company's SWOT parameters."""
    return [swot_settings.FACTORS[k][0] for k in ev.settings(co)["factors"]]


def research_due(co: str) -> bool:
    return company_research.due(STORE.research.get(co) or {})


def evidence(co: str) -> dict:
    """What the agent reads. The numbered items come from evidence.registry."""
    return {"company": co, "factors": factors(co),
            "watched_companies": [{"case_id": c["id"], "name": c["who"]} for c in STORE.cases.values() if co in c["cos"]],
            "evidence": [{"id": x["id"], "origin": x["origin"], "case_id": x["case_id"], "date": x["date"], "source": x["source"], "text": x["text"]}
                         for x in ev.registry(co)]}


# ---------- checks ----------
def check(draft: dict, co: str, evidence_ids: set[str] | None = None) -> list[str]:
    """The rules the Home screen depends on. Returns problems; empty means the draft can be used."""
    errs: list[str] = []
    cand = set(candidate_cases(co))
    reg = ev.registry(co)
    ids = evidence_ids if evidence_ids is not None else {x["id"] for x in reg}
    own = {x["id"] for x in reg if x["origin"] == "self"}
    allowed = factors(co)
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
            if x.get("factor") not in allowed:
                errs.append(f"{q}{i + 1} needs a factor from: {', '.join(allowed)}.")
            if q in "SW" and own and not set(x["evidence"]) & own:
                errs.append(f"{q}{i + 1} is about the company itself, so it must cite evidence about the company (origin self).")
    for q, key in (("O", "opportunities"), ("T", "threats")):
        for i, x in enumerate(draft[key]):
            if not (0 <= x["impact"] <= 100 and 0 <= x["urgency"] <= 100):
                errs.append(f"{q}{i + 1}: impact and urgency must be between 0 and 100.")
            if x["case_id"] is not None and x["case_id"] not in cand:
                errs.append(f"{q}{i + 1}: case_id {x['case_id']} is not on {co}'s desk.")
    moves = draft["moves"]
    most = min(4, len(cand))
    if cand and not 1 <= len(moves) <= most:
        errs.append(f"Recommend 1-{most} moves (one per watched company's case); you recommended {len(moves)}.")
    if not cand and (moves or draft["set_aside"]):
        errs.append(f"{co} watches no company with evidence, so return no moves and an empty set_aside.")
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
            if cand and x["impact"] > 50 and x["urgency"] > 50 and f"{q}{i + 1}" not in used:
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
    detail = {q: [{"reasoning": x["reasoning"], "factor": x.get("factor"),
                   "sources": ev.cite([by_id[e] for e in dict.fromkeys(x["evidence"]) if e in by_id])}
                  for x in draft[k]]
              for q, k in (("S", "strengths"), ("W", "weaknesses"), ("O", "opportunities"), ("T", "threats"))}
    return swot, pos, detail


def _one_move_per_case(draft: dict) -> dict | None:
    """The draft with only the first move per case (and set-aside entries for cases a move uses
    dropped), when that is what breaks it; the agent loop accepts it only if it then passes."""
    try:
        seen, moves = set(), []
        for m in draft["moves"]:
            if m["case_id"] not in seen:
                seen.add(m["case_id"])
                moves.append(m)
        if len(moves) == len(draft["moves"]):
            return None
        return {**draft, "moves": moves, "set_aside": [s for s in draft["set_aside"] if s["case_id"] not in seen]}
    except (KeyError, TypeError):
        return None


# ---------- drafters: one model call each; the loop below is provider-neutral ----------
class AgentError(Exception):
    pass


def default_drafter() -> Drafter:
    """The shared LLM routes (Groq, then NVIDIA, then Azure OpenAI); see llm_routes.py."""
    try:
        return Drafter()
    except LLMError as e:
        raise AgentError(str(e))


# ---------- the agent loop ----------
def run(co: str, drafter=None, on_round=None) -> dict:
    """Draft, check, revise. Returns {draft, registry, rounds} or raises AgentError."""
    drafter = drafter or default_drafter()
    reg = ev.registry(co)
    ids = [x["id"] for x in reg]
    schema = _schema(candidate_cases(co), ids, factors(co))
    cases = candidate_cases(co)
    limit = (f"It watches {len(cases)} compan{'y' if len(cases) == 1 else 'ies'} with evidence, so recommend at most "
             f"{min(4, len(cases))} move{'' if min(4, len(cases)) == 1 else 's'}, each on a different case." if cases
             else "It watches no company with evidence yet, so return no moves and an empty set_aside.")
    messages = [{"role": "user", "content": f"Write the SWOT and moves for this RPG company from this evidence. {limit}\n\n"
                 + json.dumps(evidence(co), indent=1, ensure_ascii=False)}]
    errs: list[str] = []
    for rnd in range(1, MAX_ROUNDS + 1):
        if on_round:
            on_round(rnd)
        try:
            text = drafter.draft(SYSTEM, messages, schema, "swot")
        except LLMError as e:
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
        repaired = _one_move_per_case(draft) if isinstance(draft, dict) else None
        if repaired and not check(repaired, co, set(ids)):
            return {"draft": repaired, "registry": reg, "rounds": rnd}
        messages += [{"role": "assistant", "content": text}, {"role": "user", "content": "The draft breaks these rules. Fix them and return the full SWOT again.\n- " + "\n- ".join(errs)}]
    raise AgentError(f"The draft still broke {len(errs)} rule(s) after {MAX_ROUNDS} rounds: " + " ".join(errs[:3]))


# ---------- background jobs ----------
_ids = itertools.count(1)
JOBS: dict[str, dict] = {}


def build(co: str, user: str, drafter=None, research: bool = False, job: dict | None = None) -> None:
    """Blocking: research the company first (when asked), then draft, check and store its SWOT.
    Raises AgentError when it cannot. Called from a worker thread (start(), the weekly scheduler run)."""
    job = job if job is not None else {}
    if research:
        from radar import bridge  # imported here: radar.bridge is loaded after this module
        job["phase"] = "research"
        bridge.run_on_loop(bridge.research_now(co))
        job["phase"] = "drafting"
    missing = missing_evidence(co)
    if missing:
        raise AgentError(missing)
    drafter = drafter or default_drafter()
    out = run(co, drafter, on_round=lambda r: job.update(round=r))
    STORE.swot[co], STORE.positions[co], STORE.swot_detail[co] = to_store(out["draft"], out["registry"])
    origins = [x["origin"] for x in out["registry"]]
    STORE.swot_source[co] = {"by": "agent", "model": drafter.model, "at": datetime.now().strftime("%d %b %H:%M"),
                             "rounds": out["rounds"], "evidence": {o: origins.count(o) for o in ("live", "self", "daily")},
                             "research_at": (STORE.research.get(co) or {}).get("at"), "factors": factors(co)}
    STORE.save_agent_swot(co)
    STORE.audit(user, "swot_rebuild", co)


log = get_logger("agents.swot_analyst")


def _rewrite_theses(user: str) -> None:
    """A rebuilt SWOT makes the RPG company's theses and competitor overviews out of date: start their rewrite."""
    from radar.bridge import run_on_loop
    from services import jobs, scheduler

    try:
        run_on_loop(jobs.start("theses", scheduler.write_agents_due, started_by=user), timeout=30)
    except Exception as e:  # noqa: BLE001 — the scheduler's 30-minute theses run catches up
        log.warning("theses_not_started", error=str(e))


def start(co: str, user: str, drafter=None, research: bool = False) -> dict:
    """build() as a background job. research=True refreshes the company's public research first."""
    running = next((j for j in JOBS.values() if j["company"] == co and j["status"] == "running"), None)
    if running:
        return running
    jid = f"swot_{next(_ids)}"
    job = {"id": jid, "company": co, "status": "running", "phase": "drafting", "round": 0, "max_rounds": MAX_ROUNDS,
           "error": None, "started": datetime.now().strftime("%d %b %H:%M")}
    JOBS[jid] = job

    def work():
        try:
            build(co, user, drafter, research, job)
            job["status"] = "completed"
            _rewrite_theses(user)
        except AgentError as e:
            job.update(status="failed", error=str(e))
        except Exception as e:  # keep the job pollable whatever happens
            job.update(status="failed", error=f"Unexpected error: {e}")

    threading.Thread(target=work, daemon=True).start()
    return job
