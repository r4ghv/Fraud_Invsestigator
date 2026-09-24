"""explainer is wired as the UI's explanation layer (spec M10: wire in with
tests, not left dead). Deterministic template; LLM rephrase stays optional."""
from fraud_agent.src.explainer import build

BEFORE = {"actions": [{"action": "MONITOR_CARD", "route": "auto"}], "approval": "auto"}


def test_build_deterministic_template():
    a = build({"type": "risk_score"}, 3, 0.4, 0.6, BEFORE, None, 2)
    b = build({"type": "risk_score"}, 3, 0.4, 0.6, BEFORE, None, 2)
    assert a == b
    assert "MONITOR_CARD" in a
    assert "No further evidence obtained" in a


def test_build_includes_after_stage_and_route():
    after = {"actions": [{"action": "BLOCK_CARD", "route": "L1"}], "approval": "L1"}
    text = build({"type": "customer_report"}, 5, 0.9, 0.8, BEFORE, after, 4)
    assert "BLOCK_CARD" in text
    assert "via L1" in text
    assert "Prior similar cases=4" in text
