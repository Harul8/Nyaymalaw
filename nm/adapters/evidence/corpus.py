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
from datetime import date
from pathlib import Path

from nm.domain.citation import wanted_section
from nm.knowledge.citator import Citator
from nm.knowledge.identity import IdentityIndex
from nm.knowledge.jurisdiction import binding_status
from nm.knowledge.manifest import Manifest
from nm.ports.evidence import (
    Binding,
    Coverage,
    EvidenceNeed,
    EvidenceResult,
    Finding,
    ParaKind,
    SourceKind,
    Treatment,
)

_ATTRIBUTABLE = ("ratio", "reasoning", "order")


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

        resolved = self._manifest.resolve(need.question, on=need.governing_date)
        entry, superseded = resolved.entry, resolved.superseded
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
                                  searched_stores=("manifest",))

        section = self._wanted_section(need)
        if section is None:
            return EvidenceResult(
                coverage=Coverage.NOT_HELD,
                missing=(f"{entry.act_name} is held, but no specific provision was "
                         f"identified in the question to retrieve."),
                searched_stores=("manifest",),
            )

        findings, stores = self._union_lookup(entry.act_patterns, section, entry, need)
        if findings:
            return EvidenceResult(coverage=Coverage.ANSWERED, findings=findings,
                                  searched_stores=stores,
                                  assumption=resolved.note() or None)

        # Zero hits. The manifest -- not the hit count -- decides which of the
        # two remaining states this is.
        if self._manifest.intends(entry, section):
            return EvidenceResult(
                coverage=Coverage.HELD_NOT_FOUND,
                missing=(f"{entry.act_name} s.{section} is declared as intended "
                         f"coverage but was not retrieved from {', '.join(stores)}. "
                         f"This is a RETRIEVAL DEFECT, not a corpus gap."),
                searched_stores=stores,
            )
        return EvidenceResult(
            coverage=Coverage.NOT_HELD,
            missing=f"{entry.act_name} s.{section} is not held in the corpus.",
            searched_stores=stores,
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
        return need.provision_hint or wanted_section(need.question)

    def _union_lookup(self, patterns: tuple[str, ...], section: str, entry,
                      need: EvidenceNeed):
        """THE UNION. Every identifier convention, and the store is NAMED."""
        stores: list[str] = []
        findings: list[Finding] = []
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
                findings.append(Finding(
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
                    origin="resolved",
                ))
                break  # the first complete copy wins; the union is over PATTERNS
        finally:
            con.close()
        return tuple(findings), tuple(stores)

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
                   order by rank limit 40""",
                (" OR ".join(f'"{t}"' for t in terms),)).fetchall()
        except sqlite3.OperationalError as exc:
            return EvidenceResult(
                coverage=Coverage.HELD_NOT_FOUND,
                missing=f"the authority index could not be queried: {exc}",
                searched_stores=("authority_index",))
        finally:
            con.close()

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
                origin="searched",
                # Lexical coverage of the question, NOT a relevance score. It
                # says how much of what was asked this paragraph contains, and
                # nothing at all about whether it answers it.
                confidence=round(matched / len(terms), 2),
            ))

        if findings:
            findings.sort(key=lambda f: -f.confidence)
            return EvidenceResult(coverage=Coverage.ANSWERED, findings=tuple(findings),
                                  searched_stores=("authority_index",))
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
        return seen[:8]


def default_authority_index(root: Path) -> Path:
    return Path(root) / ".nm" / "authority.db"


def in_force_on(entry, day: date) -> bool:
    if entry.in_force_from and day < entry.in_force_from:
        return False
    if entry.in_force_to and day > entry.in_force_to:
        return False
    return True
