"""Evidence collector: TigerGraph MCP/GSQL interface with mock fallback.
Real queries live in src/tigergraph/queries.gsql. Agent code calls these
functions so swapping mock->Savanna is one env var.
"""
from __future__ import annotations
import os


def get_account_history(account_id: str) -> dict:
    if os.getenv("TIGERGRAPH_HOST"):
        raise NotImplementedError("Wire to Savanna MCP once creds provided")
    return {"account_id": account_id, "txns": [], "devices": [],
            "source": "mock — awaiting HHGOA_IEEE load"}


def get_linked_accounts(device_id: str) -> dict:
    if os.getenv("TIGERGRAPH_HOST"):
        raise NotImplementedError("Wire to Savanna MCP once creds provided")
    return {"device_id": device_id, "accounts": [], "source": "mock"}
