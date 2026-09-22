"""Deterministic risk scorer. No LLM."""
from __future__ import annotations


def combine(bank_score_0_100: float, graph_signals: list[tuple[bool, float]]) -> tuple[float, float]:
    """Return (risk_score, confidence). graph_score = max matched conf*100 else 20."""
    matched = [c for hit, c in graph_signals if hit]
    graph_score = max(matched) * 100 if matched else 20.0
    risk = 0.5 * bank_score_0_100 + 0.5 * graph_score
    # confidence rises with agreement / evidence count
    conf = 0.5 + 0.1 * len(matched)
    if matched and abs(bank_score_0_100 - graph_score) < 20:
        conf += 0.2
    return round(min(100.0, risk), 2), round(min(0.95, conf), 2)
