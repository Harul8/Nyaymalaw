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
`f"{dispute(thread.label)}"` is CORRECT and must not fail: taking `.label` off
a thread is the fix, not the defect. (Not `{thread.label!r}` -- see the second
sweep below: `repr` is the wrong renderer for a different reason.) So only
the interpolated value ITSELF being an identifier counts -- through `str()`,
`repr()`, `or` and a conditional, and not through an attribute or a call taken
off it. A sweep that failed on
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
    assert _leaks_in(ast.parse("Node(shown=f'the limitation on {dispute(thread.label)}')"),
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
    from nm.domain.spoken import dispute, named

    assert dispute("") == "an unlabelled dispute"
    assert dispute("   ") == "an unlabelled dispute"
    assert dispute("the sale") == named("the sale")


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


# ===================== the second sweep: never by `repr` =====================
#
# A HELD STRING SET INTO PROSE IS DELIMITED BY `spoken.named`, NEVER BY `repr`.
#
# Measured on 22 September 2026, three of five live matters withheld by G-QUOTE
# on thread labels this product composed itself -- `"Use of firm's mark
# 'VAISHNAVI'"`, `"Injunction against Ravi's intention to sell the property."`.
# `repr` picks its delimiter from the content, so ONE APOSTROPHE turns a label
# into a double-quoted string, and a double-quoted string is exactly what the
# grounding gate reads as a quotation of retrieved text. The gate was right;
# the renderer handed it a quotation nobody made. Same population as the key
# sweep above, because it is the same surface: what a person reads.

#: The live labels that were withheld, verbatim from the transcripts.
_LIVE_LABELS = (
    "Use of firm's mark 'VAISHNAVI'",
    "Injunction against Ravi's intention to sell the property.",
    "The tenant's occupation since 1 August 2019",
)


def _is_repr(value: ast.expr) -> bool:
    if not isinstance(value, ast.FormattedValue):
        return False
    if value.conversion == ord("r"):
        return True
    call = value.value
    return (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and call.func.id == "repr")


def _is_label(value: ast.FormattedValue) -> bool:
    inner = value.value
    if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) \
            and inner.func.id == "repr" and inner.args:
        inner = inner.args[0]
    return isinstance(inner, ast.Attribute) and inner.attr == "label"


def _reprs_in(tree: ast.AST, where: str) -> list[str]:
    """Every advocate-facing renderer that delimits a value with `repr`, and
    every `repr` of a thread label ANYWHERE -- a label also reaches the model's
    prompt, and a model shown a double-quoted label quotes it back."""
    found: list[str] = []
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and fn.name in SINK_METHODS and fn.name not in RECORD_RENDERERS:
            for node in ast.walk(fn):
                if isinstance(node, ast.JoinedStr):
                    found += [f"{where}:{node.lineno} {fn.name}() renders "
                              f"{ast.unparse(v.value)} by repr"
                              for v in node.values if _is_repr(v)]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in SINK_KWARGS | {"question"} \
                        and isinstance(kw.value, ast.JoinedStr):
                    found += [f"{where}:{node.lineno} {kw.arg}= renders "
                              f"{ast.unparse(v.value)} by repr"
                              for v in kw.value.values if _is_repr(v)]
        if isinstance(node, ast.JoinedStr):
            found += [f"{where}:{node.lineno} renders a thread label by repr"
                      for v in node.values if _is_repr(v) and _is_label(v)]
        # AND OUTSIDE AN F-STRING: `return repr(labels[value])` was how the
        # exposure section named a dispute, straight into the answer.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "repr" and node.args \
                and _names_a_label(node.args[0]):
            found.append(f"{where}:{node.lineno} renders a thread label by repr")
    return sorted(set(found))


def _names_a_label(expr: ast.expr) -> bool:
    if isinstance(expr, ast.Attribute):
        return expr.attr == "label"
    if isinstance(expr, ast.Subscript) and isinstance(expr.value, ast.Name):
        return expr.value.id == "labels"
    return False


