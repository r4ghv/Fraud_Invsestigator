"""8-step agent orchestration. Deterministic except optional explanation rephrase."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from .policy_engine import PolicyEngine
from .pattern_detectors import velocity_burst, device_mismatch
from .risk_scorer import combine
from .next_best_action import recommend
from .case_manager import CaseManager
from .evidence_collector import get_account_history
from .explainer import build

ROOT = Path(__file__).resolve().parents[1]


def investigate(trigger: dict, bank_score: float, txns: list[dict], device: dict) -> dict:
    eng = PolicyEngine(ROOT / "policies" / "policy.yaml")
    cm = CaseManager(ROOT / "outputs")
    case = cm.create(trigger)

    hist = get_account_history(trigger.get("account_id", "unknown"))
    cm.add_evidence(case, hist)

    sigs = [velocity_burst(txns),
            device_mismatch({"device_id": device.get("id")}, set(device.get("known", [])))]
    pattern = "velocity_burst" if sigs[0][0] else ("device_mismatch" if sigs[1][0] else None)
    pconf = max(c for _, c in sigs)
    risk, conf = combine(bank_score, sigs)
    nba_before = recommend(eng, "before_evidence", risk, conf, pattern, pconf).to_dict()

    # controlled evidence gathering (max 1 mock round for now)
    nba_after = None
    if not eng.should_stop(eng.tier(risk), conf):
        # e.g. step_up_auth result simulated as no new risk
        nba_after = recommend(eng, "after_evidence", risk, min(0.9, conf + 0.1),
                              pattern, pconf).to_dict()

    expl = build(trigger, len(case["evidence"]), risk, conf, nba_before, nba_after,
                 len(cm.similar(pattern)))
    case = cm.record(case, nba_before, nba_after, expl)
    return {"case": case, "nba_before": nba_before, "nba_after": nba_after,
            "explanation": expl, "risk": risk, "confidence": conf, "pattern": pattern}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    trig = {"type": "risk_score", "account_id": "demo_acct"}
    out = investigate(trig, 75.0, [{"timestamp": 0, "amount": 5}, {"timestamp": 10, "amount": 8},
                                   {"timestamp": 20, "amount": 500}],
                      {"id": "dev_new", "known": ["dev_old"]})
    print(json.dumps(out, indent=2))
