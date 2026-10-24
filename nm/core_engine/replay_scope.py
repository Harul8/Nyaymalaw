"""What one check of a turn derives once (owner request P35, 21 Oct 2026).

The check made when a turn is saved (P46, 24 Oct 2026: the only time a saved answer is rebuilt;
reopening shows it as saved) binds each of its pieces - every section, its authority checks
and review, the check across sections and the overview - to evidence re-derived from the
research. Each check re-derived that evidence for itself: one turn of live run 8 built its
sources 17 times and took half a minute to check. Within one check, what is derived from an
object is derived once, by the identity of the very objects it is derived from; a record is
never changed while it is checked, and outside a check nothing is remembered.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_DERIVED = ContextVar("replay_scope_derived", default=None)


@contextmanager
def replaying():
    """One check of a turn: what `once` derives inside it is derived once."""
    token = _DERIVED.set({})
    try:
        yield
    finally:
        _DERIVED.reset(token)


def once(key, inputs, make):
    """What `make` derives from `inputs`, derived once within a check and on every call
    outside one. `key` names the derivation and the identities of its inputs; the inputs are
    kept with what was derived, so no other object can come to stand under the same identity."""
    derived = _DERIVED.get()
    if derived is None:
        return make()
    held = derived.get(key)
    if held is not None and len(held[0]) == len(inputs) and all(
            kept is given for kept, given in zip(held[0], inputs)):
        return held[1]
    made = make()
    derived[key] = (tuple(inputs), made)
    return made


def known(key, inputs, made):
    """Record what is already derived from `inputs` (a record validated is its own validation)."""
    derived = _DERIVED.get()
    if derived is not None:
        derived[key] = (tuple(inputs), made)
