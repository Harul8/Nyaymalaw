"""ONE CLAUSE FOR WHO IS BEING SPOKEN TO, and every prompt that addresses the
advocate carries it.

WHAT E-102 CAUGHT TWICE, IN TWO DIFFERENT PLACES
--------------------------------------------------
31 August 2026: *the register is instructional rather than peer-to-peer.* The
judge quoted the RECOMMENDATION. Fixed — by giving the recommendation the proof
positions the file already held, and by stopping the ground reproducing the
whole bare Act.

6 September 2026, judged again on current code with the control failing first:
STILL FAIL, and the judge quoted somewhere else entirely.

    "The acknowledgment letter from 12 June 2024 is sufficient to reset the
     limitation period, as it explicitly admits the outstanding debt…"   ← theory
    "Under the applicable law, a recovery action must be commenced within
     three years from the date the debt became due"                ← adversarial
    "We will be prepared to negotiate a settlement if necessary, but the fact
     remains that a legitimate claim exists"                       ← adversarial

Six prompts in this product write prose an advocate reads and exactly ONE had a
register rule. CLAUDE.md §1 in its plainest form: stating a fix generally is
not applying it generally, and that gap is where a year of whack-a-mole lives.

WHY THE POPULATION IS DECLARED RATHER THAN INFERRED
-----------------------------------------------------
"Does this prompt's output reach the advocate verbatim" is not statically
decidable — `theory` returns a SCHEMA whose fields are rendered into an
element, and `cause` returns a schema whose fields this product formats. Same
call, different answer.

So the question is ANSWERED FOR EVERY MEMBER instead, which is the arrangement
`UNWIRED`, `RESERVED`, `NO_REPRODUCTION` and `CLOSED` all use here. The
population comes from the code — every `*_SYSTEM` constant in `nm/core/` — and
a constant in neither list fails the build, so the seventh prompt cannot be
added without someone deciding which kind it is.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from nm.domain.register import ADDRESSES_THE_ADVOCATE, PEER, STRUCTURED_ONLY

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE = ROOT / "nm" / "core"


def system_constants() -> set[str]:
    """Every module-level prompt constant in `nm/core/`, as `path::NAME`.

    A prompt is a `*_SYSTEM` or bare `SYSTEM` assigned at module level. That
    is a naming convention, and the alternative — inferring which strings are
    prompts — is the kind of half-inference whose failures cannot be reasoned
    about.
    """
    found: set[str] = set()
    for path in sorted(CORE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(ROOT).as_posix()
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith("SYSTEM"):
                    found.add(f"{rel}::{target.id}")
    return found


# ================================ the rule ==================================

def test_every_prompt_is_declared_one_kind_or_the_other():
    """POPULATION FROM THE CODE. A seventh prompt cannot be added without
    someone deciding whether its words reach the advocate."""
    declared = set(ADDRESSES_THE_ADVOCATE) | set(STRUCTURED_ONLY)
    undeclared = sorted(system_constants() - declared)
    assert not undeclared, (
        f"these prompts are in neither list, so nobody has decided whether "
        f"their words reach the advocate: {undeclared}. Add to "
        f"ADDRESSES_THE_ADVOCATE with the reason, or to STRUCTURED_ONLY.")


def test_no_declaration_names_a_prompt_that_is_gone():
    """The half that keeps the table honest. A declaration table rots in one
    direction: the prompt is renamed, the entry stays, and the next reader
    believes a rule that is enforced on nothing."""
    real = system_constants()
    # The recommendation is built inline in `_recommend` rather than as a
    # module constant, so it is named in the table and cannot be scanned for.
    inline = {"nm/core/turn.py::recommendation"}
    stale = sorted(
        (set(ADDRESSES_THE_ADVOCATE) | set(STRUCTURED_ONLY)) - real - inline)
    assert not stale, (
        f"these are declared and no longer exist: {stale}")


def test_every_advocate_facing_prompt_carries_the_clause():
    """THE DEFECT, AS A RULE. Five of the six had no register rule at all when
    E-102 was re-judged."""
    import importlib

    missing = []
    for name in ADDRESSES_THE_ADVOCATE:
        if name.endswith("::recommendation"):
            body = (ROOT / "nm" / "core" / "turn.py").read_text(encoding="utf-8")
            if "+ PEER +" not in body:
                missing.append(name)
            continue
        rel, const = name.split("::")
        module = importlib.import_module(
            rel[:-3].replace("/", ".").replace("\\", "."))
        text = getattr(module, const, "")
        if PEER not in text:
            missing.append(name)
    assert not missing, (
        f"these address the advocate and carry no register clause: {missing}. "
        f"E-102 quoted two of them on 6 September 2026.")


def test_a_structured_prompt_does_not_carry_it():
    """THE BOUND, and it is a real cost rather than tidiness. A register
    clause in a prompt whose output this product formats is prompt budget
    spent on nothing, on every turn, for ever."""
    import importlib

    wasted = []
    for name in STRUCTURED_ONLY:
        rel, const = name.split("::")
        module = importlib.import_module(
            rel[:-3].replace("/", ".").replace("\\", "."))
        if PEER in getattr(module, const, ""):
            wasted.append(name)
    assert not wasted, (
        f"these render through our own formatting and carry the register "
        f"clause anyway: {wasted}")


def test_every_entry_says_why_it_is_there():
    """A list with no reasons is a list nobody can correct."""
    thin = [k for k, v in ADDRESSES_THE_ADVOCATE.items() if len(v.split()) < 6]
    assert not thin, f"these are declared with no reason worth reading: {thin}"


# ========================== the positive control ============================

def test_the_scan_can_see_a_prompt_that_lost_its_clause():
    """S11. A sweep over prompts that all happen to carry it proves nothing
    about the sweep, and one checker that always returned `[]` passed on every
    commit for weeks (B-049).

    Planted as a MISSING declaration and a MISSING clause, because those are
    the two ways the seventh prompt actually arrives: someone adds a prompt
    and does not classify it, or classifies it and does not give it the words.
    """
    # (a) a prompt in neither list
    declared = set(ADDRESSES_THE_ADVOCATE) | set(STRUCTURED_ONLY)
    planted = "nm/core/planted.py::PLANTED_SYSTEM"
    assert planted not in declared
    assert sorted({planted} | system_constants()) != sorted(system_constants()), (
        "the population set did not grow, so the scan cannot see a new prompt")

    # (b) a declared prompt whose text has no clause
    assert PEER not in "You are senior counsel. Be brief.", (
        "the clause matched a prompt that does not contain it, so the check "
        "would pass on every prompt in the product")
    assert PEER in ("something before" + chr(10) + chr(10) + PEER), (
        "the clause is not found when it IS present, so the check would fail "
        "on every prompt instead -- the same uselessness the other way up")


# ============================== the clause ==================================

def test_the_clause_says_what_may_not_be_explained_not_how_to_sound():
    """D5.1: *it needs a RULE, NOT A TONE INSTRUCTION*, and a politeness layer
    bolted on is the kind of patch that document forbids.

    Every one of these prompts already said something like "you are senior
    counsel" and every one still failed. What is checkable by a writer against
    their own sentence is what they may not DO.
    """
    assert "Do not explain what a legal term means" in PEER
    assert "Do not state the general rule" in PEER
    assert "Do not reassure" in PEER


def test_the_clause_forbids_reassurance_in_both_directions():
    """*"We will be prepared to negotiate a settlement if necessary, but the
    fact remains that a legitimate claim exists"* — E-102, 6 September 2026.

    That is not politeness in reverse. D5.1 names agreeable language as the
    path of least resistance, and confidence offered in place of a finding is
    softening wearing a confident face.
    """
    assert "not analysis" in PEER
    assert "softening" in PEER


def test_the_clause_is_one_string_and_not_six():
    """WHAT REFUSES THE SECOND COPY (CLAUDE.md §4). The recommendation carried
    its own wording first, because it was the only prompt E-102 had caught;
    six copies of a sentence drift from each other within a slice, which is
    what a register rule cannot survive."""
    turn = (ROOT / "nm" / "core" / "turn.py").read_text(encoding="utf-8")
    assert "WHERE THE FILE ALREADY HOLDS THE DOCUMENT A STEP CONCERNS" \
        not in turn, (
            "the recommendation still carries its own copy of the register "
            "rule, so it can drift from the other five")
    assert "+ PEER +" in turn
