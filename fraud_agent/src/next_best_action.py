"""NBA recommender: deterministic wrapper over PolicyEngine.
Produces before/after-evidence records required by submission spec.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from .policy_engine import PolicyEngine


@dataclass
class NBARecord:
    stage: str  # "before_evidence" | "after_evidence"
    risk_score: float
    confidence: float
    actions: list[str]
    approval: str
    sar_required: bool
    reason: str

    def to_dict(self): return asdict(self)


def recommend(engine: PolicyEngine, stage: str, risk_score: float, confidence: float,
              pattern: str | None, pattern_conf: float, **kw) -> NBARecord:
    d = engine.decide(risk_score=risk_score, pattern=pattern,
                      pattern_conf=pattern_conf, **kw)
    return NBARecord(stage, risk_score, confidence, d.actions, d.approval,
                     d.sar_required, d.reason)
