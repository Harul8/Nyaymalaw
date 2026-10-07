"""Express scripted reader proposals through the shipped operation contract."""
from __future__ import annotations

from copy import deepcopy
from functools import wraps


def _fresh_coverage_extents(payload, result):
    """Project offered fixture syntax without repairing a substantive decision."""
    if (payload.get("coverage_extent_contract") != "coverage_source_extents_v1"
            or not isinstance(result, dict) or not isinstance(result.get("coverage"), dict)):
        return
    references = payload.get("source_treatments")
    references = references if isinstance(references, dict) else {}

    def selected(portion, identity):
        if not isinstance(portion, dict) or "extent" in portion:
            return portion
        source = references.get(identity) if isinstance(identity, str) else None
        words = source.get("quoted") if isinstance(source, dict) else None
        if (isinstance(words, str) and bool(words.strip())
                and type(portion.get("start")) is int and type(portion.get("end")) is int
                and portion["start"] == 0 and portion["end"] == len(words)):
            return {**{key: value for key, value in portion.items()
                       if key not in ("start", "end")}, "extent": "whole_source"}
        return {**portion, "extent": "exact_subrange"}

    coverage = result["coverage"]
    checks = coverage.get("source_checks")
    for check in checks if isinstance(checks, list) else ():
        if isinstance(check, dict) and isinstance(check.get("substantive_spans"), list):
            check["substantive_spans"] = [selected(portion, check.get("source_id"))
                                          for portion in check["substantive_spans"]]
    dispositions = coverage.get("dispositions")
    if isinstance(dispositions, list):
        coverage["dispositions"] = [selected(portion, portion.get("source_id"))
                                    if isinstance(portion, dict) else portion
                                    for portion in dispositions]


def _fresh_coverage_groups(payload, result):
    """Group only equivalent, explicitly authored purpose and range judgments.

    No source-owner label, candidate acceptance or representation permission
    supplies a missing judgment. Contradictory and incomplete flat proposals
    stay flat; already grouped proposals are never repaired.
    """
    if (payload.get("coverage_group_contract") != "coverage_source_groups_v1"
            or payload.get("coverage_extent_contract") != "coverage_source_extents_v1"
            or not isinstance(result, dict)):
        return
    coverage = result.get("coverage")
    if (not isinstance(coverage, dict)
            or set(coverage) != {"state", "reason", "source_checks", "dispositions"}):
        return
    checks, portions = coverage["source_checks"], coverage["dispositions"]
    identities = payload.get("coverage_source_ids")
    references = payload.get("source_treatments")
    if (not isinstance(checks, list) or not isinstance(portions, list)
            or not isinstance(identities, list) or not isinstance(references, dict)
            or any(not isinstance(identity, str) for identity in identities)
            or len(identities) != len(set(identities))):
        return
    owned = set(identities)

    def interval(part, identity, fields):
        if not isinstance(part, dict):
            return None
        reference = references.get(identity)
        words = reference.get("quoted") if isinstance(reference, dict) else None
        if not isinstance(words, str) or not words.strip():
            return None
        if part.get("extent") == "whole_source" and set(part) == fields | {"extent"}:
            return 0, len(words)
        if (part.get("extent") == "exact_subrange"
                and set(part) == fields | {"extent", "start", "end"}
                and type(part.get("start")) is int and type(part.get("end")) is int
                and 0 <= part["start"] < part["end"] <= len(words)):
            return part["start"], part["end"]
        return None

    def union(ranges):
        merged = []
        for start, end in sorted(ranges):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        return merged

    by_source = {identity: [] for identity in identities}
    for part in portions:
        if (not isinstance(part, dict) or not isinstance(part.get("source_id"), str)
                or part["source_id"] not in owned
                or not isinstance(part.get("reason"), str)
                or not isinstance(part.get("record_ids"), list)
                or not isinstance(part.get("candidate_ids"), list)
                or any(not isinstance(value, str) for value in
                       [*part["record_ids"], *part["candidate_ids"]])
                or interval(part, part["source_id"], {
                    "source_id", "status", "record_ids", "candidate_ids", "reason"}) is None):
            return
        represented = part.get("status") == "represented"
        if (part.get("status") not in {
                "represented", "missing", "unresolved", "outside_scope", "non_account"}
                or represented != bool(part["record_ids"] or part["candidate_ids"])):
            return
        by_source[part["source_id"]].append(part)
    groups = {}
    for check in checks:
        if (not isinstance(check, dict)
                or set(check) != {"source_id", "content_purpose", "substantive_spans", "reason"}
                or not isinstance(check.get("source_id"), str)
                or check["source_id"] not in owned or check["source_id"] in groups
                or not isinstance(check.get("content_purpose"), str)
                or not isinstance(check.get("reason"), str)
                or not isinstance(check.get("substantive_spans"), list)):
            return
        identity, purpose = check["source_id"], check["content_purpose"]
        selected = by_source[identity]
        group = {"content_purpose": purpose, "reason": check["reason"]}
        if purpose == "account":
            account = [part for part in selected if part["status"] != "non_account"]
            context = [part for part in selected if part["status"] == "non_account"]
            spans = [interval(span, identity, set()) for span in check["substantive_spans"]]
            ranges = [interval(part, identity, {
                "source_id", "status", "record_ids", "candidate_ids", "reason"})
                for part in account]
            contexts = [interval(part, identity, {
                "source_id", "status", "record_ids", "candidate_ids", "reason"})
                for part in context]
            if (not spans or not account or None in spans or union(spans) != union(ranges)
                    or len(spans) != len(set(spans)) and spans != ranges
                    or any(start < other_end and other_start < end
                           for start, end in ranges for other_start, other_end in contexts)):
                return
            group.update(account_portions=[{key: value for key, value in part.items()
                                            if key != "source_id"} for part in account],
                         non_account_portions=[{key: value for key, value in part.items()
                                                if key not in {"source_id", "status",
                                                               "record_ids", "candidate_ids"}}
                                               for part in context])
        elif purpose in {"non_account", "unresolved"}:
            if (check["substantive_spans"] or len(selected) > 1
                    or selected and (selected[0]["status"] != purpose
                                     or selected[0]["extent"] != "whole_source")):
                return
            if selected and selected[0]["reason"] != group["reason"]:
                group["reason"] += "\n" + selected[0]["reason"]
        else:
            return
        groups[identity] = group
    if set(groups) == owned:
        result["coverage"] = {"state": coverage["state"], "reason": coverage["reason"],
                              "source_groups": groups}


