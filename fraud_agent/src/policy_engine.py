"""Deterministic policy engine. No LLM, no network, no randomness."""
from __future__ import annotations
import yaml
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    actions: list[str]
    approval: str
    sar_required: bool
    tier: str
    reason: str


class PolicyEngine:
    def __init__(self, policy_path: str | Path):
        with open(policy_path) as f:
            self.p = yaml.safe_load(f)

    def tier(self, score: float) -> str:
        s = max(0.0, min(100.0, float(score)))
        if s <= self.p["risk_tiers"]["low"]["max_score"]:
            return "low"
        if s <= self.p["risk_tiers"]["medium"]["max_score"]:
            return "medium"
        return "high"

    def decide(self, *, risk_score: float, pattern: str | None,
               pattern_conf: float, confirmed_fraud: bool = False,
               amount: float = 0.0, linked_accounts: int = 0) -> Decision:
        t = self.tier(risk_score)
        m = self.p["action_matrix"][t]
        if confirmed_fraud or self._sar_trigger(amount, linked_accounts):
            d = m.get("confirmed_fraud", m["default"])
            return Decision(d["actions"], d["approval"], True, t,
                            f"tier={t} sar_trigger amount={amount} linked={linked_accounts}")
        if pattern and pattern_conf >= 0.8 and "high_confidence_pattern" in m:
            d = m["high_confidence_pattern"]
            return Decision(d["actions"], d["approval"], False, t,
                            f"tier={t} pattern={pattern} conf={pattern_conf:.2f}")
        d = m["default"]
        return Decision(d["actions"], d["approval"], d.get("sar", False), t,
                        f"tier={t} default")

    def _sar_trigger(self, amount: float, linked: int) -> bool:
        st = self.p["sar_triggers"]
        return amount >= st["confirmed_fraud_amount_gte"] or \
            linked >= st["pattern_repeated_across_accounts_gte"]

    def evidence_requests(self) -> list[str]:
        return list(self.p["evidence_policy"]["request_order"])

    def should_stop(self, tier: str, confidence: float) -> bool:
        ep = self.p["evidence_policy"]["stop_when"]
        return tier in ep["risk_tier_in"] and confidence >= ep["confidence_gte"]
