"""EVERY FIELD ON THE RECORD REACHES THE MODEL, or says why it does not.

WHY THIS EXISTS
-----------------
B-091 asked which fields on the persisted record nothing WRITES. This asks the
other half: which fields the record HOLDS and the model is never TOLD. Both
walk the same closure; only the second one answers "does this product actually
use what it remembers".

The first two members were found one at a time, by hand, and each was a real
defect that reached — or was about to reach — an advocate:

    B-092  `Posture.opponent`      no producer; the board said "unknown"
                                   forever while the advocate had named them
    B-093  `Provenance.document`   a document's content was handed to every
                                   model call as the advocate's own claim

A population discovered one member at a time has no enumerator. This is it.

WHY THIS ONE COULD NOT BE SETTLED BY A SWEEP ALONE
----------------------------------------------------
Unlike B-091, "should this field be told?" is not mechanical. The account has
a MEASURED character budget (`ACCOUNT_BUDGET`, 3000) and every marker added is
paid for in facts that then do not fit — the trade B-085 exists to make
visible. So the sweep does not decide; it forces the decision to be WRITTEN
DOWN, and refuses a field that is neither told nor declared.

THE DECISIONS, AND THE REASONING FOR EACH
--------------------------------------------
TOLD:
  `Fact.basis` + `basis_source`  its own docstring: "the difference decides
                                 what has to be proved and by whom"
  `Fact.certainty`               `documented` is the ADVOCATE saying a
                                 document evidences this, which is not what
                                 `_source` renders and matters to a limitation
  `Posture.opponent`             B-092
  `Posture.client_described_as`  once per thread, a dozen characters
  `Provenance.document` + `page` B-093

WITHHELD, each with the reason and the condition that reopens it — see
`WITHHELD` below.
"""
from __future__ import annotations

import dataclasses
import datetime
import enum
import typing

import pytest

from nm.work_the_file.matter_contracts import (
    Matter,
    Provenance,
)

pytestmark = pytest.mark.class_a

SAID = Provenance(kind="advocate_statement", turn="t1")
STATEMENT = "the agreement was registered"


# ============================== the population ==============================

def _parts(annotation):
    yield annotation
    for arg in typing.get_args(annotation):
        yield from _parts(arg)


def _closure() -> tuple[type, ...]:
    seen: dict[type, None] = {}

    def walk(t) -> None:
        if not (isinstance(t, type) and dataclasses.is_dataclass(t)):
            return
        if t in seen:
            return
        seen[t] = None
        for annotation in typing.get_type_hints(t).values():
            for part in _parts(annotation):
                walk(part)

    walk(Matter)
    return tuple(seen)


def content_fields() -> tuple[str, ...]:
    """The scalars that could carry CONTENT.

    Containers are the structure of the record and are obviously carried —
    the account IS the facts. What can be silently lost is a scalar sitting
    on one of them.
    """
    out: list[str] = []
    for t in _closure():
        hints = typing.get_type_hints(t)
        for f in dataclasses.fields(t):
            annotation = hints[f.name]
            if typing.get_origin(annotation) in (tuple, list, dict):
                continue
            args = [a for a in typing.get_args(annotation)
                    if a is not type(None)]
            base = args[0] if args else annotation
            if base in (str, bool, int, datetime.date) or (
                    isinstance(base, type) and issubclass(base, enum.Enum)):
                out.append(f"{t.__name__}.{f.name}")
    return tuple(out)


# ========================= the declared withholdings ========================

