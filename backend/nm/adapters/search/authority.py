"""A4 — the FTS reader over the authority index.

WHAT IT READS
--------------
`.nm/authority.db`, built by `pipeline/indexing/build_authority_index.py`: an FTS5 table
over attributable case paragraphs, plus an `identity` table saying when it was
built, from what, and how many of the source's paragraphs it holds.

THE INDEX IS ASKED WHAT IT IS, EVERY TIME
------------------------------------------
Not once at import. The identity is cheap to read and the alternative -- a
cached identity describing a file that has since been rebuilt -- is the stale
server defect (B-061) in a smaller box. `backend/nm/domain/identity.py` makes the same
argument about the running process.

AN ABSENT INDEX IS NOT AN EMPTY ONE
------------------------------------
Every failure path here returns `Coverage.NOT_ASSESSED` with the reason, never
an empty hit list. The file may be missing, unreadable, or built without the
identity table, and none of those is "the corpus does not hold your case".
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from nm.domain.citation import reporter_key
from nm.knowledge.identity import IdentityIndex
from nm.knowledge.jurisdiction import stored_court
from nm.knowledge.manifest import CorpusPublicationRefused, PublishedCorpus
from nm.ports.evidence import Coverage, Treatment
from nm.ports.search import (
    CaseDiscovery,
    CaseExpansion,
    CaseHit,
    CitationResolution,
    CorpusSearch,
    IndexIdentity,
    Paragraph,
    ResolutionState,
    SearchHit,
)

#: How many characters of a paragraph the advocate is shown per hit.
SNIPPET = 320

#: The most hits one query may return. A search that hands back a thousand
#: paragraphs has not answered anything.
MAX_LIMIT = 100

#: How many ranked paragraphs case-level discovery folds. Bounded so a common
#: term does not read the whole index to answer "which cases"; the bound is
#: reported through `paragraphs_ranked`, so a discovery that hit it says so.
DISCOVERY_POOL = 200


class AuthorityIndexSearch:
    """Reads the FTS index. Ranks paragraphs; identifies nothing."""

    def __init__(self, index_path: str | Path,
                 identity_path: str | Path | None = None) -> None:
        self._path = Path(index_path)
        #: NAMED SO A ZERO CAN BE READ. "the corpus" would be the very
        #: ambiguity B-163 is about — three stores hold the same Act and
        #: disagree, so a result says WHICH one answered it.
        self.name = f"the authority index ({self._path.name})"
        self._published_snapshot: PublishedCorpus | None = None
        #: THE IDENTITY INDEX, beside the authority index by default -- the
        #: same default the evidence adapter uses, so the two read one file.
        #: Absent, `resolve` says INDEX_UNAVAILABLE and `treatment` says
        #: NOT_CHECKED; neither becomes a clearance.
        self._identity_index = IdentityIndex(
            Path(identity_path) if identity_path is not None
            else self._path.parent / "identity.db")

    @property
    def available(self) -> bool:
        return self._path.exists()

    def identity_version(self) -> str:
        """The corpus version the index says it was built from, or ''."""
        if not self._path.exists():
            return ""
        try:
            con = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        except sqlite3.Error:
            return ""
        try:
            ident = self._identity(con)
        finally:
            con.close()
        return ident.corpus_version if ident is not None else ""

    def treatment(self, case_id: str) -> Treatment:
        return self._identity_index.treatment(case_id)

    def case_identity(self, case_id: str):
        return self._identity_index.case(case_id)

    @classmethod
    def from_published_corpus(
        cls,
        publication_root: str | Path,
        *,
        authority_index: str = "indexes/authority.db",
    ) -> "AuthorityIndexSearch":
        """Open the index only through a complete immutable generation."""
        snapshot = PublishedCorpus.open(publication_root, verify_all=True)
        return cls.from_published_snapshot(snapshot, authority_index=authority_index)

    @classmethod
    def from_published_snapshot(
        cls,
        snapshot: PublishedCorpus,
        *,
        authority_index: str = "indexes/authority.db",
    ) -> "AuthorityIndexSearch":
        """Build from the same bound snapshot as the evidence adapter."""
        identity = "indexes/identity.db"
        search = cls(snapshot.member_path(authority_index),
                     identity_path=(snapshot.member_path(identity)
                                    if snapshot.has_member(identity) else None))
        search._published_snapshot = snapshot
        return search

    # ------------------------------------------------------------- identity ---

    def _identity(self, con: sqlite3.Connection) -> IndexIdentity | None:
        try:
            rows = dict(con.execute("select key, value from identity"))
        except sqlite3.Error:
            try:
                rows = {k: v for k, v in con.execute("select * from identity")}
            except sqlite3.Error:
                return None
        if not rows:
            return None

        def num(key: str) -> int | None:
            """A count from the identity, or None where it is not recorded.

            NOT 0 (BK-19). This returned `int(rows.get(key, 0))`, so an
            identity missing `indexed_paragraphs` reported ZERO INDEXED --
            indistinguishable from an index that was built and holds
            nothing.

            CLAUDE.md's own worked example is this shape: `table.get(kind,
            0.0)` made every unlisted atom type score worse than every
            listed one, and the fix was general rather than a row per atom
            type.
            """
            raw = rows.get(key)
            if raw is None:
                return None
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None

        return IndexIdentity(
            name=self.name,
            built_at=str(rows.get("built_at", "unknown")),
            source=str(rows.get("source", "unknown")),
            corpus_version=str(rows.get("corpus_version", "unknown")),
            held=num("indexed_paragraphs"),
            of_source=num("source_paragraphs"),
            scope=str(rows.get("scope")
                      or "Telangana and the Union of India"),
        )

    # --------------------------------------------------------------- search ---

    def search(self, query: str, *, court: str | None = None,
               from_year: int | None = None, to_year: int | None = None,
               limit: int = 20) -> CorpusSearch:
        """A cached reader may not serve law withdrawn before it emits."""
        try:
            if self._published_snapshot is not None:
                self._published_snapshot.require_usable()
            result = self._search(
                query, court=court, from_year=from_year, to_year=to_year, limit=limit,
            )
            if self._published_snapshot is not None:
                self._published_snapshot.require_usable()
            return result
        except CorpusPublicationRefused as exc:
            return CorpusSearch(
                query=query, index=self.name, coverage=Coverage.NOT_ASSESSED,
                filters={key: value for key, value in (
                    ("court", court), ("from_year", from_year), ("to_year", to_year),
                ) if value is not None},
                why=f"Published legal source is not usable: {exc}",
            )

    def _search(self, query: str, *, court: str | None = None,
                from_year: int | None = None, to_year: int | None = None,
                limit: int = 20) -> CorpusSearch:
        # BK-38. THE COURT IS RESOLVED ONCE, HERE, and both the WHERE clause
        # and the disclosure read the same answer. Resolving it at the query
        # and describing it at the response would be two answers to one
        # question, and the description is the half nobody would notice
        # drifting.
        resolved_court, court_said = stored_court(court)
        filters = {k: v for k, v in
                   (("court", court), ("from_year", from_year),
                    ("to_year", to_year)) if v not in (None, "")}
        # WHAT THE COURT FILTER ACTUALLY BECAME, in words.
        #
        # `filters` reported what the CALLER asked for. A zero result then
        # said `court: Supreme Court` beside no hits, which reads as "the
        # corpus holds nothing from the Supreme Court" -- while the truth was
        # that the filter never matched a stored value. BK-38's acceptance is
        # that a zero states exactly which normalised filters ran.
        if court:
            filters = {**filters, "court_read_as": court_said}

        if not (query or "").strip():
            return CorpusSearch(
                query=query, index=self.name, coverage=Coverage.NOT_ASSESSED,
                filters=filters,
                why="no query was given, so nothing was searched")

        if not self._path.exists():
            return CorpusSearch(
                query=query, index=self.name, coverage=Coverage.NOT_ASSESSED,
                filters=filters,
                why=(f"the authority index is not present at {self._path}. "
                     f"Build it with `python pipeline/indexing/build_authority_index.py`. "
                     f"This is NOT a statement about what the corpus holds — "
                     f"nothing was searched."))

        try:
            con = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            return CorpusSearch(
                query=query, index=self.name, coverage=Coverage.NOT_ASSESSED,
                filters=filters,
                why=f"the authority index could not be opened: {exc}")

        try:
            identity = self._identity(con)
            if identity is None:
                # S11: the ONLY reason the previous build's 437MB dense index
                # was knowably unusable is that it shipped an identity. An
                # index that cannot say what it is gets used on trust, and
                # trust is what produced confidently wrong neighbours.
                return CorpusSearch(
                    query=query, index=self.name,
                    coverage=Coverage.NOT_ASSESSED, filters=filters,
                    why=("the index carries no identity, so there is no way to "
                         "know what corpus it was built from or how much of it "
                         "it holds. It was not searched."))

            match = _fts_query(query)
            if match is None:
                return CorpusSearch(
                    query=query, index=self.name,
                    coverage=Coverage.NOT_ASSESSED, filters=filters,
                    identity=identity,
                    why=("the query held no searchable term once FTS operators "
                         "were removed, so nothing was searched"))

            where = ["paras match ?"]
            args: list[object] = [match]
            # BK-38. THE COURT IS RESOLVED, NOT COMPARED.
            #
            # This was `lower(court) = lower(?)`, so `Supreme Court` returned
            # ZERO while `Supreme Court of India` returned 395,734 -- and a
            # zero from an exact-match filter reads exactly like "the corpus
            # holds nothing". That is B-163's shape, and this repository has
            # recorded it three times against the legal corpus.
            #
            # IT RESOLVES THROUGH THE CLOSED COURT VOCABULARY, which is why
            # this is not fuzzy matching: the index holds exactly two court
            # values, so `normalise_court` IDENTIFIES rather than ranks
            # (CLAUDE.md §5). A spelling that names no court this index holds
            # returns nothing AND SAYS SO, which is a different answer from
            # a search that ran and found nothing.
            if court:
                if resolved_court:
                    where.append("court = ?")
                    args.append(resolved_court)
                else:
                    # A FILTER THAT MATCHES NOTHING IS APPLIED HONESTLY. It
                    # would be easy to drop it and search everything; the
                    # advocate asked for one court and would be handed
                    # another's authority under a heading they chose.
                    where.append("1 = 0")
            if from_year is not None:
                where.append("cast(year as integer) >= ?")
                args.append(int(from_year))
            if to_year is not None:
                where.append("cast(year as integer) <= ?")
                args.append(int(to_year))

            args.append(max(1, min(int(limit), MAX_LIMIT)))
            rows = con.execute(
                "select case_id, case_name, court, year, para_type, "
                "       snippet(paras, 6, '', '', ' … ', 40), rank "
                "from paras where " + " and ".join(where) +
                " order by rank limit ?", args).fetchall()
        except sqlite3.Error as exc:
            return CorpusSearch(
                query=query, index=self.name, coverage=Coverage.NOT_ASSESSED,
                filters=filters,
                why=f"the index rejected the query: {exc}")
        finally:
            con.close()

        hits = tuple(_hit(r) for r in rows)
        return CorpusSearch(
            query=query, index=self.name,
            # ANSWERED even at zero. Zero hits from an index that RAN is a
            # different claim from an index that could not run, and the
            # identity travelling alongside is what lets the advocate read the
            # zero against what the index actually holds.
            coverage=Coverage.ANSWERED,
            identity=identity, filters=filters, hits=hits,
            why=None if hits else _why_empty(filters))


    # ------------------------------------------------ discovery (P21) ------

    def discover(self, query: str, *, court: str | None = None,
                 from_year: int | None = None, to_year: int | None = None,
                 limit: int = 20) -> CaseDiscovery:
        """Cases, ranked by their best paragraph. BK-25-AC1.

        ONE FTS QUERY, GROUPED, and not a second ranking. The paragraph
        search is the only thing that ranks; this folds its rows by case so a
        holding spread across several paragraphs surfaces as one case with a
        count, rather than as several snippets an advocate has to recognise
        as one judgment. The pool is bounded (`DISCOVERY_POOL`) so a common
        term does not read the whole index to answer "which cases".
        """
        # SCOPE BEFORE RETRIEVAL. A court this index does not hold is decided
        # here, from the closed vocabulary, and NOTHING IS SEARCHED -- the
        # paragraph search would have applied `1 = 0` and read nothing, but
        # the query would still have travelled. The filters carry what the
        # court was read as, so the caller classifies it as unsupported
        # coverage rather than as zero results.
        resolved_court, court_said = stored_court(court)
        if court and not resolved_court:
            filters = {"court": court, "court_read_as": court_said}
            if from_year is not None:
                filters["from_year"] = from_year
            if to_year is not None:
                filters["to_year"] = to_year
            identity = self._identity_or_none()
            if identity is None:
                return CaseDiscovery(query=query, index=self.name,
                                     coverage=Coverage.NOT_ASSESSED, filters=filters,
                                     why="the authority index is not present or carries "
                                         "no identity")
            return CaseDiscovery(query=query, index=self.name, coverage=Coverage.ANSWERED,
                                 identity=identity, filters=filters, cases=(),
                                 why=court_said)
        pooled = self.search(query, court=court, from_year=from_year,
                             to_year=to_year, limit=DISCOVERY_POOL)
        if pooled.coverage is Coverage.NOT_ASSESSED:
            return CaseDiscovery(query=query, index=self.name,
                                 coverage=Coverage.NOT_ASSESSED,
                                 filters=pooled.filters, why=pooled.why)
        by_case: dict[str, list[SearchHit]] = {}
        for hit in pooled.hits:
            by_case.setdefault(hit.case_id, []).append(hit)
        cases = []
        for case_id, hits in by_case.items():
            best = min(hits, key=lambda h: h.rank)
            cases.append(CaseHit(
                case_id=case_id, case_name=best.case_name, court=best.court,
                year=best.year, paragraphs_matched=len(hits),
                best_rank=best.rank, confidence=best.confidence,
                snippet=best.snippet))
        cases.sort(key=lambda c: c.best_rank)
        cases = cases[:max(1, min(int(limit), MAX_LIMIT))]
        return CaseDiscovery(
            query=query, index=self.name, coverage=Coverage.ANSWERED,
            identity=pooled.identity, filters=pooled.filters,
            cases=tuple(cases), paragraphs_ranked=len(pooled.hits),
            why=None if cases else pooled.why)

    def _identity_or_none(self) -> IndexIdentity | None:
        if not self._path.exists():
            return None
        try:
            con = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        except sqlite3.Error:
            return None
        try:
            return self._identity(con)
        finally:
            con.close()

    def expand(self, case_id: str, *, query: str | None = None,
               limit: int = 200) -> CaseExpansion:
        """Every indexed paragraph of one case, BY LOCATOR, in source order.

        `complete` IS `False` BY CONSTRUCTION for this index: it holds the
        attributable kinds only (`attributable_kinds` in its identity), so a
        judgment's facts and submissions are not here to be read back. That
        is said as a value, because an expansion that looked whole and was
        not is how a holding gets cited out of the context that qualified it.
        """
        if not self._path.exists():
            return CaseExpansion(case_id=case_id, index=self.name,
                                 coverage=Coverage.NOT_ASSESSED,
                                 why=f"the authority index is not present at {self._path}")
        try:
            con = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            return CaseExpansion(case_id=case_id, index=self.name,
                                 coverage=Coverage.NOT_ASSESSED,
                                 why=f"the authority index could not be opened: {exc}")
        try:
            identity = self._identity(con)
            if identity is None:
                return CaseExpansion(case_id=case_id, index=self.name,
                                     coverage=Coverage.NOT_ASSESSED,
                                     why="the index carries no identity")
            kinds = dict(con.execute("select key, value from identity")).get(
                "attributable_kinds", "")
            match = _fts_query(query) if query else None
            if match:
                where, args = "paras match ?", [f'case_id:"{case_id}" AND ({match})']
            else:
                where, args = "case_id = ?", [case_id]
            rows = con.execute(
                "select chunk_id, case_id, case_name, court, year, para_type, text "
                f"from paras where {where} order by chunk_id limit ?",
                [*args, max(1, min(int(limit), 500))]).fetchall()
        except sqlite3.Error as exc:
            return CaseExpansion(case_id=case_id, index=self.name,
                                 coverage=Coverage.NOT_ASSESSED,
                                 why=f"the index rejected the read: {exc}")
        finally:
            con.close()
        paragraphs = tuple(_paragraph(r) for r in rows)
        return CaseExpansion(
            case_id=case_id, index=self.name, coverage=Coverage.ANSWERED,
            identity=identity, paragraphs=paragraphs,
            # KNOWN INCOMPLETE when the index says it kept only some kinds.
            complete=False if kinds else None,
            why=(None if paragraphs else
                 f"the index holds no paragraph for case {case_id!r}; it may "
                 f"hold the case under another id, or not at all"))

    def passage(self, locator: str) -> Paragraph | None:
        """ONE paragraph, by its exact chunk id. `None` means not held --
        which the caller must not read as absence of the law; the index says
        which kinds it holds."""
        if not self._path.exists() or not (locator or "").strip():
            return None
        try:
            con = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        except sqlite3.Error:
            return None
        try:
            row = con.execute(
                "select chunk_id, case_id, case_name, court, year, para_type, text "
                "from paras where chunk_id = ? limit 1", (locator.strip(),)).fetchone()
        except sqlite3.Error:
            return None
        finally:
            con.close()
        return _paragraph(row) if row else None

    def resolve(self, citation: str) -> CitationResolution:
        """A typed citation, to exactly one case or to nothing. BK-38-AC1.

        Through the identity index's `citations` table on the reporter KEY --
        the same key the index was built with, from `nm.domain.citation`, so
        build and read cannot disagree about what a citation is. Exact match
        reached 90.9% of held judgments where name matching reached 0.83%
        (CLAUDE.md §5); there is no fallback to a name.
        """
        key = reporter_key(citation)
        if not key:
            return CitationResolution(raw=citation, key=key or "?",
                                      state=ResolutionState.UNRESOLVED,
                                      why="the citation held no reporter key")
        if not self._identity_index.available:
            return CitationResolution(
                raw=citation, key=key, state=ResolutionState.INDEX_UNAVAILABLE,
                why="the identity index is not built, so no citation can be "
                    "resolved. Run `python pipeline/indexing/build_identity_index.py`")
        case_id = self._identity_index.case_for_citation(key)
        if not case_id:
            return CitationResolution(
                raw=citation, key=key, state=ResolutionState.UNRESOLVED,
                why=f"no held judgment carries the citation {citation.strip()!r} "
                    f"(key {key}). Nothing near it is offered: a near-miss is "
                    f"how the wrong case gets cited")
        return CitationResolution(raw=citation, key=key,
                                  state=ResolutionState.RESOLVED, case_id=case_id)


# ------------------------------------------------------------------ helpers ---

#: FTS5 treats these as syntax. A user typing `s. 53A "part performance"` is
#: not writing a query language, and an unescaped quote raises rather than
#: searching -- which arrives as a 500 and reads, to the advocate, as absence.
_OPERATORS = re.compile(r"""["'()*:^\-]|(?<!\w)(AND|OR|NOT|NEAR)(?!\w)""")


def _fts_query(raw: str) -> str | None:
    """Every term quoted, so nothing the advocate typed is read as an operator.

    PUNCTUATION COMES OFF BEFORE THE LENGTH TEST, and that ordering is the
    whole point. `s. 53A part performance` kept `s.` as a two-character term,
    which the porter tokenizer reduces to the token `s` — and because FTS5
    joins terms with an implicit AND, every paragraph that did not contain a
    bare `s` was excluded. A citation written the way advocates write it
    silently narrowed the search to almost nothing, and the result would have
    read as a corpus that does not hold the section.
    """
    cleaned = _OPERATORS.sub(" ", raw)
    terms = [t for t in (re.sub(r"\W+", "", w) for w in cleaned.split())
             if len(t) > 1]
    if not terms:
        return None
    return " ".join(f'"{t}"' for t in terms)


def _hit(row: tuple) -> SearchHit:
    case_id, case_name, court, year, para_type, snippet, rank = row
    try:
        yr = int(year)
    except (TypeError, ValueError):
        # `None`, not 0. A year of zero is a claim about when it was decided.
        yr = None
    return SearchHit(
        case_id=str(case_id or "").strip() or "unknown",
        case_name=str(case_name or "").strip() or "(party names not held)",
        court=str(court or "").strip() or "(court not held)",
        year=yr,
        para_type=str(para_type or "").strip() or "unknown",
        # AN ABSENT SNIPPET SAYS SO. `""` would render as a hit with a case
        # name, a court, a confidence -- and no text, which reads as a
        # paragraph that says nothing rather than as one the index would not
        # give back.
        snippet=(str(snippet)[:SNIPPET] if str(snippet or "").strip()
                 else "(the index returned no text for this paragraph)"),
        rank=float(rank or 0.0),
        confidence=_confidence(float(rank or 0.0)),
    )


def _paragraph(row: tuple) -> Paragraph:
    chunk_id, case_id, case_name, court, year, para_type, text = row
    try:
        yr = int(year)
    except (TypeError, ValueError):
        yr = None
    return Paragraph(
        locator=str(chunk_id), case_id=str(case_id or "").strip() or "unknown",
        case_name=str(case_name or "").strip() or "(party names not held)",
        court=str(court or "").strip() or "(court not held)", year=yr,
        para_type=str(para_type or "").strip() or "unknown",
        text=str(text or "").strip() or "(the index returned no text for this paragraph)")


def _confidence(rank: float) -> float:
    """FTS5 `rank` is negative and better when more negative, and it is
    comparable only WITHIN one query. This maps it into [0, 1] for display and
    claims nothing more: two hits from different searches must not be compared
    on it, which is why it is never persisted onto a matter."""
    return max(0.0, min(1.0, -rank / (1.0 - rank))) if rank < 0 else 0.0


def _why_empty(filters: dict) -> str:
    """A ZERO NAMES WHAT NARROWED IT.

    B-163: a zero result must name the index it came from. A zero from a
    FILTERED search must also name the filter, because an advocate who set a
    court and got nothing is owed the difference between "not in this court"
    and "not in the corpus"."""
    if filters:
        named = ", ".join(f"{k}={v}" for k, v in filters.items())
        return (f"no paragraph matched, with these filters applied: {named}. "
                f"Clearing them searches the whole index.")
    return ("no paragraph in the index matched. The index holds attributable "
            "case paragraphs — party names and case titles are not searched "
            "here, so a search by case name will miss.")
