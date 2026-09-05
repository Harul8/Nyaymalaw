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
from dataclasses import replace

import pytest

from nm.domain import summary
from nm.domain.matter import (
    Basis,
    Certainty,
    Fact,
    FactBasis,
    Matter,
    Posture,
    Provenance,
    Role,
    Thread,
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
    # -- structure, not content ---------------------------------------------
    "Matter.id": "an identifier. The model reasons about the matter, not "
                 "about its key, and a key in a prompt is a token spent on "
                 "something no answer can turn on.",
    "Matter.advocate_id": "structure. Who is signed in decides access, not "
                          "advice.",
    "Matter.version": "structure — the optimistic-concurrency counter.",
    "Matter.title": "derived FROM the account, so telling it back would "
                    "spend budget restating the first line of the file.",
    "Thread.id": "an identifier, as above.",
    "Posture.version": "structure — the posture's own revision counter.",
    "Posture.source_fact": "an identifier. The fact it points AT is in the "
                           "account; the pointer is not content.",
    "Fact.id": "an identifier. It is used to PIN and to supersede, both "
               "inside the product.",
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


def test_every_field_is_told_or_declared():
    """THE SWEEP.

    Asked the other way — is everything in the account on the record — it
    would confirm that what we render exists, which cannot fail. This asks
    which fields the record holds and the model never sees.
    """
    undeclared = [f for f in content_fields() if f not in WITHHELD]
    assert not undeclared, (
        "these are on the advocate's record and nothing decides whether the "
        "model is told them. A field left out silently and one left out on "
        "purpose look identical from every other direction (S1). Render it, "
        "or declare it in WITHHELD with the reason:\n  "
        + "\n  ".join(undeclared))


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

def _context(**over) -> str:
    fact = Fact(id="f1", statement=STATEMENT, provenance=SAID, **over)
    thread = replace(Thread.create(label="the sale"),
                     posture=Posture(role=Role.PLAINTIFF, basis=Basis.STATED),
                     chronology=("f1",))
    matter = replace(Matter.create(advocate_id="adv_1", title="a sale"),
                     facts=(fact,), threads=(thread,))
    return summary.build(matter, thread.id).as_context()


def test_how_the_client_knows_it_reaches_the_model():
    """Its own docstring: "the difference decides what has to be proved and
    by whom". A model given only the sentence cannot tell them apart."""
    assert "direct knowledge" in _context(basis=FactBasis.DIRECT_KNOWLEDGE)
    # HEARSAY cannot be constructed without a source -- `Fact.__post_init__`
    # refuses it, because a basis with no source cannot be walked back. The
    # guard is the reason the two travel together in the account.
    assert "hearsay" in _context(basis=FactBasis.HEARSAY,
                                 basis_source="his brother")


def test_the_source_of_a_basis_travels_with_it():
    """The same argument as a page number in B-093 — it is what makes the
    claim checkable rather than merely asserted."""
    told = _context(basis=FactBasis.HEARSAY, basis_source="his brother")
    assert "hearsay" in told and "his brother" in told, told


def test_an_unassessed_basis_is_said_once_and_not_per_fact():
    """THE THIRD STATE, AND THE BUDGET, IN ONE CHECK.

    `not_assessed` invisible is the S8 shape — the model reads every unmarked
    line as ordinary rather than as ungraded. Marked on each fact it would
    spend roughly 240 characters of 3000 repeating one sentence, paid for in
    facts that then do not fit.
    """
    told = _context()
    assert "has not been assessed" in told, told
    assert told.count("not assessed") <= 1, (
        "the ungraded state is repeated per fact:\n" + told)


def test_a_documented_date_is_not_the_same_as_a_remembered_one():
    """AND IT IS NOT WHAT `_source` RENDERS. `_source` says the product read
    this off a document it holds; `documented` says the ADVOCATE says a
    document evidences it. A date on a registered deed and a date the client
    remembers are not the same date, and the arithmetic is identical either
    way while the risk is not."""
    assert "documented" in _context(certainty=Certainty.DOCUMENTED)
    assert "documented" not in _context(certainty=Certainty.ASSERTED)


def test_the_ordinary_fact_carries_no_marker():
    """THE BOUND. Marking the ordinary case spends a measured budget saying
    the ordinary thing, and every character comes out of a fact."""
    plain = _context()
    assert f"{STATEMENT} (" not in plain, (
        "an unremarkable fact was given a marker:\n" + plain)


def test_the_advocates_own_word_for_their_client_survives_the_role():
    """B-094. It was rendered only on the `role is UNKNOWN` branch, so the
    moment the role settled, "the workman" left the file note for good."""
    thread = replace(Thread.create(label="the claim"),
                     posture=Posture(role=Role.PETITIONER, basis=Basis.STATED,
                                     client_described_as="workman"))
    matter = replace(Matter.create(advocate_id="adv_1", title="a claim"),
                     threads=(thread,))
    established = summary.build(matter, thread.id).established
    assert any("workman" in e for e in established), established


def test_a_contested_side_reaches_the_model(tmp_path):
    """B-096, AND IT IS THE SHARPEST MEMBER OF THIS POPULATION.

    `Posture.conflicts` appeared NOWHERE in this module. The board rendered
    `loud` and `conflict` from it, so the ADVOCATE saw a warning — while every
    derivation on the same turn reasoned as though the side were settled.

    The side is the one thing in this product that REVERSES the advice rather
    than weakening it: the same provision helps one party and hurts the other.
    A product that knows the side is in dispute and advises confidently anyway
    is doing the exact thing C3 exists to prevent, with the evidence of the
    dispute sitting on its own record.
    """
    from nm.domain.matter import PostureConflict

    contested = Posture(role=Role.PLAINTIFF, basis=Basis.STATED,
                        conflicts=(PostureConflict(on_record=Role.PLAINTIFF,
                                                   now_suggested=Role.DEFENDANT),))
    thread = replace(Thread.create(label="the sale"), posture=contested)
    matter = replace(Matter.create(advocate_id="adv_1", title="a sale"),
                     threads=(thread,))
    context = summary.build(matter, thread.id).as_context()

    assert "SIDE IS IN DISPUTE" in context, (
        "the file records a contested posture and the model is not told:\n"
        + context)
    assert "plaintiff" in context and "defendant" in context, (
        "the dispute is announced without saying which two roles are in it, "
        "which tells a model there is a problem and nothing it can act on")
    assert "Do not choose" in context, (
        "the model is told the side is disputed and not told what to do "
        "about it — an instruction it can follow beats a fact it must "
        "interpret")


def test_an_uncontested_posture_says_nothing_about_a_dispute():
    """THE BOUND. A dispute line on every matter would train the model to
    skip it, which is B-090 one layer down — a signal that fires always
    carries no information."""
    settled = replace(Thread.create(label="the sale"),
                      posture=Posture(role=Role.PLAINTIFF, basis=Basis.STATED))
    matter = replace(Matter.create(advocate_id="adv_1", title="a sale"),
                     threads=(settled,))
    assert "DISPUTE" not in summary.build(matter, settled.id).as_context()


# ============ the guard input must never widen with the account ============

def _matter_with(fact: Fact) -> tuple[Matter, Thread]:
    thread = replace(Thread.create(label="the sale"),
                     posture=Posture(role=Role.PLAINTIFF, basis=Basis.STATED),
                     chronology=("f1",))
    return replace(Matter.create(advocate_id="adv_1", title="a sale"),
                   facts=(fact,), threads=(thread,)), thread


def test_the_guard_input_carries_no_word_this_product_composed():
    """C3, DEFEATED TWICE BY WIDENING AN INPUT AND NOT BY A BAD INFERENCE.

    The first time, the posture extractor read "we act for the party moving"
    out of our own blocking question and the verbatim guard confirmed the
    span, because it was there -- in OUR text.

    The second time was 5 September 2026 and it was this day's own work. Three
    changes put product words into the account: a document name (B-093), a
    basis marker (B-094), and a note reading "How the client KNOWS any of this
    has not been assessed". `_FIRST_PERSON` matches `client`, so
    `speaks_of_the_representation` became true ON EVERY MATTER, and a
    COMPLAINANT posture was settled out of "a cheque was dishonoured on 3
    March".

    Rewording that note would have fixed that note. This asserts the RULE.
    """
    fact = Fact(id="f1", statement=STATEMENT,
                provenance=Provenance(kind="document", turn="t1",
                                      document="sale_deed.pdf", page=3),
                basis=FactBasis.HEARSAY, basis_source="his brother",
                certainty=Certainty.DOCUMENTED)
    matter, thread = _matter_with(fact)
    built = summary.build(matter, thread.id)

    assert built.advocate_words == STATEMENT, (
        "the guard input is not the advocate's sentence alone:\n"
        + built.advocate_words)
    for ours in ("sale_deed.pdf", "hearsay", "his brother", "documented",
                 "has not been assessed", "earlier statement(s)"):
        assert ours not in built.advocate_words, (
            f"{ours!r} is this product's word and it reached the guard input")


def test_the_account_and_the_guard_input_are_not_the_same_string():
    """They were, and that IS the defect. The account must keep carrying our
    markers -- a model that cannot see the basis cannot weigh it -- so the
    only safe arrangement is two strings built apart."""
    fact = Fact(id="f1", statement=STATEMENT, provenance=SAID,
                basis=FactBasis.DIRECT_KNOWLEDGE)
    matter, thread = _matter_with(fact)
    built = summary.build(matter, thread.id)

    assert "direct knowledge" in built.account, (
        "the account lost the marker, so the split was made by removing "
        "information rather than by separating two uses of it")
    assert built.account != built.advocate_words


def test_first_person_language_never_arrives_from_our_own_notes():
    """THE MECHANISM, TESTED WHERE IT BROKE.

    `speaks_of_the_representation` is what separates an advocate stating
    their side from an account of events, and it is asked of the guard input.
    Given a matter where the advocate spoke only of events, it must stay
    false however much this product has written into the account.
    """
    from nm.core.posture import speaks_of_the_representation

    fact = Fact(id="f1", statement="a cheque was dishonoured on 3 March",
                provenance=SAID)
    matter, thread = _matter_with(fact)
    built = summary.build(matter, thread.id)

    assert "client" in built.account, (
        "this test is not exercising the case it was written for -- the "
        "account no longer carries the note that caused the defect")
    assert not speaks_of_the_representation(built.advocate_words), (
        "an account of events reads as a statement of the representation")


def test_the_account_stays_inside_its_budget_with_every_note_appended():
    """THE NOTES ARE APPENDED AFTER THE FITTING LOOP, so each one has to be
    reserved for. The left-out note broke this once; the basis note broke it
    again the day it was added, at 3065 characters against 3000."""
    facts = tuple(
        Fact(id=f"f{i}", statement=f"turn {i}: something happened, filler "
                                   f"filler filler filler filler",
             provenance=SAID)
        for i in range(400))
    # THE CHRONOLOGY IS WHAT PUTS A FACT ON A THREAD. Without it the account
    # is empty and this test would pass by measuring nothing.
    thread = replace(Thread.create(label="t"),
                     posture=Posture(role=Role.PLAINTIFF, basis=Basis.STATED),
                     chronology=tuple(f.id for f in facts))
    matter = replace(Matter.create(advocate_id="adv_1", title="long"),
                     facts=facts, threads=(thread,))
    built = summary.build(matter, thread.id)

    assert len(built.account) <= summary.ACCOUNT_BUDGET, (
        f"{len(built.account)} characters against a "
        f"{summary.ACCOUNT_BUDGET} budget")
    assert "has not been assessed" in built.account, (
        "the basis note was dropped rather than reserved for")
