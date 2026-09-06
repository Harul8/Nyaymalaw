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
CLOSED: dict[str, str] = {
    "Kind": "A POSITION or a MEASUREMENT, chosen by the code that RECORDS the "
            "derivation, not read from the matter. The limitation knows it is "
            "a date and `_record` knows it is emitting a count — there is no "
            "world in which the product derived something and could not say "
            "which kind it was. And the default is POSITION, so an "
            "unclassified value is announced when it moves rather than "
            "silently filed as accumulation: the third state would be the "
            "quiet direction here, which is backwards.",
    "DispositionState": "D9 names exactly four — run, parked(reason), "
                        "blocked(needs), closed(reason) — and every issue "
                        "carries one by construction. There is no 'nobody "
                        "decided' state BECAUSE THE DEFAULT IS `RUN`, and that "
                        "is the safe direction: this whole feature exists "
                        "because classification LOST 641 of 3,192 issues, so "
                        "an issue nobody has ruled on is live, not pending. A "
                        "fifth member meaning 'undecided' would be somewhere "
                        "for an issue to sit unread, which is the defect "
                        "wearing a permitted name.",
    "Coordinate": "D8's seven dimensions of a claim — party, cause, relief, "
                  "forum, timing, procedure, burden. `unvaried` builds from "
                  "this enum, so a coordinate NOBODY MOVED appears as a named "
                  "gap rather than as a missing member; the escape lives on "
                  "the result, where the question is answered. Same "
                  "arrangement as Threshold, and for the same reason: a "
                  "report that varied two coordinates and called the case dead "
                  "has not done the work.",
    "GapKind": "the four the PRD ranks by — blocking gate, deadline, "
               "information value, consequence. THE KIND IS THE RANK, so "
               "`Gap.kind` has no default and there is no unclassified state "
               "to sort: a fifth member would have to sort somewhere, and "
               "third buries an unclassified blocking gate under every "
               "deadline while first makes everything nobody thought about "
               "scream. Whoever writes the gap says what makes it urgent.",
    "ScreenKind": "the five front-door screens B2-B6 name. `unscreened` "
                  "builds from this enum, so a screen NOBODY RAN appears as a "
                  "named row rather than as a missing member -- the escape is "
                  "on ScreenState, where the question is answered. Same "
                  "arrangement as Threshold and Coordinate.",
    "ElementKind": "the four permitted kinds, with deliberately no fifth. An "
                   "element the product could not classify is not emitted at "
                   "all, so there is no state to express.",
    "Mode": "how the answer is shaped. The router always picks one, and a "
            "shape nobody picked would render as nothing.",
    "Route": "matter or not. Ambiguity resolves to MATTER BY DECISION (B1): a "
             "workup on a question wastes time, and the reverse missed a "
             "five-word emergency, which is the worse error.",
    "Response": "the gate matrix's own vocabulary. Every row is authored and "
                "the constructor refuses one without a response, so a gate "
                "with no response cannot exist.",
    "Scope": "as Response — what a gate refuses, authored per row and refused "
             "by the constructor if absent.",
    "Persistence": "as Response — whether a gate survives a restart, authored "
                   "per row rather than discovered.",
    "Certainty": "documented or asserted. ASSERTED is the conservative "
                 "default: it is the WEAKER claim, so defaulting there "
                 "understates the evidence rather than overstating it.",
    "Phase": "which phase of the turn is running. The engine is always in "
             "exactly one, and a failure records the phase it died in.",
    "SourceKind": "what a Finding IS — a provision or an authority. A Finding "
                  "that is neither cannot be constructed, because every field "
                  "that makes it auditable differs between the two.",
    "Tier": "model configuration. A step declares a tier or the build fails, "
            "so there is no tier nobody chose.",
    "DeadlineKind": "what IMPOSES a deadline — a limitation Article, a notice "
                    "period, a listing. `OTHER` carries the ones this list "
                    "does not name; a deadline with no source at all cannot "
                    "be constructed.",
    "Threshold": "the complete list of thresholds D1 checks. The map is BUILT "
                 "from this enum, so an unassessed threshold appears as a "
                 "BLOCKED row rather than as a missing member — the escape is "
                 "on ThresholdState, which is where the question is answered.",
}


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


