"""Prior-case retrieval (GraphRAG memory layer): deterministic, case-specific,
no embeddings. Loads closed_cases_history.csv once; resolves each closed case's
channel/region from its first fraud txn via the graph store (cached) so two
cases with the same pattern but different amount/region get different top-3
lists (spec M13)."""
from __future__ import annotations
import csv
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
_HISTORY: list[dict] | None = None
_CTX: dict[str, tuple[str, str]] = {}  # case_id -> (channel, region), resolved once


def _load() -> list[dict]:
    global _HISTORY
    if _HISTORY is None:
        with open(DATA / "closed_cases_history.csv") as f:
            _HISTORY = list(csv.DictReader(f))
    return _HISTORY


def amount_closeness(a: float, b: float) -> float:
    """1.0 within 10%, 0.5 within 50%, else 0."""
    if a <= 0 or b <= 0:
        return 0.0
    rel = abs(a - b) / max(a, b)
    return 1.0 if rel <= 0.10 else 0.5 if rel <= 0.50 else 0.0


def _case_ctx(r: dict, store) -> tuple[str, str]:
    cid = r["case_id"]
    if cid not in _CTX:
        tid = (r.get("first_fraud_txn_id") or "").strip()
        row = (store._txn.get(str(tid), {}) if store is not None else {}) or {}
        _CTX[cid] = (str(row.get("channel", "")), str(row.get("addr1", "")))
    return _CTX[cid]


def similar(pattern: str, flagged_notes: str = "", limit: int = 3, *,
            amount: float = 0.0, channel: str = "", region: str = "",
            connected_cards: tuple = (), store=None) -> list[str]:
    """Top-3 prior cases for THIS case: pattern match dominates; channel, region,
    amount closeness, connected cards, and note overlap make it case-specific."""
    note_tokens = {w for w in flagged_notes.lower().split() if len(w) > 3}
    scored = []
    for r in _load():
        s = 2 * (r["pattern"] == pattern)
        ch, reg = _case_ctx(r, store)
        if channel and ch and ch == channel:
            s += 1
        if region and reg and reg == region:
            s += 1
        s += amount_closeness(float(r.get("exposure_usd") or 0), amount)
        if connected_cards and r.get("card_id") in connected_cards:
            s += 1
        if note_tokens and note_tokens & set(
                (r.get("analyst_notes") or "").lower().split()):
            s += 1
        if s > 0:
            scored.append((s, r["case_id"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [cid for _, cid in scored[:limit]]
