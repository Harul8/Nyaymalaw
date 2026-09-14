"""A REHEARSAL IS EVIDENCE ABOUT PEOPLE. P40. BK-85-AC5, BK-88-AC3.

WHAT THESE DEFEND
-------------------
P40 declares its own two expected failures and both are here by name:

    Missing information or absent primary contact does not silently stop the
    required response.

    Evidence includes people/contact results, not just an incident-policy
    document.

The first is a rota whose primary did not answer and whose secondary was never
paged, and a clock left undetermined because nobody had the full picture. The
second is an exercise record with no participants in it, which is what an
incident policy looks like once it has been filed as evidence.

WHAT THIS SUITE CANNOT ESTABLISH
----------------------------------
That any exercise happened. Every record here is a fixture, `participants` is
supplied by the test rather than by people, and `human_execution` on both
criteria stays NOT RUN. What is proved is that the machinery refuses the eleven
ways a rehearsal can be recorded as complete without having been one -- which
is the part a build can prove, and it is not the part that discharges the
criterion.
"""
from __future__ import annotations

import hashlib
import inspect
import pathlib

import pytest

from nm.domain.incident import (
    Applicability,
    Authority,
    Contact,
    Containment,
    CustodyItem,
    Decision,
    Exercise,
    Finding,
    IncidentContractUnreadable,
    NotificationDecision,
    Reached,
    ReportingClock,
    Rota,
    Step,
    Timeline,
    load_clocks,
    projection,
    refuse_close,
)

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIGEST = hashlib.sha256(b"a synthetic exhibit").hexdigest()
PILOT = "cfg-pilot-1"

NOTICED = "2026-09-14T09:00:00+05:30"
DECIDED_IN_TIME = "2026-09-14T12:00:00+05:30"     # 3h
DECIDED_LATE = "2026-09-14T20:00:00+05:30"        # 11h


def _clocks() -> tuple[ReportingClock, ...]:
    return (
        ReportingClock(clock_id="cert_in_initial_report", hours=6,
                       starts_from="noticed_at", instrument="Directions 70B",
                       applicability=Applicability.NOT_DETERMINED),
        ReportingClock(clock_id="dpdp_board_detailed_update", hours=72,
                       starts_from="noticed_at", instrument="Rule 7",
                       applicability=Applicability.NOT_DETERMINED),
    )


def _timeline(**kw) -> Timeline:
    base = dict(occurred_at="2026-09-14T08:00:00+05:30",
                detected_at="2026-09-14T08:45:00+05:30",
                noticed_at=NOTICED,
                assessed_at="2026-09-14T10:00:00+05:30",
                contained_at="2026-09-14T11:00:00+05:30")
    base.update(kw)
    return Timeline(**base)


def _rota(role="incident_commander", primary=Reached.ANSWERED,
          secondary=Reached.NOT_PAGED) -> Rota:
    return Rota(role=role, contacts=(
        Contact(role=role, person_id=f"{role}-primary", order=1,
                reached=primary,
                responded_at=NOTICED if primary is Reached.ANSWERED else ""),
        Contact(role=role, person_id=f"{role}-secondary", order=2,
                reached=secondary,
                responded_at=NOTICED if secondary is Reached.ANSWERED else ""),
    ))


def _decisions(**kw) -> tuple[NotificationDecision, ...]:
    common = dict(decision=Decision.PREPARED_FOR_HUMAN_AUTHORISATION,
                  decided_by="legal-owner", decided_at=DECIDED_IN_TIME,
                  basis="prepared on available information for review",
                  on_available_information=True)
    common.update(kw)
    return tuple(NotificationDecision(clock_id=clock.clock_id, **common)
                 for clock in _clocks())