def test_every_outcome_enum_can_say_that_nothing_was_established():
    """THREE STATES, NEVER TWO — checked over the whole vocabulary at once.

    An enum that cannot express "not assessed" forces every producer to pick
    one of the decisive answers, and whichever it picks the product is stating
    a conclusion it never reached.
    """
    offenders: list[str] = []
    for cls, qualified in sorted(_enums().items(), key=lambda kv: kv[1]):
        if cls.__name__ in CLOSED:
            continue
        # AN ENUM MAY DECLARE ITS OWN ESCAPE, and that is the better answer
        # wherever the word list would have to guess. `ThresholdState`'s escape
        # is BLOCKED -- somebody must still answer it -- while NOT_APPLICABLE
        # is a FINDING, and no vocabulary of substrings could tell those apart.
        # A classmethod is not an enum member, so it declares without adding a
        # value.
        if callable(getattr(cls, "not_established", None)):
            assert cls.not_established() in list(cls), (
                f"{qualified}.not_established() does not return one of its own "
                f"members, so the declaration points at nothing")
            continue
        names = [m.name.lower() for m in cls]
        if not any(any(e in n for e in ESCAPES) for n in names):
            offenders.append(f"{qualified}: {', '.join(m.name for m in cls)}")

    assert not offenders, (
        "these enums model an outcome and cannot say that nothing was "
        "established:\n  " + "\n  ".join(offenders)
        + "\n\nAdd the third member, or declare the enum CLOSED above with the "
          "reason something always chose one of its values. An enum with two "
          "states forces every producer to pick a decisive answer — and "
          "whichever it picks, the product states a conclusion it never "
          "reached (B-042, B-055).")


def test_every_closed_vocabulary_declares_why_it_is_closed():
    """The allowlist may not rot into a way of avoiding the rule.

    An entry for an enum that no longer exists is a reason nobody re-examined,
    and a blank reason is an exemption nobody made.
    """
    known = {c.__name__ for c in _enums()}
    stale = sorted(set(CLOSED) - known)
    assert not stale, (
        f"CLOSED names enums that no longer exist: {stale}. An exemption for "
        f"something gone is a decision nobody is re-examining.")
    for name, reason in CLOSED.items():
        assert len(reason) > 25, (
            f"{name} is declared closed with no real reason. 'Something always "
            f"chose it' has to be true and has to be said.")


def test_the_third_state_is_a_value_and_never_a_null():
    """B-055's specific shape: the third state existing OUTSIDE the vocabulary.

    `ActBasis` had [named, inferred] and carried "nothing governs this" as
    `basis=None`. It worked, and nothing forced a consumer to handle it —
    which is what `None` costs and a member does not.
    """
    from nm.knowledge.manifest import ActBasis, Resolution

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


def test_every_metric_field_survives_into_the_persisted_record():
    """A METRIC THAT IS NOT SERIALISED CANNOT BE MEASURED.

    `cause_reads` was added to `TurnMetrics` in slice 5, counted correctly on
    every turn, included in `settling_reads`, and left out of `as_dict()` — so
    every persisted record was missing it and every question asked of the
    metrics store answered as though the read had never happened.

    It is the shape this project keeps paying for, one layer along: a value
    that exists in the type and never reaches the place it is read from. The
    release gate reads these records; a field absent here is a criterion that
    silently measures the wrong thing.
    """
    import dataclasses

    from nm.domain.metrics import TurnMetrics

    m = TurnMetrics(turn_id="t", matter_id="m")
    #: Fields deliberately kept OFF the record, each with the reason.
    off_record = {
        # A monotonic clock read, not a measurement. `latency_ms` is what the
        # record carries and is derived from it.
        "started",
        # Carried under `tokens` with shortened keys -- {"in", "out",
        # "cached"} -- so they ARE written and a name match cannot see it.
        # Declared rather than inferred: guessing which renamed key holds
        # which field is exactly the kind of inference that passes a record
        # missing something.
        "tokens_in", "tokens_out", "cached_tokens",
    }
    written = _keys_at_any_depth(m.as_dict())
    missing = sorted(
        f.name for f in dataclasses.fields(TurnMetrics)
        if f.name not in written and f.name not in off_record)
    assert not missing, (
        "these metrics are counted and never written, so nothing downstream "
        f"can read them: {missing}\n\nAdd them to `as_dict`, or to "
        "`off_record` above with the reason they are not a measurement.")


def test_the_metric_scan_can_see_an_unserialised_field():
    """THE POSITIVE CONTROL. A scan over a record that happens to be complete
    proves nothing about the scan."""
    import dataclasses

    from nm.domain.metrics import TurnMetrics

    written = _keys_at_any_depth(TurnMetrics(turn_id="t", matter_id="m").as_dict())
    planted = "zz_never_serialised"
    assert planted not in written
    off = {"started", "tokens_in", "tokens_out", "cached_tokens"}
    names = {f.name for f in dataclasses.fields(TurnMetrics)} | {planted}
    assert sorted(n for n in names if n not in written and n not in off)         == [planted]
