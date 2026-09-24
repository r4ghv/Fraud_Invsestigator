"""Retrieval specificity (spec M13): case-specific top-3 lists; history loaded
once. Synthetic rows only (no big CSVs)."""
import pytest

from fraud_agent.src import retrieval


def history_rows():
    return [
        {"case_id": "CC-1", "pattern": "card_not_present_fraud",
         "outcome": "confirmed_fraud", "exposure_usd": "30.00", "card_id": "K1",
         "first_fraud_txn_id": "T1", "connected_card_ids": "K9",
         "analyst_notes": "burst of small online charges"},
        {"case_id": "CC-2", "pattern": "card_not_present_fraud",
         "outcome": "confirmed_fraud", "exposure_usd": "3000.00", "card_id": "K2",
         "first_fraud_txn_id": "T2", "connected_card_ids": "",
         "analyst_notes": "large single takeover spend"},
        {"case_id": "CC-3", "pattern": "card_not_present_fraud",
         "outcome": "closed_legitimate", "exposure_usd": "30.50", "card_id": "K3",
         "first_fraud_txn_id": "T3", "connected_card_ids": "",
         "analyst_notes": ""},
    ]


class FakeStore:
    """Duck-typed store: closed cases resolve channel/region via first fraud txn."""
    _txn = {"T1": {"addr1": "225", "channel": "in_person"},
            "T2": {"addr1": "444", "channel": "online"},
            "T3": {"addr1": "225", "channel": "online"}}


@pytest.fixture(autouse=True)
def stub_history(monkeypatch):
    monkeypatch.setattr(retrieval, "_load", lambda: history_rows(), raising=False)
    monkeypatch.setattr(retrieval, "_CTX", {}, raising=False)


def test_amount_specific_top3():
    """M13 acceptance: same pattern, different amount -> different top-3."""
    small = retrieval.similar("card_not_present_fraud", amount=30.0)
    big = retrieval.similar("card_not_present_fraud", amount=3000.0)
    assert small[0] == "CC-1"
    assert big[0] == "CC-2"
    assert small != big


def test_region_specific_top3():
    """M13 acceptance: same pattern, different region -> different top-3."""
    store = FakeStore()
    r_225 = retrieval.similar("card_not_present_fraud", amount=100.0,
                              region="225", store=store)
    r_444 = retrieval.similar("card_not_present_fraud", amount=100.0,
                              region="444", store=store)
    assert r_225[0] == "CC-1"
    assert r_444[0] == "CC-2"
    assert r_225 != r_444


def test_channel_specific_top3():
    store = FakeStore()
    online = retrieval.similar("card_not_present_fraud", amount=100.0,
                               channel="online", store=store)
    in_person = retrieval.similar("card_not_present_fraud", amount=100.0,
                                  channel="in_person", store=store)
    assert online[0] in ("CC-2", "CC-3")
    assert in_person[0] == "CC-1"


def test_flagged_notes_used():
    """M13: flagged_notes must influence the ranking (was ignored)."""
    with_notes = retrieval.similar("card_not_present_fraud",
                                   flagged_notes="online burst charge", amount=1000.0)
    assert with_notes[0] == "CC-1"


def test_deterministic_order():
    a = retrieval.similar("card_not_present_fraud", amount=100.0, region="225",
                          store=FakeStore())
    b = retrieval.similar("card_not_present_fraud", amount=100.0, region="225",
                          store=FakeStore())
    assert a == b