WITHHELD: dict[str, str] = {
    "Matter.last_activity":
        "WHEN the file was last worked is a fact about the ADVOCATE'S "
        "diary, not about the dispute. A model told it will reason from "
        "it -- `the matter has been dormant, so...` -- which is an "
        "inference about their practice and not about the law. The "
        "chronology carries every date that bears on the case, dated by "
        "the forum's calendar and sourced. Reopens if a read is ever "
        "asked about delay in prosecution, where when the advocate last "
        "touched the file is genuinely material.",
    "Matter.emergency_because":
        "It is a screening decision about the FILE, not material for an "
        "answer. Telling a model that a matter was admitted under an "
        "emergency exception invites it to write about the emergency "
        "instead of the question, and the exception is already on the "
        "advocate's screen as a blocked screen row. Reopens if a read is "
        "ever asked to WEIGH urgency rather than report it.",
    # -- structure, not content ---------------------------------------------
    "Matter.id": "an identifier. The model reasons about the matter, not "
                 "about its key, and a key in a prompt is a token spent on "
                 "something no answer can turn on.",
    "Matter.advocate_id": "structure. Who is signed in decides access, not "
                          "advice.",
    "Matter.version": "structure — the optimistic-concurrency counter.",
    "Matter.intake_request_key":
        "WITHHELD. A stable request identity for opening/retrying the intake "
        "shell, not a case fact. The intake receipt consumer uses it to avoid "
        "duplicate matters. REOPENS only for a separate operational audit "
        "consumer, never as legal evidence in the reasoning account.",
    "Matter.title": "derived FROM the account, so telling it back would "
                    "spend budget restating the first line of the file.",
    "Thread.id": "an identifier, as above.",
    "Thread.checklist_session":
        "an identifier, and one whose only use is COMPARISON. "
        "`turn.session_reference != thread.checklist_session` is how a "
        "resumed checklist is told from a continuing one; the value itself "
        "says nothing about the dispute, and a model shown an opaque session "
        "key either ignores it or writes about it. What the comparison "
        "CONCLUDES -- that this is a resumption -- is already told, as "
        "`resumed`. Reopens if a read is ever asked which session an answer "
        "came from, which is an audit question and not a legal one.",
    "Posture.version": "structure — the posture's own revision counter.",
    "Posture.source_fact": "an identifier. The fact it points AT is in the "
                           "account; the pointer is not content.",
    "Fact.id": "an identifier. It is used to PIN and to supersede, both "
               "inside the product.",
    "Fact.version":
        "WITHHELD. A proposition revision counter, not the content of a "
        "correction or its evidential weight. The current canonical Fact "
        "statement is carried. REOPENS when a history-aware comparison "
        "consumer is built; a number alone must not pretend to preserve "
        "the missing immutable historical revision lineage.",
    "TurnReceipt.turn_id":
        "WITHHELD. Release/replay identity, consumed by the exact receipt "
        "ledger, not a new fact or legal authority for the reasoning model.",
    "TurnReceipt.offer_fingerprint":
        "WITHHELD. An integrity digest of an original operation offer. "
        "Matching it authorises exact retry, not an inference about the case.",
    "TurnReceipt.recorded_at":
        "WITHHELD. Release-record time, not an event date, deadline or source "
        "currency date. The historical response UI consumes it explicitly.",
    "TurnReceipt.message":
        "WITHHELD. A released operation's admitted instruction is retained "
        "for attributed History, not reintroduced as an independent source. "
        "Canonical admitted Facts already supply the account; refeeding an "
        "archive duplicates evidence and can revive superseded instructions. "
        "REOPENS only for an expressly scoped historical audit consumer.",
    "TurnReceipt.input_admitted":
        "WITHHELD. Input-persistence status is enforced by receipt and turn "
        "owners; it is not a truth label or a model instruction. A false "
        "value cannot retain an unadmitted message. REOPENS only for a "
        "separate operational receipt explanation, not case reasoning.",
    "Provenance.turn": "structure — which turn recorded it.",
    "Provenance.span": "structure — offsets into the message.",
    "AskedQuestion.gate": "structure. The question's TEXT is carried; the "
                          "gate that raised it is ours, not the advocate's.",
    "AskedQuestion.asked_on": "structure.",
    "AskedQuestion.thread": "structure — the account is already narrowed to "
                            "one thread.",
    "AskedQuestion.answered_by": "structure — the answering turn's id.",
    "AskedQuestion.times_asked": "CARRIED, but through `ignored` on the "
                                 "open-questions block rather than as a "
                                 "number, so it reads as a warning and not "
                                 "as a statistic.",
    "AskedQuestion.text": "CARRIED — every open and answered question is in "
                          "`as_context()`. Listed here because the walk sees "
                          "it and silence about a carried field would be "
                          "indistinguishable from an omission.",
    "Thread.label": "CARRIED, on the posture line.",
    "Thread.deferred_reason": "CARRIED, where a thread was deferred.",
    "Posture.role": "CARRIED, on the posture line.",
    "Posture.basis": "CARRIED — stated vs inferred, on the posture line.",
    "Posture.opponent": "CARRIED (B-092).",
    "Posture.client_described_as": "CARRIED (B-094) — kept once the role is "
                                   "known rather than dropped.",
    "Fact.statement": "CARRIED. It is the account.",
    "Fact.date": "CARRIED, stamped at the head of the line.",
    "Fact.certainty": "CARRIED (B-094) where `documented`.",
    "Fact.read_quality":
        "CARRIED for document provenance in `_source`, in all three states, "
        "with an explicit non-verification caveat. It qualifies extraction "
        "readability, not advocate statements, authenticity or truth. The "
        "raw advocate-words guard remains free of these product labels.",
    "Fact.basis": "CARRIED (B-094), with the third state said ONCE.",
    "Fact.basis_source": "CARRIED (B-094), beside the basis it evidences.",
    "Provenance.document": "CARRIED (B-093).",
    "Provenance.page": "CARRIED (B-093).",

    # -- WITHHELD ON PURPOSE, each with what would reopen it -----------------
    "Fact.superseded_by":
        "WITHHELD. `chart` removes a superseded fact from the account "
        "DELIBERATELY — that is the whole of B-086. Telling the model that a "
        "withdrawn statement exists invites it to reason from a date the "
        "advocate has retracted, which is the defect, not the fix.",
    "Fact.exact_words":
        "WITHHELD as a separate line. It is the verbatim record of the "
        "statement that is ALREADY the account, so rendering both would "
        "double every quoted fact against a measured budget. It is read by "
        "`Fact.quoted`, which every quote gate consults.",
    "Fact.material":
        "WITHHELD. Nothing writes it (declared in "
        "test_every_persisted_field_has_a_writer) and it defaults TRUE, so "
        "today it would mark every fact with the ordinary case. REOPENS the "
        "moment something writes `material=False`, because a fact graded "
        "immaterial and one nobody graded are then different things.",
    "Fact.weight":
        "WITHHELD, and for a second reason beyond having no writer. Weight is "
        "the PRODUCT's own grading of a fact. Feeding our grading back to the "
        "model that must then weigh the case invites it to treat its own "
        "earlier view as evidence — the model should form a view from the "
        "facts, not from our summary of them. REOPENS only with a decision "
        "that the advocate's grading, not ours, is what is being carried.",
    "Fact.confirmed":
        "WITHHELD. Read by the intake path, which is UNWIRED, and it has no "
        "guard: a fact never put to the advocate and one they declined to "
        "confirm are both `None` (B-091). Telling the model a null would "
        "carry that ambiguity into the advice. REOPENS with intake.",
    "Fact.confirmed_at":
        "WITHHELD — the timestamp of a confirmation nothing records yet, and "
        "a time is structure even once it exists.",
    "PostureConflict.on_record":
        "CARRIED (B-096) — the role the file records, named in the dispute "
        "line so the model is told WHICH two roles are contested rather than "
        "that a conflict exists.",
    "PostureConflict.now_suggested":
        "CARRIED (B-096) — the role this turn reads as.",
    "PostureConflict.applied":
        "WITHHELD. `Posture.conflicts` is carried and this flag on it is not "
        "written (B-091), so it is False for a conflict acted on and for one "
        "that was not — telling the model a value that means nothing is "
        "worse than telling it nothing. REOPENS the moment something writes "
        "it, because a conflict already resolved and one still open are then "
        "different instructions.",
}


