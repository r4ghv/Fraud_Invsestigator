"""Test TigerGraph auth. Usage: python -m fraud_agent.src.tg_check
Prints a clear OK/FAIL so we stop guessing about credentials."""
from __future__ import annotations
import os, sys, requests
from pathlib import Path

ENV = Path(__file__).resolve().parents[1] / ".env"


def load_env() -> dict:
    for line in open(ENV):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    return {k: v for k, v in os.environ.items() if k.startswith("TIGERGRAPH_")}


def check() -> bool:
    e = load_env()
    host = e.get("TIGERGRAPH_HOST", "").rstrip("/")
    secret = e.get("TIGERGRAPH_SECRET", "")
    if not host or not secret:
        print("FAIL: TIGERGRAPH_HOST or TIGERGRAPH_SECRET missing in .env")
        return False
    r = requests.get(f"{host}/restpp/endpoints",
                     headers={"Authorization": f"GSQL-Secret {secret}"}, timeout=30)
    body = r.text
    if r.status_code == 200 and "error" not in body[:40]:
        print("OK: secret accepted")
        return True
    msg = ""
    try:
        msg = r.json().get("message", "")
    except Exception:
        msg = body[:200]
    print(f"FAIL [{r.status_code}]: {msg}")
    if "cannot be found" in msg:
        print("Hint: the secret string in .env does not match any secret in the workspace.")
        print("Create a new secret in Admin Portal > My Profile (copy the full value once),")
        print("and make sure it is scoped to graph 'Fraud'.")
    elif "Access Denied" in msg:
        print("Hint: secret exists but lacks access to this graph/user.")
    return False


if __name__ == "__main__":
    sys.exit(0 if check() else 1)
