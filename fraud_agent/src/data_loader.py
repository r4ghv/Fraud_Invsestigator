"""CSV-backed evidence store. Deterministic; counts tool calls for answer files."""
from __future__ import annotations
import csv
from pathlib import Path
from datetime import datetime

DATA = Path(__file__).resolve().parents[1] / "data"
TXN_COLS = ["TransactionID", "TransactionAmt", "ProductCD", "card1", "addr1", "addr2",
            "P_emaildomain", "R_emaildomain", "customer_id", "ts", "channel", "risk_score"]
IDENT_PROFILE = ["DeviceType", "DeviceInfo", "id_30", "id_31", "id_33"]


class Store:
    def __init__(self):
        self.calls = 0
        self._txn: dict[str, dict] = {}
        self._cust: dict[str, list[dict]] = {}
        self._ident: dict[str, dict] = {}
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        with open(DATA / "transactions.csv") as f:
            for r in csv.DictReader(f):
                t = {k: r.get(k, "") for k in TXN_COLS}
                self._txn[str(t["TransactionID"])] = t
                self._cust.setdefault(r.get("customer_id", ""), []).append(t)
        try:
            with open(DATA / "identity.csv") as f:
                for r in csv.DictReader(f):
                    self._ident[str(r["TransactionID"])] = r
        except FileNotFoundError:
            pass
        for v in self._cust.values():
            v.sort(key=lambda r: r["ts"])
        self._loaded = True

    def flagged(self, tid: str) -> dict:
        self.calls += 1
        self.load()
        return dict(self._txn[str(tid)])

    def card_window(self, customer: str, around_ts: str, days: int = 60) -> list[dict]:
        self.calls += 1
        self.load()
        c = datetime.strptime(around_ts, "%Y-%m-%d %H:%M:%S")
        return [r for r in self._cust.get(customer, [])
                if abs((datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S") - c).days) <= days]

    def device_profile(self, tid: str) -> str:
        i = self._ident.get(str(tid), {})
        return " | ".join(str(i.get(k, "")) for k in IDENT_PROFILE if i.get(k))

    def device_neighbors(self, profile: str, exclude_customer: str = "") -> list[str]:
        """Other customers sharing the same device profile (shared-origin check)."""
        self.calls += 1
        self.load()
        if not profile:
            return []
        out, seen = [], set()
        for tid, i in self._ident.items():
            p = " | ".join(str(i.get(k, "")) for k in IDENT_PROFILE if i.get(k))
            if p == profile:
                cust = self._txn.get(str(tid), {}).get("customer_id", "")
                if cust and cust != exclude_customer and cust not in seen:
                    seen.add(cust)
                    out.append(cust)
                if len(out) >= 10:
                    break
        return out
