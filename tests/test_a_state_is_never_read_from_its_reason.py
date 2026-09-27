"""A STATE IS NEVER READ FROM ITS REASON'S WORDS.

THE MEASURED DEFECT, 26 September 2026. `authority_weight.weigh` decided that
two benches were CO-ORDINATE by finding the word "co-ordinate" in the reason
`identity.supersedes` wrote -- because `Precedence` had one value for a finding
(equal benches) and a gap (an unrecorded bench). Reword the sentence and the
advocate is told a conflict is a gap, or the reverse, with nothing failing.

THE RULE: a decision is made on a value. No code in the product may branch on
whether a phrase occurs in a `why`, `reason` or `because` string. The scan's
population is every module under backend/nm; the counterexample it must reject
is the code this replaced.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
PROSE = {"why", "reason", "because"}


def _reads_a_state_from_prose(tree: ast.AST) -> list[int]:
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or not isinstance(node.ops[0], (ast.In, ast.NotIn)):
            continue
        phrase, target = node.left, node.comparators[0]
        name = (target.id if isinstance(target, ast.Name)
                else target.attr if isinstance(target, ast.Attribute) else "")
        if isinstance(phrase, ast.Constant) and isinstance(phrase.value, str) and name in PROSE:
            lines.append(node.lineno)
    return lines


def test_no_state_in_the_product_is_decided_by_a_phrase_in_its_reason():
    offenders = []
    for path in (ROOT / "backend" / "nm").rglob("*.py"):
        for line in _reads_a_state_from_prose(ast.parse(path.read_text(encoding="utf-8"))):
            offenders.append(f"{path.relative_to(ROOT).as_posix()}:{line}")
    assert offenders == [], f"a state is read from a reason's words: {offenders}"


def test_the_scan_rejects_the_code_it_replaced():
    """The counterexample: the line authority_weight carried until 26 September."""
    replaced = ('standing = (Standing.CO_ORDINATE if "co-ordinate" in why\n'
                '            else Standing.NOT_RECORDED)\n')
    assert _reads_a_state_from_prose(ast.parse(replaced)) == [1]
