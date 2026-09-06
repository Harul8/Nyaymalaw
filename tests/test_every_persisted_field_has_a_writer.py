"""EVERY FIELD ON THE ADVOCATE'S RECORD IS WRITTEN BY SOMETHING, or says why not.

WHY THIS EXISTS
-----------------
A dataclass field is a PROMISE that something computes it. Nothing in this
build checked the promise, and three defects were found one at a time, by
hand, each fixed on its own:

    B-073  `Factor`         the s.18 acknowledgement read did not exist
    B-086  `superseded_by`  a correction had nowhere to land
    B-088  `conflicts_with` found while fixing B-088, still unwritten

A population being discovered one member at a time is a population with no
enumerator. CLAUDE.md's own rule: a shape with N defects and N unrelated fixes
is N places for the N+1th to hide -- and `conflicts_with` WAS the N+1th, found
by accident rather than by a check. On the first run of this sweep the real
count was TWELVE.

WHY A PERMANENTLY EMPTY FIELD IS DANGEROUS AND NOT MERELY UNTIDY
------------------------------------------------------------------
It reads as a capability from every direction that matters -- the type, the
PRODUCES contract, the record shown to the advocate -- and its emptiness is
indistinguishable from a matter where the thing genuinely did not happen.
That is S1, an absent input reading as success, and it reached the advocate:
`Posture.opponent` had no producer at all, while the record projection
rendered `"against": "unknown"` and the matter summary omitted the line. An
advocate who had named the other side was told, on every turn, that the
opponent was unknown.

THE POPULATION IS THE PERSISTED CLOSURE, WALKED AT RUNTIME
-------------------------------------------------------------
Not a list of types. Everything reachable from `Matter` by field type, which
is exactly what the store writes to disk and reads back -- so a field added to
a sibling type tomorrow is in the population without anyone remembering to add
it. That is the lesson of
`test_every_declared_schema_is_satisfiable_when_nothing_was_established`,
which was written against one module in the morning and was blind to a sibling
by the afternoon.

WHY WRITERS AND NOT READERS
-----------------------------
A reader can only be found by attribute NAME, and names collide across types:
`applied` is a field of `PostureConflict` and also an enum member read in
`limitation.py`, and `document` belongs to both `Provenance` and
`DocumentFact`. A scan that counts those as readers passes for the wrong
reason, which is S11 -- a check that cannot fail. Writers are keyword
arguments, which resolve to the call being made. Asking a question the scan
can actually answer is worth more than asking the fuller one badly.

The store's decoder cannot make a field look written: it builds every type
generically through `cls(**{...})` and names no field at all.
"""
from __future__ import annotations

import ast
import dataclasses
import pathlib
import typing

import pytest

from nm.domain.matter import Matter

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ============================== the population ==============================

def _parts(annotation):
    yield annotation
    for arg in typing.get_args(annotation):
        yield from _parts(arg)


def persisted_types() -> tuple[type, ...]:
    """Everything reachable from `Matter` by field type.

    `Matter` is what the store commits, so its closure is the whole of the
    advocate's record and nothing else. Walked rather than listed, because a
    list is a thing to forget to update.
    """
    seen: dict[type, None] = {}

    def walk(t) -> None:
        if not (isinstance(t, type) and dataclasses.is_dataclass(t)):
            return
        if t in seen:
            return
        seen[t] = None
        for annotation in typing.get_type_hints(t).values():
            for part in _parts(annotation):
                walk(part)

    walk(Matter)
    return tuple(seen)


def optional_fields() -> tuple[tuple[type, dataclasses.Field], ...]:
    """A field with a default is one the caller may leave alone.

    A field WITHOUT one cannot be silently empty: every construction has to
    pass it, so the compiler is already the check. Only the optional ones can
    be permanently unset while looking deliberate.
    """
    return tuple(
        (t, f)
        for t in persisted_types()
        for f in dataclasses.fields(t)
        if f.default is not dataclasses.MISSING
        or f.default_factory is not dataclasses.MISSING)


# ================================ the writers ===============================

