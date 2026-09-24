"""Deterministic investigator. Produces HHGOA answer-format JSON. LLM use: zero (tokens=0)."""
from __future__ import annotations
import argparse, csv, json, time
from datetime import date
from pathlib import Path
from .data_loader import Store
from .pattern_detectors import card_testing, cnp_burst, cnp_new_device, out_of_region, account_takeover
from .policy_engine import PolicyEngine
from .retrieval import similar
from .validator import validate

ROOT = Path(__file__).resolve().parents[1]
PATTERN_LABELS = {"card_testing": "card_testing", "cnp": "card_not_present_fraud",
                  "cnp_new": "card_not_present_new_device", "oor": "out_of_region_use",
                  "ato": "account_takeover"}


def prob_from(signals: list[tuple[bool, float]], bank: float, deny: bool, confirm: bool) -> float:
    if confirm:
        return 0.05
    if deny:
        return 0.9
    hits = [c for h, c in signals if h]
    base = max(hits) if hits else 0.2
    # bank score adjusts, never decides alone
    p = 0.7 * base + 0.3 * bank
    return round(min(0.95, max(0.05, p)), 2)


def investigate(case_row: dict, store: Store, eng: PolicyEngine) -> dict:
    t0 = time.time()
    tid, cust = case_row["flagged_txn_id"], case_row["customer_id"]
    trig = case_row["trigger_type"]
    bank = float(case_row["risk_score"] or 0.5)
    flag = store.flagged(tid)
    window = store.card_window(cust, flag["ts"])
    # H4: detectors see only rows up to the flagged txn (no look-ahead)
    before = [r for r in window if r["ts"] <= flag["ts"]]
    ident = {k: v for k, v in store._ident.items()}
    prof = store.device_profile(tid)

    import statistics
    hist = [r for r in before if r["TransactionID"] != tid]
    med = statistics.median([float(r["TransactionAmt"]) for r in hist]) if hist else 0
    ct, cc, ci = card_testing(before)
    cb, bc, bi = cnp_burst(before, med)
    cn, nc, ni = cnp_new_device(before, ident)
    oo, oc, oi = out_of_region(before, flag)
    # account_takeover: the 10 txns ending at the flagged txn
    idx = next((i for i, r in enumerate(before) if r["TransactionID"] == tid), len(before) - 1)
    at, ac, ai = account_takeover(before[max(0, idx - 9): idx + 1], ident)

    # H4: a detector hit must include the flagged txn, otherwise it is ignored
    def anchored(hit, ids):
        return (hit, ids) if (hit and tid in ids) else (False, [])
    ct, ci = anchored(ct, ci)
    cb, bi = anchored(cb, bi)
    cn, ni = anchored(cn, ni)
    oo, oi = anchored(oo, oi)
    at, ai = anchored(at, ai)
    order = [(ct, cc, "card_testing", ci), (cn, nc, "card_not_present_new_device", ni),
             (cb, bc, "card_not_present_fraud", bi), (oo, oc, "out_of_region_use", oi),
             (at, ac, "account_takeover", ai)]
    hits = [(c, l, i) for h, c, l, i in order if h]
    pattern, pconf, aids = (hits[0][1], hits[0][0], hits[0][2]) if hits else ("none", 0.1, [])
    # R7: disputed charge matching own monthly same-product rhythm -> not fraud
    r7 = False
    if trig == "customer_report" and pattern in ("none", "card_not_present_fraud") and window:
        r7_cfg = eng.p["rules"]["R7_disputed_recurring"]
        same = [r for r in window
                if r.get("ProductCD") == flag.get("ProductCD") and r["TransactionID"] != tid]
        med_same = statistics.median([float(r["TransactionAmt"]) for r in same]) if same else 0
        dts = sorted(date.fromisoformat(r["ts"][:10]) for r in same)
        gaps = [(b - a).days for a, b in zip(dts, dts[1:])]
        lo, hi = r7_cfg["gap_days"]
        monthly = len(gaps) >= 2 and all(lo <= g <= hi for g in gaps)
        amt = float(flag["TransactionAmt"])
        r7 = (len(same) >= r7_cfg["min_same"] and monthly and med_same > 0
              and abs(amt - med_same) / med_same < r7_cfg["amount_tol"])
        if r7:
            pattern, pconf, aids = "none", 0.2, []
    # trip guard: 3+ days of in-person activity in flagged region -> trip, not clone
    trip = False
    if pattern == "out_of_region_use":
        days = {r["ts"][:10] for r in window if str(r.get("addr1")) == str(flag.get("addr1"))}
        if len(days) >= eng.p["rules"]["trip_guard"]["min_days"]:
            trip = True
            pattern, pconf, aids = "none", 0.2, []
    # C2: guards DROP signals — probability only sees surviving signals
    dropped = set()
    if r7:
        dropped = {name for _, _, name, _ in order}
    if trip:
        dropped.add("out_of_region_use")
    sigs = [(h, c) for h, c, name, _ in order if h and name not in dropped]
    neighbors = store.device_neighbors(prof, cust)
    shared = len(neighbors) > 0
    # H8: every decision threshold comes from policy.yaml
    rules_cfg = eng.p["rules"]
    r1_max = rules_cfg["R1_verify_before_block"]["max_single_signal_prob"]
    low_lte, high_gte = rules_cfg["stop"]["low_lte"], rules_cfg["stop"]["high_gte"]
    case_open = rules_cfg["case_open_threshold"]
    # H6: one exposure value, computed once — drives case, SAR, and BLOCK route
    fraud_exposure = round(sum(abs(float(store._txn.get(i, flag)["TransactionAmt"]))
                               for i in (aids or [tid])), 2)

    # evidence (deterministic claims)
    ev = [
        {"claim": f"Flagged txn {tid} ${flag['TransactionAmt']} {flag['channel']} region {flag.get('addr1')}, risk {bank}",
         "source": "graph", "ref": "query:flagged_transaction", "entity_ids": [tid]},
        {"claim": f"Card window: {len(window)} txns for {cust} in ±60d; pattern={pattern} conf={pconf}",
         "source": "graph", "ref": "query:card_window", "entity_ids": aids[:6] or [tid]},
        {"claim": f"Device profile '{prof or 'n/a'}' shared with {len(neighbors)} other customer(s)",
         "source": "graph", "ref": "query:device_neighbors", "entity_ids": neighbors[:5]},
    ]

    # initial NBA (before evidence); R5 needs the cleared purchase amount
    p0 = prob_from(sigs, bank, False, False)
    cleared = max((float(store._txn[i]["TransactionAmt"]) for i in ci), default=0.0) if ct else 0.0
    initial = eng.initial(p0, len(hits), pattern, cleared)

    # controlled evidence: customer_validation assumed from trigger
    reqs, settled, deny, confirm = [], False, False, False
    if r7:
        reqs = [{"type": "customer_validation", "asked_after_step": 3,
                 "assumed_response": "Assumed customer disputes but charge matches own recurring pattern (R7)"}]
    elif trig == "customer_report":
        reqs = [{"type": "customer_validation", "asked_after_step": 3,
                 "assumed_response": "Customer denies making the flagged purchase (per case_pack trigger)"}]
        deny, settled = True, True
    elif p0 < r1_max and len(hits) <= 1:
        reqs = [{"type": "customer_validation", "asked_after_step": 3,
                 "assumed_response": "Assumed no reply within 24h (R4) — no data provided"}]

    p1 = prob_from(sigs, bank, deny, confirm)
    if r7:
        p1 = 0.20
        final = [{"action": "CREATE_CASE", "route": "auto", "reason": "R7: disputed recurring pattern"},
                 {"action": "VERIFY_WITH_CUSTOMER", "route": "auto", "reason": "R7"},
                 {"action": "WARN_CUSTOMER", "route": "auto", "reason": "R7: recurring charge reminder, do not block"}]
        verdict, status = "legitimate", "closed_legitimate"
    elif deny:
        verdict, status = "fraud", "closed_fraud"
        final = eng.after_denial(fraud_exposure, shared)
    elif confirm:
        final = eng.after_confirm()
        verdict, status = "legitimate", "closed_legitimate"
    elif p1 <= low_lte:
        final = [{"action": "CLOSE_NO_FRAUD", "route": "auto", "reason": "stop: low probability"},
                 {"action": "GENERATE_REPORT", "route": "auto", "reason": "internal record"}]
        verdict, status = "legitimate", "closed_legitimate"
    elif p1 >= r1_max and hits:
        final = eng.after_denial(fraud_exposure, shared) if deny else [
            {"action": "DECLINE_TRANSACTION", "route": "L1", "reason": f"strong {pattern} signal p={p1}"},
            {"action": "CREATE_CASE", "route": "auto", "reason": "3a: probability >= 0.30"}]
        if deny or p1 >= high_gte:
            verdict, status = "fraud", "closed_fraud"
        else:
            verdict, status = "uncertain", "escalated"
            if eng.r8_escalate(verdict, fraud_exposure, conflicts=True):
                final.append({"action": "ESCALATE_TO_ANALYST", "route": "auto", "reason": "R8: uncertain, exposed or conflicting"})
            final.insert(0, {"action": "VERIFY_WITH_CUSTOMER", "route": "auto", "reason": "R1: confirm before block"})
    else:
        final = initial if not reqs else eng.r4_no_reply(fraud_exposure)
        verdict = "uncertain" if (reqs or p1 >= case_open) else "legitimate"
        status = "escalated" if verdict == "uncertain" else "closed_legitimate"

    # R9/H7: confirmed fraud, no known pattern, shared device across customers
    pattern_description = ""
    r9 = pattern == "none" and verdict == "fraud" and shared
    if r9:
        pattern, pconf = "undocumented", 0.7
        n = len(neighbors) + 1
        dts = [date.fromisoformat(r["ts"][:10]) for r in window]
        span = (max(dts) - min(dts)).days + 1
        amts = [float(r["TransactionAmt"]) for r in window]
        others = ", ".join(neighbors[:3])
        pattern_description = (
            f"{n} customers used device profile '{prof}' within {span} days; "
            f"amounts ${min(amts):.2f}-${max(amts):.2f} across {len(window)} transactions. "
            f"The customer denied flagged txn {tid}, but the activity matches none of the five "
            f"known patterns (no card-testing, CNP, new-device, regional, or takeover signature). "
            f"Found by running all five detectors, then checking device-profile neighbors in the "
            f"graph: {others} share this device — coordinated abuse across customers.")
        if not any(a["action"] == "CREATE_CASE" for a in final):
            final.append({"action": "CREATE_CASE", "route": "auto",
                          "reason": "R9: case for undocumented pattern"})
        if not any(a["action"] == "ESCALATE_TO_ANALYST" for a in final):
            final.append({"action": "ESCALATE_TO_ANALYST", "route": "auto",
                          "reason": "R9: coordinated undocumented pattern"})
        status = "escalated"

    affected = (aids or [tid]) if verdict == "fraud" else []
    exposure = fraud_exposure if verdict == "fraud" else 0.0
    # H7: only a recognised undocumented pattern triggers the R9 coordinated-abuse SAR
    undoc = pattern == "undocumented"
    need_sar, sar_why = eng.sar_needed(verdict, exposure, shared, undoc, p1)
    has_file = any(a["action"] == "FILE_REPORT" for a in final)
    if need_sar and not has_file:
        final.append({"action": "FILE_REPORT", "route": "L2", "reason": sar_why})
    if not need_sar:
        final = [a for a in final if a["action"] != "FILE_REPORT"]

    stop, stop_why = eng.should_stop(p1, len(ev), settled)
    if not stop:
        stop_why = "uncertain single-signal case escalated per R8; further graph steps unlikely to change decision"
        status = "escalated" if verdict == "uncertain" else status

    # R8: uncertain cases escalate when exposed or conflicting, else stay open
    if verdict == "uncertain":
        has_esc = any(a["action"] == "ESCALATE_TO_ANALYST" for a in final)
        if not has_esc and eng.r8_escalate(verdict, fraud_exposure, conflicts=len(hits) > 1):
            final.append({"action": "ESCALATE_TO_ANALYST", "route": "auto",
                          "reason": "R8: uncertain and exposed or conflicting evidence"})
            has_esc = True
        status = "escalated" if has_esc else "open"

    mem = similar(pattern if pattern != "none" else "card_not_present_fraud")
    sar = {"file": need_sar, "reason": sar_why,
           "narrative": "" if not need_sar else
           f"Card {case_row['card_id']} (customer {cust}): {pattern} episode of {len(affected)} txns totaling ${exposure} around {flag['ts'][:10]}, flagged txn {tid} (${flag['TransactionAmt']}, {flag['channel']}). Device profile '{prof or 'n/a'}' shared with {len(neighbors)} other customer(s). Trigger: {trig}. Customer denial assumed from report; sequence inconsistent with history. Suspicious per {sar_why}.",
           "subjects": ([cust, case_row["card_id"]] + neighbors[:3]) if need_sar else [],
           "total_amount_usd": exposure if need_sar else 0,
           "activity_dates": [flag["ts"][:10], flag["ts"][:10]] if need_sar else []}
    return {
        "case_id": case_row["case_id"],
        "case": {"status": status, "verdict": verdict, "fraud_probability": p1, "pattern": pattern,
                 "pattern_description": pattern_description,
                 "affected_txn_ids": affected, "first_suspicious_txn_id": (affected[0] if affected else ""),
                 "connected_card_ids": [], "connected_device_profiles": [prof] if shared and prof else [],
                 "exposure_usd": exposure,
                 "evidence": ev, "similar_prior_cases": mem,
                 "summary": f"{pattern} {verdict} p={p1}; {len(window)}-txn window, device shared with {len(neighbors)} others; trigger {trig}.",
                 "written_to_graph": False, "graph_case_id": ""},
        "evidence_requests": reqs,
        "next_best_actions": {"initial": initial, "final": final,
            "what_changed": "nothing" if final == initial else "evidence assumption updated probability and actions per R2/R4/R8"},
        "sar": sar, "stop_reason": stop_why, "tool_calls": store.calls, "tokens": 0,
        "latency_s": round(time.time() - t0, 1)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="fraud_agent/data/case_pack.csv")
    ap.add_argument("--out", default="fraud_agent/cases")
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    store, eng = Store(), PolicyEngine(ROOT / "policies" / "policy.yaml")
    rows = list(csv.DictReader(open(a.cases)))[:a.limit]
    for r in rows:
        ans = investigate(r, store, eng)
        errs = validate(ans, eng.p, store)
        if errs:
            raise SystemExit(f"{r['case_id']} FAILED validation: " + "; ".join(errs))
        (out / f"{r['case_id']}.json").write_text(json.dumps(ans, indent=2))
        print(r["case_id"], ans["case"]["verdict"], ans["case"]["pattern"], ans["case"]["fraud_probability"], ans["next_best_actions"]["final"])
