"""A GATE THAT DISCLOSES MUST REACH THE BYTES, AND SOMETHING MUST PROVE IT.

**The shape, stated without what exposed it.** A gate whose declared RESPONSE
is `disclose` fires into the metrics, the matrix records a `visible` promise,
and the advocate's answer carries nothing. Nothing here about screens, and
nothing about slice 6 -- that was only the instance.

**B-128 was that instance.** `nm/core/screens.py` had been complete since slice
6 and nothing constructed a `Screen`; `_run_screens` fired `G-UNSCREENED` under
a comment saying *"the output says so rather than reading as though it had
passed"*, and the served answer held ZERO screen-related lines. Every unit test
in the module was green. CLAUDE.md §8 exactly: a guard that is right in the
core and absent from the composition root.

**Then the sweep found the siblings, which is the whole point of sweeping.**
Measured 7 September 2026 over all thirteen built disclose gates: G-HELDNOTFOUND
and G-COVERAGE were each asserted ONLY against `metrics.gates_fired`. Both
tests are green, both would stay green if the disclosure never reached an
`Element`, and both describe in their own comments what the advocate is
supposed to see. *That* is the population -- not one module.

**Why a declaration and not a scanner.** The first attempt scored test lines by
overlap with each gate's `visible` clause. It reported eight of thirteen
covered, and the eight were noise -- a proof test matched G-ADVERSE on two
common words, and G-UNSCREENED, which had just been fixed and does reach the
bytes, came back SILENT. CLAUDE.md §5: fuzzy may RANK, never IDENTIFY. A
check that identifies must match exactly, so every gate is DECLARED and the
declaration is verified against the source.

The shape is `UNWIRED` in `test_reached_from_production.py`, which has worked
here for a slice: an admitted gap is work, a silent one is a surprise.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from nm.domain.gates import GATES, Response

ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

#: What counts as ADVOCATE-FACING. Each is a carrier the advocate actually
#: receives: the answer's elements, the questions put on the file, the served
#: body. `metrics` is deliberately absent -- that is the very distinction this
#: file exists to draw, and adding it here would make the check unfailable.
CARRIERS: tuple[str, ...] = (
    "out.answer",        # the served answer
    "answer.elements",   # its elements, read directly
    "matter.asked",      # a question put to the advocate and kept
    ".answer.elements",
    "resp.json",         # the HTTP body
)

#: gate id -> "file::test". The named test must assert on a CARRIER.
PROVEN: dict[str, str] = {
    "G-UNSCREENED":
        "test_turn_contract.py::"
        "test_every_screen_is_named_to_the_advocate_and_none_reads_as_clear",
    "G-HELDNOTFOUND":
        "test_turn_contract.py::"
        "test_a_held_but_not_found_result_is_a_defect_not_a_disclosure",
    "G-CORRECTION":
        "test_correction_supersedes.py::"
        "test_a_missed_correction_becomes_a_blocking_question",
    "G-PROOF":
        "test_proof_on_a_served_turn.py::"
        "test_an_unwired_element_table_says_so_rather_than_saying_nothing",
    "G-COVERAGE":
        "test_grounding_gate.py::"
        "test_the_corpus_gap_is_disclosed_before_the_authority_search_not_after",
    "G-CASCADE":
        "test_gaps_and_cascade_on_a_served_turn.py::"
        "test_a_corrected_date_moves_the_value_and_says_what_it_was",
    "G-NOTHELD":
        "test_turn_contract.py::"
        "test_a_not_held_result_names_what_is_missing",
    "G-SPLIT":
        "test_a_disclosure_is_served_not_recorded.py::"
        "test_the_disputes_not_advised_on_are_named_in_the_answer",
    "G-EXPOSURE":
        "test_a_disclosure_is_served_not_recorded.py::"
        "test_the_cross_file_pass_is_disclosed_once_on_every_file",
    "G-MODEL":
        "test_a_disclosure_is_served_not_recorded.py::"
        "test_a_refused_read_is_named_to_the_advocate_and_not_only_to_the_metrics",
    "G-NOTASSESSED":
        "test_a_disclosure_is_served_not_recorded.py::"
        "test_a_search_that_never_ran_says_so_and_borrows_no_neighbour",
    "G-SALVAGE":
        "test_a_disclosure_is_served_not_recorded.py::"
        "test_a_salvage_pass_that_could_not_run_says_so_on_the_served_turn",
    "G-ADVERSE":
        "test_a_disclosure_is_served_not_recorded.py::"
        "test_a_theory_that_could_not_be_formed_does_not_pass_as_one",
    "G-READ":
        "test_reads_registry.py::"
        "test_the_turn_discloses_which_read_came_back_empty",
}

#: gate id -> WHY nothing proves the advocate sees it. Six of the thirteen,
#: enumerated MECHANICALLY on 7 September 2026 rather than read off by eye --
#: which matters, because the first pass at this table put G-HELDNOTFOUND and
#: G-COVERAGE here on the strength of their first assertions and both had the
#: carrier assertion four lines further down. A wrong NOT_PROVEN row is worse
#: than none: it invents work and it slanders a test that was doing its job.
NOT_PROVEN: dict[str, str] = {
    # EMPTY, as of 7 September 2026 -- all thirteen are proven on the
    # advocate's own bytes. BK-9 closed the last five.
    #
    # THE TABLE STAYS. An empty exception list that has been deleted
    # cannot record the next exception, and the next gate to be added
    # with `disclose` and no served test needs somewhere honest to go --
    # the accounting check below fails the build until it has one.
    # Deleting this would turn that failure into a puzzle.
}


def _built_disclose() -> list[str]:
    """The population, FROM THE MATRIX and not from this file."""
    return [g.id for g in GATES
            if g.response is Response.DISCLOSE and g.built]


def _body(spec: str) -> str:
    """The source of the test a declaration names, PLUS the helpers it
    calls from its own module.

    ONE LEVEL OF INDIRECTION, DELIBERATELY. A suite that drives five
    served turns puts `out.answer.elements` in a helper, and reading only
    the test function called those five proof of nothing -- measured, on
    the five this check was built to accept.

    It is not a widening of CARRIERS. `metrics` still fails, at either
    level: the distinction this file exists to draw is between what the
    advocate receives and what the run recorded, and a helper that reads
    the metrics proves exactly as little as a test that does.
    """
    filename, _, name = spec.partition("::")
    path = TESTS / filename
    assert path.exists(), f"{spec} names a file that does not exist"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    defined = {n.name: n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)}
    node = defined.get(name)
    assert node is not None, f"{spec} names a test that does not exist"

    out = [ast.get_source_segment(src, node) or ""]
    for call in ast.walk(node):
        if (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in defined
                and call.func.id != name):
            out.append(ast.get_source_segment(src, defined[call.func.id])
                       or "")
    return "\n".join(out)

def test_every_built_disclose_gate_is_accounted_for():
    """Thirteen gates, thirteen declarations. A gate added to the matrix with
    `disclose` and `built` and no row here fails the build -- which is the
    difference between this and the comment that was already in `_run_screens`
    claiming the output said so."""
    population = set(_built_disclose())
    declared = set(PROVEN) | set(NOT_PROVEN)

    missing = sorted(population - declared)
    assert not missing, (
        "these gates DISCLOSE, are declared built, and nothing says whether "
        "the advocate ever sees them:\n  " + "\n  ".join(missing)
        + "\n\nAdd a PROVEN entry naming the test that asserts on the answer, "
        "or a NOT_PROVEN entry saying what is missing. B-128 is what the "
        "second kind prevents becoming: a promise in the matrix and silence "
        "in the bytes.")

    stale = sorted(declared - population)
    assert not stale, (
        "declared here and no longer a built disclose gate:\n  "
        + "\n  ".join(stale) + "\n\nA declaration that outlives its gate is a "
        "false statement about the product, which is B-127's rule for the "
        "backlog applied to this table.")

    both = sorted(set(PROVEN) & set(NOT_PROVEN))
    assert not both, f"declared as both proven and not proven: {both}"


@pytest.mark.parametrize("gate", sorted(PROVEN))
def test_a_proven_gate_names_a_test_that_asserts_on_the_advocates_bytes(gate):
    """THE HALF THAT MAKES THE DECLARATION MEAN SOMETHING.

    Naming a test is easy and a test that asserts on `gates_fired` proves the
    metric, not the disclosure. So the named test must touch a CARRIER -- and
    `metrics` is not one, deliberately.
    """
    body = _body(PROVEN[gate])
    assert any(c in body for c in CARRIERS), (
        f"{PROVEN[gate]} is named as proof that the advocate sees {gate}, and "
        f"it asserts on none of {CARRIERS}. If it checks `gates_fired`, it "
        f"holds with the disclosure never rendered -- exactly the assertion "
        f"that let B-128 stand for a slice.")


def test_a_not_proven_row_carries_a_reason_and_not_a_category():
    """"Deferred" is indistinguishable from forgotten. Every row says what is
    asserted TODAY and what is not, so the next person can close it without
    re-deriving the measurement."""
    for gate, why in NOT_PROVEN.items():
        assert len(why) > 60, f"{gate}: {why!r} is a label, not a reason"
        assert "assert" in why.lower() or "module" in why.lower(), (
            f"{gate}: the reason does not say what IS checked today, so "
            f"nobody can tell how far off closing it is")


# ============ the positive controls ========================================
#
# CLAUDE.md: a sweep must plant a bad member. Both of these were run RED
# before the fixtures were added -- a check that has never failed is S11.

def test_the_check_can_see_an_undeclared_gate():
    """Plant a built disclose gate that nothing declares."""
    population = set(_built_disclose()) | {"G-PLANTED"}
    assert sorted(population - (set(PROVEN) | set(NOT_PROVEN))) == [
        "G-PLANTED"], (
        "the accounting check cannot see a gate that is missing from both "
        "tables, so it would pass on the next G-UNSCREENED")


def test_the_check_can_see_a_declaration_that_proves_only_the_metric():
    """Plant the exact assertion that let B-128 stand: a test that checks
    `gates_fired` and nothing the advocate receives."""
    metric_only = (
        "def test_x():\n"
        "    fired = {g.gate_id: g for g in out.metrics.gates_fired}\n"
        "    assert 'G-HELDNOTFOUND' in fired\n")
    assert not any(c in metric_only for c in CARRIERS), (
        "`metrics.gates_fired` satisfies CARRIERS, so the proof check cannot "
        "fail and every PROVEN row is decoration")
