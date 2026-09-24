"""Rule tests — spec finding H9: one test per policy rule R1..R10,
asserting exact action lists and approval routes (README Section 3).
"""
from test_agent_flow import POLICY, PolicyEngine, StubStore, case, txn
from test_agent_flow import BASE
from test_answer_validator import cnp_burst_rows, h7_rows, r7_rows

from fraud_agent.src.agent import investigate

ENG = PolicyEngine(POLICY)


def pairs(actions):
    return [(a["action"], a["route"]) for a in actions]


def test_r1_verify_before_block_single_weak_signal():
    acts = ENG.initial(0.45, 1, "none")
    assert pairs(acts) == [
        ("VERIFY_WITH_CUSTOMER", "auto"),
        ("STEP_UP_AUTH", "auto"),
        ("CREATE_CASE", "auto"),
    ]
    assert not any(a["action"].startswith("BLOCK") for a in acts)


def test_r2_customer_denies_routes_by_exposure():
    # exposure <= $2,500 -> L1, no report under $1,000 and no shared origin
    assert pairs(ENG.after_denial(200, False)) == [
        ("BLOCK_CARD", "L1"), ("CREATE_CASE", "auto")]
    # exposure > $2,500 -> L2 and report required (exposure > $1,000)
    assert pairs(ENG.after_denial(3000, False)) == [
        ("BLOCK_CARD", "L2"), ("CREATE_CASE", "auto"), ("FILE_REPORT", "L2")]
    # shared origin forces the report even below $1,000 (also R6)
    assert pairs(ENG.after_denial(200, True)) == [
        ("BLOCK_CARD", "L1"), ("CREATE_CASE", "auto"),
        ("FILE_REPORT", "L2"), ("MONITOR_CONNECTED_CARDS", "auto")]


def test_r3_customer_confirms():
    assert pairs(ENG.after_confirm()) == [("CLOSE_NO_FRAUD", "auto")]


def test_r4_no_reply_escalates_only_over_500():
    # within $500: monitor + decline only
    assert pairs(ENG.r4_no_reply(100)) == [
        ("MONITOR_CARD", "auto"), ("DECLINE_TRANSACTION", "L1")]
    # over $500: add escalation
    assert pairs(ENG.r4_no_reply(600)) == [
        ("MONITOR_CARD", "auto"), ("DECLINE_TRANSACTION", "L1"),
        ("ESCALATE_TO_ANALYST", "auto")]


def test_r5_card_testing_actions_and_cleared_block():
    # decline + step-up when nothing large cleared yet
    assert pairs(ENG.initial(0.9, 3, "card_testing", cleared=50)) == [
        ("DECLINE_TRANSACTION", "L1"), ("STEP_UP_AUTH", "auto")]
    # purchase over $100 already cleared -> block too (route by exposure)
    assert pairs(ENG.initial(0.9, 3, "card_testing", cleared=150)) == [
        ("DECLINE_TRANSACTION", "L1"), ("STEP_UP_AUTH", "auto"),
        ("BLOCK_CARD", "L1")]
    assert pairs(ENG.initial(0.9, 3, "card_testing", cleared=3000)) == [
        ("DECLINE_TRANSACTION", "L1"), ("STEP_UP_AUTH", "auto"),
        ("BLOCK_CARD", "L2")]


def test_r6_shared_origin_reports_and_monitors():
    acts = ENG.after_denial(50, True)
    assert ("FILE_REPORT", "L2") in pairs(acts)
    assert ("MONITOR_CONNECTED_CARDS", "auto") in pairs(acts)
    assert ("CREATE_CASE", "auto") in pairs(acts)


def test_r7_disputed_recurring_do_not_block():
    ans = investigate(case("100", "customer_report"),
                      StubStore(r7_rows()), ENG)
    assert ans["case"]["verdict"] == "legitimate"
    assert pairs(ans["next_best_actions"]["final"]) == [
        ("CREATE_CASE", "auto"),
        ("VERIFY_WITH_CUSTOMER", "auto"),
        ("WARN_CUSTOMER", "auto"),
    ]


def test_r8_escalate_when_uncertain_and_exposed_or_conflicting():
    assert ENG.r8_escalate("uncertain", 600, conflicts=False) is True
    assert ENG.r8_escalate("uncertain", 100, conflicts=False) is False
    assert ENG.r8_escalate("uncertain", 100, conflicts=True) is True
    assert ENG.r8_escalate("fraud", 600, conflicts=True) is False
    # integration: $1080 uncertain episode keeps ESCALATE, status escalated
    ans = investigate(case("100", "risk_score"), StubStore(cnp_burst_rows()), ENG)
    assert ans["case"]["verdict"] == "uncertain"
    assert ans["case"]["status"] == "escalated"
    assert ("ESCALATE_TO_ANALYST", "auto") in pairs(ans["next_best_actions"]["final"])
    # small unconfirmed episode: uncertain but unexposed -> stays open, no escalate
    from datetime import timedelta
    rows = [
        txn(1, BASE - timedelta(days=40), 30, "in_person", "225"),
        txn(2, BASE - timedelta(days=35), 25, "in_person", "225"),
        txn(10, BASE - timedelta(days=3), 60, "online", "444"),
        txn(11, BASE - timedelta(days=2), 70, "online", "444"),
        txn(12, BASE - timedelta(days=1), 80, "online", "444"),
        txn(100, BASE, 55, "in_person", "444"),
    ]
    ans = investigate(case("100", "risk_score"), StubStore(rows), ENG)
    assert ans["case"]["verdict"] == "uncertain"
    assert ans["case"]["status"] == "open"
    assert ("ESCALATE_TO_ANALYST", "auto") not in pairs(ans["next_best_actions"]["final"])


def test_r9_undocumented_pattern_gets_report():
    # engine gate: coordinated/undocumented fraud -> SAR required, cites R9
    need, why = ENG.sar_needed("fraud", 50, False, True, 0.9)
    assert need is True and "R9" in why
    # small known-pattern fraud without shared origin stays case-only
    assert ENG.sar_needed("fraud", 50, False, False, 0.9) == (
        False, "3a: case only, below report thresholds")


def test_r10_block_all_requires_two_confirmed_cards():
    assert ENG.p["rules"]["R10_block_all"]["min_confirmed_cards"] == 2
    # with < 2 confirmed connected cards, BLOCK_ALL_CARDS must never appear
    for rows, c in [(h7_rows(), case("100", "customer_report")),
                    (cnp_burst_rows(), case("100", "risk_score")),
                    (r7_rows(), case("100", "customer_report"))]:
        ans = investigate(c, StubStore(rows), ENG)
        assert ("BLOCK_ALL_CARDS", "auto") not in pairs(ans["next_best_actions"]["initial"])
        assert ("BLOCK_ALL_CARDS", "L2") not in pairs(ans["next_best_actions"]["final"])