def _keywords(tree: ast.AST) -> tuple[set[str], set[str]]:
    """(`Class.field` where the write could be attributed, bare `field` else).

    A DIRECT CONSTRUCTOR CALL SAYS WHICH TYPE IT WRITES. `replace(x, ...)`
    does not -- `x` is a name and its type is not statically known here -- so
    those stay bare and match any class holding that field.

    A class is a capitalised callable, which is the one convention this
    codebase actually follows. A helper named like a class would make this
    MORE precise, never less: the write would be attributed to a type that has
    no such field, and match nothing.
    """
    attributed: set[str] = set()
    bare: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = (node.func.id if isinstance(node.func, ast.Name)
                  else node.func.attr if isinstance(node.func, ast.Attribute)
                  else "")
        named = bool(target) and target[0].isupper()
        for kw in node.keywords:
            if not kw.arg:
                continue
            (attributed if named else bare).add(
                f"{target}.{kw.arg}" if named else kw.arg)
    return attributed, bare


def _swept(package: str) -> tuple[set[str], set[str]]:
    attributed: set[str] = set()
    bare: set[str] = set()
    for path in sorted((ROOT / package).rglob("*.py")):
        a, b = _keywords(ast.parse(path.read_text(encoding="utf8")))
        attributed |= a
        bare |= b
    return attributed, bare


def written_in(package: str) -> set[str]:
    """Every field name written anywhere under `package`, BARE.

    What "is this field ever written at all" wants, and what the two coverage
    checks below ask. The reservation check asks a narrower question and uses
    `written_precisely`.
    """
    attributed, bare = _swept(package)
    return bare | {name.split(".")[-1] for name in attributed}


def written_precisely(package: str) -> tuple[set[str], set[str]]:
    """(`Class.field` writes, bare writes that could not be attributed).

    Kept separate so a caller has to decide which it means. Collapsing them is
    what let `ProofPosition(material=...)` retire `Fact.material`.
    """
    return _swept(package)


# ========================== the declared reservations =======================

RESERVED: dict[str, str] = {
    # -- guarded, so the reservation cannot rot into a silent gap ------------
    "Provenance.document":
        "`Provenance.__post_init__` REFUSES a `kind='document'` provenance "
        "without it, so the first document-sourced fact either carries it or "
        "fails loudly. Nothing writes it because nothing produces document "
        "facts yet -- `nm.core.intake` is declared UNWIRED in "
        "test_reached_from_production.",
    "Provenance.page":
        "The same guard, the same clause. Written or refused together with "
        "`document`; neither can arrive without the other.",

    # -- a third state, which is a VALUE and is the point of the field -------
    "Fact.weight":
        "Weight.NOT_ASSESSED, same shape. `evidence_item` refuses a weight "
        "asserted without a reason, so the graded states cannot arrive "
        "quietly; the ungraded state is what an unweighted fact honestly is.",

    # -- guarded, and awaiting the read that fills them ----------------------
    "Fact.basis_source":
        "`Fact.__post_init__` refuses a basis that NEEDS a source without "
        "one, so this cannot be empty for the states that require it. Empty "
        "is correct for the states that do not.",
    "Fact.exact_words":
        "`Fact.quoted` returns '' rather than guessing, and every quote gate "
        "reads `quoted`. A fact with no verbatim record is one that may not "
        "be quoted, which is the intended behaviour and not a gap.",
    "Fact.material":
        "Defaults TRUE, so the empty case is the INCLUSIVE one: a fact nobody "
        "graded is treated as material and reaches the proof position. The "
        "dangerous direction would be defaulting false and silently dropping "
        "it.",

    # -- OPEN, and named as open --------------------------------------------
    "Fact.confirmed":
        "OPEN (B-091). Confirmation is read by the intake path, which is "
        "UNWIRED. Unlike `document` there is NO GUARD: a fact that was never "
        "put to the advocate and one they declined to confirm are both None. "
        "Wire with intake, or split the state.",
    "Fact.confirmed_at":
        "OPEN (B-091), and the same clause as `confirmed` -- it is the "
        "timestamp of a confirmation that nothing records yet.",
    "Fact.conflicts_with":
        "OPEN (B-091). No writer AND no reader: the contradiction read that "
        "would fill it does not exist. Kept rather than deleted because the "
        "adverse-fact pass in D8 is where it belongs, and deleting it would "
        "lose the only record that the question was asked.",
    "PostureConflict.applied":
        "OPEN (B-091). `Posture.conflicts` is written; this flag on the "
        "conflict is not, so a conflict that has been acted on and one that "
        "has not are the same value. It is False for both.",
}


