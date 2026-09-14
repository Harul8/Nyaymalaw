"""NOTHING RUNS UNASKED, NOTHING SENDS TWICE, NOTHING NAMES THE OTHER FILE.
BK-58-AC1, BK-58-AC2. P45.

WHAT THESE DEFEND
-------------------
Proactive work is the one capability that acts when nobody is watching, and
each of its three failures is silent:

    WORK NOBODY AUTHORISED. A monitoring job started because a matter existed,
    not because anybody asked -- and the advocate finds out when a message goes
    out on their behalf.

    THE SAME NOTIFICATION TWICE. A due event replayed by a restart, a second
    scheduler or a retried click. The advocate stops reading them.

    THE OTHER CLIENT'S FILE, NAMED. The conflict screen established a clash by
    handing over which other client the party is acting against -- to whoever
    has this file open, which by this release includes a delegate and a locum
    working a handover.

AND THE FOURTH, WHICH IS THE WORST: A CLAIM OF CONTINUOUS MONITORING. An
advocate told "I will watch this" who was not watched is worse off than one
told nothing, because they stopped watching too.
"""
from __future__ import annotations

import pytest
from nm.core.conflict import screen
from nm.core.screens import ScreenState
from nm.core.service import (
    SERVICE_KINDS,
    ServiceJob,
    ServiceRefused,
    cancel,
    idempotency_key,
    job_from_dict,
    put_job,
    record_outcome,
    revoke_reaches,
    schedule,
    watch_report,
)
from nm.domain.operation import Outcome
from nm.domain.service import (
    AuthorityState,
    Notify,
    ServiceAuthority,
    Trigger,
    grant,
    refuse_service,
    revoke,
)

pytestmark = pytest.mark.class_a

TODAY = "2026-09-14"


def _authority(**kw) -> ServiceAuthority:
    base = dict(
        authority_id="sa_1", matter_id="m1",
        responsible_actor="the instructing advocate",
        purpose="remind me before the limitation runs",
        trigger=Trigger.CADENCE, notify=Notify.IN_PRODUCT,
        granted_by="adv_1", granted_at="2026-09-01", cadence="weekly")
    base.update(kw)
    return grant(**base)


def _job(**kw) -> ServiceJob:
    return schedule(_authority(), job_id="sj_1", kind="deadline_reminder",
                    due_on="2026-10-01", today=TODAY, **kw)


# ================= 1. no work without a recorded authority ==================

def test_nothing_is_scheduled_where_nothing_authorises_it():
    """THE BACKLOG'S NEGATIVE CONTROL: *schedule monitoring without
    authority*."""
    with pytest.raises(ServiceRefused, match="nothing authorises"):
        schedule(None, job_id="sj_1", kind="deadline_reminder",
                 due_on="2026-10-01", today=TODAY)


def test_a_partial_authority_authorises_nothing():
    """An authority that does not say what makes the work due is not an
    authority to work whenever we like."""
    bare = ServiceAuthority(authority_id="sa_x", matter_id="m1")
    assert bare.state_on(TODAY) is AuthorityState.NOT_RECORDED
    with pytest.raises(ServiceRefused, match="does not record"):
        schedule(bare, job_id="sj_1", kind="deadline_reminder",
                 due_on="2026-10-01", today=TODAY)


def test_an_authority_cannot_be_granted_incomplete():
    """The state is not a parameter and the record cannot be born empty."""
    with pytest.raises(ValueError, match="a service authority records"):
        grant(authority_id="sa_2", matter_id="m1", responsible_actor="",
              purpose="", trigger=Trigger.NOT_STATED,
              notify=Notify.NOT_STATED, granted_by="", granted_at="")


def test_a_cadence_authority_must_say_how_often():
    with pytest.raises(ValueError, match="how often it runs"):
        _authority(trigger=Trigger.CADENCE, cadence="")


