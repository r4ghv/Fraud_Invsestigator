"""Split HHGOA CSVs into <=1MiB chunks (Savanna upload cap) and emit per-file load jobs.

Usage:
    python -m fraud_agent.src.chunk_and_load --split     # create chunks
    python -m fraud_agent.src.chunk_and_load --upload    # upload chunks + run jobs
"""
from __future__ import annotations
import argparse, os, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CHUNKS = DATA / "chunks"
MAX = 1048576 - 4096  # leave room for multipart envelope

SOURCES = {
    "txn_file": "transactions_graph.noheader.csv",
    "ident_file": "identity.noheader.csv",
    "cc_file": "closed_cases_history.noheader.csv",
}

# Loading targets per data source (positional indices, header="false")
TARGETS = {
    "txn_file": [
        "VERTEX Customer VALUES ($0, \"\")",
        "VERTEX Card VALUES ($16, $16)",
        "VERTEX Txn VALUES ($0, $2, $17, $18, $3, $10, $19)",
        "VERTEX BillingRegion VALUES ($10)",
        "EDGE OWNS VALUES ($16, $16)",
        "EDGE MADE VALUES ($16, $0)",
        "EDGE BILLED_IN VALUES ($0, $10)",
    ],
    "ident_file": [
        "VERTEX DeviceProfile VALUES ($40, $40, $30, $31, $33)",
        "EDGE FROM_DEVICE VALUES ($0, $40)",
    ],
    "cc_file": [
        "VERTEX ClosedCase VALUES ($0, $5, $6, $10, $14)",
        "VERTEX Card VALUES ($3, $2)",
        "VERTEX Customer VALUES ($2, \"\")",
        "EDGE OWNS VALUES ($2, $3)",
        "EDGE ON_CARD VALUES ($0, $3)",
    ],
}


def env() -> dict:
    for line in open(ROOT / ".env"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    return {"host": os.environ["TIGERGRAPH_HOST"].rstrip("/"),
            "secret": os.environ["TIGERGRAPH_SECRET"]}


def split() -> dict[str, list[Path]]:
    CHUNKS.mkdir(exist_ok=True)
    out: dict[str, list[Path]] = {}
    for var, fname in SOURCES.items():
        src = DATA / fname
        if not src.exists():
            raise SystemExit(f"missing {src}")
        parts, buf, n = [], [], 0
        with open(src) as f:
            for line in f:
                b = len(line.encode())
                if n + b > MAX and buf:
                    parts.append("".join(buf))
                    buf, n = [], 0
                buf.append(line)
                n += b
        if buf:
            parts.append("".join(buf))
        paths = []
        for i, text in enumerate(parts):
            p = CHUNKS / f"{var}_{i:03d}.csv"
            p.write_text(text)
            paths.append(p)
        out[var] = paths
        print(f"  {var}: {len(parts)} chunks, {src.stat().st_size/1e6:.1f} MB total")
    return out


def job_body(var: str) -> str:
    parts = sorted(CHUNKS.glob(f"{var}_*.csv"))
    files = "\n".join(f'  DEFINE FILENAME p{i};' for i in range(len(parts)))
    ds = "\n".join(
        f'  LOAD p{i} TO {t} USING header="false", separator=",";'
        for i in range(len(parts)) for t in TARGETS[var])
    return f"CREATE LOADING JOB load_{var} FOR GRAPH Fraud {{\n{files}\n\n{ds}\n}}\n"


def create_job(e: dict, body: str) -> None:
    name = body.split("JOB ")[1].split()[0]
    requests.delete(f"{e['host']}/gsql/v1/loading-jobs/{name}?graph=Fraud",
                   headers={"Authorization": f"GSQL-Secret {e['secret']}"}, timeout=60)
    r = requests.post(f"{e['host']}/gsql/v1/loading-jobs?graph=Fraud", data=body.encode(),
                      headers={"Authorization": f"GSQL-Secret {e['secret']}",
                               "Content-Type": "text/plain"}, timeout=300)
    if r.status_code >= 400:
        raise SystemExit(f"create [{r.status_code}]: {r.text[:300]}")
    print("  ", r.json().get("message"))


def upload(e: dict, var: str) -> None:
    job = f"load_{var}"
    for p in sorted(CHUNKS.glob(f"{var}_*.csv")):
        tag = p.stem.rsplit("_", 1)[1]  # "cc_file_000" -> "000"
        url = f"{e['host']}/gsql/v1/loading-jobs/{job}/files/p{tag}"
        with open(p, "rb") as f:
            r = requests.post(url, files={"file": (p.name, f, "text/csv")},
                              headers={"Authorization": f"GSQL-Secret {e['secret']}"},
                              timeout=300)
        if r.status_code >= 400:
            raise SystemExit(f"upload {p.name} [{r.status_code}]: {r.text[:200]}")
    print(f"   uploaded {len(list(CHUNKS.glob(f'{var}_*.csv')))} chunks for {var}")


def run(e: dict, var: str) -> None:
    parts = len(list(CHUNKS.glob(f"{var}_*.csv")))
    ds = [{"filename": f"p{i}", "name": "file", "path": f"p{i}.csv"} for i in range(parts)]
    r = requests.post(f"{e['host']}/gsql/v1/loading-jobs/run?graph=Fraud",
                      json=[{"name": f"load_{var}", "dataSources": ds}],
                      headers={"Authorization": f"GSQL-Secret {e['secret']}",
                               "Content-Type": "application/json"}, timeout=300)
    if r.status_code >= 400:
        raise SystemExit(f"run [{r.status_code}]: {r.text[:300]}")
    jid = r.json()["jobIds"][0]
    print(f"   running {var}: {jid}")
    for _ in range(540):
        time.sleep(10)
        s = requests.get(f"{e['host']}/gsql/v1/loading-jobs/status?graph=Fraud&jobIds={jid}",
                         headers={"Authorization": f"GSQL-Secret {e['secret']}"}, timeout=60)
        st = str(s.json())
        if "FINISHED" in st:
            import re
            m = re.search(r"validLine[^0-9]*(\\d+)", st)
            print(f"   {var} done, validLine={m.group(1) if m else '?'}")
            return
        if "FAILED" in st or "ABORT" in st:
            print("  ", st[:400])
            raise SystemExit(1)
    print("   timeout waiting for", var)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", action="store_true")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    e = env()
    if a.split:
        split()
    if a.upload:
        vars_ = [a.only] if a.only else list(SOURCES)
        for v in vars_:
            create_job(e, job_body(v))
            upload(e, v)
            run(e, v)
