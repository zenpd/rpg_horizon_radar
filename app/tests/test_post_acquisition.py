"""radar/post_acquisition.py: a pure reclassification over the baseline SWOT
for one deal case — never a new score, never a fabricated valuation. Uses
the real demo baseline (swot.json's CEAT entry) rather than a hand-built
fixture, so the test also catches a drift between this module's assumptions
and the actual SWOT shape."""
from __future__ import annotations

import pytest

from radar import post_acquisition, swot_agent
from radar.store import STORE


@pytest.fixture(autouse=True)
def fresh_store(seeded):
    STORE.agent_saved = {}
    STORE.post_acq_swot = {}
    STORE.reset()
    yield


def test_degenerate_case_returns_none_when_nothing_cites_it():
    # "d_strata" is a real case id but CEAT's baseline SWOT never cites it.
    assert post_acquisition.project("CEAT", "d_strata") is None


def test_meridian_acquisition_secures_opportunity_resolves_threat_addresses_weakness():
    out = post_acquisition.project("CEAT", "d_meridian")
    assert out is not None
    assert [i["text"] for i in out["secured"]] == ["Meridian, a key supplier, is distressed and may be open to a deal"]
    assert [i["text"] for i in out["resolved"]] == ["Rival A has bought 6% of Meridian"]
    assert len(out["addressed"]) == 1
    assert out["addressed"][0]["id"] == "W2"
    assert "Meridian" in out["addressed"][0]["reasoning"]  # the move's own why, carried over verbatim


def test_net_shift_counts_are_plain_arithmetic_not_a_score():
    out = post_acquisition.project("CEAT", "d_meridian")
    d = out["delta"]
    assert d == {
        "secured_o": 1, "resolved_t": 1, "addressed_w": 1,
        "baseline": {"S": 3, "W": 3, "O": 4, "T": 3},
        "projected": {"S": 3, "W": 2, "O": 3, "T": 2},
    }


def test_projection_is_scoped_to_the_right_company():
    # d_sensa is also on CEAT's desk (per targets.json desks), but its O/move
    # belong to a different case_id than d_meridian — no cross-contamination.
    out = post_acquisition.project("CEAT", "d_sensa")
    assert out is not None
    assert all(i["case_id"] != "d_meridian" for i in out["secured"])


def test_rebuild_recaptures_an_approved_case_the_old_swot_missed():
    # KEC's demo baseline SWOT doesn't cite d_sensa (one of the two known demo
    # gaps) — approving it now leaves the honest "rebuild to capture this" gap.
    assert post_acquisition.project("KEC", "d_sensa") is None
    STORE.cases["d_sensa"].update(stage="act", owner="Test Owner")
    assert ("KEC", "d_sensa") not in STORE.post_acq_swot

    # A rebuild (real or, here, simulated) now cites it — the fix must catch
    # this up for the ALREADY-approved case, not just future approvals.
    STORE.swot["KEC"]["O"].append(["Sensa partnership closes KEC's smart-component gap", "d_sensa"])
    STORE.positions["KEC"]["O"].append([60, 60])
    swot_agent._reproject_approved_cases("KEC")

    out = STORE.post_acq_swot.get(("KEC", "d_sensa"))
    assert out is not None
    assert out["secured"][0]["case_id"] == "d_sensa"


def test_rebuild_does_not_touch_cases_still_awaiting_a_decision():
    # d_ashford is on KEC's desk but never approved — a rebuild must not
    # invent a projection for a case nobody decided on yet.
    swot_agent._reproject_approved_cases("KEC")
    assert ("KEC", "d_ashford") not in STORE.post_acq_swot