def fresh_review_reply(payload, data):
    """Transport only faithful old selections to the explicit fresh wire shape.

    This never creates checks or repairs their ownership, flags, spans or other
    evidence. Contradictory, repeated and malformed selections remain authored
    defects for the production owner to reject.
    """
    result = deepcopy(data)
    original = payload.get("original_input", payload)
    _fresh_coverage_extents(original, result)
    if original.get("review_selection_contract") != "checked_source_selection_v1":
        _fresh_coverage_groups(original, result)
        return result
    rows = result.get("verdicts") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        _fresh_coverage_groups(original, result)
        return result
    candidates = {row["candidate_id"]: row for row in original.get("candidates", [])
                  if isinstance(row, dict) and isinstance(row.get("candidate_id"), str)}
    for row in rows:
        account = row.get("account_check") if isinstance(row, dict) else None
        if not isinstance(account, dict) or "source_ids" not in account:
            continue
        selected, checks = account["source_ids"], account.get("source_checks")
        if (not isinstance(selected, list) or not isinstance(checks, list)
                or any(not isinstance(value, str) or not value for value in selected)
                or any(not isinstance(check, dict)
                       or not isinstance(check.get("source_id"), str)
                       or not check["source_id"] for check in checks)):
            continue
        checked = [check["source_id"] for check in checks]
        if (len(selected) != len(set(selected)) or len(checked) != len(set(checked))
                or set(selected) != set(checked)):
            continue
        identity = row.get("candidate_id")
        if not isinstance(identity, str) or identity not in candidates:
            continue
        candidate = candidates[identity]
        owned = candidate.get("allowed_account_source_ids")
        if (not isinstance(owned, list) or any(not isinstance(value, str) for value in owned)
                or not set(selected) <= set(owned)):
            continue
        del account["source_ids"]
    if original.get("material_source_selection_contract") == "ordered_original_account_support_v1":
        # Project the script's declared source-purpose decisions; this is not
        # classification of the test words or endorsement of producer labels.
        purposes = {}
        ambiguous = set()
        for row in rows:
            for check in row.get("account_check", {}).get("source_checks", []):
                if not isinstance(check, dict) or type(check.get("supplies_account_content")) \
                        is not bool:
                    continue
                identity, purpose = check.get("source_id"), check["supplies_account_content"]
                if identity in purposes and purposes[identity] != purpose:
                    ambiguous.add(identity)
                purposes[identity] = purpose
        coverage = result.get("coverage", {})
        for check in coverage.get("source_checks", []):
            if (isinstance(check, dict)
                    and check.get("content_purpose") in ("account", "non_account")):
                purposes.setdefault(check["source_id"], check["content_purpose"] == "account")
        result.setdefault("source_readings", {
            identity: {"content_role": ("reported_matter_account" if purposes.get(identity)
                                       else "work_instruction" if identity in purposes
                                       else "uncertain"),
                       "reason": "The scripted review's declared original-source purpose."}
            for identity in original.get("source_treatments", {})})
        for row in rows:
            account = row.get("account_check") if isinstance(row, dict) else None
            if not isinstance(account, dict) or "source_ids" in account:
                continue
            candidate = candidates.get(row.get("candidate_id"), {})
            allowed = candidate.get("allowed_account_source_ids", [])
            selections = dict.fromkeys(allowed)
            checks = account.get("source_checks")
            if not isinstance(checks, list):
                continue
            valid = True
            seen = set()
            for check in checks:
                if (not isinstance(check, dict) or "supports_statement" in check
                        or check.get("source_id") not in selections
                        or check.get("source_id") in seen
                        or check.get("source_id") in ambiguous
                        or type(check.get("supplies_account_content")) is not bool
                        or type(check.get("supports_proposal")) is not bool):
                    valid = False
                    break
                selected = {key: value for key, value in check.items() if key not in
                            ("source_id", "supplies_account_content", "supports_proposal")}
                selected["supports_statement"] = check["supports_proposal"]
                if isinstance(selected.get("support_spans"), list):
                    selected["support_spans"] = [
                        {"extent": "exact_subrange", **part} if isinstance(part, dict) else part
                        for part in selected["support_spans"]]
                selections[check["source_id"]] = selected
                seen.add(check["source_id"])
            if valid:
                del account["source_checks"]
                account["source_selections"] = selections
    _fresh_coverage_groups(original, result)
    return result


