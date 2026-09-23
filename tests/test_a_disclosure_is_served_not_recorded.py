"""BK-9 — the five disclose gates nobody proved the advocate ever sees.

WHAT THIS FILE IS FOR, AND WHY IT IS ONE FILE
----------------------------------------------
`tests/test_disclosure_reaches_the_advocate.py` is the ACCOUNTING: every gate
whose response is `disclose` and which is declared built must name either the
test that reads it out of the advocate's own bytes, or the reason nothing
does. On 7 September 2026 it stood at eight proven and five not. This file is
those five.

They are together because they are ONE SHAPE, not five topics — B-128's shape,
stated without the specifics that exposed it: *a gate fires into the metrics,
the matrix records a `visible` promise, and the answer carries nothing.* Five
separate additions to five suites would have been five chances to write four.

WHAT EACH ASSERTS, AND WHAT IT DELIBERATELY DOES NOT
-----------------------------------------------------
Each drives a SERVED turn and reads `out.answer.elements`. None asserts on
`metrics.gates_fired` ALONE, because that assertion holds with the disclosure
never rendered — it is the assertion that let B-128 stand for a slice. Each
also NAMES its gate, so a rename cannot separate the matrix row from the bytes
while both halves stay green.

ONE DOUBLE, NOT FIVE. Three of the five are reachable only when a read fails,
and `_Fails` refuses exactly one read by its `x-nm-read` name. A per-test
adapter would have been the second copy CLAUDE.md §4 asks about — and the
schema already carries the read's name, so nothing had to be invented to
select on.

B-077 DOES NOT CLOSE HERE, THOUGH IT LOOKS AS THOUGH IT SHOULD. It carries
the status *"fixed — unverified on a served turn"*, which reads like this
shape; reading the row shows it is not. What B-077 needs is the DIFFERENTIAL
judge E-073, because the defect was an asymmetry — the recommendation softened
the finding against our own client — and no mechanical assertion on the bytes
can see that. A row that matches on its status line and not on its substance is
the kind of tidy-up that turns a real gap into a closed one.
"""
from __future__ import annotations

from datetime import date

import pytest
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.core.turn import TurnInput
from nm.ports.evidence import Coverage, EvidenceResult
from nm.ports.model import ModelError

from tests.test_turn_contract import _Evidence, _model_config, build, confirmed

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 4)

#: A claim whose period HAS RUN under the twelve years the fixture retrieves.
#: Taken from `test_salvage_on_a_served_turn.py`, where its own guard once
#: caught a brief chosen for the period the author had in mind rather than the
#: one the turn computes.
EXPIRED = ("We act for the plaintiff, a supplier at Hyderabad. Goods were "
           "supplied against invoices on 14 March 2010 and were never paid "
           "for.")

#: TWO DISPUTES TAKE TWO TURNS. `_exposure` calls the model only when the
#: file holds two threads or more; below that `cross_thread` returns
#: NONE_FOUND, which is a finding and not a skip. Both disputes in one
#: message opened ONE thread, and the exposure read was never reached.
FIRST = ("We act for the defendant at Hyderabad in a cheque matter. The "
         "loan was repaid in cash with no receipt.")
SECOND = ("Separately, we have a recovery suit for the same client against "
          "a supplier at Secunderabad.")


#: THE EXPOSURE PASS'S NOT-RUN SENTENCE. Reworded in `602e3f0` from "THE
#: CROSS-FILE PASS DID NOT RUN ... nobody looked" to plain language; the rule
#: -- a refused pass is DISCLOSED and never reads as one that ran clean -- did
#: not change, so both tests below match the one phrase rather than each
#: carrying its own copy of the words.
NOT_COMPARED = "could not establish a complete comparison between these disputes"

class _Fails(ScriptedModelAdapter):
    """Refuses ONE read, by the name the schema already carries.

    `x-nm-read` exists on every structured schema in the product, so selecting
    on it invents no vocabulary and cannot drift from the reads it names. A
    double that refused everything would prove only that a dead model is
    disclosed, and three of the five gates below live on a SINGLE read
    failing while the rest of the turn works.
    """

    def __init__(self, config, read: str, **kw):
        super().__init__(config, **kw)
        self._refuse = read

    def structured(self, prompt, schema, tier, **kw):
        if schema.get("x-nm-read") == self._refuse:
            raise ModelError(f"the {self._refuse} read was refused by a test")
        return super().structured(prompt, schema, tier, **kw)



