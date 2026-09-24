"""Detector tests — spec findings C1, H5, H4. Synthetic rows only (no big CSVs)."""
from datetime import datetime, timedelta

from fraud_agent.src.pattern_detectors import card_testing, cnp_burst, cnp_new_device

BASE = datetime(2016, 7, 1, 12, 0, 0)


def txn(pid, offset_min, amt, channel="online", addr1="225"):
    return {
        "TransactionID": str(pid),
        "ts": (BASE + timedelta(minutes=offset_min)).strftime("%Y-%m-%d %H:%M:%S"),
        "TransactionAmt": str(amt),
        "channel": channel,
        "addr1": addr1,
        "ProductCD": "W",
        "customer_id": "C00001",
    }


def cnp_burst_rows():
    """4 online txns within 48h; one amount far above the rest -> cnp_burst fires."""
    return [txn(1, 0, 10), txn(2, 30, 10), txn(3, 60, 10), txn(4, 90, 1000)]


# --- C1: cnp_new_device must not fire without device evidence -----------------

def test_c1_no_identity_evidence_no_hit():
    rows = cnp_burst_rows()
    hit, conf, ids = cnp_new_device(rows, {})
    assert hit is False, "C1: burst alone must not be labelled new-device fraud"
    assert ids == []
    # the underlying burst is real, so cnp_burst must still fire (label falls back)
    assert cnp_burst(rows, 10.0)[0] is True


def test_c1_new_device_hits():
    ident = {str(i): {"id_15": "New"} for i in "1234"}
    hit, conf, ids = cnp_new_device(cnp_burst_rows(), ident)
    assert hit is True and conf == 0.75 and len(ids) == 4


def test_c1_new_and_proxy_is_stronger():
    ident = {str(i): {"id_15": "New", "id_23": "anonymous"} for i in "1234"}
    hit, conf, _ = cnp_new_device(cnp_burst_rows(), ident)
    assert hit is True and conf == 0.8


def test_c1_proxy_only_still_hits():
    ident = {str(i): {"id_23": "transparent"} for i in "1234"}
    hit, conf, _ = cnp_new_device(cnp_burst_rows(), ident)
    assert hit is True and conf == 0.75


# --- H5: a large first purchase is not a card test ---------------------------

def test_h5_large_first_purchase_not_a_test():
    rows = [txn(1, 0, 900), txn(2, 10, 1), txn(3, 20, 1), txn(4, 120, 50)]
    hit, _, ids = card_testing(rows)
    assert hit is False, "H5: $900 must not count toward the 3-small-auth sequence"
    assert ids == []


def test_h5_three_small_then_large_hits():
    rows = [txn(1, 0, 1), txn(2, 10, 2), txn(3, 20, 1), txn(4, 90, 80)]
    hit, conf, ids = card_testing(rows)
    assert hit is True and conf == 0.85
    assert len(ids) == 4


def test_h5_small_sequence_must_fit_window():
    # $1, $2 span 90 minutes > 60 min R5 window
    rows = [txn(1, 0, 1), txn(2, 90, 2), txn(3, 95, 1), txn(4, 120, 80)]
    hit, _, _ = card_testing(rows)
    assert hit is False
