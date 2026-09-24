"""Guard tests — spec finding C2: guards must DROP signals, not just relabel
the pattern; the dropped signal must not drive fraud probability."""
from test_agent_flow import BASE, POLICY, StubStore, case, txn

from fraud_agent.src.agent import investigate
from fraud_agent.src.policy_engine import PolicyEngine


def test_c2_trip_guard_drops_signal_from_probability():
    """Trip guard resets pattern to 'none'; its 0.7 confidence must not score."""
    from datetime import timedelta
    rows = [
        # home-region in-person history (region 225)
        txn(1, BASE - timedelta(days=40), 30, "in_person", "225"),
        txn(2, BASE - timedelta(days=35), 25, "in_person", "225"),
        # online txns in the flagged region across 3+ days -> trip guard
        txn(10, BASE - timedelta(days=3), 60, "online", "444"),
        txn(11, BASE - timedelta(days=2), 70, "online", "444"),
        txn(12, BASE - timedelta(days=1), 80, "online", "444"),
        # flagged: in-person in region 444 (away from home) -> out_of_region fires
        txn(100, BASE, 55, "in_person", "444"),
    ]
    ans = investigate(case("100"), StubStore(rows), PolicyEngine(POLICY))
    assert ans["case"]["pattern"] == "none", "trip guard should relabel to none"
    # C2: probability must come from surviving signals only.
    # Only signal was out_of_region (conf 0.7); after the drop, base = 0.2:
    # p = 0.7*0.2 + 0.3*0.61 = 0.323 -> 0.32. Pre-fix it scores the dropped
    # 0.7 signal: 0.7*0.7 + 0.3*0.61 = 0.67 (the HHG-001 bug).
    assert ans["case"]["fraud_probability"] == 0.32, (
        "C2: dropped out_of_region signal still drove the probability"
    )


# --- C3: real R7 — same product, monthly rhythm, per-product median ----------

def _r7_case():
    return case("100", trigger="customer_report")


def test_c3_r7_monthly_same_product_is_legitimate():
    """Disputed charge matching a monthly same-product rhythm -> legitimate."""
    from datetime import timedelta
    rows = [
        txn(1, BASE - timedelta(days=55), 20.0, "in_person", "225", product="W"),
        txn(2, BASE - timedelta(days=30), 20.5, "in_person", "225", product="W"),
        txn(3, BASE - timedelta(days=5), 19.5, "in_person", "225", product="W"),
        # other-product charges that skew the overall window median to ~200
        txn(4, BASE - timedelta(days=50), 200.0, "in_person", "225", product="C"),
        txn(5, BASE - timedelta(days=40), 200.0, "in_person", "225", product="C"),
        txn(6, BASE - timedelta(days=20), 200.0, "in_person", "225", product="C"),
        txn(100, BASE, 20.0, "in_person", "225", product="W"),  # disputed
    ]
    ans = investigate(_r7_case(), StubStore(rows), PolicyEngine(POLICY))
    assert ans["case"]["pattern"] == "none"
    assert ans["case"]["verdict"] == "legitimate"
    acts = [a["action"] for a in ans["next_best_actions"]["final"]]
    assert acts == ["CREATE_CASE", "VERIFY_WITH_CUSTOMER", "WARN_CUSTOMER"]
    assert not any(a.startswith("BLOCK") for a in acts), "R7 must never block"


def test_c3_r7_requires_monthly_rhythm():
    """Same product & amount but a clustered burst is NOT a recurring rhythm."""
    from datetime import timedelta
    rows = [
        txn(1, BASE - timedelta(days=10), 20.0, "in_person", "225", product="W"),
        txn(2, BASE - timedelta(days=5), 20.0, "in_person", "225", product="W"),
        txn(3, BASE - timedelta(days=2), 20.0, "in_person", "225", product="W"),
        txn(100, BASE, 20.0, "in_person", "225", product="W"),  # disputed
    ]
    ans = investigate(_r7_case(), StubStore(rows), PolicyEngine(POLICY))
    # no rhythm -> R7 must not fire -> customer denial path -> fraud
    assert ans["case"]["verdict"] == "fraud"
    acts = [a["action"] for a in ans["next_best_actions"]["final"]]
    assert "BLOCK_CARD" in acts


def test_c3_low_signal_closes_legitimate():
    """p <= stop.low after guards with a tiny bank score -> close, not escalate."""
    rows = [txn(100, BASE, 45.0, "in_person", "225")]
    c = case("100", trigger="risk_score")
    c["risk_score"] = "0.03"
    ans = investigate(c, StubStore(rows), PolicyEngine(POLICY))
    assert ans["case"]["verdict"] == "legitimate"
    assert ans["case"]["fraud_probability"] <= 0.15
    acts = [a["action"] for a in ans["next_best_actions"]["final"]]
    assert "CLOSE_NO_FRAUD" in acts and "ESCALATE_TO_ANALYST" not in acts
