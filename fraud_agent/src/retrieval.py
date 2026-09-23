"""Prior-case retrieval. Deterministic keyword/pattern overlap, no embeddings."""
from __future__ import annotations
import csv
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


def similar(pattern: str, flagged_notes: str = "", limit: int = 3) -> list[str]:
    rows = list(csv.DictReader(open(DATA / "closed_cases_history.csv")))
    scored = []
    for r in rows:
        s = 0
        if r["pattern"] == pattern:
            s += 2
        if r["outcome"] == "confirmed_fraud":
            s += 1
        scored.append((s, r["case_id"]))
    scored.sort(reverse=True)
    return [c for _, c in scored[:limit]]
