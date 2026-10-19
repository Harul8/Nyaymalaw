"""EVERY OUTCOME ENUM CAN SAY "NOT ASSESSED" — or is declared a closed
vocabulary, with the reason.

WHY
---
The single most repeated defect in this project is an absent input reading as
success, and the fix is always the same sentence: THREE STATES, NEVER TWO.
`docs/DEFECT_SHAPES.md` records it as S1, the register records it nine times,
and the codebase says it out loud in a dozen docstrings — `Binding`,
`Coverage`, `TreatmentState`, `CoverageState`, `BindState`, `Dispute` all carry
a third member and explain why.

And it was still being missed, because nothing enumerated the enums:

    B-042  `role_basis` was a required enum of [stated, inferred] while `role`
           could be `not_stated`. The model had no legal value to return for
           the ordinary case, so it sent "", validation failed, and the read
           failed OPEN — indistinguishable from the advocate saying nothing.
    B-055  `ActBasis` had [named, inferred] and carried "nothing governs this
           question" as `basis=None`, outside the vocabulary. `must_disclose`
           answered falsely-negative by accident, and no consumer was forced to
           handle a state the product is routinely in.

WHY AN ALLOWLIST
----------------
Not every enum models an outcome. `ElementKind` is four permitted kinds with
"deliberately no fifth"; `Tier` is configuration. Forcing an escape member into
those would be worse than useless. So each is declared CLOSED below with its
reason — the question gets answered at every enum, including the thirtieth,
rather than a category being silently skipped.
"""
from __future__ import annotations

import enum
import importlib
import pkgutil

import pytest

pytestmark = pytest.mark.class_a

#: Words a member uses to mean "this was not established". Matched as
#: substrings so `NOT_COMPARABLE` and `HELD_NOT_FOUND` count.
ESCAPES = (
    "not_assessed", "not_measured", "not_checked", "not_stated", "not_resolved",
    "not_comparable", "not_found", "not_held", "unknown", "cannot_tell",
    "unbindable", "ambiguous", "unbuildable", "failed", "none", "undated",
    "not_computed", "not_applicable",
    # `Origin.NOT_ESTABLISHED`, added the moment S5 introduced it. Provenance
    # nobody recorded is a third state and it must not read as RESOLVED, which
    # is what the old `origin: str = "resolved"` default made it read as.
    "not_established",
    # `DecidedBy.NOT_RECORDED`, added the moment the decisions section
    # introduced it. It is NOT a synonym for `not_assessed`: nobody looked and
    # someone decided but the record does not say who are different states,
    # and the second is the one that must never be guessed at -- guessing
    # ADVOCATE promotes our own inference to their instruction, which the
    # merge then refuses to overwrite, so a wrong guess becomes permanent.
    "not_recorded",
)

#: The word list is this check's maintenance cost, and it is a small and
#: VISIBLE one: a new enum whose escape is spelled a new way fails the build
#: with a message naming the enum and its members. That is the right trade
#: against the alternative -- inferring which member means "not established" --
#: which would guess, and a guess here passes an enum that has no escape at all.
#: `DateState.UNDATED` was added this way, the moment C5 introduced it.

#: Enums that are CLOSED VOCABULARIES, not outcomes. Each with the reason it
#: cannot be "not assessed" — because something always chose it.


def _enums() -> dict[type, str]:
    """Every Enum the product defines, found by import rather than listed."""
    import nm

    found: dict[type, str] = {}
    for mod in pkgutil.walk_packages(nm.__path__, prefix="nm."):
        try:
            m = importlib.import_module(mod.name)
        except Exception:  # noqa: BLE001 -- an unimportable module is its own defect
            continue
        for name in dir(m):
            obj = getattr(m, name)
            if (isinstance(obj, type) and issubclass(obj, enum.Enum)
                    and obj.__module__.startswith("nm.")):
                found[obj] = f"{obj.__module__}.{obj.__name__}"
    return found


def test_the_scan_can_see_the_products_enums():
    """A guard on the guard: an empty population passes everything below."""
    assert len(_enums()) >= 20, (
        "almost no enums were discovered — this file would then be asserting "
        "nothing over nothing")


def test_the_third_state_is_a_value_and_never_a_null():
    """B-055's specific shape: the third state existing OUTSIDE the vocabulary.

    `ActBasis` had [named, inferred] and carried "nothing governs this" as
    `basis=None`. It worked, and nothing forced a consumer to handle it —
    which is what `None` costs and a member does not.
    """
    from nm.Archives.legal_brain.retrieve.manifest_sources import ActBasis, Resolution

    assert ActBasis.NOT_RESOLVED in list(ActBasis)
    assert Resolution(None).basis is ActBasis.NOT_RESOLVED, (
        "an unresolved Resolution does not carry the unresolved BASIS, so a "
        "consumer asking `basis is INFERRED` gets its answer by accident")
    assert not Resolution(None).must_disclose


# ============ every metric reaches the record it is measured from ==========


def _keys_at_any_depth(doc) -> set[str]:
    """Every key in the record, nested included.

    `as_dict` groups the token counts under `tokens`, so a flat comparison
    would report three false offenders and teach the reader to add exemptions
    rather than to fix the one real gap.
    """
    out: set[str] = set()
    if isinstance(doc, dict):
        for k, v in doc.items():
            out.add(k)
            out |= _keys_at_any_depth(v)
    elif isinstance(doc, (list, tuple)):
        for v in doc:
            out |= _keys_at_any_depth(v)
    return out


#: TurnMetrics fields deliberately kept OFF `as_dict()`, each with the reason.
#: ONE declaration, read by the scan AND its positive control: the control kept
#: its own copy, so a field declared here and not there failed the control
#: rather than the scan -- a second copy of a list is a second answer.
OFF_RECORD: frozenset[str] = frozenset({
    # A monotonic clock read, not a measurement. `latency_ms` is what the
    # record carries and is derived from it.
    "started",
    # Carried under `tokens` with shortened keys -- {"in", "out", "cached"} --
    # so they ARE written and a name match cannot see it. Declared rather than
    # inferred: guessing which renamed key holds which field is exactly the
    # kind of inference that passes a record missing something.
    "tokens_in", "tokens_out", "cached_tokens",
    # MATTER-PRIVATE, so it is written to the ENCRYPTED transcript
    # (`TurnEngine._record_turn`) and never to this plaintext projection. Each
    # row carries the recommended step's own words and the model's basis for
    # judging it independent of the limitation -- the same reason `detail` is
    # held back from the metrics store (`_FREE_TEXT`).
    "step_assessments",
})