def test_only_granted_permits_work_and_it_is_written_once():
    """Three call sites decide nothing for themselves: scheduling, dispatch
    and result acceptance all read the same property."""
    assert AuthorityState.GRANTED.permits_work is True
    for other in (AuthorityState.REVOKED, AuthorityState.EXPIRED,
                  AuthorityState.NOT_RECORDED):
        assert other.permits_work is False
    assert AuthorityState.not_established() is AuthorityState.NOT_RECORDED


def test_an_expired_authority_stops_scheduling():
    stale = _authority(expires_on="2026-09-10")
    assert stale.state_on(TODAY) is AuthorityState.EXPIRED
    with pytest.raises(ServiceRefused, match="expired"):
        schedule(stale, job_id="sj_1", kind="deadline_reminder",
                 due_on="2026-10-01", today=TODAY)


def test_an_undeclared_kind_of_work_is_refused():
    with pytest.raises(ServiceRefused, match="not a kind of work"):
        schedule(_authority(), job_id="sj_1", kind="phone_the_opponent",
                 due_on="2026-10-01", today=TODAY)
    assert "conflict_recheck" in SERVICE_KINDS


# ================ 2. one due event is one job, however replayed =============

def test_a_replayed_due_event_returns_the_job_that_already_covers_it():
    """THE BACKLOG'S OTHER NEGATIVE CONTROL: *replay the same due event*."""
    first = _job()
    again = schedule(_authority(), job_id="sj_2", kind="deadline_reminder",
                     due_on="2026-10-01", today=TODAY, existing=(first,))
    assert again is first
    assert again.job_id == "sj_1"


def test_the_key_is_about_the_work_and_not_about_when_it_was_attempted():
    a = idempotency_key(matter_id="m1", kind="deadline_reminder",
                        due_on="2026-10-01", authority_id="sa_1")
    b = idempotency_key(matter_id="m1", kind="deadline_reminder",
                        due_on="2026-10-01", authority_id="sa_1")
    assert a == b
    assert a != idempotency_key(matter_id="m1", kind="deadline_reminder",
                                due_on="2026-10-08", authority_id="sa_1")


def test_two_schedulers_that_both_minted_an_id_store_one_job():
    """The store deduplicates BY KEY, not by job id. Otherwise the duplicate
    arrives through the store rather than through the wire."""
    first = _job()
    twin = ServiceJob(job_id="sj_other", matter_id="m1", authority_id="sa_1",
                      kind="deadline_reminder", due_on="2026-10-01",
                      idempotency_key=first.idempotency_key)
    assert len(put_job((first,), twin)) == 1


def test_a_different_matter_is_a_different_job():
    """THE POSITIVE CONTROL on deduplication. A key that collapsed two
    matters would silence one of them."""
    assert idempotency_key(matter_id="m1", kind="deadline_reminder",
                           due_on="2026-10-01", authority_id="sa_1") \
        != idempotency_key(matter_id="m2", kind="deadline_reminder",
                           due_on="2026-10-01", authority_id="sa_1")


# ============ 3. cancellation, revocation, and what asking is not ===========

def test_asking_to_cancel_is_not_cancelling():
    """Work already running is not erased by a cancellation arriving, and
    the record keeps the difference between asked and happened."""
    asked = cancel(_job(), at=TODAY, because="the hearing moved")
    assert asked.outcome is Outcome.CANCEL_REQUESTED
    assert asked.outcome.settled() is False


def test_an_unknown_outcome_cannot_be_cancelled_into_certainty():
    """It may already have reached somebody. Marking it cancelled would say
    it did not."""
    unknown = record_outcome(_job(), outcome=Outcome.UNKNOWN,
                             because="the provider never acknowledged")
    after = cancel(unknown, at=TODAY, because="stop it")
    assert after.outcome is Outcome.UNKNOWN
    assert "settles nothing about what happened" in after.because


def test_a_settled_job_is_not_reopened_by_a_cancellation():
    done = record_outcome(_job(), outcome=Outcome.COMPLETED, receipt="RCT-1")
    assert cancel(done, at=TODAY, because="too late").outcome is Outcome.COMPLETED