def _exercise(**kw) -> Exercise:
    base = dict(
        exercise_id="ex-1", scenario_id="unauthorised-export",
        scenario_version=3, conducted_at=NOTICED, timeline=_timeline(),
        configuration_digest=PILOT,
        rotas=(_rota("incident_commander"), _rota("legal_owner")),
        decisions=_decisions(),
        custody=(CustodyItem(item_id="exhibit-1", sha256=DIGEST,
                             held_by="security-owner", held_at=NOTICED,
                             privileged=True),),
        containment=(Containment(action_id="revoke-tokens", taken_at=NOTICED,
                                 authorised_by=Authority.INCIDENT_COMMANDER),),
        findings=(Finding(step_id="page-commander", owner="ops-owner",
                          state=Step.EXECUTED),),
        participants=("incident_commander-primary", "legal_owner-primary"))
    base.update(kw)
    return Exercise(**base)


# ============ 1. the clocks are read, never written into Python ============

def test_the_reviewed_clocks_are_read_from_the_declared_contract():
    """*Do not invent legal notification periods.* Writing six hours into a
    module makes it wrong the moment the review is superseded."""
    clocks = load_clocks(ROOT)
    by_id = {clock.clock_id: clock for clock in clocks}
    assert "cert_in_initial_report" in by_id
    assert "dpdp_board_detailed_update" in by_id
    assert by_id["cert_in_initial_report"].hours == 6
    assert by_id["dpdp_board_detailed_update"].hours == 72
    for clock in clocks:
        assert clock.starts_from == "noticed_at"
        assert clock.instrument.strip()


def test_no_reporting_period_is_written_into_the_module():
    """The population is the module's own source, not one function."""
    from nm.domain import incident

    source = inspect.getsource(incident)
    body = source.split('"""', 2)[-1]
    for invented in ("hours = 6", "hours=6", "hours = 72", "hours=72",
                     "SIX_HOURS", "SEVENTY_TWO"):
        assert invented not in body, invented


def test_the_two_clocks_are_not_interchangeable():
    """One averaged deadline would be wrong in both directions."""
    clocks = load_clocks(ROOT)
    assert len({clock.clock_id for clock in clocks}) == len(clocks)
    assert len({clock.hours for clock in clocks}) == len(clocks)


def test_neither_clock_is_asserted_to_apply():
    """The review records the scope determination as outstanding, and this
    build may not assert a legal duty nobody has established."""
    for clock in load_clocks(ROOT):
        assert clock.applicability is Applicability.NOT_DETERMINED
        assert clock.applicability.is_settled is False
    assert Applicability.not_established() is Applicability.NOT_DETERMINED


def test_an_unreadable_contract_is_a_refusal_and_not_zero_duties(tmp_path):
    """A registry that produced no clocks would let a rehearsal complete
    having reported to nobody."""
    (tmp_path / "docs" / "blueprint").mkdir(parents=True)
    (tmp_path / "docs" / "blueprint" / "evaluations.json").write_text(
        '{"media_contract": {}}', encoding="utf8")
    with pytest.raises(IncidentContractUnreadable):
        load_clocks(tmp_path)
    with pytest.raises(IncidentContractUnreadable):
        load_clocks(tmp_path / "nowhere")


# ==== 1b. the reviewed clock cannot be quietly edited in either direction ===
#
# The domain may not hard-code a legal period, and the DOCUMENT may not be
# edited to a different one either. `blueprint_evaluations` pins the reviewed
# values beside the document's own copy, exactly as MEDIA_PROHIBITED is pinned
# beside prohibited_operations, so changing six hours to eight takes the dated
# applicability review, the document and the checker in one reviewed commit.

def _criteria() -> set[str]:
    from tools.blueprint import load

    _, registry = load(ROOT)
    return {ac["id"] for row in registry["items"]
            for ac in row.get("acceptance") or []}


def _document() -> dict:
    import json

    return json.loads(
        (ROOT / "docs/blueprint/evaluations.json").read_text(encoding="utf-8"))


def _edited(**changes):
    """A deep copy with one field changed, so the real document is untouched."""
    import copy
    import json

    from tools.blueprint_evaluations import check_evaluations

    document = copy.deepcopy(_document())
    block = document["incident_response"]
    before = json.dumps(block, sort_keys=True)
    for path, value in changes.items():
        where = block
        parts = path.split(".")
        for part in parts[:-1]:
            where = where[int(part)] if part.isdigit() else where[part]
        last = parts[-1]
        if last == "pop":
            where.pop()
        else:
            where[int(last) if last.isdigit() else last] = value
    # ASSERT THE MUTATION LANDED before reading the checker's answer.
    assert json.dumps(block, sort_keys=True) != before, changes
    return check_evaluations(document, _criteria())


