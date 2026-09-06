"""D9 — SPOTTING issues, so the register has something to hold.

WHAT WAS MISSING
-----------------
`nm/domain/issue.py` carried the whole register since slice 6: facets that
cannot be deleted, `classify` with no filter in it, `accounted_for` returning
what was LOST rather than a count, and `effect_for` deriving the effect from
the posture so a stale reading is impossible. Nothing ever produced an
`Issue`, so none of it ran on a served turn (B-079).

STORED AND MERGED, AS OF 6 SEPTEMBER 2026 — AND THE OLD ARGUMENT WAS WRONG
---------------------------------------------------------------------------
This said, until that date, that issues were DERIVED EVERY TURN AND NOT
STORED, reasoning by analogy from D9's refusal to store an `effect`: a stored
effect cannot detect its own reversal, so a stored issue would go stale the
same way.

The analogy does not hold, and GS-15 showed why. `effect` is a FUNCTION of the
posture, so re-deriving it is how it stays true. An issue is not a function of
anything — it is a question somebody noticed — and re-deriving it every turn
does not keep it fresh, it makes it VANISH when the read has an off turn. The
count went 1, 1, 1, 0, 2 across five turns and the thread had no issues at all
on turn 4, having carried one for three turns. `DispositionState` says in its
own docstring that there is no member meaning "gone"; the pipeline deleted
every issue on every turn by rebuilding the list.

So issues live on the thread and are MERGED. The staleness the old argument
feared is real and is handled where it belongs: an issue whose facts have been
corrected is one to PARK with a reason, which is what `Disposition` is for —
not one to make disappear by not mentioning it.

WHAT THAT COST WAS PREDICTED TO BE, AND WHAT IT ACTUALLY WAS. The note here
used to say ids were unstable so a disposition could not be carried. Ids are
stable now, and the cost turned out to be elsewhere: the same question came
back in three phrasings and accumulated. `build_prompt` below is where that is
answered — the read is shown what is on the thread and names the id it is
restating, because nothing may compare two sentences and decide they are one
issue (CLAUDE.md 5).

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
                    "restates": {
                        "type": "string",
                        "description": "EMPTY STRING for a new issue. If this "
                                       "is the SAME QUESTION as one already "
                                       "on the thread, worded differently, "
                                       "put that issue's id here instead of "
                                       "adding a second copy of it.",
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
                "required": ["statement", "kind", "runs_against", "quoted", "restates"],
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
def build_prompt(message: str, account: str, standing=()):
    """`standing` is THE ISSUES ALREADY ON THIS THREAD, with their ids.

    MEASURED ON GS-15, 6 September 2026, the run where issues first survived.
    The count went 1, 2, 3, 4, 8 and three of the six were the same question:

        What is the limitation period for the claim of specific performance?
        What is the limitation period that applies to the claim for specific
          performance?
        Is the plaintiff's claim for specific performance time-barred?

    Never losing an issue had bought a list that repeats itself, and an
    advocate reading eight lines where there are three questions is reading
    noise.

    THE READ NAMES THE ID; NOTHING COMPARES SENTENCES. Deciding that two
    phrasings are one issue by similarity is IDENTIFICATION BY FUZZY
    MATCHING, which CLAUDE.md 5 forbids for exactly the reason it would fail
    here -- "is the claim time-barred" and "what is the limitation period"
    share almost no words and are the same question, while two issues about
    different provisions can read nearly identically.

    So the read is shown what is already there and says which one it means.
    Same move as `corrects` on the date row: the reader that has the evidence
    in front of it answers, instead of something downstream reconstructing the
    relationship without it.
    """
    from nm.ports.model import Prompt

    listed = "\n".join(f"  {i.id}\t{i.statement}" for i in standing)
    already = (f"ISSUES ALREADY ON THIS THREAD. If you are asking one of these "
               f"again in different words, put its id in `restates` rather "
               f"than repeating it:\n{listed}\n\n" if listed else "")
    return Prompt(
        system=SYSTEM,
        user=(f"{already}"
              f"THE FILE SO FAR:\n{account or '(nothing recorded yet)'}\n\n"
              f"THIS TURN:\n{message}"),
    )


@implements("D9")
def read(said: dict, thread: ThreadId, account: str,
         standing=()) -> ReadIssues:
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

        # THE ID THE READ NAMED, where it named one this thread actually
        # holds. An id the file does not hold is DROPPED rather than carried:
        # a restatement pointing at nothing would silently become a new issue
        # anyway, and one pointing at another thread's issue would merge two
        # threads' work -- the silent direction in both cases.
        known = {i.id for i in standing}
        restates = str(row.get("restates") or "").strip()
        spotted.append(Issue(
            thread=thread,
            statement=statement,
            **({"id": restates} if restates in known else {}),
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
