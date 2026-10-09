"""services/ripple.py: pure template-matching, no DB, no LLM. Every rationale
must trace back to a literal SubsidiaryDependency row — see the module
docstring's hard rule."""
from __future__ import annotations

from db.models import Entity, Subsidiary, SubsidiaryDependency
from services.ripple import compute_ripple_effects, compute_ripple_effects_for_subsidiaries

CEAT = Subsidiary(code="CEAT", name="CEAT", sectors=["tyres"], compliance_gate=True, signal_focus="")
ZENSAR_ROW = SubsidiaryDependency(
    id=1, subsidiary_code="CEAT", dependency_type="shared_service", counterparty_name="Zensar",
    counterparty_kind="rpg_subsidiary", counterparty_subsidiary_code="ZENSAR",
    description="IT/software systems integration and support",
    keywords=["software", "sensor", "iot", "digital"],
)
RUBBER_ROW = SubsidiaryDependency(
    id=2, subsidiary_code="CEAT", dependency_type="raw_material", counterparty_name="Malabar Rubber",
    counterparty_kind="external_vendor", counterparty_subsidiary_code=None,
    description="Natural rubber supply for tyre compounding",
    keywords=["rubber", "latex", "plantation"],
)


def test_direct_relevance_when_keyword_matches_entity():
    entity = Entity(name="Sensa Labs", sectors=["iot", "sensors"], category="Smart-tyre sensor technology vendor")
    out = compute_ripple_effects([ZENSAR_ROW, RUBBER_ROW], CEAT, entity)
    by_name = {r["counterparty_name"]: r for r in out}
    assert by_name["Zensar"]["relevance"] == "direct"
    assert by_name["Malabar Rubber"]["relevance"] == "routine"


def test_rationale_cites_the_real_row_fields_only():
    entity = Entity(name="Sensa Labs", sectors=["iot"], category="Smart-tyre sensor technology vendor")
    out = compute_ripple_effects([ZENSAR_ROW], CEAT, entity)
    assert out[0]["rationale"] == (
        "Acquiring Sensa Labs (Smart-tyre sensor technology vendor) would extend CEAT's demand on "
        "Zensar — IT/software systems integration and support"
    )
    assert out[0]["dependency_type"] == "shared_service"
    assert out[0]["counterparty_subsidiary_code"] == "ZENSAR"


def test_direct_rows_sort_before_routine():
    entity = Entity(name="Sensa Labs", sectors=["iot"], category="Smart-tyre sensor technology vendor")
    out = compute_ripple_effects([RUBBER_ROW, ZENSAR_ROW], CEAT, entity)
    assert [r["relevance"] for r in out] == ["direct", "routine"]


def test_every_dependency_row_surfaces_even_without_a_keyword_match():
    # No keyword from either row appears in this entity's text — both are
    # still returned (as "routine"), matching the acquirer's own fabric, not
    # a silent filter.
    entity = Entity(name="Veltrix Biopharma Ltd", sectors=["pharma"], category="API manufacturer")
    out = compute_ripple_effects([ZENSAR_ROW, RUBBER_ROW], CEAT, entity)
    assert len(out) == 2
    assert all(r["relevance"] == "routine" for r in out)


def test_for_subsidiaries_wrapper_groups_by_code():
    kec = Subsidiary(code="KEC", name="KEC International", sectors=["epc"], compliance_gate=False, signal_focus="")
    kec_row = SubsidiaryDependency(
        id=3, subsidiary_code="KEC", dependency_type="shared_vendor", counterparty_name="Raychem RPG",
        counterparty_kind="rpg_subsidiary", counterparty_subsidiary_code="RAYCHEM",
        description="Cable accessories for EPC projects", keywords=["cable", "electrical"],
    )
    entity = Entity(name="Ashford EPC Projects Ltd", sectors=["epc"], category="Mid-sized EPC contractor")
    out = compute_ripple_effects_for_subsidiaries(
        {"CEAT": [RUBBER_ROW], "KEC": [kec_row]}, [CEAT, kec], entity
    )
    assert {r["subsidiary_code"] for r in out} == {"CEAT", "KEC"}
