"""BK-35 — the period runs from the STATUTORY TRIGGER, or it does not run.

THE DEFECT, AND WHY IT WAS THE WORST ONE IN THE PRODUCT
--------------------------------------------------------
`_limitation` chose the accrual like this::

    accrual = next((f for f in chart if f.date is not None), None)

The earliest dated fact, whatever the cause. So a specific-performance file
giving a 2023 agreement, no date fixed for performance, and a 2024 written
refusal ran the period from the agreement — where Article 54's third column
says it runs from the date fixed for performance or, where none is fixed,
from notice that performance is refused.

Every citation on that turn was correct. The Article was right, the period was
read out of retrieved text, the arithmetic was right. Only the STARTING POINT
was chosen by sort order, and nothing in the answer showed it. That is this
repository's founding failure verbatim: two right components and an inverted
answer living in the gap between them.

WHAT THIS FILE ASSERTS, AND WHY IT IS A RULE AND NOT A SCENARIO
----------------------------------------------------------------
Not "Article 54 runs from the refusal" — that is the scenario that exposed it,
and a test asserting it would pass while Article 14 kept running from whatever
sorted first. The rule is:

    THE PERIOD RUNS FROM THE ENTRY SOMETHING IDENTIFIED AS THE TRIGGER,
    AND WHERE NOTHING IDENTIFIED ONE, IT DOES NOT RUN AT ALL.

So the read is driven BOTH WAYS — told to name the last entry, then the first
— because a test that only checks the last would pass on a product that had
gone back to sorting. The two directions are the positive control on each
other.

AND THE POPULATION COMES FROM THE CODE. `test_every_curated_article_says_when
_its_period_starts` walks `LIMITATION_ARTICLE` rather than a list written
here, so the eighth Article cannot be curated without a trigger — which is the
form CLAUDE.md §1 asks for: not the fix restated, but the enumerator that
refuses the next omission.
"""
from __future__ import annotations

import json
import re
from datetime import date

import pytest
from nm.adapters.model.scripted import SCRIPTED_READS
from nm.core.deadlines import DeadlineKind
from nm.core.turn import TurnInput
from nm.knowledge.resolution import LIMITATION_ARTICLE, accrual_trigger_for

from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 4)

#: ONE SENTENCE PER EVENT. `scripted_dates` takes the sentence a date sits in,
#: so three dates in one sentence produce three entries with identical words —
#: and a read choosing between entries that read the same cannot choose. That
#: was measured, not assumed: the first version of this brief was one sentence
#: and every entry arrived as "The agreement of sale is dated 15 April 2024,
#: possession was handed ov".
BRIEF = ("We act for the plaintiff at Hyderabad in a suit for specific "
         "performance. The agreement of sale is dated 15 April 2024. "
         "Possession was handed over on 20 April 2024. On 12 June 2024 the "
         "defendant refused in writing to execute the sale deed.")


def _offered(prompt: str) -> list[tuple[str, date]]:
    """The entries the read was OFFERED, in the order it was shown them.

    READ OFF THE PROMPT rather than off the thread, because the thread stores
    fact IDS and the dates live elsewhere — and because this is the list the
    read actually had to choose from. A test that rebuilt it from somewhere
    else could disagree with what the product sent, and would then be
    checking its own reconstruction.
    """
    pattern = r"^\s+(fact_[0-9a-f]+)\t(\d{4}-\d\d-\d\d)\t"
    return [(m.group(1), date.fromisoformat(m.group(2)))
            for m in re.finditer(pattern, prompt, flags=re.M)]


def _answering(choose, seen: list):
    """A stand-in for the accrual read that picks by POSITION, not by words.

    `choose` is handed the entries as shown and returns one id, or "".
    Choosing by position is what makes the two directions comparable: the
    same brief, the same entries, and the only thing that varies is which one
    the read names.
    """
    def responder(user: str) -> str:
        rows = _offered(user)
        seen.extend(rows)
        return json.dumps({
            "fact_id": choose(rows),
            "limb": "notice that performance is refused",
            "why": "named by the test",
        })
    return responder


def _run(tmp_path, monkeypatch, choose):
    seen: list[tuple[str, date]] = []
    monkeypatch.setitem(SCRIPTED_READS, "accrual", _answering(choose, seen))
    engine, _store = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF,
                               today=TODAY))
    return out, seen


def _window(out):
    """The committed limitation window off the served turn.

    OFF THE MATTER AND OFF THE ANSWER — never off a value the test built
    itself (CLAUDE.md §8). The `Limitation` object is not persisted at all;
    what survives the turn is the register entry and the words the advocate
    reads, so those are what these tests assert on. A guard that is right in
    `_limitation` and lost before the register is written is not a guard, and
    reading the return value would not have shown the difference.

    `on is None` IS THE THIRD STATE, present as a row rather than a missing
    one, which is what makes `not computed` visible instead of absent.
    """
    rows = [d for d in out.matter.threads[0].deadlines
            if d.kind is DeadlineKind.LIMITATION]
    assert len(rows) == 1, (
        f"expected exactly one limitation window on the thread, got "
        f"{len(rows)} — an uncomputed one must be a row, not an absence")
    return rows[0]


def _said(out) -> str:
    """Every word the advocate is shown on this turn."""
    return " ".join(e.text for e in out.answer.elements)


# ============================================ the rule, driven both ways ===