def _two_thread_file(engine):
    """A file with two disputes on it, and the proof that both opened.

    Without the assertion a fixture that stops opening the second thread
    leaves both exposure tests green while the read they exist for is
    never reached -- which is exactly what the first version of this file
    did, and it looked like a product defect.
    """
    out = None
    for message in (FIRST, SECOND):
        out = engine.run(TurnInput(
            advocate_id="adv_1", message=message, today=TODAY,
            matter_id=out.matter.id if out else None))
    assert len(out.matter.threads) >= 2, (
        "the second dispute did not open, so there is no pair for an "
        "exposure to exist in and the read under test never runs")
    return out


def _served(out) -> str:
    return " ".join(e.text for e in out.answer.elements)


def _fired(out) -> set[str]:
    return {g.gate_id for g in out.metrics.gates_fired}


# ===================== G-EXPOSURE — exactly once, empty or not ============

@pytest.mark.eval_id("E-082")
def test_the_cross_file_pass_is_disclosed_once_on_every_file(tmp_path):
    """E-082's counterexample is *emitted twice, or silently omitted*, and the
    two fail in OPPOSITE directions: twice is noise the advocate learns to
    skip, and omitted reads as "nothing found" when nobody looked.

    Both are byte-level facts. The module test cannot see either, because both
    are about how many times a served answer says it.
    """
    engine, _ = build(tmp_path)
    out = _two_thread_file(engine)

    assert "G-EXPOSURE" in _fired(out), (
        "the cross-file pass did not fire on a file with two disputes")

    lines = [e.text for e in out.answer.elements
             if e.text.startswith("Across this file")
             or NOT_COMPARED in e.text]
    assert len(lines) == 1, (
        f"E-082 wants the section EXACTLY once, empty or not; this answer "
        f"carries {len(lines)}:\n" + "\n".join(lines))


# ===================== G-MODEL — the gap is VISIBLE, not just recorded ====

def test_a_refused_read_is_named_to_the_advocate_and_not_only_to_the_metrics(
        tmp_path):
    """G-MODEL's clause: *the NEED fails, not the turn. The gap is visible and
    nothing is recorded as advice.*

    `test_provider_independence.py` proves both halves of the second sentence.
    Nothing proved the first, which is the one the advocate experiences — a
    turn that quietly drops its cross-file pass reads exactly like a turn that
    ran it and found nothing.
    """
    engine, _ = build(tmp_path, model=_Fails(_model_config(), "exposure",
                                             responses={"__default__": "Act."}))
    out = _two_thread_file(engine)

    assert "G-MODEL" in _fired(out)
    said = _served(out)
    assert NOT_COMPARED in said, (
        "the exposure read was refused and the answer does not say so — an "
        "absent pass and an empty one are opposite facts:\n" + said[:900])
    # THE EXPOSURE PASS'S OWN SENTENCE, not the fragment. "found none"
    # alone also ends G-ADVERSE's clean-state line, which is a perfectly
    # correct thing for a different gate to say on the same turn -- and
    # this assertion broke the day that landed. An assertion on a
    # fragment is an assertion on a coincidence.
    assert "damages another and found none" not in said, (
        "the exposure read was REFUSED and the answer reports it as a "
        "pass that ran and found nothing -- opposite facts")


# ===================== G-NOTASSESSED — not looked at, in those words ======

