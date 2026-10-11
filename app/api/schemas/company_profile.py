from pydantic import BaseModel


class CompanyProfileOut(BaseModel):
    listing_status: str  # "public" | "private"
    listing_label: str
    listing_detail: str
    market_reaction: str
    integration_stance: str
    deal_structure_hint: str
    regulatory_note: str
    disclaimer: str
