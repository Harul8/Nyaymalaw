"""RECEIVING MATERIAL, AND NEVER CLAIMING TO HAVE READ IT. BK-54-AC1. P16.

THE RULE, stated without the exhibit that exposed it
------------------------------------------------------
**A transcript is a machine's reading of audio. It establishes no legal fact,
and no state short of a person's confirmation may be rendered as though it
did.**

Five states, and every pair of neighbours is a distinction somebody will want
to skip. The expensive one is PROCESSED against REVIEWED: a transcript exists,
therefore the product knows what the recording says, therefore the advocate may
rely on it. Each step there is wrong.

WHAT IS ASSERTED
------------------
    an upload is bounded, resumable, and checked on the OBSERVED bytes
    a declared hash that does not match is FAILED_INTEGRITY, never received
    a duplicate completion is idempotent and does not make a second asset
    an overrun is refused rather than resumed
    a cancelled upload stays cancelled
    a part-read exhibit is PARTIALLY_READ and NAMES the pages it lost
    no state establishes a fact, including REVIEWED
    every span locates itself, or it cannot be checked against the original
"""
from __future__ import annotations

import pytest

from nm.domain.intake import (
    Asset,
    AssetState,
    Reading,
    ReadQuality,
    ReceiptState,
    Span,
    UploadSession,
)

pytestmark = pytest.mark.class_a


def _session(size: int = 10, declared_hash: str = "abc") -> UploadSession:
    return UploadSession(upload_id="u1", matter_id="mat_1",
                         actor_id="adv@example.test", declared_size=size,
                         declared_hash=declared_hash,
                         declared_type="application/pdf")


# ============================ bounded and resumable =========================

def test_an_upload_resumes_until_the_declared_size_is_reached():
    """The negative control: a session that never completed would satisfy
    every refusal below and receive nothing."""
    session = _session().receive(b"12345")
    assert session.resumable is True
    assert session.remaining == 5
    assert session.chunks == 1

    session = session.receive(b"67890")
    assert session.resumable is False
    assert session.remaining == 0
    assert session.chunks == 2


def test_an_overrun_is_refused_rather_than_resumed():
    """The declared size is the bound, and a bound that can be exceeded by
    continuing to send is not one."""
    session = _session(size=3).receive(b"toolong")
    assert session.state is ReceiptState.FAILED_INTEGRITY
    assert "the declared size is the bound" in session.note
    assert session.resumable is False


def test_a_completed_session_ignores_further_chunks():
    session = _session().receive(b"1234567890").complete(
        observed_hash="abc", observed_type="application/pdf")
    assert session.state is ReceiptState.RECEIVED
    assert session.receive(b"more") == session


# =============================== integrity ==================================

def test_a_hash_that_does_not_match_is_failed_integrity_and_never_received():
    """A corrupt upload that reads as received is material somebody will
    later rely on."""
    session = _session().receive(b"1234567890").complete(
        observed_hash="a-different-hash", observed_type="application/pdf")
    assert session.state is ReceiptState.FAILED_INTEGRITY
    assert "do not match the hash" in session.note


def test_an_incomplete_upload_is_not_received():
    session = _session().receive(b"123").complete(
        observed_hash="abc", observed_type="application/pdf")
    assert session.state is ReceiptState.FAILED_INTEGRITY
    assert "3 of 10 bytes" in session.note


def test_the_observed_type_is_kept_rather_than_the_declared_one():
    """A client that declares `application/pdf` and sends something else has
    not uploaded a PDF."""
    session = _session(declared_hash="").receive(b"1234567890").complete(
        observed_hash="whatever", observed_type="image/png")
    assert session.state is ReceiptState.RECEIVED
    assert session.observed_type == "image/png"
    assert session.declared_type == "application/pdf"


def test_a_duplicate_completion_is_idempotent():
    """A lost response is the ordinary case and must not become a second
    asset."""
    once = _session().receive(b"1234567890").complete(
        observed_hash="abc", observed_type="application/pdf")
    twice = once.complete(observed_hash="abc", observed_type="application/pdf")
    assert twice == once
    assert twice.chunks == once.chunks


def test_a_cancelled_upload_stays_cancelled():
    session = _session().receive(b"123").cancel("the advocate stopped it")
    assert session.state is ReceiptState.CANCELLED
    assert session.receive(b"456") == session
    assert session.complete(observed_hash="abc",
                            observed_type="x").state is ReceiptState.CANCELLED


