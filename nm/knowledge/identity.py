"""Case identity recovered from the source judgments, and what it makes decidable.

Reads `.nm/identity.db`, built offline by `tools/build_identity_index.py` from
`legal_database/raw_data/CaseLaws/` — the layer the derived vector store dropped.

TWO THINGS BECOME POSSIBLE, AND NEITHER WAS BEFORE
---------------------------------------------------
1. BENCH STRENGTH. `Bench:` is present on 90.2% of source files, so the rule
   *a larger bench supersedes a smaller one within the same court* is
   computable for the great majority of judgments. It was declined on a
   measurement taken from the derived layer that put coverage at 7.5%.

2. A TREATMENT ANSWER THAT IS NOT SILENCE. The shipped citator reaches 0.83% of
   held judgments. Reporter citations reach 82.2%, and that changes the
   QUESTION that can be answered:

       before   "does the citator have an entry for this case?"   0.83% yes
       now      "does anything in the 34,037 judgments held
                 adversely treat this case?"                      82.2% answerable

   The second is a real check with a stated scope. The first was a fact about
   an index.

`CHECKED` IS NOT `GOOD LAW`, AND THE DIFFERENCE IS THE WHOLE POINT
-------------------------------------------------------------------
A case with citations that nothing here treats adversely is *not adversely
treated by anything in this corpus*. Treatment by a judgment the corpus does
not hold is invisible, and always will be. So the scope travels with the
answer, every time, and the advocate is told what was searched rather than
handed a verdict.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path

from nm.knowledge.jurisdiction import Court, normalise_court
from nm.ports.evidence import Treatment, TreatmentState


class Tier(IntEnum):
    """Court seniority. HIGHER WINS, and the ordering is the whole rule.

    `UNKNOWN` is 0 rather than a middle value on purpose: an unrecognised court
    must never out-rank a recognised one, and a comparison against it yields
    `NOT_COMPARABLE` rather than a quiet loss.
    """

    UNKNOWN = 0
    SUBORDINATE = 1
    HC_OTHER = 2
    HC_OWN = 3          # the High Court for this jurisdiction, or its predecessor
    SUPREME = 4


_TIER_OF = {
    Court.SUPREME_COURT: Tier.SUPREME,
    Court.HC_TELANGANA: Tier.HC_OWN,
    Court.HC_ANDHRA_PRADESH: Tier.HC_OWN,
    Court.HC_OTHER: Tier.HC_OTHER,
    Court.SUBORDINATE: Tier.SUBORDINATE,
    Court.UNKNOWN: Tier.UNKNOWN,
}


class Precedence(str, Enum):
    """Which of two authorities governs. THREE outcomes, never two.

    `NOT_COMPARABLE` is what an equal bench, an unknown bench or an unknown
    court returns. Forcing it to a winner would tell an advocate that one
    authority beats another when the rule does not say so — and two co-ordinate
    benches that disagree is a real situation with a real answer (the later is
    followed, or the point goes to a larger bench), not a ranking problem.
    """

    LEFT = "left"
    RIGHT = "right"
    NOT_COMPARABLE = "not_comparable"


@dataclass(frozen=True)
class CaseIdentity:
    case_id: str
    court: str | None = None
    year: int | None = None
    title: str | None = None
    bench_size: int | None = None
    bench: str | None = None
    petitioner: str | None = None
    respondent: str | None = None
    cited_by: int | None = None
    bench_source: str | None = None
    """HOW the bench size was established, not just what it is.

    `bench_header` and `coram_header` are STATED by the judgment.
    `author_inline` is INFERRED from the authoring judge where no coram is
    given -- 2,223 judgments, taken as one judge so they stay usable rather
    than being discarded.

    The inference can only ever rank an authority BELOW where it belongs: one
    is the minimum bench, so a Division Bench read as a single judge loses a
    comparison it should win, and nothing is ever ranked higher than it is.
    That is a recall cost, not a wrong answer — but a reader must still be able
    to see which it was, so it travels with the record.
    """

    @property
    def tier(self) -> Tier:
        return _TIER_OF[normalise_court(self.court)]

    @property
    def bench_known(self) -> bool:
        return bool(self.bench_size)

    @property
    def bench_inferred(self) -> bool:
        """The size came from the authoring judge, not from a stated coram."""
        return self.bench_source == "author_inline"

    def describe(self) -> str:
        """One line an advocate can weigh, in the vocabulary they use.

        An INFERRED size says so. "Single judge" read off a signature and
        "single judge" read off a coram are different facts, and an advocate
        deciding how much weight to give an authority is entitled to know
        which one they have.
        """
        n = self.bench_size
        if not n:
            return "bench not recorded"
        if self.bench_inferred:
            return "single judge (inferred from the authoring judge; no coram stated)"
        if n == 1:
            return "single judge"
        if n == 2:
            return "Division Bench (2)"
        if n >= 5:
            return f"Constitution Bench ({n})"
        return f"{n}-judge bench"


def supersedes(left: CaseIdentity, right: CaseIdentity) -> tuple[Precedence, str]:
    """THE HIERARCHY RULE, with the reason attached.

        the Supreme Court binds every High Court (Art. 141)
        within one court, a larger bench supersedes a smaller one

    A reason travels with the answer because an advocate who cannot see WHY one
    authority was ranked above another has to take it on trust, and this is a
    ranking they will act on.
    """
    if left.tier is Tier.UNKNOWN or right.tier is Tier.UNKNOWN:
        return Precedence.NOT_COMPARABLE, (
            "one of the courts could not be identified, so seniority cannot be "
            "established. It is not assumed")

    if left.tier != right.tier:
        winner = Precedence.LEFT if left.tier > right.tier else Precedence.RIGHT
        higher, lower = ((left, right) if left.tier > right.tier else (right, left))
        return winner, (f"{higher.court or 'the higher court'} is senior to "
                        f"{lower.court or 'the other court'}")

    if not (left.bench_known and right.bench_known):
        return Precedence.NOT_COMPARABLE, (
            "same court, and the bench is not recorded for at least one of "
            "them — a larger bench supersedes a smaller one, and that cannot "
            "be applied blind")

    if left.bench_size == right.bench_size:
        return Precedence.NOT_COMPARABLE, (
            f"co-ordinate benches ({left.describe()}). Neither supersedes the "
            f"other; a conflict between them is resolved by reference to a "
            f"larger bench, not by ranking")

    winner = (Precedence.LEFT if left.bench_size > right.bench_size
              else Precedence.RIGHT)
    bigger, smaller = ((left, right) if left.bench_size > right.bench_size
                       else (right, left))
    caveat = ""
    if smaller.bench_inferred:
        # The loser's size was inferred from its authoring judge. Say so: it
        # may have been a Division Bench that signed with one name, in which
        # case this ranking is too harsh on it. The error can only run this
        # way, and the advocate can check in one click.
        caveat = (" — though the smaller one's bench was inferred from its "
                  "authoring judge and may in fact have been larger")
    return winner, (f"{bigger.describe()} supersedes {smaller.describe()} in the "
                    f"same court{caveat}")


class IdentityIndex:
    """Read-only. Built offline, consulted at turn time.

    Absent, every method returns the NOT-KNOWN answer rather than a default —
    an unbuilt index must not be able to clear an authority.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._con: sqlite3.Connection | None = None

    @property
    def available(self) -> bool:
        return self._path.exists()

    def _connect(self) -> sqlite3.Connection | None:
        if not self.available:
            return None
        if self._con is None:
            self._con = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True,
                                        check_same_thread=False)
        return self._con

    def stats(self) -> dict:
        con = self._connect()
        if con is None:
            return {"available": False}
        rows = dict(con.execute("select key, value from identity").fetchall())
        rows["available"] = True
        return rows

    def rejects(self, field: str | None = None) -> list[tuple[str, str, int]]:
        """What could not be established, BY FIELD AND ERA.

        The corpus spans 1955-2026 and the header format drifts across it, so
        an undifferentiated NULL conflates "this judgment states no bench" with
        "this era writes it differently". Bench parsing misses a fifth of the
        1950s and none of the 2010s — a fact only an enumerated reject list can
        show, and only an enumerated list can be worked.
        """
        con = self._connect()
        if con is None:
            return []
        if field:
            return con.execute(
                "select field, era, count(*) from rejects where field = ?"
                " group by 1, 2 order by 2", (field,)).fetchall()
        return con.execute(
            "select field, era, count(*) from rejects group by 1, 2"
            " order by 1, 2").fetchall()

    def reject_reason(self, case_id: str, field: str) -> str | None:
        """Why one judgment's field could not be established."""
        con = self._connect()
        if con is None:
            return None
        row = con.execute(
            "select reason from rejects where case_id = ? and field = ?",
            (case_id, field)).fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------ identity ---
    def case(self, case_id: str) -> CaseIdentity | None:
        con = self._connect()
        if con is None:
            return None
        row = con.execute(
            "select case_id, court, year, title, bench_size, bench, petitioner,"
            " respondent, cited_by, bench_source from cases where case_id = ?",
            (case_id,)).fetchone()
        return CaseIdentity(*row) if row else None

    def addressable(self, case_id: str) -> bool:
        """Does this judgment carry a reporter citation?

        If not, nothing can cite it in a way this index can resolve, so a
        search finding nothing proves nothing — and the treatment answer must
        stay `NOT_CHECKED` rather than becoming a clearance.
        """
        con = self._connect()
        if con is None:
            return False
        return bool(con.execute(
            "select 1 from citations where case_id = ? limit 1",
            (case_id,)).fetchone())

    # ----------------------------------------------------------- treatment ---
    def treatment(self, case_id: str) -> Treatment:
        """Subsequent treatment within the corpus, or an honest refusal."""
        con = self._connect()
        if con is None:
            return Treatment.not_checked(
                "the identity index is not built, so no judgment was searched "
                "for subsequent treatment. Run "
                "`python tools/build_identity_index.py`")

        rows = con.execute(
            "select verb, grade, treating_case_id, treating_year, span"
            " from treatment where target_case_id = ?", (case_id,)).fetchall()

        adverse = [r for r in rows if r[1] == "adverse"]
        if adverse:
            verbs = tuple(sorted({r[0].upper() for r in adverse}))
            by = tuple(sorted({r[2] for r in adverse}))[:6]
            return Treatment(
                state=TreatmentState.NEGATIVE,
                # NOT A VERDICT. Extraction from prose gets direction wrong
                # some of the time -- "overruled by X" and "overruled X" are
                # one word apart -- so this says a passage EXISTS and hands it
                # over. Asserting that a judgment is overruled on a regex is
                # the confident wrong answer this product exists to refuse.
                scope=(f"{len(adverse)} passage(s) in the corpus appear to treat "
                       f"this adversely. The passages are recorded and can be "
                       f"read back. This is an extraction from prose, not a "
                       f"holding: read them before relying on the judgment, and "
                       f"note that WHICH proposition was treated is not recorded"),
                verbs=verbs, by=by, source="identity_index")

        if not self.addressable(case_id):
            # Not a clearance. Nothing can cite this judgment in a form the
            # index resolves, so finding nothing establishes nothing.
            return Treatment.not_checked(
                "this judgment carries no reporter citation, so no citation to "
                "it could be resolved. Nothing was established either way")

        scope = [r for r in rows if r[1] == "scope"]
        positive = [r for r in rows if r[1] == "positive"]
        note = []
        if positive:
            note.append(f"followed or approved in {len(positive)} passage(s)")
        if scope:
            note.append(f"distinguished in {len(scope)} passage(s)")

        # CHECKED, and the SCOPE OF THE CHECK travels with it. This is a
        # statement about 34,037 judgments, not about Indian law.
        return Treatment(
            state=TreatmentState.CLEAN,
            scope=("no adverse treatment found in the 34,037 judgments held"
                   + (" — " + "; ".join(note) if note else "")
                   + ". Treatment by a judgment outside this corpus is not "
                     "visible to me"),
            verbs=tuple(sorted({r[0].upper() for r in scope + positive})),
            by=tuple(sorted({r[2] for r in scope + positive}))[:6],
            source="identity_index")