def test_revoking_the_authority_stops_every_unsettled_job():
    """BK-58-AC1's cancellation propagation. A revocation that left running
    jobs alone is a cancellation the advocate believes and the queue does
    not."""
    live = _job()
    done = record_outcome(
        schedule(_authority(), job_id="sj_3", kind="hearing_alert",
                 due_on="2026-10-02", today=TODAY),
        outcome=Outcome.COMPLETED, receipt="RCT-9")
    after = revoke_reaches((live, done), authority_id="sa_1", at=TODAY)
    assert after[0].outcome is Outcome.CANCEL_REQUESTED
    assert after[1].outcome is Outcome.COMPLETED


def test_revoking_twice_does_not_rewrite_the_first_record():
    """A retried click must not move the withdrawal date."""
    once = revoke(_authority(), by="adv_1", at="2026-09-12")
    twice = revoke(once, by="adv_2", at="2026-09-13")
    assert twice.revoked_at == "2026-09-12"
    assert twice.revoked_by == "adv_1"


def test_a_revocation_records_who_and_when():
    with pytest.raises(ValueError, match="who withdrew it and when"):
        revoke(_authority(), by="", at=TODAY)


def test_the_authority_is_refused_at_dispatch_as_well_as_at_scheduling():
    """The gap between scheduling and running is exactly where a revoked
    authority keeps sending."""
    from nm.core.service import may_dispatch

    live = _job()
    withdrawn = revoke(_authority(), by="adv_1", at="2026-09-13")
    assert may_dispatch(withdrawn, live, today=TODAY)
    assert may_dispatch(_authority(), live, today=TODAY) == ""


def test_a_result_arriving_after_revocation_is_recorded_and_not_served():
    from nm.core.service import may_accept

    withdrawn = revoke(_authority(), by="adv_1", at="2026-09-13")
    why = may_accept(withdrawn, _job(), today=TODAY)
    assert "withdrawn while this ran" in why
    assert "recorded" in why


# ============ 4. a job that ran is not a message that arrived ==============

def test_completed_without_a_receipt_does_not_claim_delivery():
    """The rule P30 keeps for a filing, at the other end of the product."""
    ran = record_outcome(_job(), outcome=Outcome.COMPLETED)
    assert ran.claims_delivery is False
    assert "whether it reached you is not established" in ran.said()


def test_completed_with_a_receipt_does():
    told = record_outcome(_job(), outcome=Outcome.COMPLETED, receipt="RCT-4")
    assert told.claims_delivery is True


def test_a_lost_acknowledgement_stays_unknown_and_is_not_settled():
    lost = record_outcome(_job(), outcome=Outcome.UNKNOWN,
                          because="the provider never acknowledged")
    assert lost.outcome.settled() is False
    assert lost.outcome.retryable() is False
    assert "has not been sent again" in lost.said()


def test_an_unknown_outcome_with_no_account_of_it_is_refused():
    with pytest.raises(ServiceRefused, match="records what was attempted"):
        record_outcome(_job(), outcome=Outcome.UNKNOWN)


def test_an_unreadable_stored_outcome_reads_as_unknown_not_completed():
    """A job whose record cannot be read is a job nobody can say reached
    anybody."""
    from nm.core.service import job_as_dict

    row = job_as_dict(record_outcome(_job(), outcome=Outcome.COMPLETED,
                                     receipt="RCT-1"))
    row["outcome"] = "probably fine"
    assert job_from_dict(row).outcome is Outcome.UNKNOWN


# ========== 5. BK-58-AC2 -- the clash, without the other client's file ======

class _Party:
    def __init__(self, name, side):
        self.name = name
        self.side = side


class _Parties:
    """The shape `backend/nm/core/parties.Parties` actually has: names as the advocate
    wrote them, lowercased only for matching."""

    def __init__(self, names, matter_id="m1"):
        self.parties = tuple(_Party(n, s) for n, s in names.items())
        self.matter_id = matter_id

    @property
    def named(self):
        return bool(self.parties)

    @property
    def names(self):
        return frozenset(p.name.strip().lower() for p in self.parties)

    def side_of(self, name):
        for p in self.parties:
            if p.name.strip().lower() == name.strip().lower():
                return p.side
        return "related"