def test_a_received_upload_cannot_be_cancelled_afterwards():
    """Cancelling something already received would erase a receipt the
    advocate has been told about."""
    session = _session().receive(b"1234567890").complete(
        observed_hash="abc", observed_type="application/pdf")
    assert session.cancel("too late").state is ReceiptState.RECEIVED


# ========================== partial reading =================================

def test_a_span_must_locate_itself():
    """A derived proposition with no place in the original cannot be checked
    against it."""
    with pytest.raises(ValueError):
        Span(certainty=ReadQuality.CLEAR)


def test_an_uncertain_span_must_say_why():
    """The advocate is otherwise told something is wrong and not what."""
    with pytest.raises(ValueError):
        Span(page=2, certainty=ReadQuality.UNCERTAIN)
    assert Span(page=2, certainty=ReadQuality.UNCERTAIN,
                note="the scan is skewed").said()


def test_a_part_read_exhibit_is_partially_read_and_names_what_it_lost():
    """A forty-page exhibit with two unreadable scans is not 'processed' and
    is not 'failed'. Reporting either loses the two pages."""
    reading = Reading(spans=(
        Span(page=1, certainty=ReadQuality.CLEAR),
        Span(page=2, certainty=ReadQuality.UNREAD, note="the scan is blank"),
        Span(page=3, certainty=ReadQuality.CLEAR)))
    assert reading.state() is AssetState.PARTIALLY_READ
    assert reading.complete is False
    assert reading.gaps == ("page 2 — unread: the scan is blank",)


def test_a_fully_read_exhibit_is_processed():
    """The negative control for the one above."""
    reading = Reading(spans=(Span(page=1, certainty=ReadQuality.CLEAR),))
    assert reading.state() is AssetState.PROCESSED
    assert reading.complete is True
    assert reading.gaps == ()


def test_a_reading_with_no_spans_is_not_assessed_rather_than_complete():
    """`all()` over an empty sequence is True, which would make a reading that
    read nothing the most complete reading in the product."""
    assert Reading().state() is AssetState.NOT_ASSESSED
    assert Reading().complete is False


def test_a_time_span_locates_a_recording():
    span = Span(from_ms=1000, to_ms=4000, certainty=ReadQuality.CLEAR)
    assert "1000" in span.said() and "4000" in span.said()


# ===================== no state establishes a fact ==========================

@pytest.mark.parametrize("state", list(AssetState))
def test_no_asset_state_establishes_a_legal_fact(state):
    """THE POINT OF THE PACKET. Answered by the type rather than left to a
    caller, because the caller who gets it wrong is the one who reads
    PROCESSED and concludes the product knows what the recording says."""
    assert state.establishes_a_fact() is False


def test_the_five_states_are_distinct_values():
    values = {s.value for s in AssetState}
    assert {"uploaded", "admitted", "processed", "partially_read",
            "reviewed"} <= values


def test_what_the_advocate_is_told_never_says_processed_when_it_is_not():
    partly = Asset(asset_id="a1", matter_id="m1",
                   state=AssetState.PARTIALLY_READ,
                   reading=Reading(spans=(
                       Span(page=1, certainty=ReadQuality.CLEAR),
                       Span(page=2, certainty=ReadQuality.UNREAD,
                            note="blank"))))
    assert "read in part" in partly.said()
    assert "page 2" in partly.said()


def test_a_reviewed_asset_says_a_review_establishes_no_fact():
    reviewed = Asset(asset_id="a1", matter_id="m1",
                     state=AssetState.REVIEWED, reviewed_by="adv@example.test")
    assert "establishes no fact" in reviewed.said()
    assert reviewed.as_dict()["establishes_a_fact"] is False


def test_an_uploaded_asset_does_not_claim_to_be_admitted():
    uploaded = Asset(asset_id="a1", matter_id="m1", state=AssetState.UPLOADED)
    assert "not yet admitted" in uploaded.said()


def test_an_unassessed_asset_says_nothing_has_been_assessed():
    assert "nothing has been assessed" in Asset(
        asset_id="a1", matter_id="m1").said()


def test_the_three_read_qualities_include_an_unread_default():
    assert ReadQuality.not_established() is ReadQuality.UNREAD
    assert ReceiptState.not_established() is ReceiptState.NOT_STARTED
    assert AssetState.not_established() is AssetState.NOT_ASSESSED
