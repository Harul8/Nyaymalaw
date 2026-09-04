"""D9 — SPOTTING issues, so the register has something to hold.

WHAT WAS MISSING
-----------------
`nm/domain/issue.py` carried the whole register since slice 6: facets that
cannot be deleted, `classify` with no filter in it, `accounted_for` returning
what was LOST rather than a count, and `effect_for` deriving the effect from
the posture so a stale reading is impossible. Nothing ever produced an
`Issue`, so none of it ran on a served turn (B-079).

DERIVED EVERY TURN, NOT STORED — AND THAT IS THE SAME ARGUMENT D9 MAKES
------------------------------------------------------------------------
D9 refuses a stored `effect` because a stored effect cannot detect its own
reversal: the advocate corrects the posture on turn 4 and a field written on
turn 2 still says `opposes`. The identical objection applies one level up. An
issue spotted on turn 2 from facts that turn 5 has since corrected is an issue
about a file that no longer exists.

So issues are re-derived from the WHOLE ACCOUNT each turn, exactly as the
limitation position is. Nothing is lost by that — the account still holds the
facts that produced the issue — and nothing goes stale.

The cost is real and worth naming: ids are not stable across turns, so a
disposition cannot yet be attached to an issue and carried forward. Nothing
parks an issue today, so nothing depends on it. The day something does, this
needs a persisted register keyed on something stabler than a generated id, and
that is a change to `Matter`, not a change here.

THE VOCABULARY IS CLOSED, AND OUT-OF-VOCABULARY IS NOT_ESTABLISHED
--------------------------------------------------------------------
`issue.facet()` already blanks and re-derives a value outside the enum, which
is the mechanism D9 asks for. This uses it rather than mapping strings itself,
because a second place that decides what a `kind` may be is a second place for
the vocabulary to drift.
"""
from __future__ import annotations

from dataclasses import dataclass

from nm.core.posture import _fold
from nm.domain.issue import Issue, IssueKind, facet
from nm.domain.matter import Side, ThreadId
from nm.domain.traceability import implements

#: The most this reads from one turn. An answer carrying twenty issues has not
#: identified the case, it has listed it -- and D9's counterexample is a
#: previous build that spotted 3,192 labels and then dropped 641 of them
#: precisely because there were too many to look at.
MAX_ISSUES = 8

ISSUE_SCHEMA: dict = {
    "x-nm-read": "issues",
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {
                        "type": "string",
                        "description": "The issue in one sentence, as a "
                                       "question the court must answer.",
                    },
                    "kind": {
                        "type": "string",
                        "enum": [k.value for k in IssueKind
                                 if k is not IssueKind.NOT_ESTABLISHED],
                    },
                    "runs_against": {
                        "type": "string",
                        # WHOSE CLAIM IT RUNS AGAINST -- a fact about the
                        # ISSUE, which does not change when the posture does.
                        # Asking instead whether it "helps us" would bake an
                        # opinion about whose problem it is into the record,
                        # and that opinion is wrong for half the advocates who
                        # will ever read it. D9 names this exactly.
                        "enum": ["moving", "defending", "unknown"],
                    },
                    "quoted": {
                        "type": "string",
                        "description": "The advocate's OWN words this issue "
                                       "arises from, verbatim.",
                    },
                },
                "required": ["statement", "kind", "runs_against", "quoted"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["issues"],
    "additionalProperties": False,
}

SYSTEM = (
    "You read an Indian advocate's account of a matter and list the ISSUES — "
    "the questions a court would have to answer to dispose of it.\n\n"
    "For each, say WHOSE CLAIM it runs against: `moving` for the party "
    "asserting the claim, `defending` for the party resisting it. That is a "
    "fact about the issue and not about who you are helping — a limitation "
    "point runs against whoever is asserting the claim, whichever side "
    "instructs you.\n\n"
    "A threshold issue — limitation, jurisdiction, forum, notice, court fees — "
    "disposes of a claim WITHOUT reaching the merits, so list it whether or "
    "not it looks decisive. `quoted` must be the advocate's own words, copied "
    "exactly.\n\n"
    "Return an empty list if the account does not yet describe a dispute."
)


@dataclass(frozen=True)
class ReadIssues:
    """THREE STATES. `examined=False` is not an empty issue list."""

    issues: tuple[Issue, ...] = ()
    examined: bool = False
    why_not: str = "nothing has read this account for issues"
    refused: tuple[str, ...] = ()

    @property
    def state(self) -> str:
        if not self.examined:
            return "not_assessed"
        return "spotted" if self.issues else "none_spotted"


UNREAD = ReadIssues()


def not_assessed(why: str) -> ReadIssues:
    return ReadIssues(examined=False, why_not=why)


@implements("D9")
def build_prompt(message: str, account: str):
    from nm.ports.model import Prompt

    return Prompt(
        system=SYSTEM,
        user=(f"THE FILE SO FAR:\n{account or '(nothing recorded yet)'}\n\n"
              f"THIS TURN:\n{message}"),
    )


@implements("D9")
def read(said: dict, thread: ThreadId, account: str) -> ReadIssues:
    """Build issues, refusing each one that is not grounded.

    A REFUSAL IS PER ISSUE, not per read. One unquotable issue among five must
    not discard the other four — that is the measured defect wearing a
    different hat, and it would be a filter with a good excuse.
    """
    rows = said.get("issues")
    if not isinstance(rows, list):
        return not_assessed("the issue read returned no list")

    spotted: list[Issue] = []
    refused: list[str] = []
    for row in rows[:MAX_ISSUES]:
        if not isinstance(row, dict):
            refused.append("an issue that was not an object")
            continue
        statement = str(row.get("statement") or "").strip()
        if not statement:
            refused.append("an issue with no statement")
            continue

        quoted = str(row.get("quoted") or "")
        if quoted.strip() and _fold(quoted) not in _fold(account):
            # THE SAME GUARD THE CAUSE AND FACTOR READS USE. An issue carrying
            # a quotation the advocate never wrote has evidence it does not
            # have -- and an issue is what the rest of the answer hangs off.
            refused.append(f"{statement[:60]}: the quoted words are not in the "
                           f"advocate's account")
            continue

        spotted.append(Issue(
            thread=thread,
            statement=statement,
            # OUT-OF-VOCABULARY IS NOT_ESTABLISHED, via the one mechanism that
            # already decides it. A second place mapping strings to kinds is a
            # second place for the vocabulary to drift.
            kind=facet(IssueKind, row.get("kind"),
                       default=IssueKind.NOT_ESTABLISHED),
            runs_against=facet(Side, row.get("runs_against"),
                               default=Side.UNKNOWN),
            proof=quoted,
        ))

    return ReadIssues(issues=tuple(spotted), examined=True,
                      refused=tuple(refused),
                      why_not=("the account does not yet describe a dispute"
                               if not spotted and not refused else ""))
