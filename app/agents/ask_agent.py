"""Ask Radar agent: answers a user's question in a conversation, from the radar's own data first and
the web when that does not answer it.

1. Retrieval, no model: the companies the question (or the recent conversation) names — RPG companies
   and watched companies, matched by name — and the company the user has selected bring their data
   from the radar as numbered evidence (R1, R2 ...): public signals and score, size, the acquisition
   thesis, the competitor overview, the SWOT, the week's findings, financial health; and the scoring
   rules when the question is about scores.
2. A model answers from that evidence alone, citing every factual sentence. When the evidence does not
   answer the question it says so and asks for a web search with a focused query.
3. Then the web (Tavily, else DuckDuckGo: services/web_search.py) adds numbered results (W1, W2 ...)
   and the model answers again from both, or says plainly that it could not find the answer.

Rule checks: every cited id must exist, and an answer must cite something unless it says it found
nothing; a broken answer goes back up to twice, and one still uncited is marked as unverified. No valuation, deal price or recommendation to bid, and no figure
that is not in the evidence."""
from __future__ import annotations

import json
import re

from agents.llm_routes import Drafter, LLMError, thesis_routes
from ingestion.connectors.live.common import about, short_name

MAX_EVIDENCE = 45
MAX_HISTORY = 6
MAX_TRIES = 3  # a first draft and up to two revisions
IDS = re.compile(r"\[((?:R|W)\d{1,3})\]")
STOP = set("the and for who what which when where how does did current latest about with from that this are was its india".split())


def normalise(answer: str) -> str:
    """Citations as [R3]: models also write [R3, R4], (R3, R4), (R3) or a bare R3."""
    group = lambda m: "".join(f"[{x}]" for x in re.findall(r"[RW]\d{1,3}", m.group(1)))
    answer = re.sub(r"[\[(]\s*((?:[RW]\d{1,3}\s*[,;]?\s*)+)[\])]", group, answer)
    return re.sub(r"(?<![\[\w])([RW]\d{1,3})(?![\]\w])", lambda m: f"[{m.group(1)}]", answer)