def reader_repairs(data, schema):
    """Express scripted operation rows under the selected correction schema.

    This is fixture transport only: it does not validate sources or improve
    the supplied proposals. The scripted row order owns each failed field.
    """
    if "repairs" not in schema.get("properties", {}):
        return data
    units = schema["properties"]["repairs"]["properties"]
    cursors = {}
    repaired = {}
    for identity in units:
        field = identity.split(":", 1)[0]
        index = cursors.get(field, 0)
        cursors[field] = index + 1
        rows = data.get(field, [])
        repaired[identity] = {"proposals": rows[index:index + 1]}
    return {"repairs": repaired}


def source_portion_reply(payload, data):
    """Transport explicitly scripted source roles through the fresh portion shape.

    This fixture does not classify words. A scenario owner's positive role
    declares its whole owned passage substantive; a declared non-account role
    has no substantive portion. New semantic tests author narrower ranges
    themselves. Explicit ranges, even malformed ones, are never improved.
    """
    original = payload.get("original_input", payload)
    result = deepcopy(data)
    if original.get("source_selection_contract") != "owned_substantive_spans_v2":
        return result
    if not isinstance(result, dict) or not isinstance(result.get("source_treatments"), dict):
        return result
    catalogue = original.get("original_source_catalogue", {})
    positive = ("reported_matter_account", "reported_party_position", "mixed")
    non_account = ("examination_material", "work_instruction", "nm_interpretation", "uncertain")
    for identity, row in result["source_treatments"].items():
        if not isinstance(row, dict) or "substantive_spans" in row:
            continue
        reference = catalogue.get(identity)
        if (not isinstance(reference, dict) or not isinstance(reference.get("quoted"), str)
                or not reference["quoted"].strip()):
            # Keep foreign/missing owned references as raw invalid output;
            # transport cannot grant provenance to an attack.
            continue
        role = row.get("content_role")
        if role in positive:
            row["substantive_spans"] = [{"start": 0, "end": len(reference["quoted"])}]
        elif role in non_account:
            row["substantive_spans"] = []
    return result


