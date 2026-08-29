"""Evidence from the real corpus.

Two rules from `docs/BASELINE.md` are enforced here rather than remembered,
because both have already produced a false gap in this project:

  act-1  COVERAGE IS A UNION across every store and identifier convention.
         The same Act is held under `the_specific_relief_act_1963` (13 sections)
         and `UNION OF INDIA_1963_1_THE SPECIFIC RELIEF ACT, 1963` (all 44).
         Querying one store reports a gap that is not there.

  S3     A ZERO RESULT NAMES THE INDEX IT CAME FROM. `case_name` holds party
         names, so a subject search against it returns zero -- and zero reads
         exactly like "not in the corpus".

Absence is therefore never inferred from a hit count. It is computed against the
manifest, which is what makes the three-state answer possible at all.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from nm.knowledge.manifest import Manifest
from nm.ports.evidence import (
    Binding,
    Coverage,
    EvidenceNeed,
    EvidenceResult,
    Finding,
    ParaKind,
    SourceKind,
)

_SECTION_RE = re.compile(
    r"\b(?:section|sec\.?|s\.)\s*(\d+[A-Za-z\-]*)\b", re.I)
_ARTICLE_RE = re.compile(r"\barticle\s*(\d+)\b", re.I)


class CorpusEvidenceAdapter:
    """Reads the bare-act chunks. Read-only, and it never writes to the corpus."""

    def __init__(self, corpus_dir: str | Path, manifest: Manifest,
                 jurisdiction: str = "Telangana") -> None:
        self._db = Path(corpus_dir) / "chunks.db"
        self._manifest = manifest
        self._jurisdiction = jurisdiction

    @property
    def available(self) -> bool:
        return self._db.exists()

    def fetch(self, need: EvidenceNeed) -> EvidenceResult:
        if not self.available:
            # The corpus could not be read. That is NOT "nothing is held" --
            # an absent input must never read as an answer.
            return EvidenceResult(
                coverage=Coverage.HELD_NOT_FOUND,
                missing=f"the corpus is not readable at {self._db}",
                searched_stores=(),
            )

        entry = self._manifest.resolve(need.question)
        if entry is None:
            return EvidenceResult(
                coverage=Coverage.NOT_HELD,
                missing=("no Act in the curated manifest governs this question. "
                         "The manifest states INTENDED coverage, so this is an "
                         "honest gap rather than a failed lookup."),
                searched_stores=("manifest",),
            )

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
                                  searched_stores=stores)

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
        if need.provision_hint:
            return need.provision_hint
        m = _SECTION_RE.search(need.question)
        if m:
            return m.group(1)
        a = _ARTICLE_RE.search(need.question)
        if a:
            return f"Article_{a.group(1)}"
        return None

    def _union_lookup(self, patterns: tuple[str, ...], section: str, entry, need):
        """THE UNION. Every identifier convention, and the store is NAMED."""
        stores: list[str] = []
        findings: list[Finding] = []
        con = sqlite3.connect(f"file:{self._db}?mode=ro", uri=True)
        try:
            for pattern in patterns:
                stores.append(pattern)
                row = con.execute(
                    """select act_id, atom_type, blob from chunks
                       where doc_type='bare_act' and act_id like ? and section_number=?
                       order by case atom_type when 'section_head' then 0 else 1 end
                       limit 1""",
                    (pattern, section)).fetchone()
                if row is None:
                    continue
                act_id, atom_type, blob = row
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
                    supports=True,
                    para_kind=ParaKind.UNKNOWN,
                    valid_from=entry.in_force_from,
                    valid_to=entry.in_force_to,
                    origin="resolved",
                ))
                break  # the first complete copy wins; the union is over PATTERNS
        finally:
            con.close()
        return tuple(findings), tuple(stores)
