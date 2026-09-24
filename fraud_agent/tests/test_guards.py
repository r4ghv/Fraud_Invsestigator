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
