"""Answer-format validator (spec Section 5). Cross-field checks against the
README contract and policy.yaml; callers fail loudly on any error."""
from __future__ import annotations

PATTERNS = {"card_testing", "card_not_present_fraud", "card_not_present_new_device",
            "out_of_region_use", "account_takeover", "undocumented", "none"}
STATUSES = {"open", "closed_fraud", "closed_legitimate", "escalated"}
VERDICTS = {"fraud", "legitimate", "uncertain"}
ROUTES = {"auto", "L1", "L2"}


def validate(ans: dict, policy: dict, store=None) -> list[str]:
    """Return format/cross-field violations for one answer; [] means valid.

    `store` (optional) enables dataset ID-existence and amount checks.
    """
    errs: list[str] = []
    c, sar, nba = ans["case"], ans["sar"], ans["next_best_actions"]
    rules = policy["rules"]
    strong = rules["strong_suspicion_prob"]

    # -- enums (README: pattern values, statuses, verdicts, routes)
    if c["verdict"] not in VERDICTS:
        errs.append(f"verdict {c['verdict']!r} not in {sorted(VERDICTS)}")
    if c["status"] not in STATUSES:
        errs.append(f"status {c['status']!r} not in {sorted(STATUSES)}")
    if c["pattern"] not in PATTERNS:
        errs.append(f"pattern {c['pattern']!r} not in allowed pattern values")

    # -- pattern_description only for 'undocumented' (README Part 1)
    if c["pattern"] == "undocumented" and not (c["pattern_description"] or "").strip():
        errs.append("pattern_description is required when pattern is 'undocumented'")
    if c["pattern"] != "undocumented" and (c["pattern_description"] or "").strip():
        errs.append("pattern_description must be empty unless pattern is 'undocumented'")

    # -- legitimate invariants (README Notes)
    if c["verdict"] == "legitimate":
        if c["affected_txn_ids"]:
            errs.append("legitimate verdict must have empty affected_txn_ids")
        if c["exposure_usd"] != 0:
            errs.append("legitimate verdict must have exposure_usd == 0")
        if sar["file"]:
            errs.append("legitimate verdict must not file a SAR")

    # -- exposure == sum of |amount| over affected_txn_ids (README)
    affected = list(c["affected_txn_ids"])
    first = c["first_suspicious_txn_id"]
    if first and first not in affected:
        errs.append("first_suspicious_txn_id must be one of affected_txn_ids")
    if store is not None:
        for i in affected + ([first] if first else []):
            if i not in store._txn:
                errs.append(f"unknown txn id in answer: {i}")
        if affected and not any(i not in store._txn for i in affected):
            total = round(sum(abs(float(store._txn[i]["TransactionAmt"])) for i in affected), 2)
            if total != c["exposure_usd"]:
                errs.append(f"exposure_usd {c['exposure_usd']} != sum of affected txns {total}")
    if c["verdict"] != "fraud" and c["exposure_usd"] != 0:
        errs.append("exposure_usd must be 0 when verdict != 'fraud'")

    # -- SAR cross-fields (H6/H7 + README SAR rules)
    has_file_action = any(a["action"] == "FILE_REPORT" for a in nba["final"])
    if sar["file"]:
        if c["verdict"] != "fraud" and c["fraud_probability"] < strong:
            errs.append(f"sar.file implies verdict == 'fraud' or p >= strong_suspicion_prob ({strong})")
        cond3a = (c["exposure_usd"] > rules["sar_exposure_gt"]
                  or bool(c["connected_device_profiles"])
                  or c["pattern"] == "undocumented")
        if not cond3a:
            errs.append("sar.file without a 3a condition (exposure>threshold / shared origin / undocumented)")
        if sar["total_amount_usd"] != c["exposure_usd"]:
            errs.append(f"sar.total_amount_usd {sar['total_amount_usd']} != case.exposure_usd {c['exposure_usd']}")
        if not sar.get("narrative"):
            errs.append("sar.file == true requires a narrative")
        if len(sar.get("activity_dates") or []) != 2:
            errs.append("sar.file == true requires activity_dates [first, last]")
        if not has_file_action:
            errs.append("sar.file == true requires FILE_REPORT in next_best_actions.final")
    else:
        if sar.get("narrative") or sar.get("subjects") or sar["total_amount_usd"] != 0 \
                or sar.get("activity_dates"):
            errs.append("sar.file == false requires empty narrative/subjects, total 0, empty dates")
        if has_file_action:
            errs.append("FILE_REPORT in final but sar.file == false")

    # -- action/route checks (policy actions, FILE_REPORT L2, BLOCK route, R1)
    l1_max = rules["block_route"]["l1_max"]
    for phase in ("initial", "final"):
        for a in nba[phase]:
            if a["action"] not in policy["actions"]:
                errs.append(f"unknown action {a['action']!r}")
                continue
            if a["route"] not in ROUTES:
                errs.append(f"route {a['route']!r} not in {sorted(ROUTES)}")
            if a["action"] == "FILE_REPORT" and a["route"] != "L2":
                errs.append("FILE_REPORT route must be L2")
            if a["action"].startswith("BLOCK"):
                want = "L1" if c["exposure_usd"] <= l1_max else "L2"
                if a["route"] != want:
                    errs.append(f"{a['action']} route {a['route']} != policy route {want} "
                                f"for exposure {c['exposure_usd']}")
                r1_max = rules["R1_verify_before_block"]["max_single_signal_prob"]
                if c["verdict"] != "fraud" and c["fraud_probability"] < r1_max \
                        and c["pattern"] != "card_testing":
                    errs.append(f"{a['action']} at p<{r1_max} on non-fraud verdict violates R1 verify-before-block")

    if nba["final"] == nba["initial"] and nba.get("what_changed") != "nothing":
        errs.append("what_changed must be 'nothing' when final == initial")
    if nba["final"] != nba["initial"] and nba.get("what_changed") == "nothing":
        errs.append("what_changed must explain the difference when final != initial")

    # -- graph write honesty: a claimed graph write must carry its vertex id
    if c.get("written_to_graph") is True and not c.get("graph_case_id"):
        errs.append("graph_case_id required when written_to_graph=true")
    return errs
