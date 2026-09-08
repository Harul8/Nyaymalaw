"""BK-11 — WHICH read could not run, said once and by name. All fifteen.

G-MODEL's clause is *the NEED fails, not the turn. The gap is visible and
nothing is recorded as advice.* `test_provider_independence.py` proved the
second sentence; BK-9 proved the first at ONE site of nine.

WHY ONE OWNER AND NOT NINE BETTER SENTENCES
---------------------------------------------
G-MODEL fired at nine `except ModelError` branches and each composed its own
disclosure, or composed none. What the advocate saw was whatever that branch
happened to append, which for most of the nine was nothing about which read
was lost.

`_decisive_empties` is the copy that is right, one step over: a decisive read
that ANSWERS WITH NOTHING. It has one owner, draws its population from the
trace, and NAMES the read. Its own docstring says why — *"the alternative is
six call sites each remembering to ask, which is the arrangement that produced
one guard for one read"* (B-088). A read that COULD NOT RUN is the
neighbouring fact and had exactly that arrangement.

So this is not a new mechanism. It is the existing one applied to the second
member of its own population. The nine sites keep their degraded RETURN — the
branch knows what value to fall back to and the owner does not — and only the
disclosure moves.

TWO MEASUREMENT MISTAKES THIS FILE EXISTS BECAUSE OF
------------------------------------------------------
**The first was the reason BK-11 was opened.** A sweep refused each read and
looked for any phrase the product uses when it is short of something. All
fifteen "said something" — under a proxy so generous it could not tell an
answer that names the missing read from one carrying an unrelated disclosure
on the same turn. Every turn carries several.

**The second was made while fixing the first, and the tests here caught it.**
The follow-up sweep asked `read in said` — a SUBSTRING — and reported fourteen
of fifteen named. `"cause" in said` matches *cause of action*; `"dispute"`
matches ordinary prose. Nothing was being disclosed at all: the fixture does
not wrap the model in `TracedModel`, so `refused_reads` did not exist on it
and the owner returned nothing every time.

CLAUDE.md §5 is about Acts and it is really about this: fuzzy may RANK, never
IDENTIFY. Both sweeps ranked. What follows parses the disclosure line and
asserts LIST MEMBERSHIP, and the fixture wraps the model the way the
composition root does — because a guard that is right in the core and absent
at the edge is not a guard, and here the guard was absent at the fixture.
"""
from __future__ import annotations

import pathlib
import re
from datetime import date

import pytest

from nm.adapters.knowledge.elements import CuratedElements
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.model.traced import TracedModel
from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine, TurnInput
from nm.ports.model import ModelError
from tests.test_turn_contract import KEY, _Evidence, _model_config, briefed

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 4)
ROOT = pathlib.Path(__file__).resolve().parents[1]

PLAIN = ("We act for the plaintiff at Hyderabad. The agreement is dated "
         "15 April 2024, possession was handed over on 20 April 2024, and "
         "the defendant has refused to execute the sale deed.")
EXPIRED = ("We act for the plaintiff, a supplier at Hyderabad. Goods were "
           "supplied against invoices on 14 March 2010 and were never paid "
           "for.")
TWO = ("We act for the defendant at Hyderabad in a cheque matter. The loan "
       "was repaid in cash with no receipt.",
       "Separately, we have a recovery suit for the same client against a "
       "supplier at Secunderabad.")
#: The accrual read runs only where the trigger DECIDES something: a cause
#: with a curated `accrues_on`, and more than one dated entry for it to choose
#: between. `PLAIN` has the dates and not the cause — it names no cause the
#: routing settles, so the trigger is empty and the read is never attempted.
#:
#: MEASURED, NOT ASSUMED, and the measurement is why this brief exists: the
#: first run of this row used `PLAIN`, the read never fired, and the failure
#: read as a missing disclosure rather than a path that had never executed.
#:
#: ONE SENTENCE PER EVENT, and that is not cosmetic. `scripted_dates` takes
#: the sentence a date sits in, so three dates in one sentence produce three
#: chronology entries with IDENTICAL words — and an accrual read choosing
#: between entries that read the same cannot choose at all. Measured: the
#: first version of this brief was one sentence and every entry arrived as
#: "The agreement of sale is dated 15 April 2024, possession was handed ov".
ACCRUAL = ("We act for the plaintiff at Hyderabad in a suit for specific "
           "performance. The agreement of sale is dated 15 April 2024. "
           "Possession was handed over on 20 April 2024. On 12 June 2024 the "
           "defendant refused in writing to execute the sale deed.")