# ================================ the checks ================================

def test_the_walk_can_see_the_record():
    """A positive control on the POPULATION.

    The closure walk returned `Matter` alone on the first attempt at the
    sibling sweep — annotations were strings under `from __future__ import
    annotations` and nothing recursed. Every check below would have passed
    against an empty set.
    """
    fields = content_fields()
    assert len(fields) > 20, f"the walk stopped early: {fields}"
    for expected in ("Fact.statement", "Posture.opponent",
                     "Provenance.document"):
        assert expected in fields, f"{expected} is not in the population"


def test_no_declaration_names_a_field_that_is_gone():
    """A declaration for a renamed field protects nothing and reads as
    though it does."""
    real = set(content_fields())
    stale = [f for f in WITHHELD if f not in real]
    assert not stale, (
        "WITHHELD names fields the record does not have:\n  "
        + "\n  ".join(stale))


def test_every_withholding_that_can_reopen_says_what_reopens_it():
    """A withholding tied to a missing writer is TEMPORARY, and one written
    in the voice of a settled decision stops being work. This is the same
    arrangement as the OPEN entries in
    test_every_persisted_field_has_a_writer."""
    for name, why in WITHHELD.items():
        assert why.strip(), f"{name} is declared with no reason"
        if "B-091" in why and "WITHHELD" in why:
            assert "REOPENS" in why or "structure" in why, (
                f"{name} is withheld because nothing writes it and does not "
                f"say what reopens the question")


# =========================== and the rendering ==============================


# ============ the guard input must never widen with the account ============


# ===== a representation is about the FILE, an account is about ONE dispute ====
#
# MEASURED 22 September 2026, on a live four-dispute brief opening "I act for
# Sattaru Ramulu". `summary.build(matter, thread_id)` narrows the account to
# one dispute, which is right for the NARRATIVE and was also narrowing the
# REPRESENTATION. The opening fact carrying that sentence lands in one
# thread's chronology, so on every other thread the posture read could not
# win: quoting the shared sentence failed guard 1 -- "the quoted span is in
# nothing the advocate wrote" -- and quoting the dispute's own paragraph
# failed guard 2, "describes events rather than stating whom the advocate acts
# for". Both guards were right. G-POSTURE blocked the whole matter.

_REPRESENTATION = ("I act for Sattaru Ramulu, who runs a hardware business "
                   "at Sangareddy.")
_OTHER_DISPUTE = ("Fourth, unrelated: Ramulu leased a shop to Meena Traders. "
                  "Rent unpaid since January 2026.")