def test_a_search_that_never_ran_says_so_and_borrows_no_neighbour(tmp_path):
    """Its two neighbours each make a claim about a search that RAN —
    G-NOTHELD that the corpus does not hold it, G-HELDNOTFOUND that retrieval
    failed on something it does. A search that never happened borrowing either
    tells the advocate something untrue.

    The standing "proof" for this gate asserted the phrase appears in
    `inspect.getsource(TurnEngine._derive)`. That holds with the branch
    unreachable, which is how a phrase can be in the product and never in a
    turn.
    """
    engine, _ = build(tmp_path, evidence=_Evidence(EvidenceResult(
        coverage=Coverage.NOT_ASSESSED,
        missing="whether Article 65 or Article 113 governs")))
    out = engine.run(TurnInput(
        advocate_id="adv_1", today=TODAY,
        message="we act for the plaintiff; what is the limitation for possession"))

    assert "G-NOTASSESSED" in _fired(out)
    said = _served(out)
    assert "NOT looked up" in said, (
        "nothing was searched and the answer does not say so:\n" + said[:900])
    assert "Nothing was searched." in said

    # THE HALF THAT MATTERS. Saying it is easy; saying it WITHOUT borrowing a
    # neighbour's claim is the property, and only the bytes carry it.
    assert "not held in the corpus" not in said.lower(), (
        "an unsearched question was reported as absent from the corpus")
    assert "defect in my retrieval" not in said, (
        "an unsearched question was reported as a retrieval failure")


# ===================== G-SALVAGE — the coordinates nobody moved ===========

@pytest.mark.eval_id("E-084")
def test_a_salvage_pass_that_could_not_run_says_so_on_the_served_turn(tmp_path):
    """D8's bound is the harder half: *never manufacture a route*. The failure
    mode this guards is silence — a claim reported as dead with no salvage
    section reads as a claim nobody could save, and a claim whose salvage read
    fell over reads identically.
    """
    # CONFIRMED: salvage answers a period that has run DEFINITIVELY, and a
    # model-selected accrual is conditional until the advocate confirms it.
    engine, store = build(tmp_path, model=_Fails(_model_config(), "salvage",
                                                 responses={"__default__": "Act."}))
    out = confirmed(engine, store,
                    TurnInput(advocate_id="adv_1", message=EXPIRED, today=TODAY),
                    trigger="time runs from the delivery of the goods")

    assert "G-SALVAGE" in _fired(out), (
        "the period has run on this brief and the salvage pass never fired — "
        "if the fixture stopped expiring, this test proves nothing")
    said = _served(out)
    assert "I have NOT varied the coordinates" in said, (
        "the salvage read was refused and the answer is silent about it, so a "
        "claim nobody could save and a claim nobody tried to save read the "
        "same:\n" + said[:900])
    assert "nobody looked" in said


# ===================== G-ADVERSE — the facts nobody answered, by name =====

@pytest.mark.eval_id("E-080")
def test_a_theory_that_could_not_be_formed_does_not_pass_as_one(tmp_path):
    """E-080's counterexample: *a theory that works only if three documents
    are forgotten READS PERFECTLY, because the three are simply not
    mentioned.* Absence is invisible.

    So is an absent theory. A turn whose theory read failed emits no theory
    line, which is exactly what a turn with nothing to say emits.
    """
    engine, _ = build(tmp_path, model=_Fails(_model_config(), "adverse",
                                             responses={"__default__": "Act."}))
    out = engine.run(TurnInput(
        advocate_id="adv_1", today=TODAY,
        message=("We act for the plaintiff at Hyderabad. The agreement is "
                 "dated 15 April 2024 and possession was handed over on "
                 "20 April 2024.")))

    assert "G-ADVERSE" in _fired(out)
    said = _served(out)
    assert "I have not formed a theory on this thread" in said, (
        "the adverse read was refused and the answer does not say the theory "
        "is missing:\n" + said[:900])
    assert "weighed against the adverse facts" in said

def test_a_theory_with_nothing_against_it_says_that_rather_than_going_quiet(
        tmp_path):
    """G-ADVERSE's CLEAN state, which was silent until 7 September 2026.

    Three declared states -- accounted, unaccounted, not_assessed -- and
    the gate emitted on two. On `accounted` it fired and said nothing, and
    where the read found no adverse facts at all the branch was
    `elif read.adverse`, so it did not fire either. An advocate reading a
    theory with no adverse line could not tell which of three things had
    happened: the facts were weighed and answered, none were found, or
    nobody looked.

    E-080's counterexample is a theory that reads perfectly because the
    adverse facts went unmentioned. A silent clean state is that
    counterexample arriving by construction rather than by mistake.

    THE CORRECT COPY WAS NEXT DOOR. `_exposure` already says "I looked
    ... and found none" on a file with no exposure -- E-082's rule, that
    an absent pass and an empty one are opposite facts. This applies the
    same rule at the second site rather than inventing a second wording.
    """
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv_1", today=TODAY,
        message=("We act for the plaintiff at Hyderabad. The agreement is "
                 "dated 15 April 2024 and possession was handed over on "
                 "20 April 2024.")))

    assert "G-ADVERSE" in _fired(out), (
        "the theory read ran and the adverse gate did not fire at all, so "
        "nothing distinguishes a clean pass from one that never happened")
    said = _served(out)
    assert ("adverse fact(s) on this thread and each is either" in said
            or "found none" in said), (
        "the adverse pass reached its clean state and the answer is "
        "silent about it:\n" + said[:900])


