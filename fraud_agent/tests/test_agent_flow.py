"""Agent-flow tests — spec finding H4: detectors must anchor on the flagged
txn and never read rows after it. Synthetic rows only (no big CSVs)."""
from datetime import datetime, timedelta
from pathlib import Path

from fraud_agent.src.agent import investigate
from fraud_agent.src.data_loader import Store
from fraud_agent.src.policy_engine import PolicyEngine

BASE = datetime(2016, 7, 1, 12, 0, 0)
POLICY = Path(__file__).parents[1] / "policies" / "policy.yaml"


def txn(pid, when, amt, channel="online", addr1="225", product="W"):
    return {
        "TransactionID": str(pid),
        "ts": when.strftime("%Y-%m-%d %H:%M:%S"),
        "TransactionAmt": str(amt),
        "channel": channel,
        "addr1": addr1,
        "ProductCD": product,
        "customer_id": "C00001",
    }


class StubStore(Store):
    """Store pre-loaded with synthetic rows; skips the 708 MB CSVs."""

    def __init__(self, txns, ident=None):
        super().__init__()
        self._txn = {t["TransactionID"]: t for t in txns}
        self._cust = {}
        for t in txns:
            self._cust.setdefault(t["customer_id"], []).append(t)
        for v in self._cust.values():
            v.sort(key=lambda r: r["ts"])
        self._ident = ident or {}
        self._loaded = True


def case(flagged_id, trigger="risk_score"):
    return {
        "case_id": "HHG-T1",
        "flagged_txn_id": flagged_id,
        "card_id": "C00001-K1",
        "customer_id": "C00001",
        "trigger_type": trigger,
        "risk_score": "0.61",
    }


def test_h4_no_lookahead_after_flag():
    """Small-auth sequence AFTER the alert must not be read (no look-ahead)."""
    flag = txn(100, BASE, 45)
    rows = [
        flag,
        txn(101, BASE + timedelta(minutes=60), 1),
        txn(102, BASE + timedelta(minutes=70), 2),
        txn(103, BASE + timedelta(minutes=80), 1),
        txn(104, BASE + timedelta(minutes=200), 60),
    ]
    ans = investigate(case("100"), StubStore(rows), PolicyEngine(POLICY))
    assert ans["case"]["pattern"] == "none", (
        "H4: detectors read rows after the flagged txn (look-ahead)"
    )


def test_h4_old_burst_not_anchored_on_flag():
    """A card-testing burst 20 days before the alert must not mark it."""
    old = [
        txn(1, BASE - timedelta(days=20), 1),
        txn(2, BASE - timedelta(days=20) + timedelta(minutes=10), 2),
        txn(3, BASE - timedelta(days=20) + timedelta(minutes=20), 1),
        txn(4, BASE - timedelta(days=20) + timedelta(minutes=180), 900),
    ]
    rows = old + [
        txn(98, BASE - timedelta(minutes=60), 40, channel="in_person"),
        txn(99, BASE - timedelta(minutes=30), 50, channel="in_person"),
        txn(100, BASE, 45, channel="in_person"),
    ]
    ans = investigate(case("100"), StubStore(rows), PolicyEngine(POLICY))
    assert ans["case"]["pattern"] == "none", (
        "H4: old burst fired without including the flagged txn"
    )