# ================================ the checks ================================

def test_the_scan_can_see_the_record():
    """A positive control on the POPULATION.

    If the closure walk returned nothing -- a resolution failure under `from
    __future__ import annotations` would do it silently -- every check below
    would pass while looking at an empty set. It did exactly that on the first
    attempt: field types were strings, nothing recursed, and the walk found
    `Matter` alone.
    """
    types = {t.__name__ for t in persisted_types()}
    assert {"Matter", "Thread", "Posture", "Fact", "Provenance"} <= types, (
        f"the persisted closure did not resolve past Matter: {sorted(types)}")
    assert len(optional_fields()) > 20, (
        "the field scan found almost nothing, which is the shape of a walk "
        "that stopped early rather than a record with no optional fields")


def test_the_scan_can_see_a_field_nothing_writes():
    """A positive control on the MECHANISM.

    A sweep that cannot fail is S11. Planted on the real scan rather than a
    fixture: a name no code in `nm/` passes as a keyword must come back
    unwritten, or the writer set is matching too broadly and every field looks
    written.
    """
    written = written_in("nm")
    assert "no_such_field_is_ever_written_anywhere" not in written
    assert "facts" in written, (
        "a field that IS written did not appear, so the scan is not reading "
        "the package")


def test_every_persisted_field_has_a_writer_or_is_declared_reserved():
    """THE SWEEP.

    Asked the other way -- does every writer target a real field -- it would
    confirm that the fields being written exist, which cannot fail. This asks
    which fields NOTHING writes, which is the only direction that finds
    anything.
    """
    written = written_in("nm")
    unwritten = [f"{t.__name__}.{f.name}"
                 for t, f in optional_fields() if f.name not in written]
    undeclared = [name for name in unwritten if name not in RESERVED]

    assert not undeclared, (
        "these fields are on the advocate's record and nothing in nm/ ever "
        "writes them. Each reads as a capability and is permanently empty, "
        "which is indistinguishable from the thing not having happened "
        "(S1). Wire it, delete it, or declare it in RESERVED:\n  "
        + "\n  ".join(undeclared))


def test_no_reservation_outlives_its_writer():
    """The half that keeps the table honest.

    A declaration table rots in ONE direction: a field gets wired, the entry
    stays, and the next reader of this file believes a gap that has been
    closed. Same arrangement as `UNWIRED` in test_reached_from_production and
    `CLOSED` in test_three_states.
    """
    attributed, bare = written_precisely("nm")
    # ATTRIBUTED FIRST, AND THE BARE SET IS THE FALLBACK. A constructor call
    # says which type it writes: `ProofPosition(material=...)` is not a writer
    # of `Fact.material`, and reading the bare name alone said it was -- which
    # would have deleted a reservation carrying a real reason.
    #
    # `replace(x, field=...)` stays bare and still matches by name, so this is
    # conservative where it cannot be precise: it asks a question rather than
    # retiring an answer.
    stale = [name for name in RESERVED
             if name in attributed or name.split(".")[-1] in bare]
    assert not stale, (
        "these are declared as having no writer and something now writes "
        "them. Delete the entry:\n  " + "\n  ".join(stale))


def test_every_reservation_names_a_field_that_exists():
    """A reservation for a field that was renamed or deleted protects nothing
    and reads as though it does."""
    real = {f"{t.__name__}.{f.name}" for t, f in optional_fields()}
    gone = [name for name in RESERVED if name not in real]
    assert not gone, (
        "RESERVED names fields the record does not have:\n  "
        + "\n  ".join(gone))


def test_the_open_reservations_say_they_are_open():
    """A reservation that is WORK must read as work.

    The four B-091 entries are gaps with no guard behind them. If they were
    written in the same voice as the guarded ones, they would read as settled
    and stop being work -- which is how the first three of these defects
    survived long enough to be found by hand.
    """
    for name, why in RESERVED.items():
        assert why.strip(), f"{name} is declared with no reason"
        if "B-091" in why:
            assert why.startswith("OPEN"), (
                f"{name} names the open defect but does not read as open")
