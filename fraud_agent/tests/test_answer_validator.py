"""Answer contract tests — spec findings H6 (single exposure) and H7
(undocumented/SAR over-filing) plus the Section 5 answer validator.
Synthetic rows only (no big CSVs).
"""
from datetime import timedelta

import pytest

from test_agent_flow import BASE, POLICY, StubStore, case, txn

from fraud_agent.src.agent import investigate
from fraud_agent.src.policy_engine import PolicyEngine
from fraud_agent.src.validator import validate

ENG = PolicyEngine(POLICY)


def cnp_burst_rows():
    """Online burst ending at the flagged txn; amounts sum to $1080."""
    return [
        txn(1, BASE - timedelta(days=3), 40),
        txn(97, BASE - timedelta(hours=2), 50),
        txn(98, BASE - timedelta(hours=1), 60),
        txn(99, BASE - timedelta(minutes=30), 70),
        txn(100, BASE, 900),
    ]


def h7_rows():
    """Clustered same-product customer dispute, $30, no SAR basis."""
    return [
        txn(1, BASE - timedelta(days=10), 30, "in_person", "225", "W"),
        txn(2, BASE - timedelta(days=5), 30, "in_person", "225", "W"),
        txn(3, BASE - timedelta(days=2), 31, "in_person", "225", "W"),
        txn(100, BASE, 30, "in_person", "225", "W"),
    ]


def r7_rows():
    """Monthly same-product rhythm + disputed $20 -> R7 legitimate."""
    return [
        txn(1, BASE - timedelta(days=55), 20.0, "in_person", "225", "W"),
        txn(2, BASE - timedelta(days=30), 20.5, "in_person", "225", "W"),
        txn(3, BASE - timedelta(days=5), 19.5, "in_person", "225", "W"),
        txn(100, BASE, 20.0, "in_person", "225", "W"),
    ]


def _inv(rows, case_row):
    store = StubStore(rows)
    ans = investigate(case_row, store, ENG)
    return ans, store


# --- H6: one exposure value; uncertain never reports a phantom exposure -------

def test_h6_uncertain_with_large_exposure_has_no_sar():
    ans, store = _inv(cnp_burst_rows(), case("100", "risk_score"))
    assert ans["case"]["verdict"] == "uncertain"
    # H6: the $1080 burst must not surface as SAR exposure on an uncertain case
    assert ans["case"]["affected_txn_ids"] == []
    assert ans["case"]["exposure_usd"] == 0
    assert ans["sar"]["file"] is False, "H6: SAR filed citing exposure the case reports as 0"
    assert ans["sar"]["total_amount_usd"] == 0
    assert validate(ans, ENG.p, store) == []


# --- H7: 'none' pattern + fraud alone must not trigger a SAR -----------------

def test_h7_none_pattern_fraud_small_no_sar():
    ans, store = _inv(h7_rows(), case("100", "customer_report"))
    assert ans["case"]["verdict"] == "fraud"
    assert ans["case"]["pattern"] == "none"
    # flagged txn is part of the episode -> affected + exposure consistent (README 326/330)
    assert ans["case"]["affected_txn_ids"] == ["100"]
    assert ans["case"]["exposure_usd"] == 30.0
    assert ans["sar"]["file"] is False, "H7: none+fraud alone must not file a SAR"
    assert validate(ans, ENG.p, store) == []


# --- Validator passes on clean agent output (all three verdicts) -------------

@pytest.mark.parametrize(
    "rows,case_row",
    [
        (cnp_burst_rows(), case("100", "risk_score")),        # uncertain
        (h7_rows(), case("100", "customer_report")),          # fraud, no SAR
        (r7_rows(), case("100", "customer_report")),          # legitimate (R7)
        ([txn(100, BASE, 45, "in_person", "225")], case("100", "risk_score")),  # legit close
    ],
)
def test_validator_passes_on_agent_outputs(rows, case_row):
    if case_row["risk_score"] == "0.61" and case_row["trigger_type"] == "risk_score" and len(rows) == 1:
        case_row["risk_score"] = "0.03"
    ans, store = _inv(rows, case_row)
    assert validate(ans, ENG.p, store) == []


