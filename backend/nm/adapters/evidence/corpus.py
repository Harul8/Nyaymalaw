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
         jurisdiction (`backend/nm/knowledge/jurisdiction.py`), never asserted here.

Absence is never inferred from a hit count. It is computed against the
manifest, which is what makes the three-state answer possible at all.

THE AUTHORITY INDEX IS SEPARATE, AND ITS ABSENCE IS VISIBLE
------------------------------------------------------------
Case-law retrieval reads `.nm/authority.db`, built offline by
`pipeline/indexing/build_authority_index.py`. When that index is absent this adapter
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
from fnmatch import fnmatchcase
from pathlib import Path

from nm.domain.citation import last_wanted_section, wanted_section
from nm.domain.clock import FORUM
from nm.domain.matter import CauseOfAction
from nm.domain.text import snippet
from nm.domain.traceability import implements
from nm.knowledge.citator import Citator
from nm.knowledge.identity import IdentityIndex
from nm.knowledge.jurisdiction import binding_status
from nm.domain.citation import provision_label
from nm.knowledge.manifest import (
    CorpusPublicationRefused,
    Manifest,
    PublishedCorpus,
    title_without_year,
)
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
    SourceDocument,
    SourceKind,
    Treatment,
    kind_for_corpus_label,
)

#: How many ranked paragraphs the authority search EXAMINES in one turn.
#:
#: A bound and not a filter, and the difference is the whole of H4. It caps
#: work; it does not decide relevance. When it binds, the answer says so and
#: says how many were not examined -- so a miss caused by the ceiling can be
#: told apart from an absence in the corpus.

def _section_order(number: str) -> tuple:
    """Sections sort as an advocate reads them: 2, 2A, 3, 10 -- not 10, 2, 2A."""
    digits = re.match(r"(\d+)", number or "")
    return (int(digits.group(1)) if digits else 10**9, number or "")

EXAMINED_CEILING = 40


def _squash(text: str) -> str:
    """Whitespace collapsed, case folded: the form containment is judged in."""
    return " ".join((text or "").split()).lower()