def test_the_declared_incident_contract_is_accepted_as_written():
    """THE POSITIVE CONTROL. Without it, a checker that refused every document
    would satisfy all four mutations below."""
    from tools.blueprint_evaluations import check_evaluations

    assert check_evaluations(_document(), _criteria()) == []


def test_editing_a_reviewed_reporting_period_is_refused():
    found = _edited(**{"reporting_clocks.0.hours": 8})
    assert any("cert_in_initial_report.hours" in one for one in found), found


def test_asserting_that_an_undetermined_clock_applies_is_refused():
    """This build may not assert a legal duty nobody with standing has
    determined -- not from the domain and not from the document."""
    found = _edited(**{"reporting_clocks.0.applicability": "applies"})
    assert any("applicability" in one for one in found), found


def test_removing_a_reviewed_clock_is_refused():
    found = _edited(**{"reporting_clocks.pop": None})
    assert any("reviewed clock population changed" in one
               for one in found), found


def test_a_document_that_let_a_test_notify_anybody_is_refused():
    found = _edited(**{"exercise.notification_by_a_test": "allowed"})
    assert any("notification_by_a_test" in one for one in found), found


# ====== 2. an absent primary contact does not silently stop anything =======

def test_a_complete_rehearsal_of_the_pilot_closes():
    """THE POSITIVE CONTROL. A machine that refused every exercise would
    satisfy this whole file and no rehearsal could ever be recorded."""
    assert refuse_close(_exercise(), clocks=_clocks(),
                        pilot_digest=PILOT) == ()


def test_a_primary_who_did_not_answer_escalates_to_the_secondary():
    """The criterion's mutation: *an unavailable primary contact.* Answered by
    the secondary is a PASS, because the response is what matters."""
    rota = _rota(primary=Reached.NO_ANSWER, secondary=Reached.ANSWERED)
    assert rota.refuse() == ()
    assert rota.answered.person_id == "incident_commander-secondary"


def test_a_secondary_nobody_paged_is_a_failed_escalation():
    """*Missing information or absent primary contact does not silently stop
    the required response.* NOT_PAGED and NO_ANSWER are opposite findings and
    both read as "nobody came" in a record that stores only the outcome."""
    rota = _rota(primary=Reached.NO_ANSWER, secondary=Reached.NOT_PAGED)
    why = rota.refuse()
    assert why and "never paged" in why[0]
    assert "must not silently stop" in why[0]
    assert Reached.not_established() is Reached.NOT_PAGED


def test_a_role_everybody_was_paged_for_and_nobody_answered_is_named():
    rota = _rota(primary=Reached.NO_ANSWER, secondary=Reached.NO_ANSWER)
    why = rota.refuse()
    assert why and "none answered" in why[0]


def test_a_role_with_an_empty_rota_cannot_be_escalated_to():
    why = Rota(role="legal_owner").refuse()
    assert why and "no contact is listed" in why[0]


# ======== 3. an exercise with nobody in it is a policy document ============

def test_an_exercise_with_no_participants_is_not_a_rehearsal():
    """*Evidence includes people/contact results, not just an incident-policy
    document.*"""
    why = refuse_close(_exercise(participants=()), clocks=_clocks())
    assert any("not a rehearsal of one" in one for one in why)


def test_a_participant_no_rota_records_answering_is_named():
    """`conducted_by_people` is DERIVED. A flag would be set by whoever was
    reading the policy document."""
    exercise = _exercise(participants=("someone-who-was-not-there",))
    assert exercise.conducted_by_people is False
    why = refuse_close(exercise, clocks=_clocks())
    assert any("no rota records them answering" in one for one in why)


# ======== 4. incomplete information is not a reason to prepare nothing =====

