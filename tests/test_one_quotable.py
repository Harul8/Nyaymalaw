"""B-108 — the prompt and the verbatim guard are one value, everywhere.

WHAT WAS MEASURED, 6 September 2026
-------------------------------------
Every read with a verbatim guard was shown more than it would accept, and
nothing in the prompt said so. On a three-fact matter with one follow-up:

    read          the guard accepted        shown and NOT quotable
    ------------  ------------------------  -----------------------------
    cause         message + advocate words  6 of 8 spans
    posture       message + advocate words  6 of 8 spans
    chronology    the message ONLY          13 of 14 — the whole file
    dispute       the message ONLY          8 of 9
    issues        the account ONLY          2 of 7 — INCLUDING THIS TURN
    factors       account + the entry       6 of 11

B-108 found this the hard way: gpt-5.2 quoted a span across three lines of the
account including our own `[1984-04-15]` stamp, the guard correctly refused
it, the cause was not taken, and the turn was withheld. A weaker model had
quoted one clean sentence and passed. The gap between SHOWN and QUOTABLE
widened the moment the model got better at using its context.

WHY THIS TEST IS A SCAN
-------------------------
The two sides took separate parameters — `build_prompt(message, account)` and
`interpret(message, data, advocate_words)` — so passing different things to
them was not a mistake anyone could see. It is what the signatures asked for.
A review cannot hold six of those in step; a scan can.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.class_a

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "nm"
HOME = PACKAGE / "domain" / "quotable.py"


def _sources():
    out = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        out.append((path, ast.parse(path.read_text(encoding="utf-8"),
                                    filename=str(path))))
    return out


def _rel(path) -> str:
    return path.relative_to(PACKAGE.parent).as_posix()


def containment_guards(sources) -> list[tuple[str, int]]:
    """`fold(a) in fold(b)` — the exact shape all seven guards used.

    Both sides folded with the BASE fold. `nm.core.grounding` asks a different
    question with `_citation_fold` — is this quotation in the retrieved
    authority — and is not swept by this, which is why the check is on the
    call and not on the word "in".
    """
    def _is_fold(node) -> bool:
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "fold")

    found = []
    for path, tree in sources:
        if path == HOME:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare) or len(node.ops) != 1:
                continue
            if not isinstance(node.ops[0], (ast.In, ast.NotIn)):
                continue
            if _is_fold(node.left) and _is_fold(node.comparators[0]):
                found.append((_rel(path), node.lineno))
    return found


def functions_named(sources, needle: str) -> dict[str, list[ast.FunctionDef]]:
    out: dict[str, list[ast.FunctionDef]] = {}
    for path, tree in sources:
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and needle in node.name:
                out.setdefault(_rel(path), []).append(node)
    return out


def _params(fn: ast.FunctionDef) -> list[str]:
    a = fn.args
    return [p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)]


# ================================ the rule ==================================

def test_nothing_decides_the_advocates_words_by_hand():
    """ONE GUARD, AND IT IS `Quotable.accepts`.

    Seven modules each had their own `fold(quoted) not in fold(...)`, and the
    thing on the right differed at every one — which is the whole defect, and
    was invisible because each looked correct where it stood.
    """
    stray = containment_guards(_sources())
    assert not stray, (
        f"these compare a quotation against text by hand instead of asking "
        f"`Quotable.accepts`: {stray}. The prompt cannot then say what the "
        f"guard will take, which is B-108.")


def test_a_read_that_builds_a_prompt_and_a_guard_uses_one_value():
    """THE STRUCTURAL PROPERTY. If both functions take `quotable`, a caller
    handing the prompt one thing and the guard another has to work at it.

    Population from the package: any module with BOTH a prompt builder and a
    reader. `nm/core/quarantine.py` added tomorrow is covered tomorrow.
    """
    sources = _sources()
    builders = functions_named(sources, "build_prompt")
    builders.update({k: v for k, v in
                     functions_named(sources, "build_inventory_prompt").items()
                     if k not in builders})
    readers = {}
    for needle in ("interpret", "read"):
        for mod, fns in functions_named(sources, needle).items():
            readers.setdefault(mod, []).extend(fns)

    wrong = []
    for mod, prompt_fns in sorted(builders.items()):
        reader_fns = [f for f in readers.get(mod, [])
                      if f.name in ("interpret", "read", "read_inventory")]
        if not reader_fns:
            continue
        prompt_takes = any("quotable" in _params(f) for f in prompt_fns)
        guard_takes = any("quotable" in _params(f) for f in reader_fns)
        if prompt_takes != guard_takes:
            wrong.append(
                f"{mod}: prompt takes quotable={prompt_takes}, "
                f"reader takes quotable={guard_takes}")

    assert not wrong, (
        "these build a prompt from one value and check the answer against "
        "another:\n  " + "\n  ".join(wrong)
        + "\n\nBoth take the `Quotable`, or neither does. One of each is how "
          "the prompt came to show what the guard would refuse.")


def test_the_six_reads_are_actually_covered():
    """THE COUNTERPART, and it is not redundant.

    The rule above is satisfied by a module with NO quotable on either side.
    These six are the population B-108 was measured on, named so that removing
    the guard from one of them fails here rather than passing quietly.
    """
    sources = _sources()
    builders = functions_named(sources, "build_prompt")
    builders.update(functions_named(sources, "build_inventory_prompt"))
    readers = {}
    for needle in ("interpret", "read"):
        for mod, fns in functions_named(sources, needle).items():
            readers.setdefault(mod, []).extend(fns)

    for mod in ("nm/core/cause.py", "nm/core/posture.py",
                "nm/core/chronology.py", "nm/core/dispute.py",
                "nm/core/issues.py", "nm/core/factors.py",
                "nm/core/evidence_item.py"):
        assert any("quotable" in _params(f) for f in builders.get(mod, [])), (
            f"{mod} builds a prompt that does not carry what may be quoted")
        assert any("quotable" in _params(f) for f in readers.get(mod, [])), (
            f"{mod} reads an answer without the value its prompt was built "
            f"from")


# ========================== the positive control ============================

def test_the_scan_catches_a_planted_hand_guard():
    """S11. A scan that cannot fail is not a scan."""
    planted = ast.parse('def read(said, account):\n'
                        '    if fold(said) not in fold(account):\n'
                        '        return None\n')
    assert containment_guards([(PACKAGE / "planted.py", planted)]) \
        == [("nm/planted.py", 2)]


def test_the_scan_leaves_a_different_question_alone():
    """THE BOUND. `nm.core.grounding` asks whether a quotation is in the
    RETRIEVED AUTHORITY, which is a different question with a different right
    answer, and folds with `_citation_fold`. A scan that swept it would push
    the citation pivot into the base fold to satisfy itself."""
    planted = ast.parse('def verify(q, corpus):\n'
                        '    if _citation_fold(q) not in _citation_fold(corpus):\n'
                        '        return None\n')
    assert containment_guards([(PACKAGE / "planted.py", planted)]) == []


def test_the_scan_catches_a_prompt_and_a_guard_that_disagree():
    """The mismatch the rule is about, planted directly."""
    tree = ast.parse('def build_prompt(quotable):\n    pass\n'
                     'def interpret(message, data, advocate_words=""):\n    pass\n')
    sources = [(PACKAGE / "planted.py", tree)]
    builders = functions_named(sources, "build_prompt")
    readers = functions_named(sources, "interpret")
    assert any("quotable" in _params(f) for f in builders["nm/planted.py"])
    assert not any("quotable" in _params(f) for f in readers["nm/planted.py"])


# ============================== the behaviour ===============================

def test_the_prompt_says_what_the_guard_will_take():
    """END TO END, on one value: the block names the section, and `accepts`
    takes exactly what the block put in it."""
    from nm.domain.quotable import CONTEXT_HEADING, WORDS_HEADING, Quotable

    q = Quotable(turn="the cheque bounced on 3 March",
                 file="We act for the payee.",
                 context="[2026-03-03] the cheque bounced on 3 March")

    block = q.block()
    assert WORDS_HEADING in block and CONTEXT_HEADING in block
    assert q.accepts("the cheque bounced")
    assert q.accepts("We act for the payee")
    assert not q.accepts("[2026-03-03] the cheque bounced on 3 March"), (
        "the stamped rendering is quotable, which is the exact span gpt-5.2 "
        "was refused for")
    assert not q.accepts("something nobody wrote")


def test_nothing_quotable_is_said_rather_than_left_silent():
    """AN ABSENT INPUT MUST NEVER READ AS PERMISSION. A read handed nothing
    quotable and told nothing about it quotes the context and is refused for
    doing what the prompt implied."""
    from nm.domain.quotable import NOTHING_HEADING, Quotable

    q = Quotable(context="only our own rendering")
    assert NOTHING_HEADING in q.block()
    assert not q.accepts("only our own rendering")
    assert not q.accepts("anything at all")


def test_the_duplication_is_measured_not_assumed():
    """B-115, REPRODUCED. The fix for B-108 shows some sentences TWICE.

    Four reads render the advocate's words as the quotable block AND this
    product's rendering of the same sentences as the context block, and the
    account budget pays for both. The rendering carries the date stamps and
    the basis note, which are real information -- dropping it to save the
    words would be the loss the advocate specifically ruled out -- so the
    duplication stands and this pins it.

    A REPRODUCTION, NOT A FIX. It fails if the duplication grows, and it fails
    if the duplication is closed and nobody closed the row: an open register
    entry nobody re-runs goes on being read after it has stopped being true,
    which B-065 and B-086 both did.

    THE TRADE, STATED. Sixteen extra words in a prompt is cheaper than a turn
    withheld because the model quoted the only copy it was shown. The shape of
    the real fix is in the register: `nm/domain/summary.py` builds `words` and
    `account` from the same facts, so it can render the ANNOTATIONS without
    re-listing the sentences they annotate.
    """
    from nm.domain.quotable import Quotable
    from nm.domain.text import fold

    #: Lines, not one string with newlines in it, so nothing here depends on
    #: an escape surviving a tool that rewrites this file.
    own = ("The agreement to sell is dated 15-4-2024.",
           "We act for the plaintiff at Hyderabad.")
    rendered_lines = ("[2024-04-15] The agreement to sell is dated 15-4-2024.",
                "We act for the plaintiff at Hyderabad.",
                "[How the client KNOWS any of this has not been assessed.]")

    q = Quotable(turn="and is it in time?",
                 file=chr(10).join(own),
                 context=chr(10).join(rendered_lines))
    rendered = fold(chr(10).join(rendered_lines))

    twice = [line for line in own if fold(line) in rendered]
    assert twice, (
        "the advocate's sentences are no longer duplicated between the "
        "quotable block and the context block. If `summary` now renders the "
        "annotations without re-listing what they annotate, B-115 is FIXED "
        "and this should be replaced by a test that it stays fixed.")

    # AND THE BLOCK REALLY CARRIES BOTH. Folding the two inputs proves they
    # overlap; this proves the prompt pays for the overlap.
    block = q.block()
    for line in twice:
        assert block.count(line) == 2, (
            f"{line!r} appears {block.count(line)} time(s) in the prompt, not "
            f"2 -- the measurement below is about a rendering that changed")

    # THE COST, AS A NUMBER. Not a bound anyone chose: the count of words the
    # prompt carries twice, so a change that makes it worse is visible.
    words_twice = sum(len(fold(line).split()) for line in twice)
    assert words_twice == 16, (   # 9 + 7, counted rather than guessed
        f"the duplicated word count moved to {words_twice}. That is not a "
        f"failure in itself; it means the rendering changed and B-115's "
        f"measurement needs re-reading rather than re-pinning.")


def test_the_refusal_says_which_of_the_three_things_went_wrong():
    """Nothing quoted, nothing to check against, and a span that is not
    theirs are three different facts, and the advocate acts differently on
    each."""
    from nm.domain.quotable import Quotable

    q = Quotable(turn="we act for the payee")
    assert "nothing quoted" in q.refusal("")
    assert "advocate wrote" in q.refusal("words never written")
    assert "nothing the advocate has written" in Quotable().refusal("anything")