def assemble_section(atoms: list[tuple[str, str]]) -> str:
    """THE WHOLE TEXT OF ONE PROVISION, from every atom a store holds for it.

    ONE COPY, and both readers call it: the provision a turn retrieves
    (`_union_lookup`) and the provision the document reader shows (LB-92).

    `atoms` is `(atom_type, full_text)` in the store's own order. Each atom's
    `full_text` is a label line -- "<Act> . s.18(2)(a): <heading>" -- and then
    the provision's own words.

    THE MEASURED DEFECT, 26 September 2026. Both readers took ONE atom per
    section -- the section head where there was one, else whichever came
    first or was longest. Where a store keeps the head as a heading only, or
    has no head at all, that one atom is part of the section: Limitation Act
    s.18 came back as sub-section (1) alone, without (2) or the Explanation
    the acknowledgment cases turn on. Across the 3,402 provisions the manifest
    intends, 760 were returned part-read, and every one was marked resolved
    and supporting.

    THE TEXT IS THE UNION, IN ORDER, WITH NOTHING SAID TWICE. The head leads
    and is kept whole, label included, so a section it already carries in full
    reads exactly as it did; every other atom adds its own words -- its label
    line dropped -- unless those words are already in the text. Verbatim
    throughout: nothing is paraphrased, reordered within an atom or supplied.
    """
    ordered = ([a for a in atoms if a[0] == "section_head"]
               + [a for a in atoms if a[0] != "section_head"])
    parts: list[str] = []
    for _atom_type, full_text in ordered:
        text = (full_text or "").strip()
        if not text:
            continue
        # The label is the first line; the words are the rest. The first atom
        # keeps its label, because the text has always begun with one.
        head, _, rest = text.partition("\n")
        words = rest.strip() or head
        if parts and _squash(words) in _squash(" ".join(parts)):
            continue
        parts.append(text if not parts else words)
    return " ".join(" ".join(parts).split())


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
                 jurisdiction: str = FORUM,
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
        self._published_snapshot: PublishedCorpus | None = None

    @classmethod
    def from_published_corpus(
        cls,
        publication_root: str | Path,
        *,
        corpus_database: str = "corpus/chunks.db",
        coverage_manifest: str = "corpus/manifest.yaml",
        authority_index: str = "indexes/authority.db",
        identity_index: str = "indexes/identity.db",
        jurisdiction: str = FORUM,
    ) -> "CorpusEvidenceAdapter":
        """Bind one request adapter to one fully verified active generation.

        A fresh adapter observes a later atomic cutover.  An adapter already in
        use remains on its immutable generation, so one legal answer can never
        mix files from before and after the pointer replacement.
        """
        snapshot = PublishedCorpus.open(publication_root, verify_all=True)
        return cls.from_published_snapshot(
            snapshot,
            corpus_database=corpus_database,
            coverage_manifest=coverage_manifest,
            authority_index=authority_index,
            identity_index=identity_index,
            jurisdiction=jurisdiction,
        )

    @classmethod
    def from_published_snapshot(
        cls,
        snapshot: PublishedCorpus,
        *,
        corpus_database: str = "corpus/chunks.db",
        coverage_manifest: str = "corpus/manifest.yaml",
        authority_index: str = "indexes/authority.db",
        identity_index: str = "indexes/identity.db",
        jurisdiction: str = FORUM,
    ) -> "CorpusEvidenceAdapter":
        """Build from an already-bound snapshot shared by all retrieval ports."""
        database = snapshot.member_path(corpus_database)
        manifest = Manifest.load(snapshot.member_path(coverage_manifest))
        authority = (
            snapshot.member_path(authority_index)
            if snapshot.has_member(authority_index) else None
        )
        identity = (
            snapshot.member_path(identity_index)
            if snapshot.has_member(identity_index) else None
        )
        adapter = cls(
            database.parent,
            manifest,
            jurisdiction=jurisdiction,
            authority_index=authority,
            identity_index=identity,
        )
        adapter._db = database
        adapter._published_snapshot = snapshot
        return adapter

    # ----------------------------------------------------------- readiness ---
    @property
    def available(self) -> bool:
        try:
            if self._published_snapshot is not None:
                self._published_snapshot.require_usable()
        except CorpusPublicationRefused:
            return False
        return self._db.exists()

    @property
    def authority_available(self) -> bool:
        return self.available and bool(self._authority_db and self._authority_db.exists())

    @property
    def published_snapshot_id(self) -> str | None:
        return (
            self._published_snapshot.snapshot_id
            if self._published_snapshot is not None else None
        )

    def withdrawn_sources(self) -> frozenset[str]:
        """The generation's withdrawals, read from its durable events. P21.

        Only when a published generation is bound: the legacy layout has no
        withdrawal record to read, and inventing an empty one would be the
        clean bill EVAL-014 refuses.
        """
        if self._published_snapshot is None:
            return frozenset()
        from nm.knowledge.manifest import withdrawn_versions

        return withdrawn_versions(self._published_snapshot.root)

    def readiness(self) -> dict:
        """Three states per capability, reported at /api/health.

        A capability that cannot run must be visible BEFORE a turn depends on
        it, not discovered as an empty answer afterwards.
        """
        if self._published_snapshot is not None:
            try:
                self._published_snapshot.require_usable()
            except CorpusPublicationRefused as exc:
                return {name: f"NOT ASSESSED -- {exc}" for name in (
                    "provisions", "authorities", "citator", "identity", "denylist",
                )}
        return {
            "provisions": "readable" if self.available else "NOT READABLE",
            "authorities": ("readable" if self.authority_available else
                            "INDEX NOT BUILT -- run pipeline/indexing/build_authority_index.py"),
            "citator": (f"{self._citator.entries} entries"
                        if self._citator.available else "NOT READABLE"),
            "identity": (
                f"{self._identity.stats().get('cases', '?')} cases, "
                f"{self._identity.stats().get('with_bench', '?')} with a bench"
                if self._identity.available else
                "INDEX NOT BUILT -- run pipeline/indexing/build_identity_index.py"),
            "denylist": f"{len(self._denylist())} chunk(s) excluded",
        }

    def accrual_trigger(self, cause: str) -> str:
        """When the period for this cause STARTS, from the curated Article.

        THE ADAPTER OWNS THIS BECAUSE `core` MAY NOT IMPORT `knowledge`
        (layercheck), and the trigger is curated in `resolution.py` beside the
        Article it belongs to. Copying it into the engine would be a second
        home for a legal fact.

        EMPTY FOR AN UNKNOWN OR UNCURATED CAUSE, and the engine then behaves
        as it did before. A cause nobody has curated a trigger for is not one
        this product knows enough about to refuse on.
        """
        from nm.knowledge.resolution import accrual_trigger_for

        return accrual_trigger_for(cause)

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
        """Permission to use a retained generation is checked at each boundary."""
        try:
            if self._published_snapshot is not None:
                self._published_snapshot.require_usable()
            result = self._fetch(need)
            if self._published_snapshot is not None:
                self._published_snapshot.require_usable()
            return result
        except CorpusPublicationRefused as exc:
            return EvidenceResult(
                coverage=Coverage.NOT_ASSESSED,
                missing=f"Published legal source is not usable: {exc}",
                searched_stores=(),
            )

    def _fetch(self, need: EvidenceNeed) -> EvidenceResult:
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
                missing=(f"{provision_label(entry.act_name, section)} is declared as intended "
                         f"coverage but was not retrieved from {', '.join(stores)}. "
                         f"This is a RETRIEVAL DEFECT, not a corpus gap."),
                searched_stores=stores,
                assumption=note,
            )
        return EvidenceResult(
            coverage=Coverage.NOT_HELD,
            missing=f"{provision_label(entry.act_name, section)} is not held in the corpus.",
            searched_stores=stores,
            assumption=note,
        )

    # ------------------------------------------------------------ internals ---
    def _wanted_section(self, need: EvidenceNeed) -> str | None:
        """WHICH provision the question asks for.

        The pattern lives in `backend/nm/domain/citation.py` and is shared with the
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

        note = (f"I resolved one possible starting point for "
                f"{cause.value.replace('_', ' ')}: "
                f"{edge.act}, {edge.provision.replace('_', ' ')}. "
                "This is a provision to examine, not a finding that it governs "
                "the claim or that a limitation period has begun.")
        if edge.alternatives:
            # WHAT ELSE IT COULD HAVE BEEN, named. A wrong route is then
            # visible at a glance instead of after the advocate has acted on it.
            note += f" Also arguable: {'; '.join(edge.alternatives).replace('_', ' ')}"
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
                # EVERY ATOM OF THE SECTION, in the store's order -- never one.
                # The provision is assembled from all of them (`assemble_section`);
                # one atom was part of the section for 760 of 3,402 provisions.
                by_store: dict[str, list[tuple[str, str]]] = {}
                for act_id, atom_type, chunk_id, blob in con.execute(
                        """select act_id, atom_type, chunk_id, blob from chunks
                           where doc_type='bare_act' and act_id like ? and section_number=?
                           order by act_id, pos""",
                        (pattern, section)):
                    if chunk_id in self._denylist():
                        continue
                    by_store.setdefault(act_id, []).append(
                        (atom_type, json.loads(blob).get("full_text") or ""))
                if not by_store:
                    continue
                act_id, text = max(((store, assemble_section(atoms))
                                    for store, atoms in by_store.items()),
                                   key=lambda pair: len(pair[1]))
                if not text:
                    continue
                candidates.append(Finding(
                    proposition=provision_label(entry.act_name, section),
                    source_kind=SourceKind.PROVISION,
                    ref=provision_label(entry.act_name, section),
                    span=text,
                    locator=f"{act_id}::{section}::section",
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

    # ------------------------------------------------------ document reader ---

    def document(self, locator: str, kind: str) -> SourceDocument:
        """The whole Act or judgment a saved passage came from. LB-92.

        A READ OF WHAT IS HELD, and nothing else: the same database the passage
        was retrieved from, the generation currently bound, no search, no model
        call, no successor-statute substitution. The donor build resolved a
        missing citation by fetching the successor sanhita and rendering it
        under the original reference; LB-91 refuses exactly that, and so does
        this method -- an unreadable locator returns `not_held` by name rather
        than the nearest thing that would fill the pane.

        THE TARGET IS LOCATED OR IT IS NOT. `target` names the segment the
        passage came from; where the locator's segment is absent from the
        current generation it stays `None`, and the reader says the passage
        could not be located instead of highlighting a neighbour.
        """
        if not self.available:
            return SourceDocument(
                state="no_reader",
                missing="the corpus is not readable on this installation")
        parts = (locator or "").split("::")
        if len(parts) != 3 or not parts[0].strip():
            return SourceDocument(
                state="not_held",
                missing=f"{locator!r} is not a locator this corpus can resolve")
        if kind == "provision":
            return self._act_document(parts[0], parts[1])
        if kind == "authority":
            return self._judgment_document(parts[0], parts[1])
        return SourceDocument(
            state="not_held", missing=f"{kind!r} is not a kind of source this reader holds")

    def _act_document(self, act_id: str, section: str) -> SourceDocument:
        """Every section of one Act, in its own order, with the cited one marked."""
        names = {entry.act_name for entry in self._manifest.entries
                 if any(fnmatchcase(act_id.lower(), pattern.lower().replace('%', '*')
                                    .replace('_', '?')) for pattern in entry.act_patterns)}
        label = next(iter(names)) if len(names) == 1 else "Legislation"
        rows = self._rows(
            self._db,
            """select section_number, atom_type, chunk_id, blob from chunks
               where doc_type='bare_act' and act_id=? order by pos""",
            (act_id,))
        if rows is None:
            return SourceDocument(
                state="no_reader",
                missing="the provision store could not be opened for reading")
        # EVERY ATOM OF EVERY SECTION, assembled by the one function the turn's
        # reader uses. This kept the LONGEST ATOM per section, which is the same
        # defect in a second place: the reader showed s.18(1) as section 18.
        atoms: dict[str, list[tuple[str, str]]] = {}
        for section_number, atom_type, chunk_id, blob in rows:
            if chunk_id in self._denylist():
                continue
            atoms.setdefault(str(section_number or "").strip(), []).append(
                (atom_type, json.loads(blob).get("full_text") or ""))
        best: dict[str, tuple[str, str]] = {}
        for number, section_atoms in atoms.items():
            body = assemble_section(section_atoms)
            if not body:
                continue
            heading = number.replace('_', ' ')
            best[number] = (heading if heading.startswith('Article ') else
                            f"Section {heading}" if heading else "Provision", body)
        if not best:
            return SourceDocument(
                state="not_held",
                missing=f"this corpus holds no readable text for {label}")
        ordered = sorted(best.items(), key=lambda item: _section_order(item[0]))
        segments = tuple(value for _, value in ordered)
        wanted = str(section or "").strip()
        target = next((i for i, (number, _) in enumerate(ordered) if number == wanted), None)
        return SourceDocument(
            state="read", label=label, store=act_id,
            snapshot_id=self.published_snapshot_id or "",
            segments=segments, target=target,
            missing="" if target is not None else
            f"the cited provision could not be located in the text held for {label}")

    def _judgment_document(self, case_id: str, chunk_id: str) -> SourceDocument:
        """Every attributable paragraph of one judgment, in its stored order."""
        if not (self._authority_db and self._authority_db.exists()):
            return SourceDocument(
                state="no_reader",
                missing="the authority index is not built on this installation")
        rows = self._rows(
            self._authority_db,
            """select rowid, para_type, chunk_id, text, case_name, court, year from paras
               where case_id=? order by rowid""",
            (case_id,))
        if rows is None:
            return SourceDocument(
                state="no_reader",
                missing="the authority index could not be opened for reading")
        segments, target, named = [], None, ""
        for _, para_type, para_chunk, body, case_name, court, year in rows:
            # THE CASE IS NAMED BY ITS NAME. `IdentityIndex.describe()` returns
            # the bench ("3-judge bench"), which is detail about a judgment the
            # advocate has not been told the name of.
            named = named or f"{case_name} ({court}, {year})"
            if para_chunk in self._denylist():
                continue
            spoken = " ".join((body or "").split())
            if not spoken:
                continue
            if para_chunk == chunk_id:
                target = len(segments)
            segments.append((str(para_type or "paragraph"), spoken))
        if not segments:
            return SourceDocument(
                state="not_held",
                missing="this corpus holds no readable paragraphs for this judgment")
        ident = self._identity.case(case_id)
        bench = f" — {ident.describe()}" if ident else ""
        return SourceDocument(
            state="read", label=f"{named or 'Judgment'}{bench}",
            store="authority_index", snapshot_id=self.published_snapshot_id or "",
            segments=tuple(segments), target=target,
            missing="" if target is not None else
            "the cited paragraph could not be located in the judgment as held")

    def _rows(self, database, sql: str, values: tuple):
        """Read-only, and a store that will not open says so rather than
        returning an empty result that reads exactly like an empty document."""
        try:
            con = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        except sqlite3.Error:
            return None
        try:
            return con.execute(sql, values).fetchall()
        except sqlite3.Error:
            return None
        finally:
            con.close()

    # ---------------------------------------------------------- authorities ---
    def _fetch_authority(self, need: EvidenceNeed) -> EvidenceResult:
        if not self.authority_available:
            # NOT an empty result. The capability exists and its index does
            # not, and those are different sentences.
            return EvidenceResult(
                coverage=Coverage.HELD_NOT_FOUND,
                missing=(
                    "the authority index is not built, so no judgment was "
                    "searched. No claim about the held population can be made. Build it with "
                    "`python pipeline/indexing/build_authority_index.py`."),
                searched_stores=("authority_index:absent",),
            )

        terms = self._terms(need)
        if not terms:
            return EvidenceResult(
                coverage=Coverage.NOT_ASSESSED,
                missing="no searchable terms were identified in the question.",
                searched_stores=("authority_index",))

        con = None
        try:
            con = sqlite3.connect(f"file:{self._authority_db}?mode=ro", uri=True)
            identity = dict(con.execute("select key, value from identity"))
            if not identity or not identity.get("corpus_version"):
                return EvidenceResult(
                    coverage=Coverage.NOT_ASSESSED,
                    missing="the authority index carries no corpus identity; nothing was searched",
                    searched_stores=())
            rows = con.execute(
                """select rowid, case_id, case_name, court, year, para_type, chunk_id, text
                   from paras where paras match ?
                   order by rank limit ?""",
                ('text:(' + " OR ".join(f'"{t}"' for t in terms) + ')',
                 EXAMINED_CEILING + 1)).fetchall()
            # Count matches with the SAME tokenizer as retrieval. Substring
            # matching counted 'title' in 'entitlement' yet rejected porter
            # inflections that FTS had actually matched. Bound every probe to
            # the candidate rows, never rescan the corpus to score a result.
            matched_by_row = {r[0]: 0 for r in rows[:EXAMINED_CEILING]}
            if matched_by_row:
                slots = ','.join('?' for _ in matched_by_row)
                for term in terms:
                    for (row_id,) in con.execute(
                        f'select rowid from paras where rowid in ({slots}) and paras match ?',
                        [*matched_by_row, f'text:"{term}"'],
                    ):
                        matched_by_row[row_id] += 1
        except sqlite3.Error as exc:
            return EvidenceResult(
                coverage=Coverage.NOT_ASSESSED,
                missing=f"the authority index could not be queried: {exc}",
                searched_stores=("authority_index",))
        finally:
            if con is not None:
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
        for row_id, case_id, case_name, court, year, para_type, chunk_id, text in rows:
            if chunk_id in self._denylist():
                continue
            kind = kind_for_corpus_label(para_type)
            if not kind.attributable:
                # G-ATTRIB. Counsel's submission is 14.8% of the corpus and
                # reads exactly like a holding, so it is dropped here rather
                # than ranked lower.
                continue
            matched = matched_by_row[row_id]
            if matched < floor:
                thin += 1
                continue
            ruling = binding_status(court, year, need.jurisdiction)
            ident = self._identity.case(case_id)
            bench = f"; {ident.describe()}" if ident else ""
            findings.append(Finding(
                proposition=snippet(need.question, 200),
                source_kind=SourceKind.AUTHORITY,
                ref=f"{case_name} ({court}, {year}{bench})",
                span=" ".join((text or "").split()),
                locator=f"{case_id}::{chunk_id}::{para_type}",
                store="authority_index",
                binding=ruling.status,
                binding_for=need.jurisdiction,
                binding_reason=f"{ruling.rule}: {ruling.reason}",
                supports=None,
                para_kind=kind,
                treatment=self._citator.treatment(case_name, case_id=case_id),
                governing_date=need.governing_date,
                origin=Origin.SEARCHED,
                # Lexical coverage of the question, NOT a relevance score. It
                # says how much of what was asked this paragraph contains, and
                # nothing at all about whether it answers it.
                confidence=round(matched / len(terms), 2),
            ))

        findings.sort(key=lambda f: -(f.confidence or 0.0))
        cut = (f"The index returned more than {EXAMINED_CEILING} ranked "
               f"matches and only the first {EXAMINED_CEILING} were "
               f"examined. There may be authority I did not reach; this is "
               f"a bound on my search, not a statement about the corpus."
               if truncated else None)
        omitted = len(set(self._primary_terms(need)) - set(terms))
        query_note = (f"Searched authority index paragraph text for: {', '.join(terms)}. "
                      f"Examined {len(rows)} ranked paragraph(s); {thin} failed "
                      f"the {floor}-term lexical floor. This does not assess semantic support.")
        if omitted:
            query_note += (f" The query-term budget omitted {omitted} further input term(s); "
                           "a narrower query may reach different material.")
        if not findings:
            query_note += (" No attributable candidate survived this search. "
                           "That is not proof that the corpus holds no relevant authority.")
        return EvidenceResult(
            coverage=Coverage.ANSWERED if findings else Coverage.SEARCHED_NO_MATCH,
            findings=tuple(findings), missing=query_note if not findings else None,
            searched_stores=("authority_index",),
            search_note=" ".join(x for x in (self._era_note(need), query_note, cut) if x))

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

    #: WORDS THAT CANNOT CARRY A LEGAL SUBJECT. Grammar, not vocabulary -- each
    #: set is CLOSED in English, the way `_FIRST_PERSON` is, and none of them
    #: names a topic. They extend `_SCAFFOLD`, which already made the same call
    #: for a shorter list.
    #:
    #: MEASURED 23 September 2026, every authority query served on the live
    #: matters that day -- fifteen. Most of each eight-term budget went on:
    #:
    #:     list numbering    one, first, second, third, three, so
    #:     function words    at, her, he, it, but, do, not, them, still, had
    #:     the file's dates  february 2018, august 2019, october 2026, 88 2025
    #:
    #: -- "one, eviction", "first, dissolution", and twice "three, connected,
    #: but, separate, matters, do, not, them". A judgment paragraph matched on
    #: "at" and "not" is incidental by construction.
    _FUNCTION = {
        "i", "me", "my", "you", "your", "he", "him", "his", "she", "her", "hers",
        "it", "its", "they", "them", "their", "us", "at", "by", "into", "over",
        "since", "before", "after", "until", "upon", "onto", "within", "between",
        "against", "through", "during", "but", "or", "so", "if", "because",
        "while", "though", "although", "as", "than", "do", "did", "done", "not",
        "no", "had", "be", "being", "still", "yet", "also", "just", "now", "then",
        "some", "all", "each", "every", "these", "those", "who", "whom", "whose",
        "when", "where", "how", "why", "here", "very", "only", "even", "again",
        "said", "say", "says", "told", "tell", "get", "got", "go", "went",
    }
    #: A brief's own numbering: "First, ...", "Two, arrears." They order the
    #: advocate's list and say nothing about any of its items.
    _LIST_MARKERS = {
        "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
        "ten", "first", "second", "third", "fourth", "fifth", "sixth",
        "firstly", "secondly", "thirdly", "fourthly", "lastly", "finally",
        "next", "another", "other",
    }
    _MONTHS = {
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
        "nov", "dec",
    }

    @classmethod
    def _primary_terms(cls, need: EvidenceNeed) -> list[str]:
        """The advocate's words that can carry a legal subject, in their order.

        A BARE NUMBER IS KEPT ONLY WHERE IT IS A PROVISION the question cites
        -- "section 138", "Article 64" -- through `nm.domain.citation`, the one
        owner of that pattern. Every other bare number in a brief is this
        file's own date, amount or case number ("2019", "88", "45,000"), and a
        judgment paragraph sharing one of those shares nothing that matters.

        A DESIGNATION MIXING DIGITS AND LETTERS IS ALWAYS KEPT -- "53A",
        "138A". It is a provision whether or not "s." precedes it, and
        `test_query_numbers_and_truncation_remain_visible` holds that line:
        losing a section number is the failure this search exists to avoid.
        """
        from nm.domain.citation import provisions_cited

        cited = {str(n).lower() for n in provisions_cited(need.question)}
        words = re.findall(r"[^\W_]+", need.question.lower())
        # THE MATTER'S OWN PARTIES ARE NEVER SEARCHED FOR -- exact tokens of the
        # names on the file, nothing inferred. See `EvidenceNeed.parties`.
        named = {t for key in (need.parties or ()) for t in re.findall(r"[^\W_]+", key)
                 if len(t) > 1}
        drop = (cls._SCAFFOLD | cls._FUNCTION | cls._LIST_MARKERS | cls._MONTHS
                | named)
        return list(dict.fromkeys(
            w for w in words
            if len(w) > 1 and w not in drop
            and (not w.isdigit() or w in cited)))

    @classmethod
    def _subject_terms(cls, need: EvidenceNeed) -> list[str]:
        """The legal subject the turn already settled, as search words.

        THE CALLER WAS MEANT TO SUPPLY THIS, and `_terms` says so: "the caller
        puts the resolved provision's subject FIRST". The one caller that
        searches authority -- the investigation lane -- selects a literal
        sentence of the brief and supplies nothing else, so the subject never
        arrived. It is on the need already: `cause_of_action`, read ONCE on the
        turn and carried into every fetch made from it.

        FROM THE PRODUCT'S OWN CLOSED VOCABULARY, never from model text, so
        this puts no model-written law into a search. A cause that was not
        established contributes nothing -- an unknown subject is not searched
        for as though it were known.
        """
        cause = (need.cause_of_action or "").strip().lower()
        if not cause or cause in ("not_established", "cannot_tell"):
            return []
        drop = cls._SCAFFOLD | cls._FUNCTION
        return [w for w in cause.split("_") if len(w) > 1 and w not in drop]

    @classmethod
    def _terms(cls, need: EvidenceNeed) -> list[str]:
        """The search terms, in the order they will be spent.

        The budget is small, so ORDER IS THE WHOLE DESIGN. The caller puts the
        resolved provision's subject FIRST and the advocate's phrasing after,
        because the question names the section and the section names the
        subject -- and taking six terms positionally from the question alone
        spends every slot on scaffolding.
        """
        # THE SUBJECT FIRST, THEN THE ADVOCATE'S WORDS, as this docstring has
        # always said. Eight slots, spent on words that can find law.
        seen = list(dict.fromkeys([*cls._subject_terms(need),
                                   *cls._primary_terms(need)]))[:8]
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
        return seen

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
