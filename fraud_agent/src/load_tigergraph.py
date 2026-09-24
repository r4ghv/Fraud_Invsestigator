"""Live TigerGraph loader: installs loading job, uploads CSVs, runs it.

Usage:
    python -m fraud_agent.src.load_tigergraph --install     # install job only
    python -m fraud_agent.src.load_tigergraph --run          # install + upload + run
    python -m fraud_agent.src.load_tigergraph --status        # job status
"""
from __future__ import annotations
import argparse, os, re, sys, time
from pathlib import Path
import requests
import pyTigerGraph as tg

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GSQL = ROOT / "src" / "tigergraph"


def env() -> dict:
    for line in open(ROOT / ".env"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    return {
        "host": os.environ["TIGERGRAPH_HOST"].rstrip("/"),
        "secret": os.environ["TIGERGRAPH_SECRET"],
        "graph": os.environ.get("TIGERGRAPH_GRAPH", "Fraud"),
    }


def connect(e: dict) -> tg.TigerGraphConnection:
    conn = tg.TigerGraphConnection(host=e["host"], graphname=e["graph"],
                                   gsqlSecret=e["secret"])
    conn.getToken(e["secret"], lifetime=7 * 24 * 3600)
    return conn


def strip_lines(path: Path) -> str:
    """Loading jobs need real filename placeholders; pyTigerGraph uploads
    each file separately and binds the DEFINE FILENAME vars by position."""
    out = []
    for ln in path.read_text().splitlines():
        s = ln.strip()
        if s.startswith("//") or not s:
            continue
        out.append(ln)
    return "\n".join(out)


def create_job(conn: tg.TigerGraphConnection, job_def: str, secret: str) -> None:
    """pyTigerGraph posts the job as form data; this server requires text/plain GSQL.
    GSQL-Secret auth is accepted directly, so no bearer token juggling is needed."""
    url = f"{conn.gsUrl}/gsql/v1/loading-jobs?graph={conn.graphname}"
    hdr = {"Authorization": f"GSQL-Secret {secret}", "Content-Type": "text/plain"}
    r = requests.post(url, data=job_def.encode(), headers=hdr, timeout=300)
    if r.status_code >= 400:
        raise SystemExit(f"createLoadingJob [{r.status_code}]: {r.text[:300]}")
    print("  created job:", r.json())


def install(conn: tg.TigerGraphConnection, run: bool = False, secret: str = "") -> None:
    # drop previous job + clear partial loads
    for stmt in ["DROP JOB load_fraud", "USE GRAPH Fraud\nCLEAR GRAPH GRAPH Fraud"]:
        try:
            conn.gsql(stmt)
            print("  ran:", stmt.replace("\n", " "))
        except Exception as e:
            print("  skipped:", stmt.replace("\n", " "), "-", str(e)[:60])
    create_job(conn, (GSQL / "load.gsql").read_text(), secret)
    print("  installed load_fraud job (server-side files)")
    if not run:
        return
    # Body is a JSON array of job objects; data sources use filename + path.
    payload = [{
        "name": "load_fraud",
        "dataSources": [
            {"filename": "txn_file", "name": "file", "path": str(DATA / "transactions_graph.noheader.csv")},
            {"filename": "ident_file", "name": "file", "path": str(DATA / "identity.noheader.csv")},
            {"filename": "cc_file", "name": "file", "path": str(DATA / "closed_cases_history.noheader.csv")},
        ],
    }]
    r = requests.post(f"{conn.gsUrl}/gsql/v1/loading-jobs/run?graph={conn.graphname}",
                      json=payload,
                      headers={"Authorization": f"GSQL-Secret {secret}",
                               "Content-Type": "application/json"},
                      timeout=300)
    if r.status_code >= 400:
        raise SystemExit(f"runLoadingJob [{r.status_code}]: {r.text[:400]}")
    print("  job submitted:", r.json())
    wait_for_job(conn)
    print("  counts:", vertex_counts(conn))


def wait_for_job(conn: tg.TigerGraphConnection, minutes: int = 90) -> None:
    for _ in range(minutes * 6):
        time.sleep(10)
        info = conn.getLoadingJobStatus("load_fraud")
        s = str(info).lower()
        print("  ...", s[:120], flush=True)
        if "success" in s or "completed" in s:
            print("  job finished OK")
            return
        if "failed" in s or "error" in s:
            print("  job failed:", str(info)[:400])
            raise SystemExit(1)


def upload(e: dict, job: str = "load_fraud") -> None:
    """Map each file to its DEFINE FILENAME position in the job order."""
    host, secret, graph = e["host"], e["secret"], e["graph"]
    files = [
        ("txn_file", DATA / "transactions_graph.noheader.csv"),
        ("ident_file", DATA / "identity.noheader.csv"),
        ("cc_file", DATA / "closed_cases_history.noheader.csv"),
    ]
    for var, path in files:
        if not path.exists():
            raise SystemExit(f"missing {path}")
        size = path.stat().st_size
        url = f"{host}/restpp/file/load/{graph}/{job}/{var}"
        # pyTigerGraph handles multipart + auth via its own endpoint
        print(f"  uploading {path.name} ({size/1e6:.1f} MB) ...", flush=True)
        with open(path, "rb") as f:
            r = requests.post(url, files={"file": (path.name, f, "text/csv")},
                              headers={"Authorization": f"GSQL-Secret {secret}"},
                              timeout=1800)
        print(f"   -> [{r.status_code}] {r.text[:120]}")
        if r.status_code >= 400:
            raise SystemExit(f"upload failed for {path.name}")


def run_job(conn: tg.TigerGraphConnection) -> None:
    print("  starting load_fraud ...", flush=True)
    conn.gsql("USE GRAPH Fraud\nRUN JOB load_fraud")
    for _ in range(600):
        time.sleep(10)
        status = status_job(conn)
        s = str(status)
        if "success" in s.lower():
            print("  job finished")
            break
        if "failed" in s.lower():
            print("  job failed:", s[:200])
            break
    print("  counts:", vertex_counts(conn))


def status_job(conn: tg.TigerGraphConnection):
    try:
        return conn.getLoadingJobStatus("load_fraud")
    except Exception:
        return conn.gsql("USE GRAPH Fraud\nSHOW JOB load_fraud")


def vertex_counts(conn: tg.TigerGraphConnection) -> dict:
    out = {}
    for v in ["Customer", "Card", "Txn", "DeviceProfile", "BillingRegion", "ClosedCase", "FraudCase"]:
        try:
            out[v] = conn.vertexCount(v)
        except Exception:
            out[v] = "?"
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    e = env()
    conn = connect(e)
    print("connected to", e["graph"])
    if a.status:
        print(status_job(conn))
        print("counts:", vertex_counts(conn))
    elif a.run:
        install(conn, run=True, secret=e["secret"])
    elif a.install:
        install(conn, secret=e["secret"])