class _Thread:
    def __init__(self, parties):
        self.parties = parties
        self.posture = None


class _Matter:
    def __init__(self, mid, title, parties):
        self.id = mid
        self.title = title
        self.threads = (_Thread(parties),)


class _Held(tuple):
    unreadable: tuple = ()


def test_a_clash_is_found_and_the_other_file_is_not_named():
    """THE BACKLOG'S NEGATIVE CONTROL: *introduce an adverse relationship
    after admission* -> *affected work is flagged for review without
    disclosing the other file*."""
    held = _Held((_Matter("m2", "Ramesh v Kiran Steels",
                          {"Kiran Steels": "client"}),))
    got = screen(_Parties({"Kiran Steels": "adverse"}), held, "adv_1")
    assert got.state is ScreenState.BLOCKED
    assert "Kiran Steels" in got.detail
    assert "another of your files" in got.detail
    # THE OTHER FILE'S IDENTITY IS ABSENT, by title and by id.
    assert "Ramesh v Kiran Steels" not in got.detail
    assert "m2" not in got.detail


def test_the_screen_still_says_which_party_and_which_sides():
    """A finding an advocate cannot act on is not protection, it is silence."""
    held = _Held((_Matter("m2", "Other", {"Kiran Steels": "client"}),))
    got = screen(_Parties({"Kiran Steels": "adverse"}), held, "adv_1")
    assert "is adverse here" in got.detail
    assert "client on another of your files" in got.detail


def test_the_same_party_on_the_same_side_is_not_a_clash():
    """THE POSITIVE CONTROL. A returning client is not a conflict, and a
    screen that fired on one would stop being read."""
    held = _Held((_Matter("m2", "Other", {"Kiran Steels": "client"}),))
    got = screen(_Parties({"Kiran Steels": "client"}), held, "adv_1")
    assert got.state is ScreenState.CLEAR


def test_the_watch_report_names_any_line_that_leaked_a_file():
    """SERVED, so a regression is visible on the page and not only in a test.
    The finder is the same one the criterion is about."""
    held = _Held((_Matter("m2", "Ramesh v Kiran", {"Kiran Steels": "client"}),))
    got = screen(_Parties({"Kiran Steels": "adverse"}), held, "adv_1")
    report = watch_report(got, _authority(), today=TODAY)
    assert report["leaks_another_matter"] == []


def test_the_leak_finder_can_see_a_planted_leak():
    """A POSITIVE CONTROL ON THE FINDER. An empty list from a checker that
    always returns one passes identically -- B-049's shape."""
    from nm.core.service import restricted_findings

    assert restricted_findings(
        "Kiran Steels is adverse here and client on 'Ramesh v Kiran'")


# ============ 6. no claim of continuous monitoring, in any state ===========

def test_an_authorised_matter_does_not_claim_continuous_monitoring():
    said = _authority().said(TODAY)
    assert "NOT continuous monitoring" in said
    assert "still yours to watch" in said


def test_an_unauthorised_matter_says_nothing_re_runs_on_their_behalf():
    report = watch_report(None, None, today=TODAY)
    assert report["continuing"] is False
    assert report["owner"] == "NOT RECORDED"
    assert "nothing re-runs it on your behalf" in report["said"]


def test_the_watch_report_names_the_owner_and_the_next_action():
    report = watch_report(None, _authority(), today=TODAY)
    assert report["owner"] == "the instructing advocate"
    assert report["next_action"]
    assert report["continuing"] is True


def test_a_revoked_authority_says_work_is_being_stopped():
    withdrawn = revoke(_authority(), by="adv_1", at="2026-09-13")
    assert "withdrawn" in withdrawn.said(TODAY)
    assert "Nothing further is scheduled" in withdrawn.said(TODAY)


def test_refuse_service_names_what_is_being_refused():
    why = refuse_service(None, today=TODAY, doing="sending a reminder")
    assert "sending a reminder" in why
