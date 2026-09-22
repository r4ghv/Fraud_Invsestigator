"""Explanation builder. Template-first; LLM optional rephrase only.
Never lets LLM change actions/approval/SAR.
"""
from __future__ import annotations
import os


def build(trigger: dict, evidence_n: int, risk: float, conf: float,
          nba_before: dict, nba_after: dict | None, prior_n: int) -> str:
    base = (
        f"Trigger={trigger}. Evidence items={evidence_n}. "
        f"Risk={risk} conf={conf}. Prior similar cases={prior_n}. "
        f"Before-evidence NBA={nba_before['actions']} via {nba_before['approval']}. "
        + (f"After-evidence NBA={nba_after['actions']} via {nba_after['approval']}."
           if nba_after else "No further evidence obtained.")
    )
    # Optional LLM rephrase: must echo same facts; skip if no key.
    if os.getenv("LLM_API_KEY"):
        try:
            return _llm_rephrase(base)
        except Exception:
            return base
    return base


def _llm_rephrase(text: str) -> str:
    raise NotImplementedError("Plug LLM rephrase here; keep facts identical")