def test_a_clock_left_undetermined_with_nothing_prepared_is_refused():
    """The CERT-In FAQ expressly permits an initial report on available
    information with later supplementation."""
    why = refuse_close(
        _exercise(decisions=_decisions(decision=Decision.UNDETERMINED,
                                       on_available_information=False)),
        clocks=_clocks())
    assert any("expressly not a reason to prepare nothing" in one
               for one in why)


def test_undetermined_on_available_information_is_an_honest_state():
    """THE POSITIVE CONTROL on the same rule. A rehearsal that could not reach
    a determination but did prepare on what was known has done the thing."""
    assert refuse_close(
        _exercise(decisions=_decisions(decision=Decision.UNDETERMINED,
                                       on_available_information=True)),
        clocks=_clocks()) == ()


def test_a_clock_nobody_decided_about_is_not_one_that_did_not_apply():
    why = refuse_close(_exercise(decisions=_decisions()[:1]),
                       clocks=_clocks())
    assert any("no recorded decision" in one
               and "dpdp_board_detailed_update" in one for one in why)


def test_undetermined_applicability_may_not_be_recorded_as_no_duty():
    """Treating undetermined as "does not apply" is how a reportable incident
    goes unreported."""
    why = refuse_close(
        _exercise(decisions=_decisions(
            decision=Decision.NOT_APPLICABLE_ON_REVIEWED_SCOPE)),
        clocks=_clocks())
    assert any("undetermined is not a finding of no duty" in one
               for one in why)


def test_a_settled_applicability_may_be_recorded_as_no_duty():
    """THE POSITIVE CONTROL. Once somebody with standing determines the scope,
    the answer is usable -- otherwise the third state is a wall."""
    settled = (ReportingClock(clock_id="cert_in_initial_report", hours=6,
                              starts_from="noticed_at", instrument="70B",
                              applicability=Applicability.DOES_NOT_APPLY),)
    exercise = _exercise(decisions=(NotificationDecision(
        clock_id="cert_in_initial_report",
        decision=Decision.NOT_APPLICABLE_ON_REVIEWED_SCOPE,
        decided_by="counsel", decided_at=DECIDED_IN_TIME,
        basis="the reviewed scope excludes this deployment"),))
    assert refuse_close(exercise, clocks=settled) == ()


# ============ 5. the clock runs from the moment the duty runs from =========

def test_a_decision_after_the_duty_is_reported_with_both_numbers():
    why = refuse_close(
        _exercise(decisions=_decisions(decided_at=DECIDED_LATE)),
        clocks=_clocks())
    assert any("11.0h after noticed_at against a 6h duty" in one
               for one in why)
    assert not any("72h duty" in one for one in why)


def test_an_untimed_clock_is_not_a_met_one():
    """A missing notice time reads as compliant in every check that subtracts
    and shrugs at an error."""
    why = refuse_close(_exercise(timeline=_timeline(noticed_at="unknown")),
                       clocks=_clocks())
    assert any("cannot be timed" in one for one in why)


def test_an_incident_record_with_no_notice_time_is_refused():
    with pytest.raises(ValueError):
        _timeline(noticed_at="   ")


def test_an_open_incident_is_representable():
    """`assessed_at` and `contained_at` are exempt from the blank rule because
    their emptiness is the record's live state."""
    open_now = _timeline(assessed_at="", contained_at="")
    assert open_now.moment("assessed_at") == ""
    assert open_now.hours_from("noticed_at", DECIDED_IN_TIME) == 3.0


# ============ 6. what the record cannot hold, and cannot do ================

def test_a_custody_row_has_no_field_that_takes_client_content():
    """*Never log client content merely to prove the exercise occurred.* A
    habit if it is a sentence; a type error if it is a schema."""
    fields = set(CustodyItem.__dataclass_fields__)
    assert fields == {"item_id", "sha256", "held_by", "held_at", "privileged"}
    assert not fields & {"content", "text", "bytes", "excerpt", "body",
                         "transcript", "quote"}


def test_an_item_nobody_hashed_cannot_be_shown_to_be_the_item_taken():
    for bad in ("", "not-a-digest", DIGEST[:63], DIGEST + "0"):
        with pytest.raises(ValueError):
            CustodyItem(item_id="x", sha256=bad, held_by="o", held_at=NOTICED)


