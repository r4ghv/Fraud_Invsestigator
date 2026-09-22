"""Deterministic graph-signal pattern detectors.
Each is a pure function over evidence dicts (from GSQL queries).
Replace thresholds after reading HHGOA_IEEE README + 5 documented typologies.
"""
from __future__ import annotations


def velocity_burst(txns: list[dict], window_min: int = 60, count_gte: int = 5) -> tuple[bool, float]:
    """Many txns in short window. Evidence: [{timestamp}]."""
    if len(txns) < count_gte:
        return False, 0.0
    ts = sorted(t["timestamp"] for t in txns)
    for i in range(len(ts) - count_gte + 1):
        if ts[i + count_gte - 1] - ts[i] <= window_min * 60:
            return True, 0.9
    return False, 0.2


def device_mismatch(txn: dict, known_devices: set) -> tuple[bool, float]:
    d = txn.get("device_id")
    if not d:
        return False, 0.3  # missing signal = uncertainty, not proof
    return (True, 0.85) if d not in known_devices else (False, 0.1)


def amount_testing(txns: list[dict]) -> tuple[bool, float]:
    """Small probes followed by large charge."""
    if len(txns) < 3:
        return False, 0.0
    amts = [t["amount"] for t in sorted(txns, key=lambda x: x["timestamp"])]
    if amts[:-1] and max(amts[:-1]) < 10 and amts[-1] > 200:
        return True, 0.8
    return False, 0.15


def shared_device_across_accounts(account_count: int, threshold: int = 3) -> tuple[bool, float]:
    if account_count >= threshold:
        return True, min(0.95, 0.6 + 0.1 * account_count)
    return False, 0.1


def card_not_present_high_risk(txn: dict) -> tuple[bool, float]:
    if txn.get("channel") == "online" and txn.get("cvv_match") is False:
        return True, 0.85
    return False, 0.1


PATTERNS = {
    "velocity_burst": velocity_burst,
    "device_mismatch": device_mismatch,
    "amount_testing": amount_testing,
    "shared_device": shared_device_across_accounts,
    "cnp_high_risk": card_not_present_high_risk,
}