SYSTEM = """You are Ask Radar, the assistant of RPG Horizon Radar, the RPG Group's M&A radar. You answer questions from the Corporate Strategy team.
Answer only from the numbered evidence given: radar data (R1, R2 ...) and, when present, web results (W1, W2 ...). Cite every factual sentence with the ids it rests on, in square brackets, e.g. "Apollo's CFO resigned on 6 October [R3]." An answer without citations is rejected.
Never state a fact, number, name or date that is not in the evidence. Never give a valuation, deal price or a recommendation to bid; you may describe signals, fit and risks.
If the evidence does not answer the question, do not guess: set needs_web true with a short, focused web search query (company names and the topic), unless web results are already given — then answer from them, or say plainly what you could not find; never say you will look it up.
Use the conversation so far to understand follow-up questions ("its", "that company").
Write short, plain English: a direct answer first, then the supporting points as a short list when there are several. Use markdown bullets; no headings."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answer", "needs_web", "web_query"],
          "properties": {"answer": {"type": "string"}, "needs_web": {"type": "boolean"},
                         "web_query": {"anyOf": [{"type": "string"}, {"type": "null"}]}}}


class AskError(Exception):
    pass


# ---------- 1. retrieval from the radar ----------
def _mentions(text: str, names: list[str]) -> list[str]:
    low = text.lower()
    return [n for n in names if about(n, low) or (len(short_name(n)) >= 4 and about(short_name(n), low))]


async def radar_evidence(db, question: str, history: list[dict], company: str) -> list[dict]:
    """The radar's data on the companies the question is about, as numbered evidence."""
    from db.models import OpportunityFinding
    from radar import views
    from radar.bridge import CO_TO_CODE
    from radar.store import COMPANIES_ORDER, STORE
    from services import market_data, scoring
    from services import state as state_store
    from services.company_research import PROFILES
    from sqlalchemy import select

    from agents import acquisition_thesis, competitor_profile

    convo = " ".join([question, *(m["content"] for m in history[-MAX_HISTORY:] if m["role"] == "user")])
    rpg = [co for co in COMPANIES_ORDER if co == company or about(co, convo.lower())
           or about(PROFILES[CO_TO_CODE[co]][0], convo.lower())]
    watched = {w["id"]: (co, w) for co in COMPANIES_ORDER for w in (STORE.live_meta.get("watch") or {}).get(co, []) if w["status"] == "watching"}
    named = set(_mentions(question, [w["name"] for _, w in watched.values()]) or _mentions(convo, [w["name"] for _, w in watched.values()]))
    live = await state_store.load(db, "live")
    out: list[dict] = []
    add = lambda text, source, date=None, url=None: out.append({"text": text, "source": source, "date": date, "url": url})

    seen: set[int] = set()
    for eid, (co, w) in watched.items():
        if w["name"] not in named or eid in seen:
            continue
        seen.add(eid)
        n = w["name"]
        row = next((r for r in views.roster(co) if r["entity_id"] == eid), None)
        if row:
            add(f"{n} is on {co}'s watchlist as a {row['role']}; size: {row['size']['label'].replace('the RPG company', co)}; "
                f"{row['signals']} public signals in 120 days; score {round(row['score']) if row['score'] is not None else 'none'}.", "Radar watchlist")
            if row.get("why"):
                add(f"Why {n} is watched: {row['why']}", "Radar discovery")
            for s in row["timeline"][:6]:
                add(f"{n}, {s['date']}: {s['label']}: {s['text']}", s["source"], s["date"], s.get("url"))
        case = f"r{eid}"
        if case in STORE.cases:
            t = await acquisition_thesis.load(db, case, co)
            if t:
                d = t["draft"]
                add(f"Acquisition thesis for {n} (for {co}, {t['at']}): {d['headline']} Likely deal: {d['acquisition_type']} — {d['acquisition_reason']}", "Radar acquisition thesis")
                add(f"Fitment of {n} for {co}: " + "; ".join(f"{x['dimension']} {x['rating']}" for x in d["fitment"]), "Radar acquisition thesis")
        p = await competitor_profile.load(db, eid, co)
        if p:
            d = p["draft"]
            add(f"Overview of {n} ({p['at']}): {d['summary']} Overall competitive pressure on {co}: {d['threat']['level']} — {d['threat']['reason']}", "Radar competitor overview")
            add(f"What to watch at {n}: " + "; ".join(d["watch"]), "Radar competitor overview")
        h = market_data.company(w.get("nse_symbol"), live)
        if h.get("listed") and not h.get("pending"):
            text = market_data.health_text(n, h.get("health") or {})
            if text:
                add(text, "Fincrux annual accounts")
            if h.get("sales_yoy") is not None:
                add(f"{n} latest quarter ({h.get('quarter')}): sales {h['sales_yoy']:+.1f}% year on year, net profit {h.get('profit_yoy') or 0:+.1f}%, operating margin {h.get('opm')}%.", "Fincrux quarterly results")

    for co in rpg:
        code = CO_TO_CODE[co]
        swot = STORE.swot.get(co)
        if swot:
            for q, label in (("S", "strength"), ("W", "weakness"), ("O", "opportunity"), ("T", "threat")):
                for i, x in enumerate(swot[q][:4], 1):
                    add(f"{co} SWOT {label} {q}{i}: {x[0] if isinstance(x, list) else x}", f"Radar SWOT ({co})")
        rows = (await db.execute(select(OpportunityFinding).where(OpportunityFinding.subsidiary_code == code)
                                 .order_by(OpportunityFinding.found_on.desc()).limit(4))).scalars().all()
        for f in rows:
            add(f"{co} daily finding ({f.found_on:%d %b}): {f.kind} — {f.title}. {f.summary}", "Radar Opportunity Analyst", f"{f.found_on:%Y-%m-%d}")
        sig = [views.summary(c) for c in STORE.cases.values() if views.in_scope(c, co) and views.acquirable(c, co)["signal"] and c["status"] != "dismissed"]
        if sig:
            add(f"{co}'s M&A signals: " + "; ".join(f"{s['who']} ({s['size']['label'].replace('the RPG company', co)})" for s in sig[:8]), "Radar M&A Signals")
        comp = [r["name"] for r in views.roster(co) if r["role"] == "competitor"]
        if comp:
            add(f"{co}'s watched competitors: " + ", ".join(comp[:12]), "Radar watchlist")
        h = market_data.company(PROFILES[code][2], live)
        if h.get("listed") and not h.get("pending"):
            text = market_data.health_text(co, h.get("health") or {})
            if text:
                add(text, "Fincrux annual accounts")

    if re.search(r"\bscor(e|es|ing)\b|intensity|how .*calculat", question.lower()):
        add("The opportunity score (called competitive intensity on competitor cards) is rule-based: each kind of public move in the latest "
            f"{scoring.WINDOW_DAYS} days adds its weight once (e.g. credit downgrade {scoring.BASE_WEIGHTS['credit_downgrade']}, "
            f"leadership churn {scoring.BASE_WEIGHTS['leadership_churn']}, fund raise {scoring.BASE_WEIGHTS['fund_raise']}); the sum is "
            "multiplied by 1.0 for one kind, 1.3 for two, 1.6 for three and 2.0 for four or more, and capped at 100.", "Radar scoring rules")
    return [{"id": f"R{i}", "kind": "radar", **x} for i, x in enumerate(out[:MAX_EVIDENCE], 1)]