def test_an_exercise_that_preserved_nothing_is_refused():
    why = refuse_close(_exercise(custody=()), clocks=_clocks())
    assert any("nothing preserved" in one for one in why)


def test_a_rehearsal_has_no_state_for_having_notified_anybody():
    """An actual notification is a human-authorised operational act, and a
    suite that could perform one would eventually perform one by accident."""
    assert "SENT" not in {member.name for member in Decision}
    assert not any("sent" in member.value for member in Decision)
    assert Decision.not_established() is Decision.UNDETERMINED


def test_a_finding_carries_a_step_and_an_owner_and_no_prose_about_the_matter():
    fields = set(Finding.__dataclass_fields__)
    assert fields == {"step_id", "owner", "state"}
    with pytest.raises(ValueError):
        Finding(step_id="page-commander", owner="  ")


# ======== 7. containment interrupts somebody's matter, so somebody owns it ==

def test_containment_with_no_recorded_authority_is_refused():
    why = refuse_close(
        _exercise(containment=(Containment(
            action_id="revoke-tokens", taken_at=NOTICED,
            reverses_client_access=True),)),
        clocks=_clocks())
    assert any("records no authority" in one for one in why)
    assert Authority.not_established() is Authority.NOT_RECORDED


def test_a_step_that_was_never_reached_is_not_a_passed_one():
    why = refuse_close(
        _exercise(findings=(Finding(step_id="secure-channel",
                                    owner="ops-owner"),)),
        clocks=_clocks())
    assert any("was never reached" in one and "ops-owner" in one
               for one in why)
    assert Step.not_established() is Step.NOT_REACHED


# ======== 8. BK-88-AC3 -- a foundation run is not the pilot's rehearsal ====

def test_a_foundation_exercise_cannot_be_inherited_as_pilot_proof():
    """BK-88-AC3'S MUTATION: *reuse a foundation fixture or a different
    processor configuration as pilot proof.*"""
    why = refuse_close(_exercise(configuration_digest="cfg-foundation"),
                       clocks=_clocks(), pilot_digest=PILOT)
    assert any("inherited from another one" in one for one in why)


def test_an_exercise_bound_to_no_configuration_is_not_the_pilots():
    """Leaving the field blank is the same substitution with the evidence
    removed rather than mismatched."""
    why = refuse_close(_exercise(configuration_digest=""),
                       clocks=_clocks(), pilot_digest=PILOT)
    assert any("names no configuration" in one for one in why)


def test_without_a_pilot_the_configuration_is_not_demanded():
    """THE NEGATIVE CONTROL on that rule: a foundation rehearsal is a real
    thing to have done, and refusing it as a foundation rehearsal would make
    the distinction meaningless in the other direction."""
    assert refuse_close(_exercise(configuration_digest=""),
                        clocks=_clocks()) == ()


# ================== 9. what the projection tells a reviewer ================

def test_the_projection_says_nothing_was_notified_to_anybody():
    shown = projection(_exercise(), clocks=_clocks())
    assert "human-authorised operational act" in shown["said"]
    assert shown["closed"] is True
    assert shown["conducted_by_people"] is True


def test_the_projection_carries_digests_rather_than_evidence():
    shown = projection(_exercise(), clocks=_clocks())
    assert shown["custody"] == [DIGEST[:12]]
    assert "a synthetic exhibit" not in str(shown)


def test_the_projection_names_the_role_nobody_answered_for():
    exercise = _exercise(rotas=(
        _rota("incident_commander"),
        _rota("legal_owner", primary=Reached.NO_ANSWER,
              secondary=Reached.NO_ANSWER)))
    shown = projection(exercise, clocks=_clocks())
    assert shown["roles"]["legal_owner"] == "nobody answered"
    assert shown["closed"] is False


def test_the_projection_names_the_scenario_version():
    shown = projection(_exercise(), clocks=_clocks())
    assert shown["scenario"] == "unauthorised-export@v3"