def source_treatment_reply(operation, payload):
    """Script the separately owned source treatment, without keyword inference."""
    if operation != "classify_account_sources":
        return None
    original = payload.get("original_input", payload)
    return source_portion_reply(payload, {"source_treatments": {identity: {
        "content_role": "reported_matter_account",
        "reason": "The scripted source-treatment decision reports account content.",
    } for identity in original["source_ids"]}})


def classified_verifier(function):
    """Supply explicit scripted provenance for direct owning-boundary tests."""
    @wraps(function)
    def called(model, **kwargs):
        if "source_treatments" not in kwargs:
            kwargs["source_treatments"] = scripted_source_treatments(
                kwargs["earlier"], kwargs["latest"])
        return function(model, **kwargs)

    return called


def scripted_source_treatments(earlier, latest, *, roles=None, turn_id="current"):
    """Explicit canonical provenance decisions for offline fixtures."""
    from nm.brain.material import addressed_sources

    _, current, prior = addressed_sources(earlier, latest)
    roles = roles or {}
    rows = {key: {"turn_id": ref.turn_id, "role": ref.role, "quoted": ref.quoted,
                  "content_role": roles.get(key, "reported_matter_account"),
                  "reason": "Scripted treatment"}
            for key, ref in prior.items() if ref.role == "advocate"}
    rows.update({key: {"turn_id": turn_id, "role": "advocate", "quoted": text,
                       "content_role": roles.get(key, "reported_matter_account"),
                       "reason": "Scripted treatment"} for key, text in current.items()})
    return rows


def scripted_support_spans(payload, data, *, scripted_source_account=False):
    """Transport an explicitly declared original-source judgment to owned ranges.

    A scenario owner opts in separately from candidate acceptance or mutation
    authority. Existing source-check booleans declare whether the original
    passage supplies account content; this helper resolves only its full exact
    range. Explicit ranges, foreign sources and malformed judgments stay raw.
    """
    result = deepcopy(data)
    if (not scripted_source_account
            or payload.get("source_support_contract")
            != "independent_original_source_support_v2"):
        return result
    if not isinstance(result, dict) or not isinstance(result.get("verdicts"), list):
        return result
    catalogue = payload.get("source_treatments", {})
    for verdict in result["verdicts"]:
        if not isinstance(verdict, dict):
            continue
        account = verdict.get("account_check")
        if not isinstance(account, dict) or not isinstance(account.get("source_checks"), list):
            continue
        for check in account["source_checks"]:
            if not isinstance(check, dict) or "support_spans" in check:
                continue
            reference = catalogue.get(check.get("source_id"))
            if (not isinstance(reference, dict) or reference.get("role") != "advocate"
                    or not isinstance(reference.get("quoted"), str)
                    or not reference["quoted"].strip()
                    or type(check.get("supplies_account_content")) is not bool):
                continue
            check["support_spans"] = (
                [{"start": 0, "end": len(reference["quoted"])}]
                if check["supplies_account_content"] else [])
    return result


def fixture_disposition(payload, source_id, *, status, record_ids=(), candidate_ids=(),
                        bounds=None, reason="The fixture owner declares this scoped disposition."):
    """Resolve a declared disposition's exact full range; choose no status or owner."""
    if bounds is None:
        reference = payload.get("source_treatments", {}).get(source_id, {})
        words = reference.get("quoted", "") if isinstance(reference, dict) else ""
        bounds = (0, len(words)) if isinstance(words, str) else (0, 0)
    return {"source_id": source_id, "start": bounds[0], "end": bounds[1],
            "status": status, "record_ids": list(record_ids), "candidate_ids": list(candidate_ids),
            "reason": reason}


def fixture_coverage(payload, *, state, source_decisions, dispositions,
                     reason="The fixture owner independently declares whole-source coverage."):
    """Construct v2 coverage from scenario-owned purpose and disposition choices.

    This does not read candidate statements, verdicts, source-owner labels,
    execution receipts or mutation scopes to decide meaning or coverage. Each
    source decision explicitly declares its purpose and may author narrower
    substantive_spans. Invalid choices and intervals remain invalid.
    """
    checks = []
    catalogue = payload.get("source_treatments", {})
    for identity, declared in source_decisions.items():
        choice = {"content_purpose": declared} if isinstance(declared, str) else deepcopy(declared)
        purpose = choice["content_purpose"]
        if "substantive_spans" not in choice:
            reference = catalogue.get(identity, {})
            words = reference.get("quoted", "") if isinstance(reference, dict) else ""
            choice["substantive_spans"] = (
                [{"start": 0, "end": len(words)}]
                if purpose == "account" and isinstance(words, str) else [])
        checks.append({"source_id": identity, **choice,
                       "reason": choice.get(
                           "reason", "The fixture owner declares source purpose.")})
    return {"state": state, "reason": reason, "source_checks": checks,
            "dispositions": deepcopy(dispositions)}


