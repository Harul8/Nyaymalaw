"""Who may use the Admin area, and at what level (plan AN.46, piece 46a; owner decisions of 7 Nov 2026).

THREE ACCESS LEVELS (D118): Advocate, Admin and Admin (view only). An advocate is everyone the server's settings do
not name, so this module knows only the two admin levels and answers "none" for the rest.

WHERE AN ADMIN IS NAMED (D117), AND WHERE NEVER. In the server's own settings, NM_ADMINS="email:admin,email:view-only",
read when the application starts. Not in an account file (an account has no field that could carry it: the test beside this
module fails if one is ever added), not over HTTP, not from the Admin pages. Changing the list means editing the settings
and restarting.

A SETTING THAT IS WRONG LOCKS SOMEONE OUT; IT CAN NEVER RAISE ANYONE. A bare email with no level is not an admin (there is
no default level to fall to), an unknown level is not an admin, an address that cannot be an account id is not an admin,
and an address named twice at different levels takes the lower. Each ignored entry is counted so the diagnostics can say
that the setting has a problem without saying whose.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from nm.arrive.advocate_contracts import advocate_id_is_storage_safe, canonical_id

SETTING = "NM_ADMINS"


class Level(str, Enum):
    ADMIN = "admin"
    VIEW_ONLY = "view-only"


class Action(str, Enum):
    """What an Admin area request does. SEE is every read; each other action changes something (D116)."""
    SEE = "see"
    ALLOWANCE = "allowance"
    APPROVAL = "approval"
    SESSIONS = "sessions"
    RESET_EMAIL = "reset-email"
    INVITE = "invite"
    SUSPEND = "suspend"
    LIBRARY_ADD = "library-add"
    LIBRARY_SWITCH = "library-switch"


#: The levels in order of power, so that a duplicate entry takes the lower.
_RANK = {Level.VIEW_ONLY: 0, Level.ADMIN: 1}
_VIEW_ONLY_MAY = frozenset({Action.SEE})


def permits(level: Level | None, action: Action) -> bool:
    """Whether someone at this level may do this. No level (an advocate) may do nothing here, not even see."""
    if level is Level.ADMIN:
        return True
    if level is Level.VIEW_ONLY:
        return action in _VIEW_ONLY_MAY
    return False


@dataclass(frozen=True)
class Roster:
    """The admins the settings name: canonical account id -> level, and how many entries were ignored."""
    levels: Mapping[str, Level]
    rejected: int = 0

    def level_of(self, account_id: str | None) -> Level | None:
        """The admin level of this account, or None for an advocate. Never raises on a strange id."""
        if not isinstance(account_id, str):
            return None
        return self.levels.get(canonical_id(account_id))

    def named(self) -> tuple[tuple[str, Level], ...]:
        """Every admin, in the order of their ids, for the Access page."""
        return tuple(sorted(self.levels.items()))


def roster_from(settings: Mapping[str, str] | None) -> Roster:
    """Read the NM_ADMINS setting. Absent or empty: nobody is an admin."""
    text = (settings or {}).get(SETTING) or ""
    levels: dict[str, Level] = {}
    rejected = 0
    for entry in text.split(","):
        if not entry.strip():
            continue
        who, colon, said = entry.rpartition(":")
        who, said = canonical_id(who), said.strip().lower()
        try:
            level = Level(said)
        except ValueError:
            level = None
        if not colon or level is None or "@" not in who or not advocate_id_is_storage_safe(who):
            rejected += 1
            continue
        if who in levels and _RANK[levels[who]] != _RANK[level]:
            rejected += 1
            level = min(levels[who], level, key=_RANK.__getitem__)
        levels[who] = level
    return Roster(MappingProxyType(levels), rejected)