#: The briefs, by name. A dict rather than a ternary chain so that adding the
#: fifth is an entry rather than an edit to the dispatch, and so that
#: `REACHED_BY` naming a brief that does not exist is a KeyError rather than a
#: silent fall-through to `PLAIN` — which is how the accrual row appeared to
#: run for a while against a brief that never reached the read.
BRIEFS: dict[str, tuple[str, ...]] = {
    "plain": (PLAIN,), "expired": (EXPIRED,), "two": TWO,
    "accrual": (ACCRUAL,),
}

#: read -> the brief that REACHES it. Measured on 7 September 2026 by refusing
#: each of the fifteen against each brief and parsing the disclosure line.
#:
#: A read is not disclosed on a turn that never attempted it, and that is
#: right rather than a gap: naming it would tell the advocate something is
#: missing from a turn that never needed it, which is the `not_assessed`
#: confusion arriving from the opposite direction. So each read is driven on
#: a brief whose SHAPE calls for it -- `salvage` where the period has run,
#: `exposure` where the file holds two disputes.
REACHED_BY: dict[str, str] = {
    "accrual": "accrual",
    # The consistency read runs wherever a step is recommended, which is every
    # turn that is not side-blind — so any brief reaches it, the same way
    # `duty` does.
    "consistency": "plain",
    # The parties read runs on every matter turn -- it is what the
    # conflict screen learns from, so it cannot be conditional.
    "parties": "plain",
    "adverse": "plain", "attacks": "plain", "cause": "plain",
    "dates": "plain", "factors": "plain", "inventory": "plain",
    "issues": "plain", "posture": "plain", "route": "plain",
    "theory": "plain",
    "dispute": "two", "exposure": "two", "role": "two",
    "proof": "expired", "salvage": "expired",
    # G-DUTY runs on EVERY turn, so any brief reaches it. `plain` keeps the
    # table honest about that: a read driven on a brief chosen to provoke it
    # would suggest this one is conditional, and it is not -- an instruction
    # is judged before the file is worked, whatever the file holds.
    "duty": "plain",
}


def _engine(tmp_path, read: str):
    """The engine, WRAPPED THE WAY THE COMPOSITION ROOT WRAPS IT.

    `TracedModel` is where `refused_reads` lives, and the shared `build`
    fixture does not apply it. A test that skipped it here would drive a
    product that cannot disclose and would pass on the assertion that no
    disclosure names the read -- which is what happened.
    """
    class _Fails(ScriptedModelAdapter):
        def structured(self, prompt, schema, tier, **kw):
            if schema.get("x-nm-read") == read:
                raise ModelError(f"the {read} read was refused by a test")
            return super().structured(prompt, schema, tier, **kw)

    return briefed(TurnEngine(
        store=FileMatterStore(tmp_path, key=KEY),
        evidence=_Evidence(),
        model=TracedModel(inner=_Fails(
            _model_config(), responses={"__default__": "File the suit."})),
        elements=CuratedElements()))


def _run(engine, brief: str):
    out = None
    for message in BRIEFS[brief]:
        out = engine.run(TurnInput(
            advocate_id="adv_1", message=message, today=TODAY,
            matter_id=out.matter.id if out else None))
    return out


def _refused_line(out) -> list[str]:
    """The reads NAMED in the disclosure, as a list.

    Parsed and compared by membership rather than searched for as a
    substring. `"cause" in said` matches *cause of action* and reported this
    feature working when it was returning nothing at all.
    """
    said = " ".join(e.text for e in out.answer.elements)
    m = re.search(r"COULD NOT RUN: ([^.]+)\.", said)
    return [x.strip() for x in m.group(1).split(",")] if m else []


