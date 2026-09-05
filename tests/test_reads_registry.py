"""THE READS TABLE BINDS, and a decisive read that answers nothing says so.

WHY THIS FILE EXISTS, AND WHAT IT FOUND ON ITS FIRST RUN
----------------------------------------------------------
`nm/domain/reads.py` says, in its own source: *"`tests/test_reads_registry.py`
fails the build on a schema in `nm/` that is not here, so a twelfth read cannot
be added without someone deciding which kind it is."*

That file did not exist. The claim had no runner, which is the entire argument
of CLAUDE.md arriving inside the module written to enforce a rule — and the
table had already drifted: it declared a `correction` read, and there is no
`x-nm-read: "correction"` schema anywhere, because B-086 folded the correction
into the DATE row. The table named a read the product does not make.

THE ENUMERATOR, AND WHY B-088'S FIX NEEDED REPLACING
------------------------------------------------------
B-088 was the correction read returning nothing on one run and not the next.
The fix guarded THAT read: a phrase list noticing the advocate say "that is
wrong". It worked. It was a patch.

The same silence in `cause` sends an exact section lookup into the wrong
statute. In `factors` it reports a live claim as dead. In `dates` it drops the
accrual the whole limitation runs from. Six reads are declared DECISIVE on one
narrow test — does the output change a DATE, an AMOUNT, or WHICH LAW IS READ —
and only one of them had a consequence for answering nothing.

So the population is the TABLE. A seventh decisive read is covered the day
someone declares it, and nobody has to remember this file exists.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from nm.domain import reads

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]


def schemas_in_the_product() -> set[str]:
    """Every `x-nm-read` marker in `nm/`, read from the source.

    From the SOURCE and not from an import, because a schema behind a branch
    that does not run at import time is still a schema the product sends.
    """
    found: set[str] = set()
    for path in sorted((ROOT / "nm").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf8"))):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=False):
                if (isinstance(key, ast.Constant) and key.value == "x-nm-read"
                        and isinstance(value, ast.Constant)):
                    found.add(value.value)
    return found


# ============================ the table binds ==============================

def test_the_scan_can_see_the_schemas():
    """A positive control. An AST walk that matched nothing would make every
    check below pass against an empty set — the failure the sibling closure
    walk actually had on its first attempt."""
    found = schemas_in_the_product()
    assert len(found) > 10, f"the scan found almost nothing: {sorted(found)}"
    assert "dates" in found and "posture" in found


def test_every_read_the_product_makes_is_declared():
    """The claim `reads.py` makes about this file, now actually made.

    A twelfth read cannot be added without someone deciding whether being
    wrong about it changes a number.
    """
    undeclared = schemas_in_the_product() - {r.key for r in reads.READS}
    assert not undeclared, (
        "these schemas are sent by the product and are not in READS, so "
        "nobody has decided whether they are decisive:\n  "
        + "\n  ".join(sorted(undeclared)))


def test_every_declared_read_is_one_the_product_makes():
    """THE DIRECTION THAT FOUND THE DRIFT.

    Asked only the other way, the table could name any number of reads that
    do not exist and read as a complete inventory. It named one: `correction`,
    left behind when B-086 folded the correction into the date row. A table
    that lists a read nobody makes tells its next reader that a call happens
    which does not.
    """
    phantom = {r.key for r in reads.READS} - schemas_in_the_product()
    assert not phantom, (
        "READS declares reads the product does not make:\n  "
        + "\n  ".join(sorted(phantom)))


def test_every_read_says_why_it_is_or_is_not_decisive():
    """Both halves are worth writing down. Without the second, the list grows
    until every read is decisive and the distinction stops meaning
    anything."""
    for read in reads.READS:
        assert read.why.strip(), f"{read.key} gives no reason"
        assert len(read.why) > 40, (
            f"{read.key}'s reason is too short to be a reason: {read.why!r}")


# ======================== the enumerator, and the gate ======================

def test_every_decisive_read_says_so_when_it_answers_with_nothing():
    """THE MECHANISM, WITH ITS POPULATION DRAWN FROM THE TABLE.

    B-088 generalised. Not "the correction read is guarded" but "a read whose
    output IS a date, an amount, or which law is read cannot come back empty
    in silence" — checked for all six, and for the seventh on the day it is
    declared.

    Driven through the port, because that is the single place every structured
    read passes. Six call sites each remembering to ask is the arrangement
    that produced one guard for one read.
    """
    from nm.adapters.model.config import ModelConfig  # noqa: F401
    from nm.adapters.model.scripted import ScriptedModelAdapter
    from nm.adapters.model.traced import TracedModel
    from nm.ports.model import Prompt, Tier
    from tests.test_turn_contract import _model_config

    decisive = [r.key for r in reads.READS if r.decisive]
    assert decisive, "the table declares no decisive read at all"

    class Empty(ScriptedModelAdapter):
        def structured(self, prompt, schema, tier, **kw):
            result = super().structured(prompt, schema, tier, **kw)
            from dataclasses import replace as _replace
            return _replace(result, data={}, text=None)

    for key in decisive:
        traced = TracedModel(inner=Empty(_model_config()))
        traced.structured(Prompt(user="anything at all"),
                          {"x-nm-read": key}, Tier.ROUTINE)
        assert traced.empty_decisive() == (key,), (
            f"the {key!r} read answered with nothing and the product did not "
            f"notice. Its output changes a date, an amount, or which law is "
            f"read, so an empty answer is indistinguishable from that thing "
            f"not being present.")


def test_a_read_that_is_not_decisive_is_allowed_to_be_empty():
    """THE BOUND, and it is what keeps the disclosure worth reading.

    Most empties are ordinary answers: the issues read finds no issue, the
    adverse read finds nothing against us. Announcing those would put a
    disclosure on nearly every turn, and a signal that fires always carries no
    information — B-090, one layer down.
    """
    from nm.adapters.model.scripted import ScriptedModelAdapter
    from nm.adapters.model.traced import TracedModel
    from nm.ports.model import Prompt, Tier
    from tests.test_turn_contract import _model_config

    ordinary = [r.key for r in reads.READS if not r.decisive]
    assert ordinary, "every read is decisive, so the distinction is empty"

    class Empty(ScriptedModelAdapter):
        def structured(self, prompt, schema, tier, **kw):
            from dataclasses import replace as _replace
            return _replace(super().structured(prompt, schema, tier, **kw),
                            data={}, text=None)

    traced = TracedModel(inner=Empty(_model_config()))
    for key in ordinary:
        traced.structured(Prompt(user="anything at all"),
                          {"x-nm-read": key}, Tier.ROUTINE)
    assert traced.empty_decisive() == (), (
        f"an ordinary read coming back empty was reported as decisive: "
        f"{traced.empty_decisive()}")


def test_no_second_copy_of_the_decisive_set_exists():
    """`nm.domain.reads` decides which reads are decisive, and nothing else.

    A hardcoded set of keys in the adapter -- which is where the check runs --
    would be a second owner for one truth (S9), and it would drift the day a
    seventh read is declared: the table would say seven and the guard would
    guard six, with nothing to notice.

    THE FIRST VERSION OF THIS CHECK WAS A SUBSTRING SCAN FOR THE WORD
    "decisive" and it flagged `nm/core/cause.py`, where the word appears in a
    comment about enum values. A check whose signal is the English language is
    noise, and noise that fails the build gets deleted rather than heeded. It
    now looks for the thing itself: a collection literal naming two or more
    decisive reads, which is what a second copy would actually look like.
    """
    keys = {r.key for r in reads.READS if r.decisive}
    offenders: list[str] = []
    for path in sorted((ROOT / "nm").rglob("*.py")):
        if path.name == "reads.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Set, ast.List, ast.Tuple)):
                continue
            named = {e.value for e in node.elts
                     if isinstance(e, ast.Constant) and isinstance(e.value, str)}
            if len(named & keys) >= 2:
                offenders.append(
                    f"{str(path.relative_to(ROOT))}:{node.lineno} lists "
                    f"{sorted(named & keys)}")
    assert not offenders, (
        "these hold their own set of decisive reads. Call "
        "`nm.domain.reads.BY_KEY` instead -- a second copy guards the reads "
        "it knew about on the day it was written:\n  "
        + "\n  ".join(offenders))


def test_the_second_copy_scan_can_see_a_second_copy():
    """A POSITIVE CONTROL, because the scan above passes trivially on a tree
    that has no such literal — and would go on passing if it were broken."""
    planted = ast.parse('GUARDED = ("dates", "cause", "posture")')
    keys = {r.key for r in reads.READS if r.decisive}
    hits = [n for n in ast.walk(planted)
            if isinstance(n, (ast.Set, ast.List, ast.Tuple))
            and len({e.value for e in n.elts
                     if isinstance(e, ast.Constant)} & keys) >= 2]
    assert hits, "the scan cannot see a hardcoded decisive set"


def test_the_turn_discloses_which_read_came_back_empty(tmp_path):
    """ON A SERVED TURN, because this defect lives between a correct read and
    an answer that never mentions it — CLAUDE.md §8."""
    from datetime import date

    from nm.adapters.model.scripted import ScriptedModelAdapter
    from nm.adapters.model.traced import TracedModel
    from nm.adapters.store.file_store import FileMatterStore
    from nm.core.turn import TurnEngine, TurnInput
    from tests.test_turn_contract import KEY, _Evidence, _model_config

    class NoDates(ScriptedModelAdapter):
        """Answers everything normally and the DATE read with nothing."""

        def structured(self, prompt, schema, tier, **kw):
            result = super().structured(prompt, schema, tier, **kw)
            if schema.get("x-nm-read") == "dates":
                from dataclasses import replace as _replace
                return _replace(result, data={"events": []}, text=None)
            return result

    store = FileMatterStore(tmp_path, key=KEY)
    engine = TurnEngine(
        store=store, evidence=_Evidence(),
        model=TracedModel(inner=NoDates(
            _model_config(),
            responses={"__default__": "Issue the notice."})))
    out = engine.run(TurnInput(
        advocate_id="adv_1", today=date(2026, 9, 5),
        message=("We act for the plaintiff at Hyderabad. The agreement is "
                 "dated 15 April 1984.")))

    said = " ".join(e.text for e in out.answer.elements)
    assert "dates" in said and "nothing back" in said, (
        "the date read came back empty and the answer does not say so:\n"
        + said)
    assert any(g.gate_id == "G-READ" for g in out.metrics.gates_fired), (
        "G-READ did not fire")
