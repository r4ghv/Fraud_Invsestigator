"""Deterministic R1-R10 policy engine. Inputs are numbers/strings, never LLM output."""
from __future__ import annotations
import yaml
from pathlib import Path


class PolicyEngine:
    def __init__(self, path: str | Path):
        self.p = yaml.safe_load(open(path))

    def block_route(self, exposure: float) -> str:
        return "L1" if exposure <= 2500 else "L2"

    def initial(self, prob: float, signals: int, pattern: str) -> list[dict]:
        """Before evidence. R1: single weak signal -> verify/step-up, not block."""
        if pattern == "card_testing":
            return [
                {"action": "DECLINE_TRANSACTION", "route": "L1", "reason": "R5: testing sequence observed"},
                {"action": "VERIFY_WITH_CUSTOMER", "route": "auto", "reason": "R1: confirm before blocking"},
            ]
        if prob < 0.70 and signals <= 1:
            return [
                {"action": "VERIFY_WITH_CUSTOMER", "route": "auto", "reason": "R1: single weak signal, verify before block"},
                {"action": "STEP_UP_AUTH", "route": "auto", "reason": "R1: verify before block"},
                {"action": "CREATE_CASE", "route": "auto", "reason": "3a: probability >= 0.30 / evidence requested"},
            ]
        if prob >= 0.70:
            return [
                {"action": "DECLINE_TRANSACTION", "route": "L1", "reason": "R5/R2: strong pattern signal"},
                {"action": "CREATE_CASE", "route": "auto", "reason": "3a: probability >= 0.30"},
            ]
        return [{"action": "MONITOR_CARD", "route": "auto", "reason": "R4: watch pending low-confidence alert"},
                {"action": "CREATE_CASE", "route": "auto", "reason": "3a: probability >= 0.30"}]

    def after_denial(self, exposure: float, shared: bool) -> list[dict]:
        acts = [{"action": "BLOCK_CARD", "route": self.block_route(exposure), "reason": "R2: customer denied"},
                {"action": "CREATE_CASE", "route": "auto", "reason": "R2"}]
        if exposure > 1000 or shared:
            acts.append({"action": "FILE_REPORT", "route": "L2", "reason": "R2/3a: exposure>1000 or shared origin"})
        if shared:
            acts.append({"action": "MONITOR_CONNECTED_CARDS", "route": "auto", "reason": "R6: shared device/region/ring"})
        return acts

    def after_confirm(self) -> list[dict]:
        return [{"action": "CLOSE_NO_FRAUD", "route": "auto", "reason": "R3: customer confirmed"}]

    def sar_needed(self, verdict: str, exposure: float, shared: bool, undoc: bool, prob: float = 0.0) -> tuple[bool, str]:
        if verdict == "legitimate":
            return False, "no fraud -> no report"
        if verdict == "uncertain" and not (exposure > 1000 or (shared and prob >= 0.5) or undoc):
            return False, "3a: uncertain without exposure/shared/coordinated -> case only, escalate per R8"
        if exposure > 1000:
            return True, "3a: confirmed/strongly suspected + exposure>1000"
        if shared and (verdict == "fraud" or prob >= 0.5):
            return True, "3a/R6: linked to shared device/region/another fraud"
        if undoc and verdict == "fraud":
            return True, "R9/3a: coordinated or undocumented pattern"
        if verdict == "uncertain":
            return False, "3a: uncertain -> case only"
        return False, "3a: case only, below report thresholds"

    def should_stop(self, prob: float, nevidence: int, settled: bool) -> tuple[bool, str]:
        s = self.p["rules"]["stop"]
        if settled:
            return True, "verification response settled the question"
        if nevidence >= s["min_evidence"] and (prob >= s["high_gte"] or prob <= s["low_lte"]):
            return True, f"probability {prob:.2f} with {nevidence} independent evidence pieces"
        return False, "uncertain — gather controlled evidence per section 5"