# --- Validator catches broken answers (mutations of a valid fraud answer) ----

def _base_fraud_answer():
    ans, store = _inv(h7_rows(), case("100", "customer_report"))
    assert ans["case"]["verdict"] == "fraud"
    assert validate(ans, ENG.p, store) == [], "base answer must be valid before mutating"
    return ans, store


def test_validator_catches_sar_amount_mismatch():
    ans, store = _base_fraud_answer()
    ans["sar"]["file"] = True
    ans["sar"]["narrative"] = "Suspicious activity narrated here."
    ans["sar"]["activity_dates"] = ["2016-07-01", "2016-07-01"]
    ans["sar"]["total_amount_usd"] = 99999.0
    errs = validate(ans, ENG.p, store)
    assert any("total_amount_usd" in e for e in errs), errs
    assert any("FILE_REPORT" in e for e in errs), errs


def test_validator_catches_unknown_id():
    ans, store = _base_fraud_answer()
    ans["case"]["affected_txn_ids"].append("T9999999")
    errs = validate(ans, ENG.p, store)
    assert any("T9999999" in e for e in errs), errs


def test_validator_catches_undocumented_without_description():
    ans, store = _base_fraud_answer()
    ans["case"]["pattern"] = "undocumented"
    errs = validate(ans, ENG.p, store)
    assert any("pattern_description" in e for e in errs), errs


def test_validator_catches_wrong_file_report_route():
    ans, store = _base_fraud_answer()
    ans["sar"]["file"] = True
    ans["sar"]["narrative"] = "Suspicious activity narrated here."
    ans["sar"]["activity_dates"] = ["2016-07-01", "2016-07-01"]
    ans["sar"]["total_amount_usd"] = ans["case"]["exposure_usd"]
    ans["next_best_actions"]["final"].append(
        {"action": "FILE_REPORT", "route": "L1", "reason": "bad"})
    errs = validate(ans, ENG.p, store)
    assert any("FILE_REPORT" in e and "L2" in e for e in errs), errs


def test_validator_catches_block_when_r1_applies():
    rows = r7_rows()
    store = StubStore(rows)
    ans = investigate(case("100", "customer_report"), store, ENG)
    assert ans["case"]["verdict"] == "legitimate"
    ans["next_best_actions"]["final"].append(
        {"action": "BLOCK_CARD", "route": "L1", "reason": "bad"})
    errs = validate(ans, ENG.p, store)
    assert any("BLOCK" in e for e in errs), errs


def test_validator_catches_sar_on_weak_uncertain():
    """sar.file needs fraud verdict or p >= strong threshold AND a 3a condition."""
    rows = [
        txn(1, BASE - timedelta(days=40), 30, "in_person", "225"),
        txn(2, BASE - timedelta(days=35), 25, "in_person", "225"),
        txn(10, BASE - timedelta(days=3), 60, "online", "444"),
        txn(11, BASE - timedelta(days=2), 70, "online", "444"),
        txn(12, BASE - timedelta(days=1), 80, "online", "444"),
        txn(100, BASE, 55, "in_person", "444"),
    ]
    ans, store = _inv(rows, case("100", "risk_score"))
    assert ans["case"]["verdict"] == "uncertain"
    assert ans["case"]["fraud_probability"] < 0.5
    ans["sar"]["file"] = True
    ans["sar"]["narrative"] = "Weak suspicion narrated."
    ans["sar"]["activity_dates"] = ["2016-06-28", "2016-07-01"]
    errs = validate(ans, ENG.p, store)
    assert any("strong_suspicion_prob" in e for e in errs), errs
    assert any("3a condition" in e for e in errs), errs
