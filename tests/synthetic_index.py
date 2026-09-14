"""A SYNTHETIC authority index and identity index, in the real schema. P21.

Two tiny SQLite files with exactly the tables `pipeline/indexing/build_authority_index.py`
and `pipeline/indexing/build_identity_index.py` create, holding invented judgments about an
invented proposition. Nothing here is Indian law and nothing here is drawn from
`legal_database/`: the case names, the citations, the paragraphs and the
treatment are fixtures, and they say so in their text.

WHY THE REAL SCHEMA. The adapter under test reads `paras` by FTS match, by
`case_id` and by `chunk_id`, and reads `citations` and `treatment` by key. A
fixture that stubbed the adapter would prove the routes agree with the stub;
this proves them against the same SQL the live indexes answer.

WHAT IT PLANTS, so the tests can ask for each:

    SYN_1990_MARKER      the holding on `marker_is_blue` is SPREAD across two
                         ratio paragraphs (P002 states the test, P003 applies
                         it); cited as `1990 SYN 1` and `AIR 1990 SYN 1`.
    SYN_2001_OVERRULED   a clean, quotable paragraph whose case is OVERRULED
                         by SYN_2010_TREATING -- correct quote, bad law.
    SYN_2010_TREATING    the case that overrules it.
    SYN_1975_KERALA      a persuasive-only court (`High Court of Kerala`), so
                         applicability is not BINDING here.
    SYN_1999_NOCITE      no reporter citation at all: treatment is NOT_CHECKED
                         because nothing could have cited it.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

AUTHORITY_SCHEMA = """
create virtual table paras using fts5(
    case_id, case_name, court, year UNINDEXED, para_type UNINDEXED,
    chunk_id UNINDEXED, text,
    tokenize = 'porter unicode61'
);
create table identity (key text primary key, value text);
"""

IDENTITY_SCHEMA = """
create table cases (
    case_id text primary key, source_file text, court text, year integer,
    title text, decided_on text, author text,
    bench_size integer, bench text, bench_source text,
    petitioner text, respondent text,
    cites integer, cited_by integer
);
create table citations (citation_key text primary key, case_id text);
create table treatment (
    target_case_id text, treating_case_id text, treating_year integer,
    verb text, grade text, span text
);
create index treatment_target on treatment(target_case_id);
create table identity (key text primary key, value text);
create table rejects (
    case_id text, field text, reason text, era text, source_file text
);
"""

SC = "Supreme Court of India"
KERALA = "High Court of Kerala"

#: (case_id, case_name, court, year, para_type, chunk_id, text)
PARAS = (
    ("SYN_1990_MARKER", "Synthetic Traders vs Fixture Steels", SC, "1990", "ratio",
     "SYN_1990_MARKER_P002_C01",
     "Synthetic fixture, not law. The test is whether the marker was blue when "
     "the goods left the seller's hands; colour at delivery is the only colour "
     "that counts."),
    ("SYN_1990_MARKER", "Synthetic Traders vs Fixture Steels", SC, "1990", "ratio",
     "SYN_1990_MARKER_P003_C01",
     "Synthetic fixture, not law. Applying that test, the marker here was blue "
     "at delivery and the buyer's later repainting is irrelevant to liability."),
    ("SYN_1990_MARKER", "Synthetic Traders vs Fixture Steels", SC, "1990", "order",
     "SYN_1990_MARKER_P009_C01",
     "Synthetic fixture, not law. The appeal is allowed with costs."),
    ("SYN_2001_OVERRULED", "Fixture Paints vs Synthetic Buyers", SC, "2001", "ratio",
     "SYN_2001_OVERRULED_P004_C01",
     "Synthetic fixture, not law. A marker repainted before delivery is blue "
     "for every purpose, whatever its original colour."),
    ("SYN_2010_TREATING", "Synthetic Buyers vs Fixture Paints II", SC, "2010", "ratio",
     "SYN_2010_TREATING_P006_C01",
     "Synthetic fixture, not law. Fixture Paints is overruled: the original "
     "colour of the marker governs, and repainting cannot make it blue."),
    ("SYN_1975_KERALA", "Coastal Fixture Co vs State of Synthetica", KERALA, "1975",
     "reasoning", "SYN_1975_KERALA_P002_C01",
     "Synthetic fixture, not law. Whether a marker is blue is a question of "
     "fact for the trial court and not for this court on appeal."),
    ("SYN_1999_NOCITE", "Unreported Fixture vs Nobody", SC, "1999", "ratio",
     "SYN_1999_NOCITE_P001_C01",
     "Synthetic fixture, not law. The marker was green and the claim fails."),
)

#: (case_id, court, year, title, bench_size, bench_source)
CASES = (
    ("SYN_1990_MARKER", SC, 1990, "Synthetic Traders vs Fixture Steels", 3, "bench_header"),
    ("SYN_2001_OVERRULED", SC, 2001, "Fixture Paints vs Synthetic Buyers", 2, "bench_header"),
    ("SYN_2010_TREATING", SC, 2010, "Synthetic Buyers vs Fixture Paints II", 5, "bench_header"),
    ("SYN_1975_KERALA", KERALA, 1975, "Coastal Fixture Co vs State of Synthetica", 1,
     "author_inline"),
    ("SYN_1999_NOCITE", SC, 1999, "Unreported Fixture vs Nobody", 1, "author_inline"),
)

#: (citation_key, case_id) -- keys as `nm.domain.citation.reporter_key` makes them
CITATIONS = (
    ("1990SYN1", "SYN_1990_MARKER"),
    ("AIR1990SYN1", "SYN_1990_MARKER"),
    ("2001SYN44", "SYN_2001_OVERRULED"),
    ("2010SYN9", "SYN_2010_TREATING"),
    ("1975KER12", "SYN_1975_KERALA"),
)

#: (target, treating, treating_year, verb, grade, span)
TREATMENT = (
    ("SYN_2001_OVERRULED", "SYN_2010_TREATING", 2010, "overruled", "adverse",
     "Fixture Paints is overruled"),
    ("SYN_1990_MARKER", "SYN_2010_TREATING", 2010, "followed", "positive",
     "Synthetic Traders was rightly decided and is followed"),
)


def build(root: Path) -> tuple[Path, Path]:
    """Write both indexes under `root`. Returns (authority_path, identity_path)."""
    root.mkdir(parents=True, exist_ok=True)
    authority = root / "authority.db"
    identity = root / "identity.db"
    for p in (authority, identity):
        if p.exists():
            p.unlink()

    con = sqlite3.connect(authority)
    con.executescript(AUTHORITY_SCHEMA)
    con.executemany("insert into paras values (?,?,?,?,?,?,?)", PARAS)
    con.executemany("insert into identity values (?,?)", [
        ("built_at", "2026-09-12T00:00:00"),
        ("source", "synthetic fixture -- not legal_database"),
        ("corpus_version", "synthetic-2026-09-12"),
        ("source_paragraphs", "12"),
        ("indexed_paragraphs", str(len(PARAS))),
        ("attributable_kinds", "ratio,reasoning,order"),
        ("partial", "no"),
        ("scope", "synthetic fixtures only; no Indian law"),
    ])
    con.commit()
    con.close()

    con = sqlite3.connect(identity)
    con.executescript(IDENTITY_SCHEMA)
    con.executemany(
        "insert into cases (case_id, court, year, title, bench_size, bench_source) "
        "values (?,?,?,?,?,?)", CASES)
    con.executemany("insert into citations values (?,?)", CITATIONS)
    con.executemany("insert into treatment values (?,?,?,?,?,?)", TREATMENT)
    con.executemany("insert into identity values (?,?)", [
        ("built_at", "2026-09-12T00:00:00"), ("cases", str(len(CASES))),
        ("with_bench", str(len(CASES))), ("citation_keys", str(len(CITATIONS))),
    ])
    con.commit()
    con.close()
    return authority, identity
