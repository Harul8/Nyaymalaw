"""Saved legal work has one owner and explicit scope, coverage and freshness."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.conversation import Message
from nm.brain.requirements_state import (
    RESEARCH_VERIFICATION,
    dispute_research_subjects,
    requirements_record,
    research_fingerprint,
    research_owner_id,
    research_record,
    subject_fingerprint,
)
from nm.work_the_file.matter_contracts import Matter

REVISION = "owned-test-corpus:1"
PASSAGE = "Where the agreed condition applies, the stated obligation must be established."


def matter():
    return Matter(id="owned-chat", advocate_id="advocate", title="Pending chat", brain_ready=False)


def subject(file, *, identity="question", kind="request", scope="none",
            purpose="requested_work", records=(), question="Explain the stated condition"):
    return dict(id=identity, kind=kind, owner_id=research_owner_id(file), scope=scope,
                purpose=purpose, question=question, record_ids=list(records))


def finding(*, kind="condition", linked=(), verification=RESEARCH_VERIFICATION):
    source = dict(id="passage-one", kind="provision", title="Test Act", locator="section 2",
                  text=PASSAGE, verification=dict(support_excerpt=PASSAGE,
                      scope_excerpt="Where the agreed condition applies",
                      scope_status="conditional", reason="The finding preserves this condition."))
    if verification in ("research_support_v2", "research_support_v3", "research_support_v4",
                        "research_support_v5", RESEARCH_VERIFICATION):
        source["verification"].update(
            contract=verification, assertion_owner="legislative_text", owner_label="Test Act",
            owner_excerpt=PASSAGE, source_treatment="adopted", treatment_excerpt=PASSAGE)
    if verification in ("research_support_v3", "research_support_v4", "research_support_v5",
                        RESEARCH_VERIFICATION):
        source["verification"].update(assertion_role="legislative_text",
                                      assertion_statement=PASSAGE, context_statements=[])
    row = dict(kind=kind, label="Establish the stated condition", need=PASSAGE,
                why="The passage identifies the condition governing this obligation.",
                force="required" if kind == "gathering" else "none",
                material_ids=list(linked), source_ids=[source["id"]], sources=[source],
                record_status="mentioned" if linked else "not_mentioned")
    if verification in ("research_support_v4", "research_support_v5", RESEARCH_VERIFICATION):
        row["use_verification"] = dict(contract=verification, checks={
            aspect: dict(verdict="supported", reason="The conditional finding preserves its limit.",
                         source_ids=[source["id"]], material_ids=list(linked))
            for aspect in ("entailment", "application", "force")})
    if verification in ("research_support_v5", RESEARCH_VERIFICATION):
        row["use_verification"]["application_premises"] = [{
            "source_id": source["id"],
            "predicate_excerpt": "Where the agreed condition applies",
            "status": "unresolved", "account_references": [],
            "preserved_condition": "Where the agreed condition applies",
            "reason": "The legal condition remains explicit; its application is unresolved.",
        }]
    if verification == RESEARCH_VERIFICATION:
        row["use_verification"]["entailment_basis"] = "source_rule"
    return row


def read(selected, context=(), *, rows=None, state="ok", revision=REVISION,
         verification=RESEARCH_VERIFICATION):
    return dict(subject=deepcopy(selected),
                fingerprint=research_fingerprint(selected, list(context), revision, verification),
                corpus_revision=revision, state=state,
                rows=deepcopy([finding(verification=verification)] if rows is None else rows),
                verification=verification, queries=[selected["question"]],
                diagnostics=[] if state == "ok" else ["Some source coverage is unavailable."],
                coverage=dict(state=state, checked_items=1 if state != "unavailable" else 0,
                              unread_items=0 if state == "ok" else 1, withheld_items=0))


def append(file, reads, *, identity="turn-one", records=(), legacy=None):
    response = dict(turn_id=identity, elements=[], material=deepcopy(list(records)))
    if reads is not None:
        response["research_reads"] = deepcopy(reads)
    if legacy is not None:
        response["requirements_read"] = deepcopy(legacy)
    turn = dict(turn_id=identity, matter_id=str(file.id), advocate_id=file.advocate_id,
                message="An attributed request.", committed=True, release_state="released",
                elements=[], response=response)
    return replace(file, brain_chat=(*file.brain_chat, turn))


def project(file, selected, context=(), *, revision=REVISION,
            verification=RESEARCH_VERIFICATION):
    return research_record(file, subjects=(selected,),
                           material_by_subject={selected["id"]: list(context)},
                           corpus_revision=revision, verification=verification)


def records():
    dispute = dict(id="dispute-one", kind="dispute", label="Contested obligation",
                   statement="A party contests an obligation.",
                   quoted="They contest the obligation.",
                   identification="identified", matter_scope="proposed")
    detail = dict(id="detail-one", kind="evidence", statement="A record is reported.",
                  quoted="I have a record.", basis="stated", importance="relevant",
                  source_turn_id="turn-one", prior_references=[])
    return dispute, detail


def board_inputs():
    dispute, detail = records()
    return (dict(state="ok", rows=[dispute]),
            dict(state="ok", rows=[detail], by_dispute={dispute["id"]: [detail]}, matter=[]))


def test_pending_chat_general_question_is_readable_without_creating_board_or_duplicate_store():
    file = matter()
    selected = subject(file)
    saved = append(file, [read(selected)])
    raw = deepcopy(saved.brain_chat)

    result = project(saved, selected)

    assert result["state"] == "ok"
    assert result["by_subject"][selected["id"]][0]["sources"][0]["text"] == PASSAGE
    assert result["reuse_allowed"][selected["id"]] is True
    assert result["coverage_by_subject"][selected["id"]]["source_freshness"] == "current"
    assert saved.brain_chat == raw
    assert saved.brain_ready is False
    board = requirements_record(saved, disputes=dict(state="ok", rows=[]),
                                material=dict(state="ok", rows=[], matter=[], by_dispute={}))
    assert board["by_dispute"] == {}


@pytest.mark.parametrize("revision,freshness", [
    (None, "unknown"), ("owned-test-corpus:2", "stale")])
def test_old_exact_sources_remain_readable_but_unknown_or_changed_corpus_cannot_reuse(revision,
                                                                                 freshness):
    selected = subject(matter())
    saved = append(matter(), [read(selected)])
    result = project(saved, selected, revision=revision)
    assert result["status_by_subject"][selected["id"]] == "ok"
    assert result["by_subject"][selected["id"]][0]["sources"][0]["text"] == PASSAGE
    assert result["reuse_allowed"][selected["id"]] is False
    assert result["coverage_by_subject"][selected["id"]]["source_freshness"] == freshness


def test_unknown_revision_when_saved_never_counts_as_reusable():
    selected = subject(matter())
    saved = append(matter(), [read(selected, revision=None)])
    result = project(saved, selected, revision=None)
    assert result["by_subject"][selected["id"]]
    assert result["reuse_allowed"][selected["id"]] is False


@pytest.mark.parametrize("state", ["partial", "unavailable"])
def test_local_coverage_failure_retains_sound_peer_without_complete_search_claim(state):
    file = matter()
    first = subject(file)
    second = subject(file, identity="other-question", question="Explain another condition")
    bad_rows = [finding()] if state == "partial" else []
    saved = append(file, [read(first, state=state, rows=bad_rows), read(second)])
    result = research_record(saved, subjects=(first, second),
                             material_by_subject={first["id"]: [], second["id"]: []},
                             corpus_revision=REVISION)
    assert result["state"] == "ok"
    assert result["status_by_subject"][first["id"]] == state
    assert bool(result["by_subject"][first["id"]]) == (state == "partial")
    assert result["reuse_allowed"][first["id"]] is False
    assert result["coverage_by_subject"][first["id"]]["unread_items"] == 1
    assert result["diagnostics_by_subject"][first["id"]]
    assert result["reuse_allowed"][second["id"]] is True


def test_exact_fingerprint_includes_scope_purpose_record_corrections_corpus_and_check_contract():
    file = matter()
    dispute, detail = records()
    selected = subject(file, scope="current", records=(dispute["id"], detail["id"]))
    context = [dispute, detail]
    original = research_fingerprint(selected, context, REVISION)
    assert research_fingerprint({**selected, "id": "later-request"},
                                list(reversed(context)), REVISION) == original
    for changed in ({**selected, "scope": "proposed"}, {**selected, "purpose": "gathering"},
                    {**selected, "question": "Assess a different condition"},
                    {**selected, "owner_id": "another-owned-chat"}):
        assert research_fingerprint(changed, context, REVISION) != original
    corrected = [dispute, {**detail, "statement": "The reported record is corrected."}]
    assert research_fingerprint(selected, corrected, REVISION) != original
    assert research_fingerprint(selected, context, "revision-two") != original
    assert research_fingerprint(selected, context, REVISION, "different-check-contract") != original
    duplicate = deepcopy(detail)
    assert research_fingerprint(selected, [*context, duplicate], REVISION) == original
    duplicate["quoted"] = "Different attributable words."
    with pytest.raises(ValueError, match="conflict"):
        research_fingerprint(selected, [*context, duplicate], REVISION)


@pytest.mark.parametrize("contract", ["research_support_v1", "research_support_v2",
                                      "research_support_v3"])
def test_checked_contract_change_keeps_old_checked_work_readable_without_reuse(contract):
    selected = subject(matter())
    saved = append(matter(), [read(selected, verification=contract)])
    raw = deepcopy(saved.brain_chat)
    result = project(saved, selected)
    assert result["state"] == "ok"
    assert result["by_subject"][selected["id"]]
    assert result["reuse_allowed"][selected["id"]] is False
    coverage = result["coverage_by_subject"][selected["id"]]
    assert coverage["source_freshness"] == "current"
    assert coverage["verification_contract"] == contract
    assert coverage["verification_current"] is False
    assert ("assertion_role" in result["by_subject"][selected["id"]][0]["sources"][0][
        "verification"]) == (contract == "research_support_v3")
    assert saved.brain_chat == raw


def test_equivalent_request_evidence_reuses_without_changing_saved_subject_or_task_identity():
    selected = subject(matter())
    saved = append(matter(), [read(selected)])
    latest = {**selected, "id": "later-request-identity"}
    result = project(saved, latest)
    assert result["reuse_allowed"][latest["id"]] is True
    assert result["read_subject_id_by_subject"][latest["id"]] == selected["id"]
    assert result["source_turn_id_by_subject"][latest["id"]] == "turn-one"
    assert result["subjects"][latest["id"]] == latest
    assert "progress" not in result


def test_record_correction_invalidates_current_research_without_rewriting_old_sources():
    file = matter()
    dispute, detail = records()
    selected = subject(file, scope="current", records=(dispute["id"], detail["id"]))
    saved = append(file, [read(selected, [dispute, detail])], records=[dispute, detail])
    raw = deepcopy(saved.brain_chat)
    corrected = [dispute, {**detail, "statement": "The earlier account has been corrected."}]
    result = project(saved, selected, corrected)
    assert result["state"] == "ok"
    assert result["status_by_subject"][selected["id"]] == "unassessed"
    assert result["by_subject"][selected["id"]] == []
    assert result["reuse_allowed"][selected["id"]] is False
    assert saved.brain_chat == raw


def test_only_dispute_gathering_findings_project_as_board_bullets():
    file = matter()
    disputes, material = board_inputs()
    subjects, contexts = dispute_research_subjects(file, disputes=disputes, material=material)
    selected = subjects[0]
    request = subject(file, identity="request", scope="current",
                      records=selected["record_ids"], question="Assess the reported obligation")
    context = contexts[selected["id"]]
    saved = append(file, [read(selected, context, rows=[finding(kind="gathering",
                                                             linked=("detail-one",)),
                                                     finding(kind="adverse")]),
                          read(request, context)], records=context)
    result = requirements_record(saved, disputes=disputes, material=material,
                                 corpus_revision=REVISION)
    assert result["state"] == "ok"
    assert list(result["by_dispute"]) == [selected["id"]]
    rows = result["by_dispute"][selected["id"]]
    assert [row["kind"] for row in rows] == ["gathering"]
    assert rows[0]["record_status"] == "mentioned"
    assert "verified" not in rows[0]
    assert selected["scope"] == "proposed"
    assert result["source_turn_id_by_dispute"] == {selected["id"]: "turn-one"}


def test_legacy_checked_gathering_is_exact_readable_unknown_freshness_and_not_assessment():
    file = matter()
    disputes, material = board_inputs()
    dispute, detail = records()
    legacy = dict(dispute_id=dispute["id"], fingerprint=subject_fingerprint(dispute, [detail]),
                  state="ok", rows=[finding(kind="gathering", verification="source_support_v4")],
                  verification="source_support_v4",
                  queries=["An earlier search"], diagnostics=[])
    legacy["rows"][0].pop("kind")
    saved = append(file, None, legacy=[legacy], records=[dispute, detail])
    raw = deepcopy(saved.brain_chat)
    result = requirements_record(saved, disputes=disputes, material=material,
                                 corpus_revision=REVISION)
    assert result["state"] == "ok"
    assert result["by_dispute"][dispute["id"]][0]["kind"] == "gathering"
    assert result["coverage_by_dispute"][dispute["id"]] == dict(
        state="ok", purpose="gathering", source_freshness="unknown", reuse_allowed=False,
        legacy=True, verification_contract="source_support_v4", verification_current=False)
    assert result["reuse_allowed"][dispute["id"]] is False
    assert saved.brain_chat == raw


def test_canonical_collection_owns_same_turn_and_never_concatenates_legacy_needs():
    file = matter()
    disputes, material = board_inputs()
    dispute, detail = records()
    legacy = dict(dispute_id=dispute["id"], fingerprint=subject_fingerprint(dispute, [detail]),
                  state="ok", rows=[finding(kind="gathering", verification="source_support_v4")],
                  verification="source_support_v4",
                  queries=[], diagnostics=[])
    saved = append(file, [], legacy=[legacy], records=[dispute, detail])
    result = requirements_record(saved, disputes=disputes, material=material)
    assert result["by_dispute"][dispute["id"]] == []
    assert result["status_by_dispute"][dispute["id"]] == "unassessed"


@pytest.mark.parametrize("damage", ["source_text", "support", "conditional_scope", "source_id",
                                   "unknown_material", "non_gathering_force", "fingerprint"])
def test_corrupt_saved_use_rejects_its_unit_and_preserves_sound_peer(damage):
    file = matter()
    first = subject(file)
    second = subject(file, identity="second", question="Another legal question")
    bad = read(first)
    row = bad["rows"][0]
    if damage == "source_text":
        row["sources"][0]["text"] = ""
    elif damage == "support":
        row["sources"][0]["verification"]["support_excerpt"] = "Not present in the source"
    elif damage == "conditional_scope":
        row["sources"][0]["verification"]["scope_excerpt"] = ""
    elif damage == "source_id":
        row["source_ids"] = [["unhashable"]]
    elif damage == "unknown_material":
        row["material_ids"] = ["another-file-record"]
        row["record_status"] = "mentioned"
    elif damage == "non_gathering_force":
        row["force"] = "required"
    else:
        bad["fingerprint"] = "invalid"
    saved = append(file, [bad, read(second)])
    result = research_record(saved, subjects=(first, second),
                             material_by_subject={first["id"]: [], second["id"]: []},
                             corpus_revision=REVISION)
    assert result["state"] == "incomplete"
    assert result["by_subject"][first["id"]] == []
    assert result["reuse_allowed"][first["id"]] is False
    assert result["status_by_subject"][second["id"]] == "ok"
    assert result["reuse_allowed"][second["id"]] is True


def test_inactive_saved_subject_cannot_introduce_unowned_record_or_other_account_owner():
    file = matter()
    selected = subject(file, scope="current", records=("foreign-record",))
    raw = read(selected, [dict(id="foreign-record", statement="Unowned content")])
    saved = append(file, [raw])
    result = research_record(saved, subjects=(), material_by_subject={})
    assert result["state"] == "incomplete"
    assert "unowned record" in result["diagnostics"][0]
    raw["subject"]["owner_id"] = "another-account"
    saved = append(file, [raw])
    result = research_record(saved, subjects=(), material_by_subject={})
    assert result["state"] == "incomplete"
    assert "authorised owner" in result["diagnostics"][0]


@pytest.mark.parametrize("scope", ["none", "other", "uncertain"])
def test_unresolved_or_other_scope_never_selects_current_matter_records(scope):
    selected = subject(matter(), scope=scope, records=("current-record",))
    with pytest.raises(ValueError, match="subject is unreadable"):
        research_fingerprint(selected, [dict(id="current-record")], REVISION)


def test_inconsistent_released_turn_identity_is_critical_before_research_can_be_used():
    selected = subject(matter())
    saved = append(matter(), [read(selected)])
    saved.brain_chat[0]["response"]["turn_id"] = "another-turn"
    result = project(saved, selected)
    assert result["state"] == "incomplete"
    assert result["by_subject"][selected["id"]] == []
    assert result["reuse_allowed"][selected["id"]] is False


@pytest.mark.parametrize("damage", ["missing_contract", "unknown_contract", "owner",
                                   "owner_excerpt", "treatment", "treatment_excerpt",
                                   "assertion_role", "assertion_statement"])
def test_advertised_current_source_contract_cannot_hide_invalid_role_or_treatment(damage):
    file = matter()
    first = subject(file)
    second = subject(file, identity="peer", question="Another scoped question")
    bad = read(first)
    verification = bad["rows"][0]["sources"][0]["verification"]
    if damage == "missing_contract":
        verification.pop("contract")
    elif damage == "unknown_contract":
        verification["contract"] = "unknown-source-contract"
    elif damage == "owner":
        verification["assertion_owner"] = "party"
    elif damage == "owner_excerpt":
        verification["owner_excerpt"] = "Different words outside this passage."
    elif damage == "treatment":
        verification["source_treatment"] = "rejected"
    elif damage == "assertion_role":
        verification["assertion_role"] = "court_conclusion"
    elif damage == "assertion_statement":
        verification["assertion_statement"] = ""
    else:
        verification["treatment_excerpt"] = ""
    saved = append(file, [bad, read(second)])
    result = research_record(saved, subjects=(first, second),
                             material_by_subject={first["id"]: [], second["id"]: []},
                             corpus_revision=REVISION)
    assert result["state"] == "incomplete"
    assert result["by_subject"][first["id"]] == []
    assert result["coverage_by_subject"][first["id"]]["verification_current"] is False
    assert result["coverage_by_subject"][second["id"]]["verification_current"] is True
    assert result["reuse_allowed"][second["id"]] is True


@pytest.mark.parametrize("field,value", [
    ("owner_excerpt", "Different source words."),
    ("treatment_excerpt", ""),
    ("assertion_owner", "party"),
    ("source_treatment", "reported"),
])
def test_historical_v2_keeps_its_full_original_owner_and_treatment_integrity(field, value):
    selected = subject(matter())
    old = read(selected, verification="research_support_v2")
    old["rows"][0]["sources"][0]["verification"][field] = value

    result = project(append(matter(), [old]), selected)

    assert result["state"] == "incomplete"
    assert result["by_subject"][selected["id"]] == []
    assert result["reuse_allowed"][selected["id"]] is False


@pytest.mark.parametrize("damage", ["missing", "foreign_words", "owner_role", "duplicate"])
def test_current_source_context_is_exact_attributed_and_never_an_independent_authority(damage):
    selected = subject(matter())
    saved_read = read(selected)
    verification = saved_read["rows"][0]["sources"][0]["verification"]
    context = {key: value for key, value in verification.items() if key in (
        "assertion_owner", "assertion_role", "assertion_statement", "owner_label",
        "source_treatment", "support_excerpt", "owner_excerpt", "treatment_excerpt")}
    context["source_treatment"] = "reported"
    verification["context_statements"] = [context]
    sound = project(append(matter(), [saved_read]), selected)
    assert sound["state"] == "ok"
    assert sound["by_subject"][selected["id"]][0]["source_ids"] == ["passage-one"]
    if damage == "missing":
        verification.pop("context_statements")
    elif damage == "foreign_words":
        context["support_excerpt"] = "Different source words."
    elif damage == "owner_role":
        context["assertion_role"] = "party_submission"
    else:
        verification["context_statements"].append(deepcopy(context))

    result = project(append(matter(), [saved_read]), selected)

    assert result["state"] == "incomplete"
    assert result["by_subject"][selected["id"]] == []


def test_historical_exact_readback_survives_new_review_without_status_upgrade_or_mutation():
    from nm.brain.source_snapshots import source_snapshots

    file = matter()
    selected = subject(file)
    historical = read(selected, verification="research_support_v1")
    reference = {**deepcopy(historical["rows"][0]["sources"][0]), "type": "legal"}
    exact_before = source_snapshots([reference])
    saved = append(file, [historical])
    raw = deepcopy(saved.brain_chat)
    result = project(saved, selected)
    assert result["state"] == "ok"
    assert result["reuse_allowed"][selected["id"]] is False
    assert result["coverage_by_subject"][selected["id"]]["verification_current"] is False
    assert source_snapshots([reference]) == exact_before
    assert saved.brain_chat == raw
    reviewed = append(saved, [read(selected)], identity="turn-two")
    current = project(reviewed, selected)
    assert current["reuse_allowed"][selected["id"]] is True
    assert current["coverage_by_subject"][selected["id"]]["verification_current"] is True
    assert current["source_turn_id_by_subject"][selected["id"]] == "turn-two"
    assert reviewed.brain_chat[0] == raw[0]


def test_historical_contract_still_rejects_corrupt_exact_source_ownership():
    selected = subject(matter())
    historical = read(selected, verification="research_support_v1")
    historical["rows"][0]["sources"][0]["verification"]["support_excerpt"] = "Invented words."
    result = project(append(matter(), [historical]), selected)
    assert result["state"] == "incomplete"
    assert result["by_subject"][selected["id"]] == []


@pytest.mark.parametrize("damage", [
    "missing", "old_contract", "rejected_check", "foreign_source", "foreign_material",
    "duplicate_source", "missing_force_source", "established_without_material",
])
def test_current_finding_use_attestation_is_owned_complete_and_cannot_be_source_labels_only(damage):
    file = matter()
    first = subject(file)
    peer = subject(file, identity="peer", question="An independent conditional enquiry")
    damaged = read(first)
    row = damaged["rows"][0]
    checks = row["use_verification"]["checks"]
    if damage == "missing":
        row.pop("use_verification")
    elif damage == "old_contract":
        row["use_verification"]["contract"] = "research_support_v3"
    elif damage == "rejected_check":
        checks["application"]["verdict"] = "unsupported"
    elif damage == "foreign_source":
        checks["entailment"]["source_ids"] = ["another-subject-source"]
    elif damage == "foreign_material":
        checks["application"]["material_ids"] = ["another-subject-record"]
    elif damage == "duplicate_source":
        checks["force"]["source_ids"] *= 2
    elif damage == "missing_force_source":
        checks["force"]["source_ids"] = []
    else:
        row["sources"][0]["verification"]["scope_status"] = "established"
    saved = append(file, [damaged, read(peer)])
    untouched = deepcopy(saved.brain_chat)

    result = research_record(saved, subjects=(first, peer),
                             material_by_subject={first["id"]: [], peer["id"]: []},
                             corpus_revision=REVISION)

    assert result["state"] == "incomplete"
    assert result["by_subject"][first["id"]] == []
    assert result["reuse_allowed"][first["id"]] is False
    assert result["reuse_allowed"][peer["id"]] is True
    assert saved.brain_chat == untouched


def test_historical_v3_keeps_role_and_context_integrity_without_inventing_new_use_checks():
    file = matter()
    selected = subject(file)
    historical = read(selected, verification="research_support_v3")
    assert "use_verification" not in historical["rows"][0]
    saved = append(file, [historical])
    untouched = deepcopy(saved.brain_chat)
    readable = project(saved, selected)
    assert readable["state"] == "ok" and readable["by_subject"][selected["id"]]
    assert readable["coverage_by_subject"][selected["id"]]["verification_current"] is False
    assert readable["reuse_allowed"][selected["id"]] is False
    assert saved.brain_chat == untouched
    historical["rows"][0]["sources"][0]["verification"].pop("context_statements")
    corrupted = project(append(file, [historical]), selected)
    assert corrupted["state"] == "incomplete"
    assert corrupted["by_subject"][selected["id"]] == []


def test_unknown_saved_contract_is_not_treated_as_readable_verified_history():
    selected = subject(matter())
    result = project(append(matter(), [read(selected, verification="unknown-source-contract")]),
                     selected)
    assert result["state"] == "incomplete"
    assert result["by_subject"][selected["id"]] == []


def test_absent_legacy_attestation_is_validated_unverified_history_without_upgrading_sources():
    file = matter()
    disputes, material = board_inputs()
    dispute, detail = records()
    legacy = dict(dispute_id=dispute["id"], fingerprint=subject_fingerprint(dispute, [detail]),
                  state="ok", rows=[finding(kind="gathering", verification="source_support_v4")],
                  queries=["An earlier search"], diagnostics=[])
    legacy["rows"][0].pop("kind")
    saved = append(file, None, legacy=[legacy], records=[dispute, detail])
    raw = deepcopy(saved.brain_chat)
    result = requirements_record(saved, disputes=disputes, material=material,
                                 corpus_revision=REVISION)
    assert result["state"] == "ok"
    assert result["by_dispute"][dispute["id"]] == []
    assert result["status_by_dispute"][dispute["id"]] == "unavailable"
    assert result["coverage_by_dispute"][dispute["id"]]["verification_contract"] is None
    assert result["coverage_by_dispute"][dispute["id"]]["verification_current"] is False
    assert "predate" in result["diagnostics_by_dispute"][dispute["id"]][0]
    assert saved.brain_chat == raw


@pytest.mark.parametrize("active", [True, False])
@pytest.mark.parametrize("tag", ["source_support_v5", "foreign-checker", [], ""])
def test_unknown_advertised_legacy_contract_is_critical_even_when_subject_is_inactive(active, tag):
    file = matter()
    disputes, material = board_inputs()
    dispute, detail = records()
    legacy = dict(dispute_id=dispute["id"], fingerprint=subject_fingerprint(dispute, [detail]),
                  state="ok", rows=[finding(kind="gathering", verification="source_support_v4")],
                  verification=tag, queries=["An earlier search"], diagnostics=[])
    legacy["rows"][0].pop("kind")
    saved = append(file, None, legacy=[legacy], records=[dispute, detail])
    if active:
        result = requirements_record(saved, disputes=disputes, material=material,
                                     corpus_revision=REVISION)
        assert result["by_dispute"][dispute["id"]] == []
        assert result["reuse_allowed"][dispute["id"]] is False
    else:
        result = research_record(saved, subjects=(), material_by_subject={},
                                 corpus_revision=REVISION)
    assert result["state"] == "incomplete"
    assert result["diagnostics"]


def test_absent_legacy_attestation_cannot_mask_malformed_exact_source():
    file = matter()
    disputes, material = board_inputs()
    dispute, detail = records()
    legacy = dict(dispute_id=dispute["id"], fingerprint=subject_fingerprint(dispute, [detail]),
                  state="ok", rows=[finding(kind="gathering", verification="source_support_v4")],
                  queries=["An earlier search"], diagnostics=[])
    legacy["rows"][0].pop("kind")
    legacy["rows"][0]["sources"][0]["verification"]["support_excerpt"] = "Invented source."
    result = requirements_record(append(file, None, legacy=[legacy], records=[dispute, detail]),
                                 disputes=disputes, material=material, corpus_revision=REVISION)
    assert result["state"] == "incomplete"
    assert result["by_dispute"][dispute["id"]] == []
    assert all("predate" not in problem for problem in result["diagnostics"])


def account_finding(turn_id, quoted):
    row = finding()
    row["use_verification"]["application_premises"][0].update(
        status="reported_satisfied", account_references=[{
            "turn_id": turn_id, "role": "advocate", "quoted": quoted,
        }])
    return row


@pytest.mark.parametrize("origin", ["current", "earlier_brain", "earlier_legacy"])
def test_application_account_words_are_exact_on_readback_without_rewriting_sources(origin):
    file = matter()
    selected = subject(file)
    prior = ()
    if origin == "current":
        source_turn = "turn-one"
    elif origin == "earlier_brain":
        file = append(file, [], identity="turn-earlier")
        source_turn = "turn-earlier"
    else:
        source_turn = "turn-legacy"
        prior = (Message(source_turn, "advocate", "An attributed request."),
                 Message(source_turn, "nm", "The earlier response is not account evidence."))
    saved = append(file, [read(selected, rows=[account_finding(
        source_turn, "attributed request")])])
    untouched = deepcopy(saved.brain_chat)

    result = research_record(saved, subjects=(selected,),
                             material_by_subject={selected["id"]: []},
                             corpus_revision=REVISION, prior_conversation=prior)

    assert result["state"] == "ok" and result["reuse_allowed"][selected["id"]] is True
    assert result["by_subject"][selected["id"]][0]["use_verification"][
        "application_premises"][0]["account_references"][0]["quoted"] == "attributed request"
    assert saved.brain_chat == untouched


@pytest.mark.parametrize("damage", ["unknown_turn", "foreign_words", "wrong_order",
                                   "future_turn", "nm_role", "malformed"])
def test_invalid_account_reference_rejects_its_read_and_preserves_valid_peer(damage):
    file = matter()
    selected = subject(file)
    peer = subject(file, identity="peer", question="A separate scoped enquiry")
    bad = read(selected, rows=[account_finding("turn-one", "An attributed request.")])
    reference = bad["rows"][0]["use_verification"]["application_premises"][0][
        "account_references"][0]
    if damage == "unknown_turn":
        reference["turn_id"] = "another-matter-turn"
    elif damage == "foreign_words":
        reference["quoted"] = "A fact never stated in this file."
    elif damage == "wrong_order":
        reference["quoted"] = "request. attributed An"
    elif damage == "future_turn":
        reference["turn_id"] = "turn-two"
    elif damage == "nm_role":
        reference["role"] = "nm"
    else:
        reference["quoted"] = []
    saved = append(file, [bad, read(peer)])
    if damage == "future_turn":
        saved = append(saved, [], identity="turn-two")
    raw = deepcopy(saved.brain_chat)
    # Passing the full canonical transcript must not make later brain turns
    # available to an earlier saved research read.
    complete = tuple(Message(turn["turn_id"], "advocate", turn["message"])
                     for turn in saved.brain_chat)

    result = research_record(saved, subjects=(selected, peer),
                             material_by_subject={selected["id"]: [], peer["id"]: []},
                             corpus_revision=REVISION, prior_conversation=complete)

    assert result["state"] == "incomplete"
    assert result["by_subject"][selected["id"]] == []
    assert result["reuse_allowed"][selected["id"]] is False
    assert result["reuse_allowed"][peer["id"]] is True
    assert saved.brain_chat == raw


def test_supplied_transcript_cannot_override_canonical_saved_brain_words():
    file = matter()
    selected = subject(file)
    saved = append(file, [read(selected, rows=[account_finding(
        "turn-one", "Altered account words.")])])
    supplied = (Message("turn-one", "advocate", "Altered account words."),)

    result = research_record(saved, subjects=(selected,),
                             material_by_subject={selected["id"]: []},
                             corpus_revision=REVISION, prior_conversation=supplied)

    assert result["state"] == "incomplete" and result["by_subject"][selected["id"]] == []


def test_board_research_uses_authorised_earlier_account_words():
    file = matter()
    disputes, material = board_inputs()
    subjects, contexts = dispute_research_subjects(file, disputes=disputes, material=material)
    selected = subjects[0]
    row = account_finding("turn-legacy", "The condition is reported.")
    row.update(kind="gathering", force="required")
    saved = append(file, [read(selected, contexts[selected["id"]], rows=[row])],
                   records=contexts[selected["id"]])
    prior = (Message("turn-legacy", "advocate", "The condition is reported."),)

    result = requirements_record(saved, disputes=disputes, material=material,
                                 corpus_revision=REVISION, prior_conversation=prior)

    assert result["state"] == "ok"
    assert result["by_dispute"][selected["id"]][0]["label"] == row["label"]


@pytest.mark.parametrize("contract", ["research_support_v4", "research_support_v5"])
def test_historical_research_is_readable_without_inventing_stronger_checks(contract):
    file = matter()
    selected = subject(file)
    old = read(selected, verification=contract)
    saved = append(file, [old])
    untouched = deepcopy(saved.brain_chat)

    result = project(saved, selected)

    assert result["state"] == "ok" and result["by_subject"][selected["id"]]
    assert result["reuse_allowed"][selected["id"]] is False
    assert result["coverage_by_subject"][selected["id"]]["verification_current"] is False
    check = result["by_subject"][selected["id"]][0]["use_verification"]
    assert ("application_premises" in check) is (contract == "research_support_v5")
    assert "entailment_basis" not in check
    assert saved.brain_chat == untouched
