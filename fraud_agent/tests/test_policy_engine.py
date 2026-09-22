from fraud_agent.src.policy_engine import PolicyEngine
from pathlib import Path

def test_tiers():
    e = PolicyEngine(Path(__file__).parents[1] / "policies" / "policy.yaml")
    assert e.tier(10) == "low" and e.tier(50) == "medium" and e.tier(90) == "high"

def test_high_risk_blocks():
    e = PolicyEngine(Path(__file__).parents[1] / "policies" / "policy.yaml")
    d = e.decide(risk_score=90, pattern=None, pattern_conf=0.0)
    assert "block_transaction" in d.actions and d.approval == "analyst"
