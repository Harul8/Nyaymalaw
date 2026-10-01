"""HYBRID JUDGMENT SEARCH: the judgment paragraphs a dispute needs, found exactly the way
its bare-act sections are. LB-106 (owner, 30 September 2026: "extend to judgements also,
both acts and judgements should be retrieved same way").

THE SAME MECHANISM (`hybrid_sections`): the dispute's own sentences and their similar
wordings, each to the word index and to the meaning index, the lists merged by
reciprocal rank, the head reranked by the same model, which is loaded once for both.

WHAT IS REUSED, AS IT IS. Measured 30 September 2026, read-only:
  * `caselaws_v2.index` -- 1,015,843 vectors of 1,024. Vectors 0 to 1,015,779 are
    passages 0 to 1,015,779 of `chunks.db` (doc_type case_law), encoded with
    BAAI/bge-large-en-v1.5; the last 63 have no passage and are never used.
  * `caselaws_bm25s` -- the word index over the same 1,015,780 passages.
The lineage job (`pipeline/record_retrieval_lineage.py`, run by the owner) records both;
until it has, this search says it did not run.

ONLY THE COURT'S OWN REASONING IS A CANDIDATE (G-ATTRIB). A paragraph of facts, of
counsel's arguments or one nobody classified is set aside BEFORE reranking and counted --
the same kinds, by the same table, as the authority index holds, so every candidate can
be opened in the reader. Counsel's submission reads exactly like a holding, which is why
it never competes for a place.

ONE PARAGRAPH PER JUDGMENT, the best the reranker found in it, and the judgment itself is
turned into a Finding by the one owner of that (`CorpusEvidenceAdapter.judgment_findings`):
binding computed from court and year against the matter's jurisdiction, treatment from
the citator, the denylist applied. What comes back are CANDIDATES -- ranked, with no
support verdict, their applicability unassessed and said -- never authority the dispute
rests on (CLAUDE.md section 5: a search may rank, never identify).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable

from nm.Archives.legal_brain.retrieve.corpus_evidence import JudgmentReaderUnavailable
from nm.Archives.legal_brain.retrieve.evidence_port import Finding, kind_for_corpus_label
from nm.Archives.legal_brain.retrieve.hybrid_sections import (
    RERANK_POOL,
    SearchModels,
    Searching,
    Unavailable,
    _Parts,
    as_candidate,
    open_collection,
)
from nm.Archives.legal_brain.retrieve.section_search_port import SectionSearch
from nm.shared.text_contracts import snippet

DOC_TYPE = "case_law"
#: How many judgments one dispute's search returns. Each is one paragraph; the needs read
#: decides which of them bear on the dispute.
JUDGMENTS = 4


class HybridJudgments(Searching):
    """`JudgmentSearchPort` over the existing judgment artefacts."""

    _what = "the judgment search"

    def __init__(self, vector_store: Path, *,
                 read_judgments: Callable[..., tuple[dict, int]],
                 models: SearchModels, lineage: Path, parts: _Parts | None = None) -> None:
        super().__init__(parts)
        self._dir = Path(vector_store)
        self._findings = read_judgments
        self._models = models
        self._lineage = Path(lineage)

    def _open(self) -> _Parts:
        return open_collection(self._dir, self._lineage, DOC_TYPE, self._models, mapped=True)

    def search(self, words: str, *, similar: tuple[str, ...] = (), as_of: date,
               jurisdiction: str, limit: int = JUDGMENTS) -> SectionSearch:
        words = " ".join((words or "").split())
        if not words:
            return SectionSearch(False, note="there were no words to search with")
        try:
            parts = self._load()
        except Unavailable as exc:
            return SectionSearch(False, note=str(exc))
        wordings = self.wordings(words, similar)
        ranked = self.ranked(parts, wordings)
        rows = parts.rows(ranked)
        # THE COURT'S OWN REASONING, decided before the reranker sees anything.
        admitted = [p for p in ranked if p in rows
                    and kind_for_corpus_label(rows[p][1].get("paragraph_type")).attributable]
        set_aside = sum(1 for p in ranked if p in rows) - len(admitted)
        head = admitted[:RERANK_POOL]
        judged = parts.rerank(wordings, [str(rows[p][1].get("full_text") or "") for p in head])

        best: dict[str, tuple[float, int]] = {}
        for position, score in zip(head, judged, strict=True):
            case = str(rows[position][1].get("case_id") or rows[position][0])
            if case not in best or score > best[case][0]:
                best[case] = (score, position)
        order = sorted(best.values(), key=lambda row: -row[0])

        paragraphs = []
        for score, position in order:
            chunk, doc = rows[position]
            paragraphs.append((str(doc.get("case_id") or ""), str(doc.get("case_name") or ""),
                               str(doc.get("court") or ""), str(doc.get("year") or ""),
                               str(doc.get("paragraph_type") or ""), chunk,
                               " ".join(str(doc.get("full_text") or "").split()),
                               round(float(score), 4)))
        try:
            found, held_back = self._findings(paragraphs, proposition=snippet(words, 200),
                                              jurisdiction=jurisdiction, governing_date=as_of)
        except JudgmentReaderUnavailable as exc:
            return SectionSearch(False, note=str(exc))
        unread = len(paragraphs) - held_back - len(found)
        candidates: list[Finding] = []
        for rank, (score, position) in enumerate(order, start=1):
            if len(candidates) >= limit:
                break
            finding = found.get(rows[position][0])
            if finding is None:
                continue
            candidates.append(as_candidate(
                finding, score, rank, len(order),
                undecided="whether it applies to this dispute has not been assessed"))
        note = (f"The judgments were searched by meaning and by words with {len(wordings)} "
                f"wording(s) of this dispute; {len(head)} paragraphs of the courts' own "
                f"reasoning were reranked and {len(candidates)} judgment(s) are shown as "
                "candidates, ranked by relevance, not established as authority for it.")
        if set_aside:
            note += (f" {set_aside} ranked paragraph(s) were facts, counsel's arguments or "
                     "unclassified, not the court's reasoning, and were set aside.")
        if held_back:
            note += (f" {held_back} were held back because the corpus's own contamination "
                     "denylist names them.")
        if unread:
            note += (f" {unread} ranked judgment paragraph(s) could not be verified "
                     "against the authority reader and were set aside.")
        return SectionSearch(True, tuple(candidates), note)