# ============ G-SPLIT — the disputes NOT advised on are named =============

#: THREE DISPUTES IN ONE MESSAGE, which is how a file is actually handed over.
#: Enumerated with the ordinals the scripted double marks off on, because the
#: product counts with a model read and the double must reach the same count
#: deterministically.
THREE_AT_ONCE = (
    "We act for the plaintiff. First, goods were supplied against invoices "
    "on 14 March 2010 and were never paid for. Second, a cheque he took "
    "towards that debt came back unpaid last month. Third, the buyer's men "
    "put up a fence across his approach road yesterday."
)


@pytest.mark.eval_id("E-082")
def test_the_disputes_not_advised_on_are_named_in_the_answer(tmp_path):
    """G-SPLIT: the count is REPORTED, and the file is not split on it.

    THIS ONCE ASSERTED THREE THREADS. BK-27 opened one per dispute the count
    read described; that read was then measured at 2-3 of 6 across six
    briefs and unstable on identical input, so the file is no longer split
    on it. What survives is the disclosure -- and the disclosure is now the
    whole mechanism, because `threading.py`'s asymmetry justified splitting
    on the ground that a wrong merge inverts the advice SILENTLY.

    THE METRICS ASSERTION ALONE WOULD HOLD WITH THE LINE INVISIBLE, which is
    B-128's shape and the reason this file exists. If the advocate is not
    told, a brief that read as three disputes becomes one thread in silence.
    """
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id='adv_1', message=THREE_AT_ONCE,
                               today=TODAY))

    assert 'G-SPLIT' in _fired(out), 'G-SPLIT did not fire at all'

    # RE-MEASURED 23 September 2026. The file IS split now, and on different
    # evidence: not the count read BK-27 split on and this test then refused,
    # but SOURCE-BOUND allocation -- every paragraph of the brief assigned to
    # the disputes it belongs to, the shared representation to all of them,
    # and the read refused where any paragraph is left over. What must hold
    # either way is that each dispute is one the advocate actually wrote.
    said_by_advocate = THREE_AT_ONCE.lower()
    for thread in out.matter.threads:
        stem = thread.label.rstrip('…').lower()
        assert stem and stem in said_by_advocate, (
            f'a dispute was opened on words the advocate did not write: '
            f'{thread.label!r}')

    said = [e.text for e in out.answer.elements if e.gate == 'G-SPLIT'
            or 'disputes on the board' in e.text]
    assert len(said) == 1, (
        'the organisation reached the metrics and not the advocate, so a '
        'message that read as several disputes was reorganised in silence: '
        + ' | '.join(e.text[:90] for e in out.answer.elements))
    assert str(len(out.matter.threads)) in said[0], (
        'the advocate is not told how many disputes the file was organised '
        'into: ' + said[0])

    # AND IT INVITES THE CORRECTION. A disclosure the advocate cannot act
    # on is a note, not a question.
    assert 'correct' in said[0].lower(), (
        'the advocate is told the count and not how to correct it: '
        + said[0])

def test_a_single_dispute_file_says_nothing_about_splitting(tmp_path):
    """POSITIVE CONTROL, and the noise half of E-082's counterexample. A
    disclosure that appears on every file is one the advocate learns to skip,
    and this one must appear only where a message actually carried several
    disputes."""
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv_1", today=TODAY,
        message=("We act for the plaintiff, a supplier at Hyderabad. Goods "
                 "were supplied against invoices on 14 March 2010 and were "
                 "never paid for.")))

    said = [e.text for e in out.answer.elements if "NOT ASSESSED" in e.text
            and "separate" in e.text]
    assert not said, f"a one-dispute file was told it had been split: {said}"
