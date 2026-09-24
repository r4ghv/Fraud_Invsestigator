"""Writes a completed case into graph Fraud: FraudCase vertex + CASE_ON edge.

Deterministic, no LLM. Per-record REST++ upserts that raise on failure, so a
failed graph write can never mark written_to_graph=true.

NOTE: a FraudCase->Txn edge (CASE_TXN) is not possible on this graph: TigerGraph
4 only accepts CREATE EDGE in global scope, the live schema is graph-local, and
ALTER has no attribute-ADD verb. Txn ids stay in the answer JSON; the graph
carries case->card linkage via CASE_ON.
"""
from __future__ import annotations

from .load_tigergraph import connect, env


def build_upsert(ans: dict, card_id: str) -> dict:
    """Pure payload description (unit-tested with synthetic answers, no network)."""
    case = ans["case"]
    return {"vertex": ("FraudCase", ans["case_id"], {
        "status": case["status"],
        "verdict": case["verdict"],
        "prob": float(case["fraud_probability"]),
        "pattern": case["pattern"],
    }), "edge": ("CASE_ON", ans["case_id"], card_id)}


def write_case(ans: dict, card_id: str, conn=None) -> str:
    """Upsert the case vertex and CASE_ON edge; return the graph_case_id."""
    conn = conn or connect(env())
    p = build_upsert(ans, card_id)
    vtype, vid, attrs = p["vertex"]
    _, src, dst = p["edge"]
    conn.upsertVertex(vtype, vid, attrs)
    conn.upsertEdge("FraudCase", src, "CASE_ON", "Card", dst)
    return vid