def fixture_representation_choices(payload, reviewed):
    """Resolve potential owned links from explicit checks and current original quotes.

    These are choices for the fixture's coverage owner, not judgments of source
    purpose, completeness or mutation authority. Candidate text supplies no
    truth; an independently scripted positive source check supplies its link.
    Production admission still rejects any proposed owner it does not admit.
    """
    catalogue = payload.get("source_treatments", {})
    choices = {identity: {"record_ids": [], "candidate_ids": []} for identity in catalogue}
    allowed_candidates = set(payload.get("coverage_candidate_ids", ()))
    retained = [{**row.get("decision", {}), "candidate_id": row.get("candidate_id")}
                for row in payload.get("retained_candidate_context", [])
                if isinstance(row, dict) and isinstance(row.get("decision"), dict)]
    for row in [*reviewed.get("verdicts", []), *retained]:
        if not isinstance(row, dict) or row.get("verdict") != "accept":
            continue
        identity = row.get("candidate_id")
        if identity not in allowed_candidates:
            continue
        account = row.get("account_check")
        if not isinstance(account, dict) or account.get("supported") is not True:
            continue
        for check in account.get("source_checks", []):
            if (not isinstance(check, dict)
                    or check.get("supplies_account_content") is not True
                    or check.get("supports_proposal") is not True):
                continue
            source = check.get("source_id")
            if source in choices and identity not in choices[source]["candidate_ids"]:
                choices[source]["candidate_ids"].append(identity)
    allowed_records = set(payload.get("coverage_record_ids", ()))
    for field in ("active_material", "active_disputes"):
        for row in payload.get(field, []):
            if not isinstance(row, dict) or row.get("id") not in allowed_records:
                continue
            references = [{"turn_id": row.get("source_turn_id"), "role": "advocate",
                           "quoted": row.get("quoted")},
                          *[ref for ref in row.get("prior_references", [])
                            if isinstance(ref, dict)]]
            for source, reference in catalogue.items():
                if (isinstance(reference, dict) and reference.get("role") == "advocate"
                        and isinstance(reference.get("quoted"), str)
                        and any(ref.get("role") == "advocate"
                                and ref.get("turn_id") == reference.get("turn_id")
                                and isinstance(ref.get("quoted"), str)
                                and ref["quoted"].strip()
                                and ref["quoted"] in reference["quoted"] for ref in references)
                        and row["id"] not in choices[source]["record_ids"]):
                    choices[source]["record_ids"].append(row["id"])
    return choices


def fixture_scoped_coverage(payload, reviewed, *, source_decisions,
                            representation_choices=None):
    """Resolve owner-declared purposes against independently checked owned links.

    Every purpose is supplied by the scenario author. A non-account or an
    out-of-scope passage receives that explicit disposition; an account with
    no checked owner remains missing. This never classifies source wording.
    """
    choices = fixture_representation_choices(payload, reviewed)
    # Explicit semantic coverage links are authored independently of candidate
    # support permissions. Production still requires actual owned admission.
    choices.update(deepcopy(representation_choices or {}))
    purposes = {}
    dispositions = []
    for identity, declared in source_decisions.items():
        purposes[identity] = "account" if declared == "outside_scope" else declared
        if declared in ("non_account", "outside_scope", "unresolved"):
            dispositions.append(fixture_disposition(payload, identity, status=declared))
        else:
            selected = choices.get(identity, {"record_ids": [], "candidate_ids": []})
            represented = bool(selected["record_ids"] or selected["candidate_ids"])
            dispositions.append(fixture_disposition(
                payload, identity, status="represented" if represented else "missing", **selected))
    state = "partial" if any(row["status"] in ("missing", "unresolved")
                             for row in dispositions) else "complete"
    return fixture_coverage(payload, state=state, source_decisions=purposes,
                            dispositions=dispositions)


