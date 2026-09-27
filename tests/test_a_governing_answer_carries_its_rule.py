"""AN ANSWER ABOUT WHICH LAW GOVERNS CARRIES THE RULE THAT PRODUCED IT.

THE MEASURED GAP, 26 September 2026, reviewing the capabilities the tool layer
will wrap. `governing()` returned the Act and a sentence; the curated
succession that decided it -- both Acts, the commencement, the saving
provision and where the row was curated from -- stayed in the table. A tool
asked "why the BNS?" could give the conclusion and not the rule, and a reader
could not tell a curated succession from a paraphrase of one.

THE RULES, over every limb, every date either side of commencement and every
pending state:

* an answer that names an Act or a saving provision carries the succession it
  applied, and that succession is the table's own row for the limb;
* the row names where it was curated from;
* an answer naming an Act without its rule cannot be built.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from nm.legal_brain.procedure import governing_law_sources as curated
from nm.legal_brain.procedure.governing_law_port import Governing, Limb, Pending

pytestmark = pytest.mark.class_a


def _answers():
    for row in curated.successions():
        for on in (None, row.commenced_on - timedelta(days=1), row.commenced_on,
                   row.commenced_on + timedelta(days=400)):
            for pending in Pending:
                yield row, curated.governing(row.limb, on, pending)


def test_the_population_is_live():
    answers = list(_answers())
    assert len(answers) >= 3 * 4 * 3, len(answers)
    assert any(a.established for _, a in answers) and any(not a.established for _, a in answers)


def test_every_answer_naming_law_carries_the_row_that_named_it():
    for row, answer in _answers():
        if answer.act or answer.read_the_saving:
            assert answer.rule is row, (row.limb, answer)
            assert answer.act in ("", row.replaced, row.replacing)
            assert answer.rule.curated_from.strip()


def test_a_limb_nobody_curated_carries_no_rule(monkeypatch):
    """PLANTED: every limb is curated today, so a limb is removed from the
    table rather than looked for -- a population of none checks nothing."""
    removed = curated.SUCCESSIONS[0]
    monkeypatch.setattr(curated, "SUCCESSIONS", curated.SUCCESSIONS[1:])
    answer = curated.governing(removed.limb, date(2025, 1, 1), Pending.NO)
    assert answer.rule is None and not answer.act and answer.because


def test_an_act_without_its_rule_cannot_be_built():
    with pytest.raises(ValueError):
        Governing(limb=Limb.SUBSTANTIVE, act="Bharatiya Nyaya Sanhita, 2023",
                  because="the offence date is after commencement")


def test_a_saving_provision_from_another_row_cannot_be_named():
    rows = curated.successions()
    with pytest.raises(ValueError):
        Governing(limb=rows[0].limb, act=rows[0].replacing, because="after commencement",
                  read_the_saving=rows[1].saving, rule=rows[0])
