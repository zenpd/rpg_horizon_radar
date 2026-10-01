"""SWOT briefs: an LLM-drafted SWOT for one subsidiary, every item citing the
evidence it rests on and explaining how.

Evidence is numbered and given to the model exactly as stored with the brief:
- E1, E2 ... the raw signals of the watched companies routed to this
  subsidiary (newest first, last WINDOW_DAYS days, at most MAX_SIGNALS);
- N1, N2 ... Corporate Strategy's team notes on the subsidiary itself.
Strengths and weaknesses describe the subsidiary, so they may rest only on team
notes; opportunities and threats come from the signals. Without team notes the
brief has no strengths or weaknesses rather than invented ones.

Agent loop: draft -> rule check (check()) -> the problems go back to the model
for a revision, up to MAX_ROUNDS drafts. A draft that never passes is not
saved; the previous brief stays current. The brief never feeds scoring
(services/scoring.py stays rule-based) and carries no valuation, price or
deal recommendation."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ClusterSubsidiaryLink, Entity, RawSignal, SignalCluster, Subsidiary, SwotBrief
from services.audit import write_audit
from shared.llm_chat import Drafter

MAX_ROUNDS = 3
WINDOW_DAYS = 120
MAX_SIGNALS = 40

SYSTEM = """You are the SWOT analyst for RPG Horizon Radar, the restricted signal radar of RPG Group Corporate Strategy.