def reviewed_record_verdicts(payload, data, *, scripted_full_scope=False,
                             scripted_source_account=False, coverage_judgment=None):
    """Carry explicit offline judgments through the shipped record checks.

    Normal public provider fixtures explicitly opt into full authorised
    coverage independently of candidate count or execution receipts. Direct
    omission/correction fixtures do not opt in; every supplied coverage value,
    including invalid values, is kept. This supplies a scripted judgment,
    never an assessment by production code.
    """
    result = deepcopy(data)
    if not isinstance(result, dict) or not isinstance(result.get("verdicts"), list):
        return result
    if (scripted_full_scope and payload.get("review_scope") is not None
            and "coverage_source_ids" in payload
            and payload.get("coverage_selection_contract") != "owned_account_dispositions_v2"):
        result.setdefault("coverage", {
            "state": "complete", "missing_source_ids": [],
            "reason": ("The normal offline fixture declares the complete authorised "
                       "account scope represented by the supplied records and proposals."),
        })
    candidates = {row["candidate_id"]: row for row in payload.get("candidates", [])}
    for row in result.get("verdicts", []):
        if not isinstance(row, dict) or not isinstance(row.get("candidate_id"), str):
            continue
        candidate = candidates.get(row.get("candidate_id"))
        if candidate is None:
            continue
        accepted = row.get("verdict") == "accept"
        sources = candidate.get("allowed_account_source_ids", [])
        primary = [identity for identity in sources if
                   payload.get("source_treatments", {}).get(identity, {}).get("quoted")
                   == candidate.get("latest_message_passage",
                                    candidate.get("latest_advocate_passage"))]
        row.setdefault("account_check", {
            "content_role": "reported_matter_account" if accepted else "uncertain",
            "supported": accepted, "introduces_legal_analysis": False,
            "source_ids": (primary or sources)[:1] if accepted else [],
            "reason": "The scripted record decision checks the attributed account layer.",
        })
        account = row.get("account_check")
        if isinstance(account, dict) and isinstance(account.get("source_ids"), list):
            account.setdefault("source_checks", [{
                "source_id": source_id,
                "supplies_account_content": True, "supports_proposal": True,
                "reason": "The scripted source decision supplies attributed account content.",
            } for source_id in account["source_ids"]])
        row.setdefault("target_checks", [{
            "target_id": target, "identity_relation": "same_underlying_account",
            "account_preserved": accepted, "required_peer_ids": [],
            "reason": "The scripted operation retains the selected account's identity.",
        } for target in candidate.get("related_dispute_ids",
                                      candidate.get("related_material_ids", []))])
    result = scripted_support_spans(
        payload, result, scripted_source_account=scripted_source_account)
    if (coverage_judgment is not None and "coverage" not in result
            and payload.get("coverage_selection_contract") == "owned_account_dispositions_v2"):
        result["coverage"] = coverage_judgment(payload, deepcopy(result))
    return fresh_review_reply(payload, result)


def reader_operations(rows, payload, *, link_field, infer_targets=True):
    sources = payload.get("original_input", payload)
    known = sources.get("prior_disputes" if link_field == "related_dispute_ids"
                        else "active_material", [])
    new_items = []
    changes = []
    for scripted in rows:
        row = dict(scripted)
        if link_field == "related_material_ids":
            scope = row.pop("matter_scope", "uncertain")
            dispute_ids = row.pop("dispute_ids", [])
            placement = row.pop("placement", None)
            owned = "matter:discussion" if placement == "matter" else "matter:unlinked"
            if "assignment_ids" not in row:
                row["assignment_ids"] = list(dispute_ids) if dispute_ids else [{
                    "current": owned,
                    "proposed": "matter:other" if sources.get("current_matter_id")
                    else owned,
                    "other": "matter:other", "none": "matter:none",
                    "uncertain": "matter:uncertain",
                }.get(scope, f"matter:{scope}")]
        relation = row.pop("relation", "new")
        target_ids = row.pop(link_field, [])
        if relation == "new" and not target_ids:
            new_items.append(row)
            continue
        if not target_ids and infer_targets:
            selected = set(row.get("prior_source_ids", []))
            target_ids = [item["id"] for item in known
                          if selected.intersection(item.get("source_ids", []))]
        changes.append({**row, "relation": relation, link_field: target_ids})
    return {"new_items": new_items, "changes": changes}
