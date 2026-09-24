"""Install investigation queries + schema edge additions on Savanna (spec M11).

Usage:
    python -m fraud_agent.src.graph_queries --install
"""
from __future__ import annotations
import argparse
from pathlib import Path

from .load_tigergraph import env, connect

GSQL = Path(__file__).resolve().parents[1] / "src" / "tigergraph"
QUERIES = ["flagged_transaction", "card_window", "device_neighbors", "connected_ring",
           "ring_reach"]


def install() -> None:
    e = env()
    conn = connect(e)
    print("connected to", e["graph"])
    # drop first: the GSQL shell aborts a multi-statement script on first error,
    # and stale/draft definitions would block the CREATEs behind them
    for q in QUERIES:
        try:
            conn.gsql(f"USE GRAPH Fraud\nDROP QUERY {q}")
            print("dropped old", q)
        except Exception:
            pass
    out = conn.gsql("USE GRAPH Fraud\n" + (GSQL / "queries.gsql").read_text())
    print(out)
    stmt = "USE GRAPH Fraud\nINSTALL QUERY " + ", ".join(QUERIES)
    print(conn.gsql(stmt))
    print("installed:", ", ".join(QUERIES))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", default=True)
    ap.parse_args()
    install()