# ---------- 3. the web ----------
def web_evidence(query: str, start: int = 1) -> tuple[list[dict], list[str]]:
    """Blocking: web results for a query (Tavily, else DuckDuckGo), as numbered evidence."""
    from services import company_research

    out, errors = [], []
    terms = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) >= 3 and w not in STOP]
    relevant = lambda text: not terms or sum(t in text.lower() for t in terms) / len(terms) >= 0.6  # most of the query's words
    for kind, body in (("web", {"query": query, "topic": "general", "search_depth": "basic", "max_results": 8}),
                       ("news", {"query": query, "topic": "news", "days": 30, "max_results": 8})):
        try:
            for x in company_research._tavily(body):
                title, content = (x.get("title") or "").strip(), (x.get("content") or "").strip()
                if title and str(x.get("url") or "").startswith("http") and relevant(f"{title} {content}"):  # no ad or redirect links
                    when = company_research._published(x)
                    out.append({"text": f"{title}: {content[:350]}", "source": x.get("source") or company_research._host(x.get("url")),
                                "date": when.strftime("%Y-%m-%d") if when else None, "url": x.get("url")})
        except Exception as e:  # noqa: BLE001 — a failed search is reported, never fatal
            errors.append(f"{kind} search: {e}")
    uniq = list({x["url"] or x["text"]: x for x in out}.values())[:10]
    return [{"id": f"W{i}", "kind": "web", **x} for i, x in enumerate(uniq, start)], errors


# ---------- 2. the answer ----------
def _check(answer: str, ids: set[str]) -> list[str]:
    errs = []
    cited = set(IDS.findall(answer))
    if cited - ids:
        errs.append(f"You cited ids that are not in the evidence: {', '.join(sorted(cited - ids))}. Cite only the ids given.")
    if not cited and ids and not re.search(r"could not find|couldn't find|no data|not in the radar|don't have|do not have", answer, re.I):
        errs.append("Cite the evidence id, in square brackets, for every fact in your answer, e.g. [W2].")
    return errs


def draft(question: str, history: list[dict], company: str, evidence: list[dict], drafter=None) -> tuple[dict, str]:
    """Blocking: one answer from the evidence given, checked and revised once. Returns (reply, model)."""
    try:
        drafter = drafter or Drafter(routes=thesis_routes())
    except LLMError as e:
        raise AskError(str(e))
    convo = [{"role": m["role"], "content": m["content"][:600]} for m in history[-MAX_HISTORY:]]
    payload = {"selected_company": company, "question": question,
               "evidence": [{k: x[k] for k in ("id", "text", "source", "date") if x.get(k)} for x in evidence] or "No evidence found."}
    messages = [*convo, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)}]
    ids = {x["id"] for x in evidence}
    for _ in range(MAX_TRIES):
        try:
            text = drafter.draft(SYSTEM, messages, SCHEMA, "ask")
            reply = json.loads(text)
        except LLMError as e:
            raise AskError(str(e))
        except (json.JSONDecodeError, TypeError):
            messages += [{"role": "user", "content": "Return only the JSON object."}]
            continue
        reply["answer"] = normalise(reply.get("answer") or "")
        errs = _check(reply["answer"], ids)
        if not errs:
            return reply, drafter.model
        messages += [{"role": "assistant", "content": text}, {"role": "user", "content": "Fix this and answer again:\n- " + "\n- ".join(errs)}]
    reply["answer"] = IDS.sub(lambda m: m.group(0) if m.group(1) in ids else "", reply.get("answer") or "")
    return reply, drafter.model


async def answer(db, question: str, history: list[dict], company: str, drafter=None, web=None) -> dict:
    """The full turn: the radar's data, an answer, the web when that is not enough, the final answer.
    Returns {content, sources (the cited evidence), used_web, model, errors}."""
    import asyncio

    evidence = await radar_evidence(db, question, history, company)
    reply, model = await asyncio.to_thread(draft, question, history, company, evidence, drafter)
    used_web, errors = False, []
    if reply.get("needs_web"):
        query = (reply.get("web_query") or question).strip()
        found, errors = await asyncio.to_thread(web or web_evidence, query)
        used_web = True
        evidence = evidence + found
        reply, model = await asyncio.to_thread(draft, question, history, company, evidence, drafter)
    content = (reply.get("answer") or "").strip() or "I could not find an answer to that in the radar's data or on the web."
    cited = set(IDS.findall(content))
    if not cited and evidence and not re.search(r"could not find|couldn't find|no data|don't have|do not have", content, re.I):
        content += "\n\n_This answer could not be tied to a specific source: treat it as unverified._"
    return {"content": content, "sources": [x for x in evidence if x["id"] in cited], "used_web": used_web, "model": model, "errors": errors}
