"""B3 — THE CONFLICT SCREEN, run against the files this advocate already holds.

WHAT IT IS A SCREEN OF, AND WHAT IT IS NOT
--------------------------------------------
It checks the parties named in this matter against the parties on every other
matter the same advocate holds. A person who is OUR CLIENT on one file and the
party AGAINST on another is the conflict this can find, and it is the one an
advocate in practice actually hits.

IT IS NOT A FIRM-WIDE REGISTRY, and the product must stop saying it is.
Registration told the advocate that "the firm's conflict registry governs this
session" while no screen ran at all -- a false assurance about the one check
whose whole value is being trusted. BK-31 says it in as many words: *do not
claim a firm-wide conflict check until a verified firm membership and a working
registry exist.* What is claimed here is exactly what is done: THIS ADVOCATE'S
OWN FILES, named as such, in the screen's own words.

WHY IT CAN BE INCOMPLETE AND WHY THAT NEVER CLEARS
----------------------------------------------------
`MatterList` already carries the ids it could not decode. A screen that ran
over nine of ten files and reported `clear` has told the advocate something
false about the tenth -- B3's own clause is that a registry unreadable in part
produces an INCOMPLETE screen, and an incomplete screen never clears. The type
enforces it: `Screen.__post_init__` refuses `unread` on anything but
INCOMPLETE.

WHAT A FINDING MAY SAY ABOUT THE OTHER FILE: NOT ITS NAME. BK-58-AC2
----------------------------------------------------------------------
Every hit used to carry the other matter's title, so establishing that a clash
existed handed over which other client the party was acting against. By this
release the screen is read by a delegate, by a locum working a handover, and by
whoever the advocate has the file open in front of. The finding now says the
party, the two sides, and that the other file is one of theirs -- which is
everything they need to act, and nothing anyone else can use.

THE THREE OUTCOMES, AND THE FOURTH THAT IS NOT AN OUTCOME
-----------------------------------------------------------
    CLEAR         parties are known, every file was read, nothing matched
    BLOCKED       a party here is on the other side of another file
    INCOMPLETE    a file could not be read; the answer is partial
    NOT_ASSESSED  no party is named yet, so nothing was checked

The last is not a failure and not a pass. An early brief says "we act for the
plaintiff" and names nobody; screening that against the roster would be
checking the file against the empty set and calling it clean.
"""
from __future__ import annotations

from nm.core.screens import Screen, ScreenKind, ScreenState


def _names_on(matter) -> dict[str, str]:
    """Every party name this matter holds, mapped to the side they are on.

    READ FROM THE THREADS' OWN POSTURE, which is where a matter records who it
    is against. `parties` is a per-thread mapping written by the intake read;
    an older matter that predates it contributes what its posture holds, which
    is less and is not nothing.
    """
    out: dict[str, str] = {}
    for thread in getattr(matter, "threads", ()):
        for name, side in (getattr(thread, "parties", None) or {}).items():
            key = str(name).strip().lower()
            if key:
                out[key] = str(side)
        posture = getattr(thread, "posture", None)
        opponent = getattr(posture, "opponent", None) if posture else None
        if opponent and str(opponent).strip():
            out.setdefault(str(opponent).strip().lower(), "adverse")
    return out


def _as_written(parties, key: str) -> str:
    """The party's name AS THIS MATTER RECORDS IT.

    `Parties.names` lowercases for matching, which is right -- and printing
    the match key back put "kiran steels" in front of an advocate who typed
    "Kiran Steels". The comparison stays case-insensitive; only what is shown
    changes.
    """
    for party in parties.parties:
        if party.name.strip().lower() == key:
            return party.name.strip()
    return key


def screen(parties, held, advocate_id: str) -> Screen:
    """The conflict screen for this matter, against `held`.

    `held` is a `MatterList` -- not a bare tuple -- so a file that could not
    be decoded reaches this function instead of vanishing from it. That
    distinction is the whole of B3's incomplete clause, and a bare tuple
    cannot express it.
    """
    if not parties.named:
        return Screen(
            kind=ScreenKind.CONFLICT,
            state=ScreenState.NOT_ASSESSED,
            not_assessed_because=(
                "no party is named on this matter yet, so there is nobody to "
                "check against your other files. Name the client and the party "
                "against, and I will run it"))

    ours = parties.names
    hits: list[str] = []
    for matter in held:
        if getattr(matter, "id", None) == getattr(parties, "matter_id", None):
            continue
        for name, side_there in _names_on(matter).items():
            if name not in ours:
                continue
            side_here = parties.side_of(name)
            # THE CONFLICT IS DIRECTIONAL. The same party on the same side of
            # two files is an ordinary repeat client, and reporting it would
            # make the screen fire on every returning client until nobody read
            # it. What blocks is the party being on OPPOSITE sides.
            if side_here == "related" or side_there == "related":
                continue
            if side_here != side_there:
                # THE OTHER FILE IS NOT NAMED. BK-58-AC2. Establishing that a
                # clash exists does not require handing over which other
                # client the party is acting against, and the screen is read
                # by whoever has this file open -- a delegate, a locum working
                # a handover, anyone over a shoulder. The advocate holds both
                # files and their matter list is one click away.
                hits.append(
                    f"{_as_written(parties, name)} is {side_here} here and "
                    f"{side_there} on another of your files")

    unread = tuple(getattr(held, "unreadable", ()) or ())
    if unread:
        return Screen(
            kind=ScreenKind.CONFLICT,
            state=ScreenState.INCOMPLETE,
            detail=(
                f"I checked {len(ours)} party(ies) against your files and "
                f"{len(unread)} of them could not be read"
                + (f"; on what I could read: {'; '.join(hits)}" if hits
                   else "; nothing matched on the files I could read")),
            covers=frozenset(ours),
            unread=unread)

    if hits:
        return Screen(
            kind=ScreenKind.CONFLICT,
            state=ScreenState.BLOCKED,
            detail=("; ".join(hits)
                    + ". This is a finding about your own files, not a "
                      "firm-wide registry check. I have not named the other "
                      "file here; open your matter list to find it"),
            covers=frozenset(ours))

    return Screen(
        kind=ScreenKind.CONFLICT,
        state=ScreenState.CLEAR,
        detail=(f"{len(ours)} party(ies) checked against your other matters "
                f"and none is on the opposite side of another file. THIS IS "
                f"YOUR OWN FILES, not a firm-wide registry"),
        covers=frozenset(ours))
