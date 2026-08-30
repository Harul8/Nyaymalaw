"""The corpus manifest. PRD §4.5 / D5A.

M1 IS THE WHOLE DESIGN, AND GETTING IT BACKWARDS MAKES THIS USELESS
-------------------------------------------------------------------
The manifest states INTENDED coverage and is therefore CURATED. A manifest
generated from what the index contains can only tell you what is there. It can
never tell you what is MISSING, because absence leaves no trace to enumerate.

To detect a gap you need an independent assertion -- "the Limitation Act 1963,
all sections and the whole Schedule" -- against which absence becomes visible.

That assertion is what makes the three-state answer computable:

    zero hits + manifest says we hold it   -> HELD_NOT_FOUND, a DEFECT
    zero hits + manifest says we do not    -> NOT_HELD, an honest refusal

Without it, both look identical and the refusal rule is unfalsifiable.

Each entry carries the identifier PATTERNS the Act is held under, because the
corpus holds the same Act under more than one convention at different degrees
of completeness -- and a coverage figure from one store is refused, not
reported (check `act-1`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path

import yaml


def _expand(spec: list) -> tuple[str, ...]:
    """Expand "1-44" into every section in the range.

    Ranges are a WRITING convenience only. What is stored is the explicit set,
    because the manifest has to answer "should we hold s.6?" for one section at
    a time, and a range that is never expanded cannot answer it.
    """
    out: list[str] = []
    for item in spec:
        text = str(item)
        if "-" in text and text.replace("-", "").isdigit():
            lo, hi = text.split("-", 1)
            out.extend(str(n) for n in range(int(lo), int(hi) + 1))
        elif text.lower().startswith("article_") and "-" in text:
            _, rng = text.split("_", 1)
            lo, hi = rng.split("-", 1)
            out.extend(f"Article_{n}" for n in range(int(lo), int(hi) + 1))
        else:
            out.append(text)
    return tuple(out)


@dataclass(frozen=True)
class ManifestEntry:
    act_name: str
    act_patterns: tuple[str, ...]
    intended_sections: tuple[str, ...]
    keywords: tuple[str, ...] = ()
    in_force_from: date | None = None
    in_force_to: date | None = None
    jurisdiction: str = "Union of India"

    def covers(self, section: str) -> bool:
        return section in self.intended_sections

    def in_force_on(self, day: date) -> bool:
        """Was this instrument in force on the governing date?

        The 2024 codes make this load-bearing rather than pedantic: the CrPC
        and the BNSS both match "criminal procedure", and serving the
        superseded one for a 2025 offence is a wrong answer that reads exactly
        like a right one.
        """
        if self.in_force_from and day < self.in_force_from:
            return False
        if self.in_force_to and day > self.in_force_to:
            return False
        return True


class ActBasis(str, Enum):
    """How the governing Act was arrived at. The same shape as `Posture.basis`.

    The product already refuses to infer a POSTURE silently, because a guess
    there gives advice to the wrong side. An Act inferred silently is the same
    defect against a different field: it sends an exact section lookup into the
    wrong statute and reports the miss as a corpus gap.
    """

    NAMED = "named"          # the question names the Act. Exact match.
    INFERRED = "inferred"    # keyword routing. A CANDIDATE, and disclosed.


#: A four-digit year at the END of a title, with its separating comma.
#: Anchored, so a year inside a title -- `Rules, 1957 (Amendment)` --
#: is left alone.
_TRAILING_YEAR = re.compile(r",\s*\d{4}\s*$")


def title_without_year(act_name: str) -> str:
    """The Act's title with its year removed. ONE COPY, and this is it.

    It was `act_name.split(",")[0]`, in two places -- the resolver and the
    test that checks no title is a substring of another. That works only
    while no title contains a comma of its own, which was true of all 17
    Acts and false of the eighteenth:

        ANDHRA PRADESH BUILDINGS (LEASE, RENT AND EVICTION) CONTROL ACT, 1960

    split on the first comma that is `andhra pradesh buildings (lease` -- a
    fragment ending mid-parenthetical that no advocate would type, so the
    Act could never be NAMED and would fall through to keyword scoring,
    which is the one thing that must never decide which Act is read.
    """
    return _TRAILING_YEAR.sub("", (act_name or "").strip()).strip()




@dataclass(frozen=True)
class Resolution:
    """Which Act governs, and on what footing."""

    entry: "ManifestEntry | None"
    basis: ActBasis | None = None
    superseded: "ManifestEntry | None" = None
    matched_on: tuple[str, ...] = ()
    carried: bool = False
    """The Act was named on an EARLIER turn of this thread, not on this one.

    Still `NAMED` — it is the advocate's own instruction and it did not stop
    being their instruction because they moved on to the next question. But it
    is disclosed, because carrying an instruction forward is a thing the
    advocate should be able to see and correct."""
    alternatives: tuple[str, ...] = ()
    """Other Acts whose keywords also matched.

    Named in the disclosure so a WRONG inference is visible at a glance rather
    than discovered after the advocate has acted on it. The correction handle
    matters more than the guess: an advocate who sees "I took this as the
    Specific Relief Act; the Limitation Act also matched" fixes it in four
    words."""

    @property
    def must_disclose(self) -> bool:
        """An inferred Act is stated to the advocate so they can correct it.

        So is a CARRIED one. It is not a guess — the advocate named it — but
        they named it on a different turn, and an Act applied to a question it
        was not stated on is exactly the kind of carry-forward that must be
        visible rather than assumed.
        """
        if self.entry is None:
            return False
        return self.basis is ActBasis.INFERRED or self.carried

    def note(self) -> str:
        if not self.must_disclose:
            return ""
        if self.carried:
            return (f"You did not name an Act on this turn, so I am still "
                    f"working from the {self.entry.act_name} — you named it "
                    f"earlier on this thread. Say if this question is about "
                    f"something else.")
        note = (f"I am taking this as the {self.entry.act_name} because you "
                f"mentioned {', '.join(self.matched_on)}. You did not name an "
                f"Act, so this is my inference and not your instruction — say "
                f"if it is wrong.")
        if self.alternatives:
            note += (f" These also matched: {', '.join(self.alternatives)}.")
        return note


@dataclass(frozen=True)
class Manifest:
    entries: tuple[ManifestEntry, ...]
    corpus_version: str = "unreconciled"
    reconciled_at: date | None = None

    @staticmethod
    def load(path: str | Path) -> "Manifest":
        doc = yaml.safe_load(Path(path).read_text(encoding="utf8"))
        entries = tuple(
            ManifestEntry(
                act_name=e["act_name"],
                act_patterns=tuple(e["act_patterns"]),
                intended_sections=_expand(e["intended_sections"]),
                keywords=tuple(e.get("keywords", ())),
                in_force_from=(date.fromisoformat(e["in_force_from"])
                               if e.get("in_force_from") else None),
                in_force_to=(date.fromisoformat(e["in_force_to"])
                             if e.get("in_force_to") else None),
                jurisdiction=e.get("jurisdiction", "Union of India"),
            )
            for e in doc["acts"]
        )
        return Manifest(
            entries=entries,
            corpus_version=doc.get("corpus_version", "unreconciled"),
            reconciled_at=(date.fromisoformat(doc["reconciled_at"])
                           if doc.get("reconciled_at") else None),
        )

    def resolve(self, question: str, on: date | None = None,
                account: str = "") -> "Resolution":
        """Which Act governs the question ON THE GOVERNING DATE.

        Returns a `Resolution` carrying the entry AND ITS BASIS — named or
        inferred — because those are different facts and the caller must be
        able to tell them apart. `superseded` is the best keyword match
        that was EXCLUDED because it was not in force on that date, and it is
        returned rather than dropped so the caller can say *"the Act you are
        describing existed, on a different date"* instead of the flat and false
        *"not held"*.

        Dropping it silently is the failure this signature exists to prevent:
        a 2025 criminal matter matches the CrPC on keywords, the CrPC is out of
        force, and a bare `None` would report a corpus gap where the truth is a
        code transition.

        Keyword-scored and deliberately simple. This is the resolution layer at
        its thinnest; the cause-of-action graph that replaces it is slice 5.
        """
        low = question.lower()

        # AN ACT NAMED IN THE QUESTION BEATS EVERY KEYWORD SCORE.
        #
        # "does section 53A of the Transfer of Property Act protect him?" in a
        # brief about dispossession scored the SPECIFIC RELIEF ACT on
        # `possession` and `dispossessed`, looked for s.53A in it, and reported
        # "Specific Relief Act s.53A is not held in the corpus" — a corpus gap
        # for a provision the corpus holds, with the right Act named in the
        # same sentence as the section number.
        #
        # Keyword scoring reads the WHOLE question, so the more context an
        # advocate gives, the more likely it is to be outvoted. Every extra
        # sentence made it worse. Found on the first realistic multi-clause
        # question put through the interface.
        named = self._named_in(low, on)
        if named is not None:
            return Resolution(named, ActBasis.NAMED)

        # THE ACT THE ADVOCATE NAMED EARLIER ON THIS THREAD.
        #
        # An advocate names the Act once. Turn 1 is "a suit under section 6 of
        # the Specific Relief Act"; turn 4 is "what is the limitation?" -- and
        # reading turn 4 alone, this product had no Act at all and reported a
        # corpus gap for a provision it had retrieved three turns earlier.
        #
        # EXACT TITLE ONLY, and that restriction is the whole of the safety
        # argument. Keyword-scoring the accumulated account would be the
        # outvoting defect at scale: scoring already reads the whole question,
        # so the more the advocate says the more likely the wrong Act wins, and
        # an account is every sentence they have ever said. An exact title is
        # their instruction; a keyword hit across four turns is a guess with
        # more evidence for it than any single turn could supply.
        if account.strip():
            carried = self._named_in(account.lower(), on)
            if carried is not None:
                return Resolution(carried, ActBasis.NAMED, carried=True)

        best: ManifestEntry | None = None
        superseded: ManifestEntry | None = None
        best_score = superseded_score = 0
        for e in self.entries:
            hits = sum(1 for k in e.keywords if k.lower() in low)
            if not hits:
                continue
            if on is not None and not e.in_force_on(on):
                if hits > superseded_score:
                    superseded, superseded_score = e, hits
                continue
            if hits > best_score:
                best, best_score = e, hits

        # KEYWORD ROUTING NO LONGER IDENTIFIES. It offers a candidate whose
        # basis is `inferred`, and the caller must disclose it. Silently
        # returning it is what sent a Transfer of Property question into the
        # Specific Relief Act and reported a corpus gap for a held provision.
        if best is None:
            return Resolution(None, None, superseded)
        matched = tuple(k for k in best.keywords if k.lower() in low)
        others = tuple(e.act_name for e in self.entries
                       if e is not best
                       and any(k.lower() in low for k in e.keywords)
                       and (on is None or e.in_force_on(on)))
        return Resolution(best, ActBasis.INFERRED, superseded,
                          matched_on=matched, alternatives=others)

    def _named_in(self, low: str, on: date | None) -> ManifestEntry | None:
        """The Act the question NAMES, if it names one.

        Matched on the title without its year, so "the Transfer of Property
        Act" finds "Transfer of Property Act, 1882". The LONGEST match wins:
        "Code of Criminal Procedure" must not be beaten by a shorter title that
        happens to be a substring of it.
        """
        best: ManifestEntry | None = None
        best_len = 0
        for e in self.entries:
            title = title_without_year(e.act_name).lower()
            if len(title) > 6 and title in low and len(title) > best_len:
                if on is not None and not e.in_force_on(on):
                    continue
                best, best_len = e, len(title)
        return best

    def intends(self, entry: ManifestEntry, section: str) -> bool:
        return entry.covers(section)

    def act(self, name: str) -> ManifestEntry | None:
        return next((e for e in self.entries if e.act_name == name), None)