@pytest.mark.parametrize("read", sorted(REACHED_BY))
def test_a_read_that_could_not_run_is_named_to_the_advocate(read, tmp_path):
    """THE CLAIM BK-11 WAS OPENED TO GET, on all fifteen reads."""
    out = _run(_engine(tmp_path, read), REACHED_BY[read])

    named = _refused_line(out)
    assert named, (
        f"the {read} read was refused and the answer does not say a read was "
        f"lost:\n" + " ".join(e.text for e in out.answer.elements)[:700])
    assert read in named, (
        f"the answer says a read could not run and names {named} — not "
        f"'{read}'. An advocate who is not told WHICH read went missing "
        f"cannot supply the thing that went missing.")

    said = " ".join(e.text for e in out.answer.elements)
    assert "recorded as advice" in said, (
        "G-MODEL's second half — that nothing rests on the missing read — is "
        "not stated")


def test_a_turn_whose_reads_all_ran_says_nothing_about_refusals(tmp_path):
    """THE BOUND, and it is the half that makes the rest mean something. A
    disclosure that appears on every turn is one the advocate stops seeing."""
    engine = briefed(TurnEngine(
        store=FileMatterStore(tmp_path, key=KEY), evidence=_Evidence(),
        model=TracedModel(inner=ScriptedModelAdapter(
            _model_config(), responses={"__default__": "File the suit."})),
        elements=CuratedElements()))
    out = engine.run(TurnInput(advocate_id="adv_1", message=PLAIN,
                               today=TODAY))
    assert _refused_line(out) == [], (
        "every read ran and the turn still reported refusals")


# ==================== the mechanism, not the fifteen instances ============

def test_the_disclosure_has_one_owner_wired_at_every_assembly_site():
    """§4: what refuses the second copy?

    There are TWO places an answer is assembled and given its trailer. Adding
    the owner to one is the nine-branch arrangement in miniature — and the
    comment above the first site already says so, about the read before this
    one.
    """
    import inspect

    src = inspect.getsource(TurnEngine)
    wired = src.count("self._refused_reads(metrics)")
    assembled = src.count("self._decisive_empties(metrics)")
    assert wired == assembled, (
        f"the refused-read disclosure is wired at {wired} of the {assembled} "
        f"sites that assemble an answer, so a turn taking the other path "
        f"loses it silently")


def test_the_population_comes_from_the_trace_and_not_from_a_list():
    """`refused_reads` reads the calls the turn actually made. A hand-written
    list of reads beside it is the second owner, and the read added to one and
    not the other is the defect this replaced."""
    import inspect

    src = inspect.getsource(TracedModel.refused_reads)
    assert "self.calls" in src and "c.failed" in src, (
        "the refused reads no longer come from the trace")
    assert not re.search(r"[\"'](?:cause|dates|posture|theory)[\"']", src), (
        "a read is named literally inside the accessor, so the population is "
        "a list somebody maintains rather than what the turn did")


def test_every_declared_read_is_driven_here():
    """THE ACCOUNTING, the same shape as the disclose-gate table.

    Fifteen reads exist in the product's schemas and every one is driven
    above. A read added tomorrow fails this until someone finds the brief
    that reaches it — which is the work, and the alternative is a feature
    that covers fourteen fifteenths of its own population and says nothing.
    """
    declared = {m for p in (ROOT / "nm").rglob("*.py")
                if "__pycache__" not in p.parts
                for m in re.findall(r'"x-nm-read":\s*"([a-z_]+)"',
                                    p.read_text(encoding="utf-8"))}

    missing = sorted(declared - set(REACHED_BY))
    assert not missing, (
        f"these reads exist and nothing here drives them: {missing}")

    stale = sorted(set(REACHED_BY) - declared)
    assert not stale, (
        f"named here and no longer a read in the product: {stale}. A "
        f"declaration that outlives the thing it describes is a false "
        f"statement about the product.")
