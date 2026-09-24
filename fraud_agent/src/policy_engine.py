"""Deterministic R1-R10 policy engine. Inputs are numbers/strings, never LLM output."""
from __future__ import annotations
import yaml
from pathlib import Path


class PolicyEngine:
    def __init__(self, path: str | Path):
        self.p = yaml.safe_load(open(path))

    def block_route(self, exposure: float) -> str:
        return "L1" if exposure <= self.p["rules"]["block_route"]["l1_max"] else "L2"

    def initial(self, prob: float, signals: int, pattern: str, cleared: float = 0.0) -> list[dict]:
        """Before evidence. R1: single weak signal -> verify/step-up, not block."""
        rules = self.p["rules"]
        r1_max = rules["R1_verify_before_block"]["max_single_signal_prob"]
        if pattern == "card_testing":
            # R5: decline + step-up; block if the follow-up purchase already cleared
            r5 = rules["R5_card_testing"]
            acts = [
                {"action": "DECLINE_TRANSACTION", "route": "L1", "reason": "R5: testing sequence observed"},
                {"action": "STEP_UP_AUTH", "route": "auto", "reason": "R5: require step-up on next auth"},
            ]
            if cleared > r5["block_if_cleared_gt"]:
                acts.append({"action": "BLOCK_CARD", "route": self.block_route(cleared),
                             "reason": f"R5: cleared purchase ${cleared:.2f} over ${r5['block_if_cleared_gt']:.0f}"})
            return acts
        if prob < r1_max and signals <= 1:
            return [
                {"action": "VERIFY_WITH_CUSTOMER", "route": "auto", "reason": "R1: single weak signal, verify before block"},
                {"action": "STEP_UP_AUTH", "route": "auto", "reason": "R1: verify before block"},
                {"action": "CREATE_CASE", "route": "auto", "reason": "3a: probability >= 0.30 / evidence requested"},
            ]
        if prob >= r1_max:
            return [
                {"action": "DECLINE_TRANSACTION", "route": "L1", "reason": "R5/R2: strong pattern signal"},
                {"action": "CREATE_CASE", "route": "auto", "reason": "3a: probability >= 0.30"},
            ]
        return [{"action": "MONITOR_CARD", "route": "auto", "reason": "R4: watch pending low-confidence alert"},
                {"action": "CREATE_CASE", "route": "auto", "reason": "3a: probability >= 0.30"}]

    def after_denial(self, exposure: float, shared: bool) -> list[dict]:
        report_gt = self.p["rules"]["R2_customer_denies"]["report_if_exposure_gt"]
        acts = [{"action": "BLOCK_CARD", "route": self.block_route(exposure), "reason": "R2: customer denied"},
                {"action": "CREATE_CASE", "route": "auto", "reason": "R2"}]
        if exposure > report_gt or shared:
            acts.append({"action": "FILE_REPORT", "route": "L2",
                         "reason": f"R2/3a: exposure>${report_gt:.0f} or shared origin"})
        if shared:
            acts.append({"action": "MONITOR_CONNECTED_CARDS", "route": "auto", "reason": "R6: shared device/region/ring"})
        return acts

    def after_confirm(self) -> list[dict]:
        return [{"action": "CLOSE_NO_FRAUD", "route": "auto", "reason": "R3: customer confirmed"}]

    def r4_no_reply(self, exposure: float) -> list[dict]:
        """R4: monitor + decline the pending auth; escalate only if exposed."""
        gt = self.p["rules"]["R4_no_reply"]["escalate_if_exposure_gt"]
        acts = [{"action": "MONITOR_CARD", "route": "auto", "reason": "R4: no reply, monitor pending"},
                {"action": "DECLINE_TRANSACTION", "route": "L1", "reason": "R4: no reply on pending auth"}]
        if exposure > gt:
            acts.append({"action": "ESCALATE_TO_ANALYST", "route": "auto",
                         "reason": f"R4/R8: exposure ${exposure:.0f} over ${gt:.0f}"})
        return acts

    def r8_escalate(self, verdict: str, exposure: float, conflicts: bool) -> bool:
        gt = self.p["rules"]["R8_uncertain_escalate"]["exposure_gt"]
        return verdict == "uncertain" and (exposure > gt or conflicts)

    def sar_needed(self, verdict: str, exposure: float, shared: bool, undoc: bool, prob: float = 0.0) -> tuple[bool, str]:
        rules = self.p["rules"]
        gt, strong = rules["sar_exposure_gt"], rules["strong_suspicion_prob"]
        if verdict == "legitimate":
            return False, "no fraud -> no report"
        if verdict == "uncertain" and not (exposure > gt or (shared and prob >= strong) or undoc):
            return False, "3a: uncertain without exposure/shared/coordinated -> case only, escalate per R8"
        if exposure > gt:
            return True, f"3a: confirmed/strongly suspected + exposure>${gt:.0f}"
        if shared and (verdict == "fraud" or prob >= strong):
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
