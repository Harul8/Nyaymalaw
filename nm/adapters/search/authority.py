"""A4 — the FTS reader over the authority index.

WHAT IT READS
--------------
`.nm/authority.db`, built by `tools/build_authority_index.py`: an FTS5 table
over attributable case paragraphs, plus an `identity` table saying when it was
built, from what, and how many of the source's paragraphs it holds.

THE INDEX IS ASKED WHAT IT IS, EVERY TIME
------------------------------------------
Not once at import. The identity is cheap to read and the alternative -- a
cached identity describing a file that has since been rebuilt -- is the stale
server defect (B-061) in a smaller box. `nm/domain/identity.py` makes the same
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

from nm.ports.evidence import Coverage
from nm.ports.search import CorpusSearch, IndexIdentity, SearchHit

#: How many characters of a paragraph the advocate is shown per hit.
SNIPPET = 320

#: The most hits one query may return. A search that hands back a thousand
#: paragraphs has not answered anything.
MAX_LIMIT = 100


class AuthorityIndexSearch:
    """Reads the FTS index. Ranks paragraphs; identifies nothing."""

    def __init__(self, index_path: str | Path) -> None:
        self._path = Path(index_path)
        #: NAMED SO A ZERO CAN BE READ. "the corpus" would be the very
        #: ambiguity B-163 is about — three stores hold the same Act and
        #: disagree, so a result says WHICH one answered it.
        self.name = f"the authority index ({self._path.name})"

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

        def num(key: str) -> int:
            try:
                return int(rows.get(key, 0))
            except (TypeError, ValueError):
                return 0

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
        filters = {k: v for k, v in
                   (("court", court), ("from_year", from_year),
                    ("to_year", to_year)) if v not in (None, "")}

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
                     f"Build it with `python tools/build_authority_index.py`. "
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
            if court:
                where.append("lower(court) = lower(?)")
                args.append(court)
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
