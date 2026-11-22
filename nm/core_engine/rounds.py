"""Plan AN.72, D322 (owner, 22 Nov 2026): one bounded loop runner, shared by the work NM does in rounds - first research's later
rounds (D320), and after them drafting and the papers read on demand (D323, D324).

A round is one proposal and what came of it. The model proposes the next piece of work; code admits what is permitted of it, carries
that out and keeps the round; code decides when the rounds stop. This module owns only that order and the stop. Its user owns the
rest: the call (on NM's main call route, through the turn's calls, so that reasoning, the cache, the accounting, Stop and the exact
replay apply to every round), what is admitted, what is carried out and what counts as something new.

The rounds stop when the model proposes nothing (NOTHING_MISSING), when everything it proposes was done before (REPEATED), when a
round brings nothing new (NOTHING_NEW), when the turn's backstop is reached before a round is paid for (BACKSTOP), or when the call
for a round cannot be made (UNAVAILABLE). There is no fixed number of rounds (D27). An advocate's Stop, and every error that is not
one of the user's named failures, passes through: it is not a reason the rounds ended.
"""
from __future__ import annotations

NOTHING_MISSING, REPEATED, NOTHING_NEW, BACKSTOP, UNAVAILABLE = (
    "nothing_missing", "repeated", "nothing_new", "backstop", "unavailable")
#: Every reason the rounds may stop, as the record keeps it.
STOPS = (NOTHING_MISSING, REPEATED, NOTHING_NEW, BACKSTOP, UNAVAILABLE)
#: The reasons a round's proposal may be admitted as nothing.
ADMITTED_NOTHING = (NOTHING_MISSING, REPEATED)


class Backstop(Exception):
    """The turn's backstop is reached: no further round may be paid for."""


def run(ask, admit, carry_out, progressed, *, spend=None, unavailable=(), before=()):
    """Rounds until one stops. Returns (rounds, stop): each round {"proposal", "actions", "outcome"} - a round whose proposal was
    admitted as nothing keeps its proposal, with actions and outcome None, and is the last - and stop {"why", "reason"}, why one of
    STOPS and reason, for BACKSTOP and UNAVAILABLE, what said so.

    ask(rounds): the model's proposal for the next round, given the rounds before it (before, then this run's own).
    admit(proposal, rounds): (actions, why) - what code permits of the proposal; where it permits nothing, why is one of
    ADMITTED_NOTHING, and otherwise None.
    carry_out(actions, rounds): what came of the round.
    progressed(outcome, rounds): whether the round brought anything new; one that did not is the last.
    spend(): called before each round's call; raises Backstop where no further round may be paid for.
    unavailable: the exception types ask raises when its call cannot be made; any other exception passes through."""
    if not all(callable(f) for f in (ask, admit, carry_out, progressed)) or spend is not None and not callable(spend):
        raise TypeError("Each part of a round is its user's function")
    rounds = []
    while True:
        earlier = [*before, *rounds]
        if spend is not None:
            try:
                spend()
            except Backstop as exc:
                return rounds, {"why": BACKSTOP, "reason": str(exc) or type(exc).__name__}
        try:
            proposal = ask(earlier)
        except tuple(unavailable) as exc:
            return rounds, {"why": UNAVAILABLE, "reason": type(exc).__name__}
        actions, why = admit(proposal, earlier)
        if why is not None:
            if why not in ADMITTED_NOTHING:
                raise ValueError("A proposal admitted as nothing says why, as the rounds keep it")
            rounds.append({"proposal": proposal, "actions": None, "outcome": None})
            return rounds, {"why": why, "reason": None}
        if not actions:
            raise ValueError("A proposal admitted as something holds what to carry out")
        outcome = carry_out(actions, earlier)
        rounds.append({"proposal": proposal, "actions": actions, "outcome": outcome})
        if not progressed(outcome, earlier):
            return rounds, {"why": NOTHING_NEW, "reason": None}
