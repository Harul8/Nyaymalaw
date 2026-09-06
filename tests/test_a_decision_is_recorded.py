"""PHASE 1 — what the product DECIDED is recorded, not only said.

THE MEASURED DEFECT
---------------------
NM makes decisions on every turn and keeps none of them. GS-15 disclosed, five
times, on five turns:

    "You named no provision, so I resolved one: the cause reads as specific
     performance, which the graph routes to Limitation Act, 1963 Article 54"

That is a choice, with a reason, and — where the graph offers them —
alternatives. It was made from scratch each turn with nothing checking the
answer was the same on turn 5 as on turn 1. A routing that silently moved
between turns would have read as a fresh sentence in the same place as the last
one.

WHAT RECORDING IT BUYS
------------------------
An advocate does not re-decide a settled question every time they are asked
something. They decided to proceed under one Article; that stands until a
reason to revisit it appears, and if it changes they say so and say why.

Recorded, a decision can be held stable, shown to have MOVED with its prior,
and OVERRULED BY THE ADVOCATE — which is what naming the alternatives was
always for. A product decision the advocate can overturn in four words is a
collaboration; one they cannot see is a guess they discover in court.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.model.traced import TracedModel
from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine, TurnInput
from nm.domain import decision as decision_domain
from nm.domain.decision import DecidedBy, Decision
from tests.test_turn_contract import KEY, _Evidence, _model_config

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 6)
OPENING = ("We act for the plaintiff at Hyderabad. The client was "
           "dispossessed and we want possession back.")


class _Routes(_Evidence):
    """Retrieval that RESOLVED a provision the advocate did not name.

    The shipping corpus adapter writes exactly this sentence; the test fixture
    does not, so the decision path would never run offline. Driven rather than
    left unexercised — an unexercised path is one that works until it ships.
    """

    article = "Article 54"

    def fetch(self, need):
        result = super().fetch(need)
        return replace(result, assumption=(
            f"You named no provision, so I resolved one: the cause reads as "
            f"specific performance, which the graph routes to Limitation Act, "
            f"1963 {_Routes.article} (curated). "
            f"Also arguable: Article 65; Article 58"))


def _engine(tmp_path, evidence=None):
    store = FileMatterStore(tmp_path, key=KEY)
    model = TracedModel(inner=ScriptedModelAdapter(
        _model_config(), responses={"__default__": "Issue the notice."}))
    return TurnEngine(store=store, evidence=evidence or _Routes(),
                      model=model), store


def _settled(store, matter_id):
    return decision_domain.from_stored(
        store.load(matter_id).threads[0].decisions)


# ============================== on the wire ================================

def test_a_resolved_provision_is_recorded_as_a_decision(tmp_path):
    """Not "the assumption is disclosed" — it always was, and it vanished with
    the turn. The choice has to survive as a THING, with its reason and its
    rivals."""
    engine, store = _engine(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                               message=OPENING))

    settled = _settled(store, out.matter.id)
    assert len(settled) == 1, f"nothing was recorded: {settled}"
    (d,) = settled
    assert d.because.strip(), "a decision with no reason cannot be argued with"
    assert d.by is DecidedBy.PRODUCT
    assert d.provisional, "a product decision must invite correction"
    assert d.alternatives == ("Article 65", "Article 58"), (
        "the rivals the routing named were not kept. An advocate reading what "
        "we DID learns less than one reading what we did NOT do, which is the "
        f"half they can correct: {d.alternatives}")


def test_a_routing_that_moves_is_announced_with_its_prior(tmp_path):
    """A settled question answered differently is a cascade event, not a
    fresh sentence in the same place as last turn.

    WITH ITS PRIOR, which is 5.4's rule everywhere else in this build: an
    advocate shown only the new answer cannot tell that it moved.
    """
    engine, store = _engine(tmp_path)
    first = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                                 message=OPENING))
    _Routes.article = "Article 65"
    try:
        out = engine.run(TurnInput(advocate_id="adv_1",
                                   matter_id=first.matter.id, today=TODAY,
                                   message="what about the notice"))
    finally:
        _Routes.article = "Article 54"

    said = " ".join(e.text for e in out.answer.elements)
    assert "resolved the provision differently" in said, (
        "the provision this rests on changed between turns and the advocate "
        "was not told:\n" + said)
    assert "Article 54" in said and "Article 65" in said, (
        "the change was announced without saying what it moved FROM")
    assert len(_settled(store, first.matter.id)) == 1, (
        "a question answered twice was filed as two settled questions")


def test_an_unchanged_routing_says_nothing(tmp_path):
    """THE BOUND. A product that announced its own consistency every turn
    would train the advocate to skip the line the real change arrives in —
    B-090, one layer down."""
    engine, _ = _engine(tmp_path)
    first = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                                 message=OPENING))
    out = engine.run(TurnInput(advocate_id="adv_1", matter_id=first.matter.id,
                               today=TODAY, message="what about the notice"))

    said = " ".join(e.text for e in out.answer.elements)
    assert "resolved the provision differently" not in said


def test_they_come_back_from_the_store_typed(tmp_path):
    """`Thread.decisions` is untyped for the cycle reason, so the store hands
    back plain dicts and the next turn would compare dicts to Decisions and
    match nothing — every choice looking new every turn, which is the defect
    arriving through its own repair."""
    engine, store = _engine(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                               message=OPENING))
    raw = store.load(out.matter.id).threads[0].decisions
    assert raw
    assert all(isinstance(d, Decision) for d in decision_domain.from_stored(raw))


# ============================== the domain =================================

def _d(what, because="a reason", by=DecidedBy.PRODUCT, turn="t1"):
    return Decision(what=what, because=because, at_turn=turn, by=by)


def test_two_answers_to_one_question_are_one_decision():
    """Keying on the whole sentence would file "route to Article 54" and
    "route to Article 65" as two settled questions rather than one that
    moved."""
    a = _d("the governing Article: Article 54")
    b = _d("the governing Article: Article 65")
    assert len(decision_domain.merge((a,), (b,))) == 1
    assert decision_domain.moved((a,), (b,))[0][0].what.endswith("54")


def test_a_different_question_is_a_different_decision():
    """THE BOUND on the key. Folding two genuinely different choices into one
    would lose whichever was decided first."""
    a = _d("the governing Article: Article 54")
    b = _d("forum: the District Court")
    assert len(decision_domain.merge((a,), (b,))) == 2


def test_the_product_does_not_overrule_the_advocate():
    """They said so. Inferring otherwise later is the product overruling its
    own instructions, which is C3 in a different place."""
    theirs = _d("the governing Article: Article 65", by=DecidedBy.ADVOCATE)
    ours = _d("the governing Article: Article 54", by=DecidedBy.PRODUCT)
    (kept,) = decision_domain.merge((theirs,), (ours,))
    assert kept.by is DecidedBy.ADVOCATE
    assert kept.what.endswith("65")


def test_the_advocate_may_overrule_the_product():
    """The permitted direction, and the reason alternatives are shown at
    all."""
    ours = _d("the governing Article: Article 54", by=DecidedBy.PRODUCT)
    theirs = _d("the governing Article: Article 65", by=DecidedBy.ADVOCATE)
    (kept,) = decision_domain.merge((ours,), (theirs,))
    assert kept.by is DecidedBy.ADVOCATE


def test_a_record_that_does_not_say_who_decided_is_not_guessed_at():
    """NOT_RECORDED is a value. Guessing ADVOCATE would promote our own
    inference to instruction, which the merge then refuses to overwrite — a
    wrong guess here becomes permanent."""
    (rebuilt,) = decision_domain.from_stored(
        [{"what": "x: y", "because": "z", "at_turn": "t1"}])
    assert rebuilt.by is DecidedBy.NOT_RECORDED
    assert rebuilt.provisional, (
        "a decision whose author is unknown must invite correction, not "
        "stand as though the advocate had given it")


def test_a_row_that_cannot_be_rebuilt_is_dropped_and_the_rest_kept():
    rebuilt = decision_domain.from_stored(
        [{"what": "a: b", "because": "c", "at_turn": "t1"},
         {"what": "no reason given"}, "not a decision", {}])
    assert len(rebuilt) == 1


def test_the_alternatives_are_read_out_of_the_sentence_the_adapter_writes():
    """Parsed back rather than plumbed through a new field: the sentence is a
    contract the adapter already keeps, and a second channel for one fact is
    the shape this build refuses. If the wording changes this returns nothing
    — worse than a wrong list, and visibly worse."""
    from nm.core.turn import _arguable

    assert _arguable("… routes to X. Also arguable: Article 65; Article 58") \
        == ("Article 65", "Article 58")
    assert _arguable("… routes to X with no rivals") == ()
    assert _arguable("") == ()
