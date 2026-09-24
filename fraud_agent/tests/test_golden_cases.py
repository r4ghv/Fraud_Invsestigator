"""Golden tests on the 20 committed answer files (spec L15 / Section 5 layout).
Run without the big CSVs — dataset ID checks are covered by synthetic-store
unit tests; these assert format, enums, and cross-field invariants on outputs.
"""
import json
import re
from pathlib import Path

import pytest

from fraud_agent.src.policy_engine import PolicyEngine
from fraud_agent.src.validator import validate

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases"
FILES = sorted(CASES.glob("HHG-0*.json"))
ENG = PolicyEngine(ROOT / "policies" / "policy.yaml")
PATTERNS = {"card_testing", "card_not_present_fraud", "card_not_present_new_device",
            "out_of_region_use", "account_takeover", "undocumented", "none"}


def test_twenty_case_files_present():
    assert [f.stem for f in FILES] == [f"HHG-{i:03d}" for i in range(1, 21)]


@pytest.mark.parametrize("f", FILES, ids=[f.stem for f in FILES])
def test_golden_answer_valid(f):
    ans = json.loads(f.read_text())
    assert ans["case_id"] == f.stem
    # full cross-field validation (README contract + policy.yaml thresholds)
    assert validate(ans, ENG.p, store=None) == []
    # deterministic design: zero LLM tokens
    assert ans["tokens"] == 0
    # NBA always records both stages
    nba = ans["next_best_actions"]
    assert nba["initial"] and nba["final"]
    assert nba["what_changed"]
    assert ans["stop_reason"]
    # README enums
    assert ans["case"]["pattern"] in PATTERNS
    if ans["case"]["pattern"] == "undocumented":
        assert ans["case"]["pattern_description"].strip()
    # submission requirement: every answer carries the graph-write result
    assert ans["case"]["written_to_graph"] in (True, False)


@pytest.mark.parametrize(
    "f", [f for f in FILES if json.loads(f.read_text())["sar"]["file"]],
    ids=[f.stem for f in FILES if json.loads(f.read_text())["sar"]["file"]])
def test_golden_sar_narrative_length(f):
    """README: SAR narrative is six to twelve sentences when file is true."""
    ans = json.loads(f.read_text())
    narrative = ans["sar"]["narrative"]
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", narrative) if s.strip()]
    assert 6 <= len(sentences) <= 12, f"{f.stem}: {len(sentences)} sentences"