@pytest.mark.parametrize("which", ["last", "first"])
def test_the_period_runs_from_the_entry_the_read_named(
        which, tmp_path, monkeypatch):
    """THE RULE. The accrual is what was IDENTIFIED, not what sorted first.

    Driven both ways on purpose. A product that had quietly gone back to
    `dated[0]` would pass the `first` case and fail the `last` one, and a test
    that only ran `last` could pass on a coincidence — the trigger entry
    happens to be last on this brief. Neither direction proves the rule
    alone; the pair does.
    """
    pick = ((lambda rows: rows[-1][0]) if which == "last"
            else (lambda rows: rows[0][0]))
    out, offered = _run(tmp_path, monkeypatch, pick)

    assert len(offered) > 1, (
        "this brief no longer offers a choice, so it cannot test one")
    assert offered[0][1] != offered[-1][1], (
        "the two entries share a date, so the window cannot tell them apart")

    window = _window(out)
    assert window.on is not None, "the period was not computed at all"

    expected = (offered[-1] if which == "last" else offered[0])[1]
    other = (offered[0] if which == "last" else offered[-1])[1]
    # THE WINDOW IS THE ACCRUAL PLUS THE PERIOD, so it lands on the named
    # entry's own month and day whatever the period is — and NOT on the
    # other entry's. A product that had gone back to sorting would hold the
    # `first` case and miss the `last` one by the 58 days between them.
    assert (window.on.month, window.on.day) == (expected.month, expected.day), (
        f"the read named the {which} entry ({expected}) and the window "
        f"closes on {window.on} — the accrual is not following the read")
    assert (window.on.month, window.on.day) != (other.month, other.day)


def test_a_read_that_names_nothing_does_not_start_the_period(
        tmp_path, monkeypatch):
    """THE HALF THAT MATTERS MOST, because it is the one that costs answers.

    Falling back to the earliest entry here is not a smaller version of the
    right answer — it IS the defect. So an unidentified trigger produces no
    date at all, and the reason names what was being looked for so the
    advocate can supply it in one turn.
    """
    out, _offered = _run(tmp_path, monkeypatch, lambda rows: "")

    assert _window(out).on is None, (
        "a date was produced from an accrual nothing identified")
    said = _said(out).lower()
    assert "performance" in said and "refus" in said, (
        f"the answer does not say what was being looked for:\n{_said(out)}")


def test_an_entry_that_is_not_on_the_chart_is_not_an_accrual(
        tmp_path, monkeypatch):
    """THE GUARD IS EXACT MEMBERSHIP, and this is the whole of it.

    The answer space is this thread's own fact ids — a closed set the turn
    generated — so CLAUDE.md §5 reaches its easiest case: an exact key exists
    and nothing is ranked. An id that is not in the set names nothing, and no
    reading of the surrounding prose would make it name something.
    """
    out, _offered = _run(tmp_path, monkeypatch,
                         lambda rows: "fact_deadbeef00")

    assert _window(out).on is None, (
        "an id that names nothing on this thread started the period")


def test_the_limb_reaches_the_advocate(tmp_path, monkeypatch):
    """AN ACCRUAL THE ADVOCATE CANNOT CHECK IS ONE THEY CANNOT CORRECT.

    Article 54 has two limbs and they give different dates; so do Articles 14
    and 19. `2024-06-12` tells an advocate nothing. `the refusal — notice that
    performance is refused` is a sentence they can disagree with in four
    words, and that disagreement is the only mechanism that catches a wrong
    accrual, because everything downstream is derived from it.
    """
    out, _offered = _run(tmp_path, monkeypatch, lambda rows: rows[-1][0])

    assert _window(out).on is not None
    assert "notice that performance is refused" in _said(out), (
        f"the limb was dropped between the read and the advocate:\n"
        f"{_said(out)}")


# ================================== the population, drawn from the code ====

def test_every_curated_article_says_when_its_period_starts():
    """THE ENUMERATOR, and it is what makes this a fix rather than a patch.

    Curating an Article without its trigger puts that cause straight back on
    the sort-order path — silently, and only for that cause. So the
    population is walked from `LIMITATION_ARTICLE` itself: the eighth Article
    cannot be added without someone reading the Schedule's third column.
    """
    missing = sorted(cause.value for cause, edge in LIMITATION_ARTICLE.items()
                     if not edge.accrues_on.strip())
    assert not missing, (
        f"these causes are curated to an Article and do not say when the "
        f"period starts, so they run from whatever sorted first: {missing}")


def test_the_trigger_lookup_has_one_owner_and_answers_for_every_cause():
    """POSITIVE CONTROL ON THE LOOKUP ITSELF.

    `accrual_trigger_for` is reached through the evidence port, so a lookup
    that silently returned "" for everything would take every turn down the
    pre-BK-35 path and every test above would still pass — the engine reads
    empty as *no curated trigger* and computes as it did before. That is
    exactly how the first half of this fix shipped and never once fired.
    """
    for cause, edge in LIMITATION_ARTICLE.items():
        assert accrual_trigger_for(cause.value) == edge.accrues_on, (
            f"the lookup and the table disagree for {cause.value}")

    # AND IT DOES NOT ANSWER FOR SOMETHING THAT IS NOT A CAUSE, which is the
    # other half of the control: a lookup that returned a trigger for junk
    # would be matching rather than resolving.
    assert accrual_trigger_for("not_a_cause_at_all") == ""
    assert accrual_trigger_for("") == ""
