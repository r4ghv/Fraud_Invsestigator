#!/usr/bin/env python3
"""Analyst UI server: static files + a live TigerGraph REST++ proxy.

Run:  python fraud_agent/ui/serve.py  ->  http://127.0.0.1:8111
Serves the repo's fraud_agent/ tree (so /cases/*.json resolve) plus:
  GET /api/graph/case/<HHG-xxx>  -> CASE_ON edge + flagged-txn graph edges
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # fraud_agent/
_conn = None


def graph_conn():
    """One cached TigerGraph connection (token fetched once)."""
    global _conn
    if _conn is None:
        import pyTigerGraph as tg
        envd = {}
        for line in open(ROOT / ".env"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                envd[k.strip()] = v.strip()
        _conn = tg.TigerGraphConnection(
            host=envd["TIGERGRAPH_HOST"].rstrip("/"),
            graphname=envd.get("TIGERGRAPH_GRAPH", "Fraud"),
            gsqlSecret=envd["TIGERGRAPH_SECRET"])
        _conn.getToken(envd["TIGERGRAPH_SECRET"], lifetime=7 * 24 * 3600)
    return _conn


def case_graph_payload(case_id: str) -> dict:
    """Live graph edges around one case: case->card plus flagged-txn context."""
    ans_path = ROOT / "cases" / f"{case_id}.json"
    if not ans_path.exists():
        return {"error": f"no such case {case_id}"}
    ans = json.loads(ans_path.read_text())
    flagged = (ans["case"]["evidence"][0].get("entity_ids") or [""])[0]
    card = ""
    import re
    m = re.search(r"card (C\d+-K\d+)", ans["case"]["summary"] + " " +
                  (ans["case"].get("pattern_description") or ""))
    if m:
        card = m.group(1)
    try:
        conn = graph_conn()
        payload = {
            "case_id": case_id,
            "graph_case_id": ans["case"]["graph_case_id"],
            "card": card,
            "flagged_txn": flagged,
            "case_on": conn.getEdges("FraudCase", ans["case"]["graph_case_id"] or case_id, "CASE_ON"),
            "device_edges": conn.getEdges("Txn", flagged, "FROM_DEVICE") if flagged else [],
            "bill_edges": conn.getEdges("Txn", flagged, "BILLED_IN") if flagged else [],
        }
        return payload
    except Exception as ex:  # graph offline must degrade, never 500 the page
        return {"error": str(ex)[:200], "case_id": case_id}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, ctype="application/json", code=200):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send((self.path_root / "ui" / "index.html").read_bytes(),
                              "text/html; utf-8")
        if path.startswith("/api/graph/case/"):
            return self._send(case_graph_payload(path.rsplit("/", 1)[-1]))
        # static: /ui/*, /cases/*
        if path.startswith(("/ui/", "/cases/")):
            f = (self.path_root / path[1:]).resolve()
            if str(f).startswith(str(self.path_root.resolve())) and f.is_file():
                ctype = "text/html" if f.suffix == ".html" else \
                        "application/javascript" if f.suffix == ".js" else \
                        "text/css" if f.suffix == ".css" else "application/json"
                if f.suffix == ".json":
                    ctype = "application/json"
                return self._send(f.read_bytes(), ctype)
        self._send({"error": "not found"}, code=404)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8111)
    a = ap.parse_args()
    H.path_root = ROOT
    print(f"Analyst UI: http://127.0.0.1:{a.port}  (Ctrl-C to stop)")
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
