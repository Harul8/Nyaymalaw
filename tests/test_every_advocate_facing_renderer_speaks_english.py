"""EVERY ADVOCATE-FACING RENDERER, NOT ONE SCRIPTED CONVERSATION. J-5-AC1. P36.

WHAT J-5 ACTUALLY SAYS
------------------------
Served text, measured: *"... on thr_634d8e9685be — This damages the defence
..."*, and in History *"TURN 1 · TURN_958000CAFFF4"*.

    *Why the sweep did not catch it.* `test_no_internal_id_reaches_the_advocate`
    drives ONE scripted conversation whose double answers everything with
    "Issue the notice and diarise it." The cross-file exposure section is never
    produced in that fixture, so the sweep cannot see the line that leaks. **Its
    population is a fixture, not the product's advocate-facing surface.**

    *The fix.* Render the thread LABEL. Widen the sweep's population to every
    element-producing path rather than one conversation.

This is the widening. It is STATIC, over the code, so a renderer in a rarely
exercised branch -- a cross-thread section, an error path, a screen nobody's
fixture reaches -- is in the population whether or not any conversation runs
it. The fixture sweep stays: it proves the served path is clean today, and this
proves no path can be written that is not.

WHAT COUNTS AS ADVOCATE-FACING
--------------------------------
Two declared populations, both small enough to read:

    SINK_KWARGS   the keyword arguments that carry text to a person --
                  `text=`, `shown=`, `said=`, `detail=`, `note=`, `label=`
    SINK_METHODS  the methods whose whole job is to produce that text --
                  `render`, `said`, `problems`, `blockers`, `unknowns`, ...

WHAT IS DELIBERATELY NOT IN THEM, and why it is not an oversight:

    `why=` and `as_line()` are the RECORD. An authority refusal has to name
    the person it was about; a refusal nobody can attribute is not a refusal.
    They are exempt HERE and `Ruling.said()` exists so that an advocate-facing
    caller has something to reach for -- which is the fix, not the exemption.

THE PRECISION MATTERS AS MUCH AS THE BREADTH
----------------------------------------------
`f"{thread.label!r}"` is CORRECT and must not fail: taking `.label` off a
thread is the fix, not the defect. So only the interpolated value ITSELF being
an identifier counts -- through `str()`, `repr()`, `or` and a conditional, and
not through an attribute or a call taken off it. A sweep that failed on
`thread.label` would be turned off within a week, and everything behind it
would go back to printing keys.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: THE IDENTIFIER-SHAPED NAMES this product mints, read off the id helpers and
#: the record types rather than guessed. A name here, interpolated straight
#: into advocate-facing text, is a key on a screen.
IDENTIFIERS: frozenset[str] = frozenset({
    "id", "thread", "from_thread", "to_thread", "thread_id", "matter_id",
    "turn_id", "fact_id", "proposal_id", "package_id", "pack_id",
    "handover_id", "decision_id", "source_id", "event_id", "advocate_id",
    "actor_id", "to_actor", "from_actor", "party_id", "node_id",
})

#: The keyword arguments that carry text to a person.
SINK_KWARGS: frozenset[str] = frozenset({
    "text", "shown", "said", "detail", "note", "label", "message",
})

#: The methods whose whole job is producing advocate-facing prose.
SINK_METHODS: frozenset[str] = frozenset({
    "render", "said", "problems", "blockers", "unknowns", "next_step",
    "describe", "explain", "unreachable", "owner_and_next",
    "unlogged_contact", "unsupported_by_report",
})

#: RENDERERS THAT NAME THE ACTOR ON PURPOSE, each with the reason.
#:
#: An admitted exemption is work; a silent one is a surprise. Both of these
#: produce the RECORD of an authority decision, and a decision nobody can
#: attribute is not a decision. `Ruling.said()` is what an advocate-facing
#: caller reaches for instead, so this exemption does not license a screen.
RECORD_RENDERERS: frozenset[str] = frozenset({"as_line", "why"})


def _identifier(expr: ast.expr) -> str:
    """The identifier this expression IS, or "".

    Not the identifiers it MENTIONS. `thread.label` mentions `thread` and is
    the correct rendering; `_label_of(e.from_thread, labels)` mentions
    `from_thread` and is the fix that closed this defect in `turn.py`. Only
    the value itself counts, seen through the wrappers that do not change it.
    """
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) \
            and expr.func.id in ("str", "repr"):
        return _identifier(expr.args[0]) if expr.args else ""
    if isinstance(expr, ast.BoolOp):
        return next((w for w in (_identifier(v) for v in expr.values) if w), "")
    if isinstance(expr, ast.IfExp):
        return _identifier(expr.body) or _identifier(expr.orelse)
    if isinstance(expr, ast.Attribute) and expr.attr in IDENTIFIERS:
        return expr.attr
    if isinstance(expr, ast.Name) and (expr.id.endswith("_id")
                                       or expr.id in IDENTIFIERS):
        return expr.id
    return ""


def _identifiers_in(node: ast.JoinedStr) -> list[str]:
    return [w for value in node.values if isinstance(value, ast.FormattedValue)
            for w in (_identifier(value.value),) if w]


def _leaks_in(tree: ast.AST, where: str) -> list[str]:
    """Every advocate-facing renderer in one module that prints a key."""
    found: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name not in SINK_METHODS or fn.name in RECORD_RENDERERS:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.JoinedStr):
                found += [f"{where}:{node.lineno} {fn.name}() renders {w!r}"
                          for w in _identifiers_in(node)]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg in SINK_KWARGS and isinstance(kw.value, ast.JoinedStr):
                found += [f"{where}:{node.lineno} {kw.arg}= carries {w!r}"
                          for w in _identifiers_in(kw.value)]
    return found


def _population() -> list[tuple[str, ast.AST]]:
    """EVERY MODULE OF THE PRODUCT. Not one conversation, not one package."""
    out = []
    for path in sorted((ROOT / "backend" / "nm").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        out.append((path.relative_to(ROOT).as_posix(),
                    ast.parse(path.read_text(encoding="utf-8"),
                              filename=str(path))))
    return out


# ================================ the sweep ==================================

def test_no_advocate_facing_renderer_prints_one_of_our_keys():
    """THE SWEEP. J-5-AC1's *surface-wide control identifies the leaking
    renderer* -- by file, line and renderer name, so the answer is a place to
    go rather than a fact to argue with."""
    leaks: list[str] = []
    for where, tree in _population():
        leaks += _leaks_in(tree, where)
    assert not leaks, (
        "these renderers put one of this product's own keys in front of an "
        "advocate. Every thread has a LABEL and `nm.domain.spoken.dispute` "
        "renders it; an advocate cannot answer a question addressed to a "
        "database key:\n  " + "\n  ".join(leaks))


# ============================ positive controls ==============================

def test_the_population_is_the_whole_product_and_is_not_empty():
    """A sweep over nothing passes. This is what says it looked."""
    population = _population()
    assert len(population) > 100, len(population)
    assert any(where == "backend/nm/core/turn.py" for where, _ in population)
    assert any(where.startswith("backend/nm/edge/") for where, _ in population)


def test_the_sweep_sees_a_leak_planted_in_a_rarely_exercised_branch():
    """THE BACKLOG'S NEGATIVE CONTROL: *emit an internal identifier through a
    rarely exercised cross-thread section*.

    THE BRANCH IS UNREACHABLE ON PURPOSE. That is the whole point of a static
    population: the fixture sweep could not see this line because no
    conversation produces it, and this one does not care.
    """
    planted = ast.parse(
        "def render(self):\n"
        "    if self.never:\n"
        "        return f'across this file: {self.from_thread} moved'\n"
        "    return 'nothing'\n")
    found = _leaks_in(planted, "planted.py")
    assert found and "from_thread" in found[0], found


def test_the_sweep_sees_a_leak_carried_by_a_keyword_sink():
    planted = ast.parse("Element(kind=k, text=f'the limitation on {thread_id}')")
    assert _leaks_in(planted, "planted.py")


def test_a_leak_behind_str_or_a_fallback_is_still_a_leak():
    """`str(...)` and `or` do not change the value, so they must not hide it.
    Both shapes were in the product when this was written."""
    assert _leaks_in(ast.parse("Node(shown=f'{str(thread_id)}')"), "p.py")
    assert _leaks_in(ast.parse("Node(shown=f'{pack.thread or pack.matter_id}')"),
                     "p.py")


# ============================ negative controls ==============================

def test_the_label_is_not_a_leak():
    """THE FIX MUST NOT FAIL. A sweep that refused `thread.label` would be
    switched off within a week, and everything behind it would go back to
    printing keys."""
    assert _leaks_in(ast.parse("Node(shown=f'the limitation on {thread.label!r}')"),
                     "p.py") == []


def test_a_label_resolved_by_a_call_is_not_a_leak():
    """`_label_of(e.from_thread, labels)` is how `turn.py` closed this exact
    defect. Failing it would revert the fix."""
    assert _leaks_in(
        ast.parse("Element(text=f'on {_label_of(e.from_thread, labels)}')"),
        "p.py") == []


def test_the_key_itself_may_still_carry_the_id():
    """Two strings, because one cannot be both: the key must stay unique
    across threads, or two threads' limitations collide -- a worse defect
    wearing a friendlier name. `name=` is not a sink."""
    assert _leaks_in(ast.parse("Node(name=f'limitation on {thread.id}')"),
                     "p.py") == []


def test_the_record_renderers_are_exempt_and_the_exemption_is_named():
    """An admitted gap is work; a silent one is a surprise. `as_line` and
    `why` name the actor because that is what a record is for."""
    assert "as_line" in RECORD_RENDERERS and "why" in RECORD_RENDERERS
    assert not (RECORD_RENDERERS & SINK_KWARGS)
    assert _leaks_in(
        ast.parse("def as_line(self):\n"
                  "    return f'actor={self.actor_id}'\n"), "p.py") == []


def test_the_advocate_facing_ruling_carries_no_account_id():
    """AND THE EXEMPTION DOES NOT LICENSE A SCREEN. `Ruling.said()` is what an
    advocate-facing caller reaches for, and it says the same thing without
    naming a key."""
    from nm.domain.authority import Act, ActingAs, permits

    said = permits("adv_9f2c11", ActingAs.ADVISING, Act.CONCEDE).said()
    assert "adv_9f2c11" not in said
    assert "may not concede" in said
    # AND THE RECORD STILL NAMES THEM.
    assert "adv_9f2c11" in permits("adv_9f2c11", ActingAs.ADVISING,
                                   Act.CONCEDE).as_line()


def test_an_unlabelled_dispute_is_said_and_never_keyed():
    """The fallback that makes a missing label invisible is the whole shape:
    where no label exists the answer is that there is none."""
    from nm.domain.spoken import dispute

    assert dispute("") == "an unlabelled dispute"
    assert dispute("   ") == "an unlabelled dispute"
    assert dispute("the sale") == "'the sale'"


def _as_line_callers(tree: ast.AST, where: str) -> list[str]:
    return [f"{where}:{node.lineno}" for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "as_line"]


def test_the_audit_line_is_never_rendered_by_the_product():
    """AND THE EXEMPTION DOES NOT LICENSE A SCREEN.

    `as_line` names the actor by account id because a record must. Nothing in
    `backend/nm/` calls it: the refusal path persists `as_dict`, and the one caller
    that existed put the audit line straight into a section an advocate reads
    -- J-5's defect arriving through a new door, written in this release by
    the same person who widened this sweep.

    A future audit path that genuinely needs it adds itself here with the
    reason. An admitted exemption is work; a silent one is a surprise.
    """
    callers: list[str] = []
    for where, tree in _population():
        callers += _as_line_callers(tree, where)
    assert not callers, (
        "these call `Ruling.as_line()`, which names the actor by account id "
        "because it is the RECORD. If the result reaches a person, use "
        "`Ruling.said()`; if it reaches a log, add the site here with the "
        f"reason: {callers}")


def test_that_check_can_see_a_caller():
    """A POSITIVE CONTROL. An empty violation set proves nothing about the
    finder, which is defect shape S11 -- the check that cannot fail."""
    planted = ast.parse("lines = [permits(a, b, c).as_line()]")
    assert _as_line_callers(planted, "planted.py")
