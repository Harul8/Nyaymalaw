"""EVIDENCE ABOUT A DEPLOYMENT IS EVIDENCE ABOUT ONE EXACT CANDIDATE. P39.
BK-42-AC1/AC2/AC8, BK-85-AC1/AC6, BK-88-AC2/AC4, BK-21-AC3/AC4.

    from nm.domain.deployment import Candidate, Inventory, refuse_claim

WHAT THIS IS FOR
------------------
A security claim without a candidate is a claim about whatever shipped last.
"Secrets are not in the artifact" is true of some build; the question is
whether it is true of THIS one, and the only thing that makes those the same
sentence is an identity on both.

So every record here carries the candidate, and `refuse_claim` refuses a claim
whose candidate does not match the one in front of it. That is the whole
mechanism, and it is the one that stops a passing scan from last month being
read as a fact about the build being released.

WHAT AN INVENTORY IS, AND WHY AN EMPTY ONE IS NOT A CLEAN ONE
---------------------------------------------------------------
Fourteen populations -- artifacts, lockfiles, provenance, runtimes, secret
sources, application and service identities, privileged and emergency roles,
support paths, telemetry destinations, subprocessors, storage boundaries and
allowed egress. Each is a `Population`, which carries whether anybody looked
separately from its rows, because a population nobody enumerated and a
population that is genuinely empty are opposite facts and read identically
as `[]`.

    A SCAN THAT FOUND NOTHING AND A SCAN THAT DID NOT RUN look the same in
    every report that stores a list. `NOT_ASSESSED` is what makes them
    different, and `refuse_claim` treats it as a blocker rather than a zero.

THE SECOND FACTOR, AND WHY IT LIVES HERE
------------------------------------------
BK-42-AC2 turns on a distinction this module already draws: an exception to
the second factor approved against a prototype or a local roster is not an
exception to the deployed access flow, because the population it was reasoned
about is not the population it would waive. `Candidate.operated` is the same
predicate in both places, which is the point of putting them in one file.

WHY THE CREDENTIAL COMPARISON IS A DIGEST
-------------------------------------------
`shared_values` is the one place in this product that answers "do these two
secrets hold the same string", and it answers it without holding the two
strings beside each other or putting either in a message.
`nm/bootstrap/composition._refuse_a_shared_seal` calls it rather than
comparing plaintext itself -- one owner, and the reporting side names
variables and never values.

WHAT THIS MODULE CANNOT ESTABLISH
-----------------------------------
Anything about a deployed environment, because there is not one. Every
inventory this build can produce describes a working tree; `Candidate.operated`
is False for all of them, and a scanner's clean result is not a penetration
test, local file permissions are not target IAM, and an environment-file edit
is not a provider credential rotation. Each of those three has a named refusal
here rather than a comment somewhere.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from nm.domain.text import blank, refuses_blank_text


class Assessed(str, Enum):
    """Whether anybody enumerated this population.

    The distinction the whole inventory turns on: `EMPTY` is a finding and
    `NOT_ASSESSED` is a gap, and they render identically as an empty list in
    every report that stores only rows.
    """

    ASSESSED = "assessed"
    EMPTY = "empty"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "Assessed":
        return cls.NOT_ASSESSED

    @property
    def can_be_relied_on(self) -> bool:
        return self is not Assessed.NOT_ASSESSED


@dataclass(frozen=True)
class Population:
    """One inventoried set, and whether anybody looked."""

    rows: tuple[str, ...] = ()
    state: Assessed = Assessed.NOT_ASSESSED

    def __post_init__(self) -> None:
        # A POPULATION CANNOT CARRY ROWS AND CLAIM NOBODY LOOKED, and it
        # cannot be empty and claim somebody did without saying so.
        if self.rows and self.state is Assessed.NOT_ASSESSED:
            object.__setattr__(self, "state", Assessed.ASSESSED)
        if not self.rows and self.state is Assessed.ASSESSED:
            object.__setattr__(self, "state", Assessed.EMPTY)

    def render(self) -> str:
        if self.state is Assessed.NOT_ASSESSED:
            return "not assessed -- nobody enumerated this"
        if self.state is Assessed.EMPTY:
            return "none, and that was checked"
        return "; ".join(self.rows)


#: THE FOURTEEN THINGS A DEPLOYED-BOUNDARY CLAIM RESTS ON. Named once, so a
#: report cannot cover thirteen and read as complete.
POPULATIONS: tuple[str, ...] = (
    "artifacts", "lockfiles", "provenance", "runtimes", "secret_sources",
    "application_identities", "service_identities", "privileged_roles",
    "emergency_roles", "support_paths", "telemetry_destinations",
    "subprocessors", "storage_boundaries", "allowed_egress",
)


@refuses_blank_text()
@dataclass(frozen=True)
class Candidate:
    """EXACTLY WHAT IS BEING CLAIMED ABOUT.

    `environment` is required and `operated` is derived from it rather than
    set: a boolean somebody sets is a boolean somebody sets while looking at
    their laptop.
    """

    commit: str
    environment: str
    config_digest: str = ""

    #: Environments this build can actually produce. Anything else is a claim
    #: about somewhere else and is treated as one.
    LOCAL = ("local", "local_rehearsal", "synthetic", "working_tree")

    @property
    def operated(self) -> bool:
        return self.environment not in Candidate.LOCAL

    @property
    def identity(self) -> str:
        return hashlib.sha256(
            f"{self.commit}|{self.environment}|{self.config_digest}"
            .encode("utf8")).hexdigest()[:16]


@dataclass(frozen=True)
class Inventory:
    """What a candidate is made of, enumerated."""

    candidate: Candidate
    populations: dict = field(default_factory=dict)

    def get(self, name: str) -> Population:
        return self.populations.get(name) or Population()

    def unassessed(self) -> tuple[str, ...]:
        """Every population nobody enumerated, BY NAME."""
        return tuple(name for name in POPULATIONS
                     if not self.get(name).state.can_be_relied_on)


class ClaimKind(str, Enum):
    """What a piece of security evidence claims, and what may produce it.

    The three at the bottom are the substitutions this packet exists to
    refuse, each of which has been offered as the thing on the left:

        PENETRATION_TESTED   a scanner exiting zero
        IAM_ENFORCED         a local file permission
        CREDENTIAL_ROTATED   an edit to an environment file
    """

    INVENTORIED = "inventoried"
    SCANNED = "scanned"
    PENETRATION_TESTED = "penetration_tested"
    IAM_ENFORCED = "iam_enforced"
    CREDENTIAL_ROTATED = "credential_rotated"

    @property
    def needs_an_operated_environment(self) -> bool:
        """Which claims cannot be made from a working tree, whatever ran."""
        return self in (ClaimKind.PENETRATION_TESTED, ClaimKind.IAM_ENFORCED,
                        ClaimKind.CREDENTIAL_ROTATED)


@refuses_blank_text()
@dataclass(frozen=True)
class Claim:
    """One security statement, bound to the candidate it is about."""

    kind: ClaimKind
    candidate: Candidate
    made_by: str
    made_at: str
    note: str


def refuse_claim(claim: Claim, *, about: Candidate,
                 inventory: Inventory | None = None) -> tuple[str, ...]:
    """WHY THIS CLAIM DOES NOT COVER THE CANDIDATE IN FRONT OF YOU.

    The first check is identity, because everything else is a fact about some
    build and the only question is whether it is a fact about this one.
    """
    out: list[str] = []
    if claim.candidate.identity != about.identity:
        out.append(
            f"this claim is about candidate {claim.candidate.identity} "
            f"({claim.candidate.commit[:12]} on {claim.candidate.environment}) "
            f"and the release candidate is {about.identity} "
            f"({about.commit[:12]} on {about.environment})")

    if claim.kind.needs_an_operated_environment and not about.operated:
        out.append(
            f"a {claim.kind.value.replace('_', ' ')} claim cannot be made "
            f"from {about.environment!r}: a scanner exiting zero is not a "
            f"penetration test, a local file permission is not target IAM, "
            f"and an environment-file edit is not a rotation at the provider")

    if inventory is not None:
        if inventory.candidate.identity != about.identity:
            out.append("the inventory describes a different candidate")
        missing = inventory.unassessed()
        if missing:
            out.append(
                "these populations were never enumerated, and an empty list "
                "from a scan that did not run reads exactly like a clean one: "
                + "; ".join(missing))
    return tuple(out)


# ------------------------------------------------- credential separation ---

def shared_values(values: dict[str, str]) -> tuple[tuple[str, ...], ...]:
    """Which named secrets hold the same value. BY DIGEST, NEVER BY VALUE.

    THE ONE OWNER OF THAT QUESTION. `nm/bootstrap/composition` asks it about
    the seal and this module asks it about a candidate's secret sources; two
    implementations of "do these hold the same string" is CLAUDE.md section 4
    at the point where the answer decides whether client files stay readable.

    A digest rather than an equality test on the strings: a check that
    compared plaintext would hold both beside each other, and the one that
    reported the collision would be holding the value it was reporting on.

    An absent or blank value is not a collision -- two unset variables are not
    a shared secret, they are two things nobody set, and reporting them as a
    collision buries the real one.
    """
    seen: dict[str, list[str]] = {}
    for name, value in sorted(values.items()):
        if blank(value):
            continue
        fingerprint = hashlib.sha256(str(value).encode("utf8")).hexdigest()
        seen.setdefault(fingerprint, []).append(name)
    return tuple(tuple(names) for names in seen.values() if len(names) > 1)


def shares_value_with(name: str, values: dict[str, str]) -> tuple[str, ...]:
    """Every OTHER name holding the same value as `name`. Names only."""
    for group in shared_values(values):
        if name in group:
            return tuple(other for other in group if other != name)
    return ()


def distinct_secrets(values: dict[str, str]) -> tuple[str, ...]:
    """The collisions, rendered for a report. NAMES ONLY, never values."""
    return tuple(f"{' and '.join(group)} hold the same value"
                 for group in shared_values(values))


class Rotation(str, Enum):
    """Where a credential rotation actually happened. BK-21-AC4.

    `LOCAL_EDIT` exists because it is what gets done and reported as the
    other one. Changing the value this process reads does not change what the
    provider will still accept, and the old value keeps working until somebody
    revokes it AT THE PROVIDER.
    """

    AT_THE_PROVIDER = "at_the_provider"
    LOCAL_EDIT = "local_edit"
    NOT_DONE = "not_done"

    @classmethod
    def not_established(cls) -> "Rotation":
        return cls.NOT_DONE

    @property
    def revokes_the_old_value(self) -> bool:
        return self is Rotation.AT_THE_PROVIDER


def refuse_rotation_claim(state: Rotation, *, operator_authority: str) -> str:
    """Why a rotation may not be claimed, or "".

    An operator authority is required even for the real one, because rotating
    a live provider credential breaks every process still holding the old
    value -- it is an operational act with a blast radius, not a hygiene step.
    """
    if not state.revokes_the_old_value:
        return (f"the credential was {state.value.replace('_', ' ')}. Changing "
                f"the value this process reads does not change what the "
                f"provider still accepts: the old value keeps working until "
                f"somebody revokes it at the provider")
    if blank(operator_authority):
        return ("no operator authority is recorded for this rotation, and "
                "rotating a live provider credential breaks every process "
                "still holding the old value")
    return ""


# ------------------------------------------------------- the second factor --

class Factor(str, Enum):
    """Whether a second factor was presented. BK-42-AC2.

    `NOT_ASSESSED` is the default and it refuses, because an access flow
    nobody checked is the absent-input defect holding the front door.
    """

    PRESENT = "present"
    ABSENT = "absent"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "Factor":
        return cls.NOT_ASSESSED


def _a_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except (ValueError, AttributeError):
        return None


@refuses_blank_text()
@dataclass(frozen=True)
class Waiver:
    """An owned, separately approved, expiring exception to the second factor.

    Every field is required and none defaults, because each absent one is a
    different way of saying "somebody decided this was fine" without saying
    who, until when, or what stands in its place.
    """

    owner: str
    approved_by: str
    expires_on: str
    #: The environment the approval reasoned about. A decision taken against
    #: a prototype roster waives the second factor for the population that
    #: roster describes, which is not the deployed one.
    approved_for_environment: str
    compensating_controls: tuple[str, ...] = ()


@refuses_blank_text()
@dataclass(frozen=True)
class AccessRequest:
    """One attempt to reach the deployed access flow."""

    account_id: str
    candidate: Candidate
    factor: Factor = Factor.NOT_ASSESSED
    waiver: Waiver | None = None


def refuse_access(request: AccessRequest, *, on: str) -> tuple[str, ...]:
    """Why this access or release approval is refused. BK-42-AC2.

    EVERY REASON NAMES THE MISSING CONDITION, because the criterion is that
    the missing condition is VISIBLE -- a refusal that says "denied" leaves
    the operator guessing which of six things to fix, and the one they guess
    is the one that was already fine.
    """
    out: list[str] = []
    today = _a_date(on)
    if today is None:
        out.append(f"the date of this attempt is {on!r}, which is not a date; "
                   f"an expiry cannot be checked against an unreadable clock")

    if request.factor is Factor.PRESENT:
        return tuple(out)

    if request.factor is Factor.NOT_ASSESSED:
        out.append("nobody established whether a second factor was presented, "
                   "and an unassessed factor is not a present one")
    else:
        out.append("no second factor was presented")

    waiver = request.waiver
    if waiver is None:
        out.append("and no approved exception covers this account, so there "
                   "is nothing to fall back on")
        return tuple(out)

    if not waiver.compensating_controls:
        out.append("the exception names no compensating control, which makes "
                   "it a waiver rather than an exception")

    if waiver.approved_by == request.account_id:
        out.append(f"the exception for {request.account_id!r} was approved by "
                   f"the same account, and an exception nobody else agreed to "
                   f"is a decision taken alone")

    if not request.candidate.operated:
        out.append(f"this access flow is {request.candidate.environment!r}, "
                   f"which is not a deployed environment: a prototype flow "
                   f"cannot demonstrate the deployed one")

    if waiver.approved_for_environment in Candidate.LOCAL:
        out.append(f"the exception was approved for "
                   f"{waiver.approved_for_environment!r}; a prototype or "
                   f"local-roster decision cannot waive the second factor for "
                   f"the production population, because the population it "
                   f"reasoned about is not the one it would waive")
    elif waiver.approved_for_environment != request.candidate.environment:
        out.append(f"the exception was approved for "
                   f"{waiver.approved_for_environment!r} and this attempt is "
                   f"against {request.candidate.environment!r}")

    expires = _a_date(waiver.expires_on)
    if expires is None:
        out.append(f"the exception's expiry is {waiver.expires_on!r}, which is "
                   f"not a date; an exception that cannot expire does not")
    elif today is not None and expires < today:
        out.append(f"the exception expired on {waiver.expires_on} and this "
                   f"attempt is on {on}")
    return tuple(out)


def projection(inventory: Inventory) -> dict:
    """What a reviewer is shown, INCLUDING WHAT NOBODY LOOKED AT."""
    return {
        "candidate": inventory.candidate.identity,
        "commit": inventory.candidate.commit,
        "environment": inventory.candidate.environment,
        "operated": inventory.candidate.operated,
        "populations": {name: inventory.get(name).render()
                        for name in POPULATIONS},
        "unassessed": list(inventory.unassessed()),
        "said": ("This describes a working tree. It is not a deployed "
                 "environment, so nothing here is target IAM, KMS or network "
                 "proof and no penetration test has been performed."),
    }
