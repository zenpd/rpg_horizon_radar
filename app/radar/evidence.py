"""The numbered evidence behind a company's SWOT. The SWOT Analyst cites these ids for every item,
and the screen shows them as each item's sources.

Each item: {id, case_id, date, source, text, origin, url}. origin is
  "live"  fetched from a real source (see sources.py)
  "demo"  the demo's invented records (rival timeline, customer voice, deal targets)
  "team"  the strategy team's own list of strengths and weaknesses (in this demo, also invented)

When a company has live signals, they replace the demo rival story: the invented timeline,
customer voice and analyst read are left out, so threats and opportunities about the rival come
from real data. Deal targets have no live source yet and stay demo data."""
from __future__ import annotations

from .reference import REF
from .store import STORE

ORIGIN_LABEL = {"live": "Live", "demo": "Demo data", "team": "Team list (demo data)"}


def uses_live(co: str) -> bool:
    return bool(STORE.live.get(co))


def rival_name(co: str) -> str:
    """The real company the live signals are about, else the demo placeholder."""
    live = STORE.live.get(co) or []
    return live[0]["company"] if live else STORE.companies[co]["rival"]


def registry(co: str, live: bool | None = None) -> list[dict]:
    live = uses_live(co) if live is None else live
    w, team = STORE.companies[co], STORE.team_sw[co]
    raw: list[dict] = []
    for q, label in (("S", "strength"), ("W", "weakness")):
        for x in team[q]:
            raw.append({"case_id": None, "date": None, "source": f"Strategy team list ({label})", "text": x, "origin": "team"})
    rival = f"t_{co}"
    if live:
        for x in STORE.live[co]:
            raw.append({"case_id": rival, "date": x["date"], "source": x["source"], "text": f"{x['company']}: {x['text']}",
                        "origin": "live", "url": x.get("url")})
    else:
        for t in w["timeline"]:
            raw.append({"case_id": rival, "date": t[0], "source": t[3], "text": f"{w['rival']} · {t[1]}: {t[2]}", "origin": "demo"})
        for v in w["voc"]:
            raw.append({"case_id": rival, "date": None, "source": "Voice of Customer tracker",
                        "text": f"Customers on {w['rival']}'s products ({v[1].lower()}, {v[4]} mentions): {v[2]} {v[3]}", "origin": "demo"})
        raw.append({"case_id": rival, "date": None, "source": "Analyst synthesis", "text": f"Analyst read on {w['rival']}: {w['analyst']}", "origin": "demo"})
    for c in STORE.cases.values():
        if c["kind"] != "deal" or co not in c["cos"]:
            continue
        t = c["target"]
        bidders = f" Bidders: {'; '.join(t['bidders'])}." if t["bidders"] else ""
        raw.append({"case_id": c["id"], "date": None, "source": "Company profile",
                    "text": f"{t['name']}: {t['business']} Rating {t['rating']}, promoter pledge {t['pledge']}%, {t['ownership']} owned.{bidders}",
                    "origin": "demo"})
        for s in t["signals"]:
            raw.append({"case_id": c["id"], "date": s[1], "source": s[3], "text": f"{t['name']} · {REF['TYPE_LABEL'][s[0]]}: {s[2]}", "origin": "demo"})
    return [{"id": f"E{i}", "url": None, **x} for i, x in enumerate(raw, 1)]


def cite(items: list[dict]) -> list[dict]:
    """The shape the screen shows for a source."""
    return [{"id": x["id"], "text": x["text"], "source": x["source"], "date": x["date"], "url": x.get("url"),
             "origin": x["origin"], "origin_label": ORIGIN_LABEL[x["origin"]]} for x in items]


def demo_detail(co: str) -> dict:
    """Sources for the hand-written demo SWOT: the team list for S/W, and the evidence of the case
    an opportunity or threat links to. There is no reasoning: nobody derived these items."""
    reg = registry(co, live=False)
    team = [x for x in reg if x["origin"] == "team"]
    nS = len(STORE.team_sw[co]["S"])
    s = STORE.swot[co]
    out = {"S": [], "W": [], "O": [], "T": []}
    for i, text in enumerate(s["S"]):
        out["S"].append({"reasoning": None, "sources": cite([x for x in team[:nS] if x["text"] == text])})
    for i, text in enumerate(s["W"]):
        out["W"].append({"reasoning": None, "sources": cite([x for x in team[nS:] if x["text"] == text])})
    for q in ("O", "T"):
        for text, cid in s[q]:
            out[q].append({"reasoning": None, "sources": cite([x for x in reg if cid and x["case_id"] == cid])})
    return out
