"""The SWOT parameters each RPG company's users can change (Radar settings -> SWOT parameters):

- sources: which evidence the research collects and the SWOT Analyst may cite;
- factors: what the company is judged on — the research searches the web for each ticked
  factor, and the SWOT Analyst tags every item with one of them;
- sector_queries: the industry news searches the Opportunity Analyst reads every day.

Stored per company in the ``swot_settings:<code>`` ConnectorState row; a company never saved
uses the defaults (everything ticked)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from services import state as state_store

SOURCES = {
    "results": "Quarterly results",
    "shareholding": "Shareholding",
    "web": "Company web pages (business, strategy, risks)",
    "news": "Company news",
    "watched": "Watched-company signals",
    "daily": "Kept daily findings",
}

# key: (label, what the web search for this factor adds to the company's name)
FACTORS = {
    "financial": ("Financial performance", "financial results revenue profit margins"),
    "market": ("Market position and brand", "market share brand position"),
    "products": ("Products and capacity", "new products capacity expansion plant"),
    "people": ("People and leadership", "leadership management team appointments"),
    "regulation": ("Regulation and legal", "regulation legal case penalty compliance"),
    "competition": ("Competition", "competitors competition pricing pressure"),
    "supply": ("Raw materials and supply chain", "raw material costs supply chain"),
    "deals": ("M&A and partnerships", "acquisition partnership joint venture"),
    "technology": ("Technology and innovation", "technology innovation research development"),
    "ownership": ("Ownership and group structure", "shareholders promoter group parent company subsidiaries joint venture stake"),
}

# Short searches: GNews matches every word, so a long phrase finds little (Tavily news, the fallback, reads them as plain language).
SECTOR_QUERIES = {
    "CEAT": ["tyre industry", "natural rubber", "vehicle sales"],
    "KEC": ["power transmission", "railway electrification", "EPC orders"],
    "ZENSAR": ["IT services", "generative AI enterprise"],
    "RPGLS": ["pharma industry", "drug prices"],
    "RAYCHEM": ["power cables", "power distribution"],
    "HARRISONS": ["tea prices", "natural rubber", "Kerala plantation"],
}
MAX_QUERIES = 6


def defaults(code: str) -> dict:
    return {"sources": list(SOURCES), "factors": list(FACTORS), "sector_queries": list(SECTOR_QUERIES.get(code, []))}


def normalize(code: str, value: dict | None) -> dict:
    """A stored or submitted value, cleaned: known keys only, in their usual order, queries trimmed."""
    if not value:
        return defaults(code)
    sources, factors = set(value.get("sources") or []), set(value.get("factors") or [])
    queries = [q.strip()[:80] for q in value.get("sector_queries") or [] if q and q.strip()]
    return {"sources": [k for k in SOURCES if k in sources], "factors": [k for k in FACTORS if k in factors],
            "sector_queries": list(dict.fromkeys(queries))[:MAX_QUERIES]}


def key(code: str) -> str:
    return f"swot_settings:{code}"


async def load(db: AsyncSession, code: str) -> dict:
    return normalize(code, await state_store.load(db, key(code)))


async def load_all(db: AsyncSession) -> dict[str, dict]:
    return {code: await load(db, code) for code in SECTOR_QUERIES}


async def save(db: AsyncSession, code: str, value: dict) -> dict:
    clean = normalize(code, value)
    await state_store.save(db, key(code), clean)
    await db.commit()
    return clean
