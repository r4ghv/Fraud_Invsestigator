"""case_writer payload shape: FraudCase vertex + CASE_ON edge (synthetic answer)."""
from fraud_agent.src.case_writer import build_upsert


def _ans():
    return {"case_id": "HHG-T1", "case": {
        "status": "escalated", "verdict": "fraud", "fraud_probability": 0.9,
        "pattern": "card_testing", "affected_txn_ids": ["T1", "T2"]}}


def test_vertex_attrs():
    p = build_upsert(_ans(), "C1-K1")
    vtype, vid, attrs = p["vertex"]
    assert (vtype, vid) == ("FraudCase", "HHG-T1")
    assert attrs == {"status": "escalated", "verdict": "fraud",
                     "prob": 0.9, "pattern": "card_testing"}


def test_case_on_edge_targets_card():
    p = build_upsert(_ans(), "C1-K1")
    assert p["edge"] == ("CASE_ON", "HHG-T1", "C1-K1")


def test_prob_is_float_even_from_string_answers():
    a = _ans()
    a["case"]["fraud_probability"] = "0.42"
    _, _, attrs = build_upsert(a, "C1-K1")["vertex"]
    assert attrs["prob"] == 0.42 and isinstance(attrs["prob"], float)