def test_a_held_string_in_prose_is_never_read_as_a_quotation():
    """THE RULE, on the renderer itself: whatever the string holds, the marks
    around it are not ones G-QUOTE reads as quoting retrieved text."""
    from nm.core.grounding import quoted_spans
    from nm.domain.spoken import dispute, named

    for label in _LIVE_LABELS:
        for rendered in (named(label), dispute(label),
                         f"I am working on {dispute(label)}."):
            assert quoted_spans(rendered) == [], (
                f"{rendered!r} reads as a quotation to the grounding gate")
        # THE DEFECT, stated so this test would have failed on it.
        assert quoted_spans(f"working on {label!r}") != []


def test_a_quotation_the_string_really_carries_is_still_checked():
    """NEGATIVE CONTROL. `named` fixes the DELIMITER and leaves the content
    alone: a double-quoted passage inside the string is a quotation that string
    makes, and hiding it from the gate would be a loosening."""
    from nm.core.grounding import quoted_spans
    from nm.domain.spoken import named

    inner = 'the notice says "possession shall be handed over forthwith"'
    assert quoted_spans(named(inner)) == [
        "possession shall be handed over forthwith"]


def test_the_file_memory_names_a_dispute_without_quoting_it():
    """The served shape: the lines the model reads about a dispute. A model
    shown a double-quoted label quotes it back, and G-QUOTE withholds."""
    from dataclasses import replace

    from nm.core.grounding import quoted_spans
    from nm.domain.matter import Thread
    from nm.domain.summary import _established_on

    thread = replace(Thread.create(label=_LIVE_LABELS[0]),
                     identifiers={"suit_number": "O.S. 12/2026"},
                     deferred_reason="awaiting the licence deed")
    lines = _established_on(thread)
    assert lines and all(_LIVE_LABELS[0] in line for line in lines)
    assert [q for line in lines for q in quoted_spans(line)] == []


def test_no_advocate_facing_renderer_delimits_by_repr():
    """THE SWEEP, over the whole product."""
    found: list[str] = []
    for where, tree in _population():
        found += _reprs_in(tree, where)
    assert not found, (
        "these set a held string into prose with `repr`, whose delimiter "
        "turns to DOUBLE quotes on one apostrophe -- which G-QUOTE reads as a "
        "quotation of retrieved text and withholds. Use "
        "`nm.domain.spoken.named`, or `spoken.dispute` for a thread label:\n  "
        + "\n  ".join(found))


def test_the_repr_sweep_sees_each_shape_it_refuses():
    """POSITIVE CONTROLS, one per shape the sweep claims to catch -- each is a
    site that was in the product on 22 September 2026."""
    assert _reprs_in(ast.parse("Node(shown=f'on {thread.label!r}')"), "p")
    assert _reprs_in(ast.parse("lines.append(f'On {thread.label!r}: x')"), "p")
    assert _reprs_in(ast.parse("R(question=f'Does this belong to {t.label!r}?')"), "p")
    assert _reprs_in(ast.parse(
        "def problems(self):\n    return [f'{self.text!r} is established']\n"), "p")
    assert _reprs_in(ast.parse("Element(text=f'on {repr(x)}')"), "p")
    assert _reprs_in(ast.parse("def f(v, labels):\n    return repr(labels[v])\n"), "p")


def test_the_repr_sweep_leaves_the_record_alone():
    """NEGATIVE CONTROL. An exception or a metric detail is the RECORD, read by
    whoever debugs it, and `repr` there is right: it shows the exact string."""
    assert _reprs_in(ast.parse("raise ValueError(f'unknown {kind!r}')"), "p") == []
    assert _reprs_in(ast.parse("metrics.fire('G', 's', f'said {phrase!r}')"), "p") == []
    assert _reprs_in(ast.parse("Node(shown=f'on {dispute(thread.label)}')"), "p") == []
