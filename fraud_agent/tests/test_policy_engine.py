from fraud_agent.src.policy_engine import PolicyEngine
from pathlib import Path

P = Path(__file__).parents[1] / "policies" / "policy.yaml"

def test_block_route():
    e = PolicyEngine(P)
    assert e.block_route(100) == "L1" and e.block_route(3000) == "L2"

def test_r1_verify_before_block():
    e = PolicyEngine(P)
    init = e.initial(0.45, 1, "none")
    assert init[0]["action"] == "VERIFY_WITH_CUSTOMER"

def test_r2_denial_blocks():
    e = PolicyEngine(P)
    assert e.after_denial(200, False)[0] == {"action": "BLOCK_CARD", "route": "L1", "reason": "R2: customer denied"}

def test_uncertain_shared_no_sar_without_prob():
    e = PolicyEngine(P)
    need, _ = e.sar_needed("uncertain", 100, True, False, 0.3)
    assert need is False
