"""Case create/progress + prior-case memory. JSON-file backed, TigerGraph-mirrorable."""
from __future__ import annotations
import json, uuid, time
from pathlib import Path


class CaseManager:
    def __init__(self, store: str | Path):
        self.store = Path(store)
        self.store.mkdir(parents=True, exist_ok=True)

    def create(self, trigger: dict) -> dict:
        case = {"case_id": str(uuid.uuid4())[:8], "status": "open",
                "trigger": trigger, "evidence": [], "findings": [],
                "decisions": [], "actions": [], "created": time.time()}
        self._save(case)
        return case

    def add_evidence(self, case: dict, item: dict) -> dict:
        case["evidence"].append(item)
        self._save(case)
        return case

    def record(self, case: dict, nba_before: dict, nba_after: dict | None,
               explanation: str) -> dict:
        case["decisions"].append({"before": nba_before, "after": nba_after})
        case["actions"].extend(nba_after["actions"] if nba_after else nba_before["actions"])
        case["findings"].append(explanation)
        case["status"] = "pending_approval" if (nba_after or nba_before)["approval"] != "auto" else "closed"
        self._save(case)
        return case

    def similar(self, pattern: str | None, limit: int = 3) -> list[dict]:
        out = []
        for p in self.store.glob("*.json"):
            c = json.loads(p.read_text())
            if pattern and any(pattern in f for f in c.get("findings", [])):
                out.append(c)
            if len(out) >= limit:
                break
        return out

    def _save(self, case: dict):
        (self.store / f"{case['case_id']}.json").write_text(json.dumps(case, indent=2))
