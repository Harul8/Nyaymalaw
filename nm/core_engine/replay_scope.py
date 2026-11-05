"""What one check of a turn derives once (owner request P35, 21 Oct 2026), and what one turn's own
work derives from its research once (plan AN.41, step 1, 4 Nov 2026).

The check made when a turn is saved (P46, 24 Oct 2026: the only time a saved answer is rebuilt;
reopening shows it as saved) binds each of its pieces - every section, its authority checks
and review, the check across sections and the overview - to evidence re-derived from the
research. Each check re-derived that evidence for itself: one turn of live run 8 built its
sources 17 times and took half a minute to check. Within one check, what is derived from an
object is derived once, by the identity of the very objects it is derived from; a record is
never changed while it is checked.

A turn's own work did the same outside any check: each section's writer, review and authority
check confirmed the sources it was given by validating the research afresh, and each part shown
drew the whole answer again, validating every dispute's research once more. On 4 Nov 2026 a turn
of five disputes spent 37 of its 73 minutes with no AI call running, and one drawing of that
answer took 75-90 seconds, nearly all of it validating research. Within one turn, what is
derived from the research alone - its validation, a dispute's part, the sources built from it,
the passages it offered - is now derived once too; a check of a draft, which a turn rewrites, is
still made on every call. A turn's threads share its scope: work given to a Pool runs in the
scope of the thread that gave it. Outside a check or a turn nothing is remembered.
"""
from __future__ import annotations

import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar

_DERIVED = ContextVar("replay_scope_derived", default=None)
#: What a turn's own scope remembers: what is derived from the research alone, by the first
#: part of its key (research.validate, research.part_of, answer_sources.build, the passages
#: response_authorities reads as offered) - and, from plan AN.41 step 1, the research plan admitted against the conversation
#: (research.accept), which each dispute's research is checked against.
RESEARCH = frozenset({"research", "part", "sources", "raw", "plan"})


class _Scope:
    """What one check or one turn has derived, shared by its threads."""

    def __init__(self, kinds=None):
        self.kinds, self.derived, self.making = kinds, {}, {}
        self.lock = threading.Lock()

    def remembers(self, key):
        return self.kinds is None or key[0] in self.kinds

    def held(self, key, inputs):
        held = self.derived.get(key)
        if held is not None and len(held[0]) == len(inputs) and all(
                kept is given for kept, given in zip(held[0], inputs)):
            return held
        return None


@contextmanager
def _within(scope):
    token = _DERIVED.set(scope)
    try:
        yield
    finally:
        _DERIVED.reset(token)


def replaying():
    """One check of a turn: what `once` derives inside it is derived once."""
    return _within(_Scope())


def turn():
    """One turn's own work (plan AN.41, step 1): what `once` derives from the research inside it
    is derived once; anything else is derived on every call."""
    return _within(_Scope(RESEARCH))


def once(key, inputs, make):
    """What `make` derives from `inputs`, derived once within a check (or, from the research, a
    turn) and on every call outside one. `key` names the derivation and the identities of its
    inputs; the inputs are kept with what was derived, so no other object can come to stand
    under the same identity. Threads sharing a scope derive each thing once: one derives it
    while the others wait for it."""
    scope = _DERIVED.get()
    if scope is None or not scope.remembers(key):
        return make()
    with scope.lock:
        held = scope.held(key, inputs)
        if held is not None:
            return held[1]
        making = scope.making.setdefault(key, threading.RLock())
    with making:
        with scope.lock:
            held = scope.held(key, inputs)
        if held is not None:
            return held[1]
        made = make()
        with scope.lock:
            scope.derived[key] = (tuple(inputs), made)
        return made


def known(key, inputs, made):
    """Record what is already derived from `inputs` (a record validated is its own validation)."""
    scope = _DERIVED.get()
    if scope is not None and scope.remembers(key):
        with scope.lock:
            scope.derived[key] = (tuple(inputs), made)


class Pool(ThreadPoolExecutor):
    """A thread pool whose work runs in the scope of the thread that gives it (plan AN.41, step
    1): a turn's sections and checks, each on its own thread, share what the turn has derived."""

    def submit(self, fn, /, *args, **kwargs):
        return super().submit(contextvars.copy_context().run, fn, *args, **kwargs)
