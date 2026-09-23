"""Deterministic pattern detectors over real HHGOA_IEEE rows. Pure functions."""
from __future__ import annotations
from datetime import datetime, timedelta


def _ts(r): return datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S")


def card_testing(card_txns: list[dict]) -> tuple[bool, float, list]:
    """R5: 3+ small online auths (<$5) within 60min, then larger purchase."""
    on = sorted([r for r in card_txns if r.get("channel") == "online"], key=_ts)
    for i in range(len(on)):
        small = [on[i]]
        for j in range(i + 1, len(on)):
            if (_ts(on[j]) - _ts(on[i])) <= timedelta(minutes=60) and float(on[j]["TransactionAmt"]) < 5.0:
                small.append(on[j])
        if len(small) >= 3:
            after = [r for r in on if _ts(r) > _ts(small[-1]) and _ts(r) - _ts(small[-1]) <= timedelta(hours=48)
                     and float(r["TransactionAmt"]) >= 5.0]
            if after:
                return True, 0.85, [r["TransactionID"] for r in small + after[:1]]
    return False, 0.1, []


def cnp_burst(card_txns: list[dict], hist_median: float) -> tuple[bool, float, list]:
    """Pattern 2: 2-4 online txns within 48h with amounts far from history."""
    on = sorted([r for r in card_txns if r.get("channel") == "online"], key=_ts)
    for i in range(len(on)):
        grp = [r for r in on[i:] if _ts(r) - _ts(on[i]) <= timedelta(hours=48)][:4]
        if 2 <= len(grp) <= 4 and hist_median > 0:
            if any(float(r["TransactionAmt"]) > 3 * hist_median for r in grp):
                return True, 0.65, [r["TransactionID"] for r in grp]
    return False, 0.15, []


def cnp_new_device(card_txns: list[dict], ident: dict) -> tuple[bool, float, list]:
    """Pattern 3: cnp burst + id_15==New and/or proxy id_23."""
    hit, conf, ids = cnp_burst(card_txns, _median(card_txns))
    if not hit:
        return False, 0.1, []
    new = sum(1 for t in ids if (ident.get(t, {}).get("id_15") or "").strip().lower() == "new")
    proxy = sum(1 for t in ids if (ident.get(t, {}).get("id_23") or "").strip().lower() in ("anonymous", "hidden", "transparent"))
    if new:
        return True, 0.8 if proxy else 0.75, ids
    return True, conf, ids


def out_of_region(card_txns: list[dict], flagged: dict) -> tuple[bool, float, list]:
    """Pattern 4: in-person flagged in region with no history, home activity continues."""
    try:
        home = __import__("collections").Counter(r.get("addr1") for r in card_txns if r.get("channel") == "in_person").most_common(1)[0][0]
    except IndexError:
        return False, 0.1, []
    f_region, f_ch = str(flagged.get("addr1")), flagged.get("channel")
    if f_ch == "in_person" and f_region != str(home):
        same = [r for r in card_txns if str(r.get("addr1")) == f_region and r.get("channel") == "in_person"]
        return (True, 0.7, [r["TransactionID"] for r in same]) if len(same) >= 1 else (False, 0.3, [])
    return False, 0.1, []


def account_takeover(card_txns: list[dict], ident: dict) -> tuple[bool, float, list]:
    """Pattern 5: mixed channels + device/match anomalies in window."""
    ch = {r.get("channel") for r in card_txns}
    if not ({"online", "in_person"} <= ch):
        return False, 0.1, []
    anon = sum(1 for r in card_txns if "anonymous" in str(ident.get(r["TransactionID"], {}).get("id_23", "")).lower())
    newdev = sum(1 for r in card_txns if "new" in str(ident.get(r["TransactionID"], {}).get("id_15", "")).lower())
    if anon + newdev >= 2:
        return True, 0.75, [r["TransactionID"] for r in card_txns[-4:]]
    return False, 0.25, []


def _median(rows):
    import statistics
    a = [float(r["TransactionAmt"]) for r in rows]
    return statistics.median(a) if a else 0.0
