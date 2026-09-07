"""WHICH PARAGRAPH LABELS MAY BE QUOTED IS ONE FACT. It had six owners.

`("ratio", "reasoning", "order")` was written out, by hand, in six places:

    nm/adapters/evidence/corpus.py   what a Finding may be built from
    tools/build_authority_index.py   what goes INTO the searchable index
    tools/releasegate.py             what RG-04 counts as retrievable
    tools/find_goldens2.py           which judgments qualify as anchors
    tools/verify_set.py              the same, for the golden set
    tools/classify_paragraphs.py     what the classifier eval scores

All six agreed on the day this was written, which is exactly why nobody
noticed. Two of them are load-bearing against each other: the index builder
decides what the corpus can retrieve and `RG-04` measures whether enough of it
IS retrievable. One list moving without the other is a blocking release
criterion scoring an index it is not describing -- B-044 verbatim, where a
zero from the wrong key read as absence and reached the advocate.

CLAUDE.md §4 asks the question this file answers: not "where is the other
copy" but WHAT MAKES A SECOND COPY IMPOSSIBLE. `nm/ports/evidence.py` owns
the mapping; `ATTRIBUTABLE_LABELS` is derived from it and never authored; and
this refuses the seventh copy at the build.

THE POPULATION IS THE WHOLE PRODUCT, not one package. `nm/` and `tools/` are
both scanned, because five of the six copies were in `tools/` and a checker
scoped to `nm/` would have found exactly one of them.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from nm.ports.evidence import ATTRIBUTABLE_LABELS, ParaKind, kind_for_corpus_label

ROOT = Path(__file__).resolve().parents[1]

#: The labels whose co-occurrence in one literal IS the duplicated fact.
FINGERPRINT = {"ratio", "reasoning", "order"}

#: The one module allowed to write them down.
OWNER = Path("nm") / "ports" / "evidence.py"


def _literal_label_sets(tree: ast.AST) -> list[int]:
    """Line numbers of every literal collection carrying the fingerprint.

    Tuples, lists, sets AND dict keys -- the six copies used three of those
    four shapes between them, and a checker that knew only about tuples would
    have missed the release gate's set and passed while the defect stood.
    """
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            items = node.elts
        elif isinstance(node, ast.Dict):
            items = [k for k in node.keys if k is not None]
        else:
            continue
        strings = {e.value.strip().lower() for e in items
                   if isinstance(e, ast.Constant) and isinstance(e.value, str)}
        if FINGERPRINT <= strings:
            out.append(node.lineno)
    return out


def _sources() -> list[Path]:
    files = [p for d in ("nm", "tools") for p in (ROOT / d).rglob("*.py")]
    assert len(files) > 40, f"only {len(files)} files scanned -- the walk is broken"
    return files


def test_only_one_module_writes_down_the_attributable_labels():
    offenders = []
    for path in _sources():
        rel = path.relative_to(ROOT)
        if rel == OWNER:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf8"))
        except SyntaxError:  # pragma: no cover -- a broken file is another test's job
            continue
        for line in _literal_label_sets(tree):
            offenders.append(f"{rel.as_posix()}:{line}")

    assert not offenders, (
        "the attributable paragraph labels are written down outside "
        f"{OWNER.as_posix()}:\n  " + "\n  ".join(offenders) +
        "\n\nImport ATTRIBUTABLE_LABELS instead. Six hand-written copies is "
        "where this started, and the index builder and RG-04 disagreeing is a "
        "release criterion measuring an index it does not describe."
    )


def test_the_checker_can_actually_fail():
    """THE POSITIVE CONTROL. S11: a check that cannot fail proves nothing.

    Each of the four literal shapes the scanner claims to catch is put to it,
    because the six real copies used three different shapes and a scanner that
    silently handled only tuples would pass this file's other test for the
    wrong reason.
    """
    shapes = (
        'X = ("ratio", "reasoning", "order")',
        'X = ["ratio", "reasoning", "order"]',
        'X = {"ratio", "reasoning", "order"}',
        'X = {"ratio": 1, "reasoning": 2, "order": 3}',
    )
    for src in shapes:
        assert _literal_label_sets(ast.parse(src)), f"not caught: {src}"

    # And it does NOT fire on a collection that merely shares a word.
    assert not _literal_label_sets(ast.parse('X = ("ratio", "facts")'))


def test_the_derived_list_cannot_drift_from_the_mapping():
    """`ATTRIBUTABLE_LABELS` is computed, so this is a statement about the
    mapping, not a second copy of it: every label in the list is attributable
    and every label outside it is not."""
    assert ATTRIBUTABLE_LABELS, "the product can quote nothing"
    for label in ATTRIBUTABLE_LABELS:
        assert kind_for_corpus_label(label).attributable, label
    for label in ("arguments", "facts", "headnote", "unknown"):
        assert not kind_for_corpus_label(label).attributable, label


@pytest.mark.parametrize("absent", ["", "   ", None, "no_such_label"])
def test_an_unrecognised_label_is_unknown_and_not_a_reading(absent):
    """S1, and §9's third state. `NOT_ATTRIBUTABLE` says a human or a model
    READ this paragraph and it is not the court deciding. A label nobody
    recognises has been read by nobody, and collapsing the two would let an
    absent input report itself as a finding."""
    assert kind_for_corpus_label(absent) is ParaKind.UNKNOWN


def test_the_three_states_are_exactly_three():
    """Not four, and not two. Two would force 'nobody classified this' and
    'this is counsel' into one value; the seven it replaced carried four
    distinctions no caller ever read."""
    assert [k.value for k in ParaKind] == [
        "attributable", "not_attributable", "unknown"]
