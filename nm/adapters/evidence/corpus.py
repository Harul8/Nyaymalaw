"""Evidence from the real corpus.

Rules from `docs/BASELINE.md` are enforced here rather than remembered, because
each has already produced a wrong answer in this project:

  act-1  COVERAGE IS A UNION across every store and identifier convention.
         The same Act is held under `the_specific_relief_act_1963` (13 sections)
         and `UNION OF INDIA_1963_1_THE SPECIFIC RELIEF ACT, 1963` (all 44).
         Querying one store reports a gap that is not there.

  S3     A ZERO RESULT NAMES THE INDEX IT CAME FROM. `case_name` holds party
         names, so a subject search against it returns zero -- and zero reads
         exactly like "not in the corpus".

  bind-1 Binding status is COMPUTED from court and date against the matter's
         jurisdiction (`nm/knowledge/jurisdiction.py`), never asserted here.

Absence is never inferred from a hit count. It is computed against the
manifest, which is what makes the three-state answer possible at all.

THE AUTHORITY INDEX IS SEPARATE, AND ITS ABSENCE IS VISIBLE
------------------------------------------------------------
Case-law retrieval reads `.nm/authority.db`, built offline by
`tools/build_authority_index.py`. When that index is absent this adapter
returns HELD_NOT_FOUND naming it -- it does NOT fall back to scanning
`chunks.db`. A fallback with different recall, swapped in silently, is the
"three stores, three answers" defect wearing a helpful face: the advocate would
have no way to know which retrieval answered them.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from nm.domain.citation import last_wanted_section, wanted_section
from nm.domain.matter import CauseOfAction
from nm.domain.traceability import implements
from nm.knowledge.citator import Citator
from nm.knowledge.identity import IdentityIndex
from nm.knowledge.jurisdiction import binding_status
from nm.knowledge.manifest import Manifest, title_without_year
from nm.knowledge.resolution import (
    CODE_TITLES,
    article_for,
    corresponding,
    governs,
)
from nm.ports.evidence import (
    Binding,
    Coverage,
    EvidenceNeed,
    EvidenceResult,
    Finding,
    Origin,
    ParaKind,
    SourceKind,
    Treatment,
)

_ATTRIBUTABLE = ("ratio", "reasoning", "order")

#: How many ranked paragraphs the authority search EXAMINES in one turn.
#:
#: A bound and not a filter, and the difference is the whole of H4. It caps
#: work; it does not decide relevance. When it binds, the answer says so and
#: says how many were not examined -- so a miss caused by the ceiling can be
#: told apart from an absence in the corpus.
EXAMINED_CEILING = 40


@dataclass(frozen=True)
class _Routed:
    """What the graph resolved: the Act, the provision, and the disclosure."""

    entry: object
    provision: str
    note: str



class CorpusEvidenceAdapter:
    """Reads the bare-act chunks and, when built, the authority index.

    Read-only throughout. It never writes to the corpus.
    """

    def __init__(self, corpus_dir: str | Path, manifest: Manifest,
                 jurisdiction: str = "Telangana",
                 authority_index: str | Path | None = None,
                 identity_index: str | Path | None = None) -> None:
        self._dir = Path(corpus_dir)
        self._db = self._dir / "chunks.db"
        self._manifest = manifest
        self._jurisdiction = jurisdiction
        self._authority_db = Path(authority_index) if authority_index else None
        self._identity = IdentityIndex(
            identity_index or (Path(authority_index).parent / "identity.db"
                               if authority_index else "nonexistent"))
        self._citator = Citator(self._dir / "citator.json", identity=self._identity)
        self._denied: set[str] | None = None

    # ----------------------------------------------------------- readiness ---
    @property
    def available(self) -> bool:
        return self._db.exists()

    @property
    def authority_available(self) -> bool:
        return bool(self._authority_db and self._authority_db.exists())

    def readiness(self) -> dict:
        """Three states per capability, reported at /api/health.

        A capability that cannot run must be visible BEFORE a turn depends on
        it, not discovered as an empty answer afterwards.
        """
        return {
            "provisions": "readable" if self.available else "NOT READABLE",
            "authorities": ("readable" if self.authority_available else
                            "INDEX NOT BUILT -- run tools/build_authority_index.py"),
            "citator": (f"{self._citator.entries} entries"
                        if self._citator.available else "NOT READABLE"),
            "identity": (
                f"{self._identity.stats().get('cases', '?')} cases, "
                f"{self._identity.stats().get('with_bench', '?')} with a bench"
                if self._identity.available else
                "INDEX NOT BUILT -- run tools/build_identity_index.py"),
            "denylist": f"{len(self._denylist())} chunk(s) excluded",
        }

    def _denylist(self) -> set[str]:
        """Chunks the corpus itself marks as contaminated.

        A denylist that ships beside the data and is never applied is worse
        than none: it records that someone knew the text was bad.
        """
        if self._denied is None:
            path = self._dir / "contamination_denylist.json"
            if not path.exists():
                self._denied = set()
            else:
                doc = json.loads(path.read_text(encoding="utf8", errors="replace"))
                self._denied = set(doc.get("chunk_ids") or ())
        return self._denied

    # --------------------------------------------------------------- fetch ---
    def fetch(self, need: EvidenceNeed) -> EvidenceResult:
        if not self.available:
            # The corpus could not be read. That is NOT "nothing is held" --
            # an absent input must never read as an answer.
            return EvidenceResult(
                coverage=Coverage.HELD_NOT_FOUND,
                missing=f"the corpus is not readable at {self._db}",
                searched_stores=(),
            )

        if need.want_authority:
            return self._fetch_authority(need)

        # H3 — RESOLUTION BEFORE SEARCH, AND BEFORE KEYWORDS.
        #
        # The graph gets the first word. Where the cause of action resolves,
        # BOTH the Act and the provision come from the edge, exactly, and no
        # keyword is consulted at all.
        #
        # It has to come first to be worth anything. Run after the keyword
        # resolver, it never fires on the case it was built for: "is the claim
        # still in time" matches no keyword, so `resolve` returns nothing, and
        # the turn ends at "no Act in the curated manifest governs this
        # question" before any edge is reached. That is B-065 precisely — and
        # it happened on twenty-three consecutive served turns.
        routed = self._route(need)
        if routed is not None:
            return self._read(routed.entry, routed.provision, need, routed.note)

        resolved = self._manifest.resolve(need.question, on=need.governing_date,
                                          account=need.account)
        entry, superseded = resolved.entry, resolved.superseded
        # THE GUESS TRAVELS WITH EVERY OUTCOME, not only with success.
        #
        # This used to be attached to the one return that produced
        # findings, so a WRONG inference that found nothing was reported as
        # a flat fact about the Act it had guessed: "Specific Relief Act,
        # 1963 is held, but no specific provision was identified" -- on a
        # question about LIMITATION, where the Act had been picked off the
        # word `possession`. Every word true, the whole misleading.
        #
        # The guess matters MOST when it produced nothing, because that is
        # when the advocate has no other signal that the wrong Act was read.
        note = resolved.note() or None
        if entry is None:
            missing = ("no Act in the curated manifest governs this question. "
                       "The manifest states INTENDED coverage, so this is an "
                       "honest gap rather than a failed lookup.")
            if superseded is not None:
                # The keyword match WAS an Act we hold -- it was simply not in
                # force on the governing date. Saying "not held" there would be
                # a lie about the corpus and hide a real answer.
                missing = (
                    f"{superseded.act_name} matched this question but was not in "
                    f"force on {need.governing_date.isoformat()} (in force "
                    f"{superseded.in_force_from or 'unrecorded'} to "
                    f"{superseded.in_force_to or 'date'}), and the successor "
                    f"instrument is not resolvable from the manifest alone. "
                    f"Provision correspondence across the 2024 codes is slice 5.")
            return EvidenceResult(coverage=Coverage.NOT_HELD, missing=missing,
                                  searched_stores=("manifest",),
                                  assumption=note)

        section = self._wanted_section(need)
        if section is None:
            return EvidenceResult(
                coverage=Coverage.NOT_HELD,
                missing=(f"{entry.act_name} is held, but no specific provision "
                         f"was identified in the question to retrieve, and the "
                         f"cause of action was not established well enough to "
                         f"look one up."),
                searched_stores=("manifest",),
                assumption=note,
            )
        return self._read(entry, section, need, note)

    def _read(self, entry, section: str, need: EvidenceNeed,
              note: str | None) -> EvidenceResult:
        """Look the provision up and answer in three states. ONE OWNER.

        Both paths into retrieval end here — the graph's exact route and the
        manifest's keyword match — so the union lookup, the HELD-BUT-NOT-FOUND
        rule and the disclosure are written once. Two copies of "zero hits, and
        the manifest decides which of the two states this is" would drift
        within a slice, and the half that drifted would report a corpus gap for
        an Act held in full.
        """
        findings, stores = self._union_lookup(entry.act_patterns, section, entry, need)
        if findings:
            return EvidenceResult(coverage=Coverage.ANSWERED, findings=findings,
                                  searched_stores=stores, assumption=note)

        # Zero hits. The manifest -- not the hit count -- decides which of the
        # two remaining states this is.
        if self._manifest.intends(entry, section):
            return EvidenceResult(
                coverage=Coverage.HELD_NOT_FOUND,
                missing=(f"{entry.act_name} s.{section} is declared as intended "
                         f"coverage but was not retrieved from {', '.join(stores)}. "
                         f"This is a RETRIEVAL DEFECT, not a corpus gap."),
                searched_stores=stores,
                assumption=note,
            )
        return EvidenceResult(
            coverage=Coverage.NOT_HELD,
            missing=f"{entry.act_name} s.{section} is not held in the corpus.",
            searched_stores=stores,
            assumption=note,
        )

    # ------------------------------------------------------------ internals ---
    def _wanted_section(self, need: EvidenceNeed) -> str | None:
        """WHICH provision the question asks for.

        The pattern lives in `nm/domain/citation.py` and is shared with the
        grounding gate. It used to be a second copy here, and when the gate's
        copy was hardened against `O.S. 442/2023` parsing as "section 442",
        this one was not -- so a realistic brief retrieved section 442 of the
        Specific Relief Act, found nothing, and reported a corpus gap.
        """
        # THIS TURN FIRST, then the thread. "What is the limitation on that?"
        # names no section; the section it means is the one named two turns
        # ago, and the alternative is telling the advocate their own file holds
        # no provision.
        return (need.provision_hint or wanted_section(need.question)
                or last_wanted_section(need.account))

    @implements("D4")
    def _route(self, need: EvidenceNeed) -> "_Routed | None":
        """H3. The Act AND the provision the cause of action points at.

        `None` where nothing resolves, and that is the ordinary case rather
        than a failure — the question then goes to the keyword resolver and, if
        that finds nothing either, to search, carrying its own confidence. What
        this may never do is return a near neighbour: an exact lookup that
        guesses is the wrong-Act defect with better manners.

        THE ADVOCATE'S OWN WORDS OUTRANK THE GRAPH. Where they have named a
        section, `_wanted_section` has it and no routing is needed or wanted;
        this fires only where the question is determinate and unspecified.
        """
        if not need.cause_of_action:
            return None
        if wanted_section(need.question):
            # THE ADVOCATE NAMED A PROVISION. Routing past it would substitute
            # this product's view of the cause for their instruction, which is
            # the one thing an exact lookup must never do.
            return None
        try:
            cause = CauseOfAction(need.cause_of_action)
        except ValueError:
            # OUT OF VOCABULARY IS NOT A ROUTE. It reaches here only if a
            # caller bypassed the reader's guard, and accepting it would make
            # an unvetted string a routing decision.
            return None
        edge = article_for(cause)
        if edge is None:
            return None
        entry = self._manifest.act(edge.act)
        if entry is None or not entry.in_force_on(need.governing_date):
            # THE GRAPH ROUTES TO AN ACT THE MANIFEST DOES NOT DECLARE, or does
            # not declare as in force on this date. The edge is not wrong; the
            # corpus simply cannot serve it, and pretending otherwise would
            # report a retrieval defect as a legal answer.
            return None

        note = (f"You named no provision, so I resolved one: the cause reads as "
                f"{cause.value.replace('_', ' ')}, which the graph routes to "
                f"{edge.act} {edge.provision.replace('_', ' ')} "
                f"({edge.curated_from})")
        if edge.alternatives:
            # WHAT ELSE IT COULD HAVE BEEN, named. A wrong route is then
            # visible at a glance instead of after the advocate has acted on it.
            note += f". Also arguable: {'; '.join(edge.alternatives)}"
        return _Routed(entry=entry, provision=edge.provision, note=note)

    def _union_lookup(self, patterns: tuple[str, ...], section: str, entry,
                      need: EvidenceNeed):
        """THE UNION. EVERY identifier convention, and the store is NAMED.

        The first version stopped at the first pattern that hit. It worked only
        because the fuller store happened to be listed first in the manifest —
        reverse the order and Specific Relief Act s.6 comes back NOT FOUND from
        an Act that holds all 44 sections. That is B-164 exactly, sitting
        latent behind a line of YAML.

        `act-1` says coverage is the union across every store AND that the
        answer names which store supplied it. Both halves are load-bearing: a
        union that short-circuits is an ordering assumption, and a store name
        that reports only where the search stopped cannot support the claim.

        Where two stores both hold the section, the FULLER TEXT wins. The thin
        copies are not merely incomplete, they are truncated, and a scattered
        13-section copy of a 44-section Act is exactly what produced the false
        gap in the first place.
        """
        stores: list[str] = []
        candidates: list[Finding] = []
        con = sqlite3.connect(f"file:{self._db}?mode=ro", uri=True)
        try:
            for pattern in patterns:
                stores.append(pattern)
                row = con.execute(
                    """select act_id, atom_type, chunk_id, blob from chunks
                       where doc_type='bare_act' and act_id like ? and section_number=?
                       order by case atom_type when 'section_head' then 0 else 1 end
                       limit 1""",
                    (pattern, section)).fetchone()
                if row is None:
                    continue
                act_id, atom_type, chunk_id, blob = row
                if chunk_id in self._denylist():
                    continue
                text = " ".join((json.loads(blob).get("full_text") or "").split())
                if not text:
                    continue
                candidates.append(Finding(
                    proposition=f"{entry.act_name} s.{section}",
                    source_kind=SourceKind.PROVISION,
                    ref=f"{entry.act_name} s.{section}",
                    span=text,
                    locator=f"{act_id}::{section}::{atom_type}",
                    store=act_id,
                    binding=Binding.BINDING,
                    binding_for=self._jurisdiction,
                    binding_reason=(
                        f"{entry.act_name} is {entry.jurisdiction} legislation in "
                        f"force on {need.governing_date.isoformat()}; it applies of "
                        f"its own force in {self._jurisdiction}"),
                    supports=True,
                    para_kind=ParaKind.UNKNOWN,
                    treatment=Treatment.statutory(),
                    valid_from=entry.in_force_from,
                    valid_to=entry.in_force_to,
                    governing_date=need.governing_date,
                    origin=Origin.RESOLVED,
                ))
        finally:
            con.close()

        if not candidates:
            return (), tuple(stores)
        # The fullest text wins, and EVERY store searched is named.
        best = max(candidates, key=lambda f: len(f.span))
        return (best,), tuple(stores)

    # ---------------------------------------------------------- authorities ---
    def _fetch_authority(self, need: EvidenceNeed) -> EvidenceResult:
        if not self.authority_available:
            # NOT an empty result. The capability exists and its index does
            # not, and those are different sentences.
            return EvidenceResult(
                coverage=Coverage.HELD_NOT_FOUND,
                missing=(
                    "the authority index is not built, so no judgment was "
                    "searched. 451,553 attributable paragraphs are held and "
                    "none of them was consulted on this turn. Build it with "
                    "`python tools/build_authority_index.py`."),
                searched_stores=("authority_index:absent",),
            )

        terms = self._terms(need)
        if not terms:
            return EvidenceResult(
                coverage=Coverage.NOT_HELD,
                missing="no searchable terms were identified in the question.",
                searched_stores=("authority_index",))

        con = sqlite3.connect(f"file:{self._authority_db}?mode=ro", uri=True)
        try:
            rows = con.execute(
                """select case_id, case_name, court, year, para_type, chunk_id, text
                   from paras where paras match ?
                   order by rank limit ?""",
                (" OR ".join(f'"{t}"' for t in terms),
                 EXAMINED_CEILING + 1)).fetchall()
        except sqlite3.OperationalError as exc:
            return EvidenceResult(
                coverage=Coverage.HELD_NOT_FOUND,
                missing=f"the authority index could not be queried: {exc}",
                searched_stores=("authority_index",))
        finally:
            con.close()

        # H4 — A CEILING THAT BINDS IS REPORTED, never silent.
        #
        # This was `limit 40`, and forty is a TOP-K CUT ON A SIMILARITY ORDER,
        # which is the one thing H4 names: *no top-k or absolute-threshold
        # cut... any similarity exclusion is an outlier rejection with a
        # recorded, measured gap, and it names what it rejected.* The
        # forty-first paragraph was discarded with no count and no trace, so a
        # miss caused by the cut was indistinguishable from an absence in the
        # corpus — the defect shape this whole product is organised against.
        #
        # The ceiling stays, because an unbounded scan of 451,553 attributable
        # paragraphs on every turn is not a retrieval strategy. What changes is
        # that it is VISIBLE when it binds, exactly as `MAX_EVIDENCE_ROUNDS` is
        # visible through `evidence_bound_hit`.
        truncated = len(rows) > EXAMINED_CEILING
        rows = rows[:EXAMINED_CEILING]

        findings: list[Finding] = []
        # THE STRUCTURAL FLOOR. A paragraph matching one incidental word of a
        # multi-word question has not answered it -- FTS ORs the terms, so
        # "doctrine" alone will match tens of thousands of paragraphs.
        #
        # This is a LEXICAL COVERAGE test, not a similarity threshold: PRD H4
        # forbids an absolute cut on a score, because a score cut discards
        # things that might be right and leaves no trace. Every rejection here
        # is counted and the count is reported.
        floor = 2 if len(terms) >= 2 else 1
        thin = 0
        for case_id, case_name, court, year, para_type, chunk_id, text in rows:
            if chunk_id in self._denylist():
                continue
            kind = ParaKind(para_type) if para_type in _ATTRIBUTABLE else ParaKind.UNKNOWN
            if not kind.attributable:
                # G-ATTRIB. Counsel's submission is 14.8% of the corpus and
                # reads exactly like a holding, so it is dropped here rather
                # than ranked lower.
                continue
            body = (text or "").lower()
            matched = sum(1 for t in terms if t in body)
            if matched < floor:
                thin += 1
                continue
            ruling = binding_status(court, year, need.jurisdiction)
            ident = self._identity.case(case_id)
            bench = f"; {ident.describe()}" if ident else ""
            findings.append(Finding(
                proposition=need.question.strip()[:200],
                source_kind=SourceKind.AUTHORITY,
                ref=f"{case_name} ({court}, {year}{bench})",
                span=" ".join((text or "").split()),
                locator=f"{case_id}::{chunk_id}::{para_type}",
                store="authority_index",
                binding=ruling.status,
                binding_for=need.jurisdiction,
                binding_reason=f"{ruling.rule}: {ruling.reason}",
                supports=True,
                para_kind=kind,
                treatment=self._citator.treatment(case_name, case_id=case_id),
                governing_date=need.governing_date,
                origin=Origin.SEARCHED,
                # Lexical coverage of the question, NOT a relevance score. It
                # says how much of what was asked this paragraph contains, and
                # nothing at all about whether it answers it.
                confidence=round(matched / len(terms), 2),
            ))

        if findings:
            findings.sort(key=lambda f: -(f.confidence or 0.0))
            era = self._era_note(need)
            cut = (f"The index returned more than {EXAMINED_CEILING} ranked "
                   f"matches and only the first {EXAMINED_CEILING} were "
                   f"examined. There may be authority I did not reach; this is "
                   f"a bound on my search, not a statement about the corpus."
                   if truncated else None)
            return EvidenceResult(
                coverage=Coverage.ANSWERED, findings=tuple(findings),
                searched_stores=("authority_index",),
                assumption=". ".join(x for x in (era, cut) if x) or None)
        return EvidenceResult(
            coverage=Coverage.NOT_HELD,
            missing=(
                f"no attributable paragraph in the authority index matched at "
                f"least {floor} of the terms {', '.join(terms)}."
                + (f" {thin} paragraph(s) matched only one term and were rejected "
                   f"as incidental rather than served as authority." if thin else "")
                + " The index covers ratio, reasoning and order paragraphs only."),
            searched_stores=("authority_index",))

    # Words that say WHAT KIND of thing is wanted rather than what it is about.
    # In an authority search "is there any judgment we can rely on" is entirely
    # scaffolding -- `want_authority` already carries that meaning -- and
    # letting those words occupy the term budget is what returned three
    # judgments about substantial questions of law for a query about summary
    # possession.
    _SCAFFOLD = {
        "the", "a", "an", "of", "for", "and", "our", "we", "is", "in", "to", "on",
        "what", "which", "client", "matter", "case", "act", "under", "there",
        "any", "judgment", "judgement", "judgments", "ruling", "authority",
        "authorities", "precedent", "rely", "relied", "whether", "please",
        "does", "should", "would", "could", "can", "tell", "give", "need",
        "want", "know", "help", "about", "with", "from", "this", "that",
        "have", "has", "been", "was", "were", "are", "will", "shall",
    }

    @classmethod
    def _terms(cls, need: EvidenceNeed) -> list[str]:
        """The search terms, in the order they will be spent.

        The budget is small, so ORDER IS THE WHOLE DESIGN. The caller puts the
        resolved provision's subject FIRST and the advocate's phrasing after,
        because the question names the section and the section names the
        subject -- and taking six terms positionally from the question alone
        spends every slot on scaffolding.
        """
        words = re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", need.question.lower())
        seen: list[str] = []
        for w in words:
            if w not in cls._SCAFFOLD and w not in seen:
                seen.append(w)
        # D3B — THE SUBJECT UNDER THE OTHER CODE, ADDED TO THE TERMS.
        #
        # "Case law is overwhelmingly pre-2024 and cites the old numbering, so
        # a system searching only the new number retrieves almost nothing"
        # (T-051). A charge under BNS s.329 has its authority under IPC s.447,
        # and searching the new number alone finds a corpus that appears empty
        # on a subject it holds thousands of judgments about.
        #
        # ADDED, never substituted. H4 forbids discarding anything that might
        # be right, and the advocate's own words stay at the front of the
        # budget — this widens recall rather than redirecting it.
        seen.extend(w for w in cls._corresponding_terms(need) if w not in seen)
        return seen[:8]

    @implements("D4")
    def _era_note(self, need: EvidenceNeed) -> str | None:
        """THE ERA RULE, said out loud when a code is named.

        *The governing date is the date of the CONDUCT*, not the date of the
        advice — and the two now sit on opposite sides of 1 July 2024 for most
        of what an advocate carries. An advocate reading authority under IPC
        s.447 on a 2025 charge needs to know which of those the retrieval
        thought it was answering, because both answers are defensible and only
        one is theirs.

        `None` where no code is named: this speaks only when there is something
        to be wrong about.
        """
        low = need.question.lower()
        named = [act for act in CODE_TITLES
                 if title_without_year(act).lower() in low]
        if not named:
            return None
        return (f"Conduct on {need.governing_date.isoformat()} is governed by "
                f"{governs(need.governing_date)}. If the conduct happened on a "
                f"different date from the one on this file, say so — the "
                f"governing date is the date of the conduct, not of the advice.")

    @classmethod
    @implements("D4")
    def _corresponding_terms(cls, need: EvidenceNeed) -> list[str]:
        """Subject words for the same provision under the other code.

        Returns nothing when the question names no provision this graph holds a
        verified pair for, which is the ordinary case. The pair list is short
        and deliberately so: an unverified correspondence would send the
        advocate to authority on a different subject, which is worse than
        retrieving nothing.
        """
        section = wanted_section(need.question)
        if not section:
            return []
        # WHICH CODE THE SECTION IS IN MUST BE STATED, never inferred from the
        # digits. `s.447` means different things in different codes, and a
        # lookup on the number alone is the wrong-Act defect one level down --
        # the one CLAUDE.md §5 measured matching the Indian Easements Act to
        # the Indian Evidence Act on the shared word `Indian`.
        low = need.question.lower()
        named = [act for act in CODE_TITLES
                 if title_without_year(act).lower() in low]
        for act in named:
            match = corresponding(act, section)
            if match is None:
                continue
            # The SUBJECT, not the number: the old judgment says "criminal
            # trespass", and matching digits across codes is exactly the
            # wrong-Act defect one level down.
            return [w for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}",
                                          match.subject.lower())
                    if w not in cls._SCAFFOLD]
        return []


def default_authority_index(root: Path) -> Path:
    return Path(root) / ".nm" / "authority.db"


def in_force_on(entry, day: date) -> bool:
    if entry.in_force_from and day < entry.in_force_from:
        return False
    if entry.in_force_to and day > entry.in_force_to:
        return False
    return True
