"""A1 — the directory: who exists, and whether this session is theirs.

DELIBERATELY NARROW, AND THE OMISSIONS ARE THE DESIGN
------------------------------------------------------
There is no `list_advocates`, no `find_by_name`, and no method that answers
"does this advocate exist". A1's second NEVER is that a failed credential must
disclose nothing about what exists, and the cheapest way to keep that true is
to give the edge no way to ask.

`authenticate` returns an identity or `None` and never says which of the two
reasons applied, because the caller must not be able to tell either. The
reason is recorded by the ADAPTER, where an operator can read it and an
attacker cannot.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from nm.domain.advocate import AdvocateIdentity, Enrolment, Session


class DirectoryPort(Protocol):
    def enrol(self, enrolment: Enrolment) -> None:
        """Record an advocate. Refuses an id that already exists."""
        ...

    def authenticate(self, advocate_id: str, password: str,
                     ) -> AdvocateIdentity | None:
        """The identity, or `None`. NEVER which of the two failures it was.

        Implementations must run the key derivation even when the advocate is
        unknown: an identical message returned in 0.2ms for a stranger and
        80ms for a wrong password discloses which accounts exist.
        """
        ...

    def open_session(self, advocate_id: str, device: str,
                     now: datetime) -> str:
        """Returns the token, once. It is never retrievable afterwards."""
        ...

    def session(self, token: str, device: str,
                now: datetime) -> Session | None:
        """The live session this token names, or `None`.

        `None` covers unknown, expired, ended and WRONG DEVICE alike — A1's
        first NEVER is that a matter list is not restored on a borrowed device
        without re-authentication, and a session that travels between devices
        is exactly that restoration.
        """
        ...

    def close_session(self, token: str, why: str) -> None:
        ...

    def identity(self, advocate_id: str) -> AdvocateIdentity | None:
        """For rendering who is signed in. Requires a live session upstream."""
        ...