For one RPG subsidiary you write a SWOT from a numbered list of evidence.
- E items are public signals about companies this subsidiary watches (competitors and adjacent players): filings, results, news, hiring, patents. Each has a company, a date, a source and a signal type.
- N items are the strategy team's own notes about the subsidiary.
- Strengths and weaknesses describe the subsidiary itself and rest only on N items. If there are no N items, return no strengths and no weaknesses.
- Opportunities and threats are what the E items mean for the subsidiary: a watched company's setback can be an opening, its expansion or win a threat. Each rests on at least one E item and names the company it is about (entity), exactly as written in the evidence, or null when it spans several.
- Every item lists the ids it rests on and gives its reasoning: one or two sentences on how that evidence leads to the item.
- Score each opportunity and threat for impact and urgency, 0-100, from the evidence alone.
- summary: two or three sentences a busy strategy head can scan.
- Never write an id inside text, reasoning or summary. Use only the evidence given; do not invent facts, numbers or names. Do not recommend deals, valuations, prices or approaches to any company."""


def _schema(evidence_ids: list[str], entities: list[str]) -> dict:
    cites = {"type": "array", "items": {"type": "string", "enum": evidence_ids or ["none"]}}
    internal = {"type": "object", "additionalProperties": False, "required": ["text", "evidence", "reasoning"],
                "properties": {"text": {"type": "string"}, "evidence": cites, "reasoning": {"type": "string"}}}
    entity = {"anyOf": [{"type": "string", "enum": entities or ["none"]}, {"type": "null"}]}
    external = {"type": "object", "additionalProperties": False,
                "required": ["text", "entity", "impact", "urgency", "evidence", "reasoning"],
                "properties": {"text": {"type": "string"}, "entity": entity, "impact": {"type": "integer"},
                               "urgency": {"type": "integer"}, "evidence": cites, "reasoning": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False,
            "required": ["summary", "strengths", "weaknesses", "opportunities", "threats"],
            "properties": {"summary": {"type": "string"},
                           "strengths": {"type": "array", "items": internal}, "weaknesses": {"type": "array", "items": internal},
                           "opportunities": {"type": "array", "items": external}, "threats": {"type": "array", "items": external}}}


async def gather_evidence(db: AsyncSession, sub: Subsidiary) -> list[dict]:
    """The numbered evidence for one subsidiary, as stored with the brief."""
    entity_ids = (await db.execute(
        select(SignalCluster.entity_id).join(ClusterSubsidiaryLink, ClusterSubsidiaryLink.cluster_id == SignalCluster.id)
        .where(ClusterSubsidiaryLink.subsidiary_code == sub.code, SignalCluster.status == "live"))).scalars().all()
    rows = []
    if entity_ids:
        since = datetime.utcnow() - timedelta(days=WINDOW_DAYS)
        rows = (await db.execute(
            select(RawSignal, Entity).join(Entity, Entity.id == RawSignal.entity_id)
            .where(RawSignal.entity_id.in_(set(entity_ids)), RawSignal.observed_at >= since, Entity.status == "watching")
            .order_by(RawSignal.observed_at.desc()).limit(MAX_SIGNALS))).all()
    out = [{"id": f"E{i}", "kind": "signal", "signal_id": s.id, "entity": e.name, "fictional": e.is_fictional,
            "signal_type": s.signal_type, "provider": s.provider, "headline": s.headline, "excerpt": s.source_excerpt,
            "url": s.source_url or None, "observed_at": s.observed_at.isoformat(timespec="seconds")}
           for i, (s, e) in enumerate(rows, 1)]
    notes = sub.team_notes or {}
    n = 0
    for quadrant in ("strengths", "weaknesses"):
        for text in notes.get(quadrant) or []:
            n += 1
            out.append({"id": f"N{n}", "kind": "team_note", "quadrant": quadrant, "headline": text})
    return out


def _evidence_text(sub: Subsidiary, evidence: list[dict]) -> str:
    lines = [f"Subsidiary: {sub.name} ({', '.join(sub.sectors or [])})", f"Signal focus: {sub.signal_focus}", "", "Evidence:"]
    for x in evidence:
        if x["kind"] == "signal":
            lines.append(f"{x['id']} | {x['entity']} | {x['observed_at'][:10]} | {x['provider']} | {x['signal_type']} | {x['headline']}"
                         + (f" — {x['excerpt'][:300]}" if x.get("excerpt") else ""))
        else:
            lines.append(f"{x['id']} | team note ({x['quadrant']}) | {x['headline']}")
    return "\n".join(lines)


def check(draft: dict, evidence: list[dict]) -> list[str]:
    """Problems with a draft; empty means it can be saved."""
    errs: list[str] = []
    by_id = {x["id"]: x for x in evidence}
    notes = {i for i, x in by_id.items() if x["kind"] == "team_note"}
    signals = {i for i, x in by_id.items() if x["kind"] == "signal"}
    for key, letter in (("strengths", "S"), ("weaknesses", "W")):
        items = draft.get(key) or []
        if not notes and items:
            errs.append(f"There are no team notes, so list no {key}.")
        if len(items) > 5:
            errs.append(f"List at most 5 {key}; you listed {len(items)}.")
        for i, x in enumerate(items, 1):
            if not x["evidence"] or any(e not in notes for e in x["evidence"]):
                errs.append(f"{key[:-1].capitalize()} {i} must cite team notes (N items) only.")
    ext = (draft.get("opportunities") or []) + (draft.get("threats") or [])
    if signals and not ext:
        errs.append("List at least one opportunity or threat from the signals.")
    for key in ("opportunities", "threats"):
        items = draft.get(key) or []
        if len(items) > 6:
            errs.append(f"List at most 6 {key}; you listed {len(items)}.")
        for i, x in enumerate(items, 1):
            name = f"{key[:-1].capitalize()} {i}" if key == "threats" else f"Opportunity {i}"
            cited = [e for e in x["evidence"] if e in signals]
            if not cited:
                errs.append(f"{name} must cite at least one signal (E item).")
            bad = [e for e in x["evidence"] if e not in by_id]
            if bad:
                errs.append(f"{name} cites {', '.join(bad)}, which are not in the evidence list.")
            if not (0 <= x["impact"] <= 100 and 0 <= x["urgency"] <= 100):
                errs.append(f"{name}: impact and urgency must be between 0 and 100.")
            if x.get("entity") and cited and x["entity"] not in {by_id[e]["entity"] for e in cited}:
                errs.append(f"{name} names {x['entity']}, but none of the signals it cites is about that company.")
    for key in ("strengths", "weaknesses", "opportunities", "threats"):
        for i, x in enumerate(draft.get(key) or [], 1):
            if not x["reasoning"].strip():
                errs.append(f"{key.capitalize()} item {i} has no reasoning.")
    texts = [draft.get("summary", "")] + [t for k in ("strengths", "weaknesses", "opportunities", "threats")
                                          for x in draft.get(k) or [] for t in (x["text"], x["reasoning"])]
    leaked = sorted({m for t in texts for m in re.findall(r"\b[EN]\d{1,3}\b", t)})
    if leaked:
        errs.append(f"Text fields mention ids ({', '.join(leaked)}). Write plain sentences; ids belong only in evidence lists.")
    return errs


class SwotError(Exception):
    pass


def run(sub: Subsidiary, evidence: list[dict], drafter: Drafter | None = None) -> tuple[dict, int, str]:
    """Blocking agent loop. Returns (draft, rounds, model)."""
    if not any(x["kind"] == "signal" for x in evidence):
        raise SwotError(f"No signals are routed to {sub.name} yet, so there is nothing to build a SWOT from.")
    drafter = drafter or Drafter()
    entities = sorted({x["entity"] for x in evidence if x["kind"] == "signal"})
    schema = _schema([x["id"] for x in evidence], entities)
    messages = [{"role": "user", "content": _evidence_text(sub, evidence)}]
    problems: list[str] = []
    for rounds in range(1, MAX_ROUNDS + 1):
        text = drafter.draft(SYSTEM, messages, schema, "swot")
        try:
            draft = json.loads(text)
            problems = check(draft, evidence)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            draft, problems = None, [f"The reply was not valid JSON for the schema ({e})."]
        if not problems:
            return draft, rounds, drafter.model
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "Revise the SWOT. Fix these problems and keep everything else:\n- " + "\n- ".join(problems)}]
    raise SwotError(f"The draft still broke {len(problems)} rule(s) after {MAX_ROUNDS} rounds: " + "; ".join(problems[:3]))


async def build(db: AsyncSession, code: str, reviewer=None, drafter: Drafter | None = None) -> dict:
    sub = (await db.execute(select(Subsidiary).where(Subsidiary.code == code))).scalar_one_or_none()
    if sub is None:
        raise SwotError(f"Unknown subsidiary {code}.")
    if not sub.compliance_gate:
        raise SwotError(f"{sub.name}'s compliance gate is closed.")
    evidence = await gather_evidence(db, sub)
    draft, rounds, model = await asyncio.to_thread(run, sub, evidence, drafter)
    brief = SwotBrief(subsidiary_code=code, generated_at=datetime.utcnow(), generated_by_id=reviewer.id if reviewer else None,
                      model=model, rounds=rounds, content=draft, evidence=evidence)
    db.add(brief)
    await db.commit()
    await write_audit(db, reviewer, "swot_generated", "swot_brief", resource_id=brief.id,
                      detail=f"subsidiary={code} model={model} rounds={rounds} evidence={len(evidence)}")
    return {"brief_id": brief.id, "subsidiary": code, "rounds": rounds, "model": model}
