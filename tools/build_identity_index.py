"""Recover case identity from the SOURCE files. AN OFFLINE JOB — run it deliberately.

    python tools/build_identity_index.py

WHY THIS EXISTS
---------------
`legal_database/vector_store/` is a derived layer, and the extraction that
produced it dropped every field that identifies a case. Reading it and
reporting the result as a fact about the corpus understated bench coverage by
twelve times and citation coverage by five, and led to a recommendation not to
build the bench-hierarchy rule at all.

`legal_database/raw_data/CaseLaws/` holds the 34,037 source judgments, and each
one opens with a structured header:

    [Cites 44 , Cited by 3 ]
    Supreme Court of India
    The State Of Tripura vs The Province Of East Bengal... on 4 December, 1950
    Equivalent citations: 1951 AIR 23, 1951 SCR 1, AIR 1951 SUPREME COURT 23
    Bench:
    Hiralal J.  Kania , Saiyid Fazal Ali , B.K. Mukherjea , N. Chandrasekhara Aiyar
    PETITIONER: THE STATE OF TRIPURA
    RESPONDENT: THE PROVINCE OF EAST BENGAL

Measured across all 34,037: `Bench:` on 90.2%, `Equivalent citations:` on
82.2%, party blocks on 40.0%.

WHAT IT BUILDS, AND WHY EACH TABLE
-----------------------------------
`cases`       one row per judgment: court, year, bench size and composition,
              parties, author. **Bench size is what makes the
              larger-bench-supersedes rule computable at all.**

`citations`   299,965 distinct reporter-citation keys -> case. THIS IS THE KEY
              THAT WAS MISSING. Judgments cite each other by AIR/SCC number,
              and case NAMES do not resolve — matching on names reached 1.2% of
              mentions because the derived names are truncated and fused.

`treatment`   target case <- treating case, with the verb and the verbatim
              span. Measured reach: 6,710 judgments, 19.7%, against 0.83% from
              the shipped citator.

PRECISION IS WORTH MORE THAN RECALL HERE, AND THE FILTERS SAY SO
-----------------------------------------------------------------
A WRONG treatment record is worse than a missing one: `not_checked` blocks
reliance, while a mistaken `overruled` — or a mistaken clearance — is a
confident wrong answer about whether law is still good, the single most
damaging thing this product can produce. So:

  * the verb must appear within `_WINDOW` characters of the citation
  * a judgment cannot treat itself
  * a judgment cannot treat a LATER one — chronology is a free, hard filter
  * the span is stored, so every record can be read back and challenged

It records its own identity (defect shape S11), and refuses to overwrite an
existing index.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sqlite3
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "legal_database" / "raw_data" / "CaseLaws"
OUT = ROOT / ".nm" / "identity.db"

# How close a treatment verb must sit to the citation it is taken to govern.
# Wide enough for "...was overruled by this Court in Kesavananda Bharati v.
# State of Kerala, AIR 1973 SC 1461...", narrow enough that a verb in an
# unrelated sentence two paragraphs away does not attach itself.
_WINDOW = 300

_HEADER_STOP = re.compile(
    r"^(PETITIONER|RESPONDENT|APPELLANT|Author|ACT|JUDGMENT|ORDER|CASE NO|DATE OF|"
    r"Equivalent citations|Bench)\s*:?\s*$", re.M)

_CITLINE = re.compile(r"^Equivalent citations:\s*(.+)$", re.M)

# Bench notations, in the order they are tried. The corpus spans 1955-2026 and
# the header format drifts across it: `Bench:` covers 90.2% and is absent from
# a fifth of the 1950s and a fourteenth of the 2020s.
_CORAM = re.compile(r"^\s*CORAM\s*:?\s*$", re.I | re.M)
_HONBLE = re.compile(r"HON'?BLE\s+(?:MR\.?|MRS\.?|MS\.?|)\s*JUSTICE\s+"
                     r"([A-Z][A-Za-z.\- ]{2,40})", re.I)
#: A modern signature block: a dotted rule terminated by `J.`, one per judge.
_SIGNATURE = re.compile(r"^\s*\.{3,}[.\s]*J\.?\s*$", re.M)
#: The AUTHOR of a judgment, written inline after the JUDGMENT heading. This is
#: NOT the bench and is never counted as one -- see the module docstring.
_INLINE_AUTHOR = re.compile(r"^\s*([A-Z][A-Za-z.\s]{2,40}),\s*(?:C\.?)?J\.\s*$", re.M)
_BENCH = re.compile(r"^Bench:\s*$", re.M)
_AUTHOR = re.compile(r"^Author:\s*\n(.+)$", re.M)
_PARTY = re.compile(r"^(PETITIONER|RESPONDENT):\s*\n(.+)$", re.M)
_TITLE = re.compile(r"^(.+?)\s+on\s+(\d{1,2}\s+\w+,\s+\d{4})\s*$", re.M)
_COUNTS = re.compile(r"\[Cites\s*\n?(\d+)\s*\n?,\s*Cited by\s*\n?(\d+)", re.S)

# THE NEUTRAL CITATION IS THE MODERN KEY, AND THE REJECTS TABLE IS WHAT FOUND
# IT. `Equivalent citations:` is absent from 6,060 judgments — 5,300 of them in
# the 2020s — because the modern Supreme Court stamps `2025 INSC 407` instead.
# 49% of those rejects carry one, so this recovers ~2,973 judgments in exactly
# the era an advocate is most likely to be citing. An undifferentiated NULL
# would never have shown that; an enumerated reject list did, on its first run.
_REPORTER = re.compile(
    r"\b(?:AIR\s*\d{4}\s*[A-Z]{2,8}\s*\d+"
    r"|\(?\d{4}\)?\s*\(?\d+\)?\s*S\.?C\.?C\.?\s*\d+"
    r"|\(?\d{4}\)?\s*\d*\s*S\.?C\.?R\.?\s*\d+"
    r"|\d{4}\s*CRI\.?\s*L\.?J\.?\s*\d+"
    r"|\d{4}\s*INSC\s*\d+)", re.I)

#: The neutral citation a judgment stamps on ITSELF, used where the header
#: carries no `Equivalent citations:` line at all.
_NEUTRAL_SELF = re.compile(r"\b(\d{4}\s*INSC\s*\d+)", re.I)

_NONKEY = re.compile(r"[^A-Z0-9]")

# Verbs, graded. `distinguished` is NOT negative -- it limits scope, it does not
# doubt correctness, and grading it as adverse would flag half the corpus.
# `reversed` and `set aside` are excluded entirely: appellate courts reverse
# lower courts in almost every appeal, so the phrase carries no information
# about the CITED case and produced the false positives measured on 30 Aug.
_VERBS: tuple[tuple[str, str], ...] = (
    ("overruled", "adverse"), ("overruling", "adverse"), ("overrule", "adverse"),
    ("no longer good law", "adverse"), ("not good law", "adverse"),
    ("per incuriam", "adverse"), ("disapproved", "adverse"),
    ("disapproving", "adverse"), ("doubted", "adverse"),
    ("distinguished", "scope"), ("distinguishing", "scope"),
    ("followed", "positive"), ("affirmed", "positive"),
    ("approved", "positive"), ("applied", "positive"),
)
# WORD BOUNDARIES ARE LOAD-BEARING. Without them "undoubted" matches "doubted",
# and "the undoubted exercise of jurisdiction by a quasi-judicial authority"
# became adverse treatment of whatever case happened to be cited nearby. Found
# by reading three sample records, not by trusting the count.
_VERB_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(v) for v, _ in _VERBS) + r")\b", re.I)
_GRADE = dict(_VERBS)

SCHEMA = """
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
create index rejects_field on rejects(field);
"""


def citation_key(raw: str) -> str:
    return _NONKEY.sub("", raw.upper())


def parse_bench(head: str, at: int) -> list[str]:
    """The judges, from the block after `Bench:`.

    THE COMMA IS THE STRUCTURE, and scanning to a stop keyword instead was
    wrong. The block is literally:

        name \\n , \\n name \\n , \\n name \\n <whatever comes next>

    Only 40% of files carry a `PETITIONER:` header to stop at, so on the other
    60% a keyword scan ran into the judgment body and swallowed "IN THE SUPREME
    COURT OF INDIA", "CIVIL APPELLATE JURISDICTION", "REPORTABLE" and the case
    number as judges. Two-judge benches came out as eleven, fourteen and
    sixteen, and the corpus appeared to hold 1,556 nine-judge benches — around
    a hundred times the number in the Supreme Court's entire history.

    So the list is consumed name-comma-name and STOPS at the first place a
    separator should be and is not. An over-count silently promotes a Division
    Bench to a Constitution Bench, which is precisely the error the hierarchy
    rule exists to prevent.
    """
    lines = [ln.strip() for ln in head[at:].splitlines()]
    lines = [ln for ln in lines if ln != ""]

    out: list[str] = []
    i = 0
    while i < len(lines):
        name = lines[i]
        if not _plausible_judge(name):
            break
        out.append(name)
        i += 1
        if i >= len(lines) or lines[i] != ",":
            break        # the last name is not followed by a separator
        i += 1
    return out


def _plausible_judge(name: str) -> bool:
    """A judge's name, and not a heading, a case number or a court.

    Deliberately narrow. A name wrongly rejected costs one judge off a count
    that is then reported as uncertain; a heading wrongly accepted inflates the
    bench and changes which authority is said to govern.
    """
    if not (3 <= len(name) <= 55):
        return False
    if re.search(r"\d", name):
        return False                      # case numbers, years, "2024 INSC 815"
    if name.isupper():
        return False                      # REPORTABLE, IN THE SUPREME COURT ...
    if re.search(r"(?i)\b(court|jurisdiction|appeal|petition|reportable|"
                 r"judgment|order|versus|appellant|respondent|petitioner|"
                 r"india|bench|coram|writ|civil|criminal|arising)\b", name):
        return False
    return bool(re.search(r"[A-Za-z]{3}", name))


def _read_bench(text: str, head: str) -> tuple[list[str], str]:
    """Every notation the corpus uses for a bench, tried in order of certainty.

    Returns the judges and the NOTATION THEY CAME FROM, because how a fact was
    established is part of the fact. `bench_source` is what lets a later reader
    see that the 2010s parse cleanly on one notation and the 1950s do not.
    """
    m = _BENCH.search(head)
    if m:
        judges = parse_bench(head, m.end())
        if judges:
            return judges, "bench_header"

    m = _CORAM.search(head)
    if m:
        judges = parse_bench(head, m.end())
        if judges:
            return judges, "coram_header"

    honble = _HONBLE.findall(head)
    if honble:
        seen: list[str] = []
        for name in honble:
            clean = " ".join(name.split())
            if clean not in seen:
                seen.append(clean)
        return seen, "honble_list"

    # A modern signature block: one dotted rule terminated by `J.` per judge.
    # Counted from the TAIL, because the same shape can appear mid-judgment
    # when an order is reproduced.
    signatures = _SIGNATURE.findall(text[-3000:])
    if signatures:
        return [f"judge {i + 1}" for i in range(len(signatures))], "signature_block"

    return [], "none"


def parse_header(text: str, path: pathlib.Path) -> dict:
    head = text[:3000]
    rec: dict = {"source_file": str(path.relative_to(SOURCE)), "case_id": path.stem}

    counts = _COUNTS.search(head)
    rec["cites"] = int(counts.group(1)) if counts else None
    rec["cited_by"] = int(counts.group(2)) if counts else None

    title = _TITLE.search(head)
    if title:
        rec["title"] = title.group(1).strip()
        rec["decided_on"] = title.group(2).strip()
        y = re.search(r"(\d{4})$", rec["decided_on"])
        rec["year"] = int(y.group(1)) if y else None
    else:
        rec["title"] = rec["decided_on"] = None
        rec["year"] = None

    # The court line sits directly above the title.
    court = re.search(r"^(.*(?:Supreme Court|High Court|HC)[^\n]*)$", head, re.M)
    rec["court"] = court.group(1).strip()[:80] if court else None

    author = _AUTHOR.search(head)
    rec["author"] = author.group(1).strip()[:80] if author else None

    parties = {k: v.strip()[:200] for k, v in _PARTY.findall(head)}
    rec["petitioner"] = parties.get("PETITIONER")
    rec["respondent"] = parties.get("RESPONDENT")

    judges, source = _read_bench(text, head)
    rec["bench"] = " | ".join(judges) if judges else None
    rec["bench_size"] = len(judges) or None
    rec["bench_source"] = source

    cits = _CITLINE.search(head)
    keys = [citation_key(c) for c in cits.group(1).split(",")] if cits else []
    source = "equivalent" if keys else "none"
    if not keys:
        # THE MODERN KEY, and the rejects table is what found it. The Supreme
        # Court now stamps `2025 INSC 407` on the judgment instead of carrying
        # an `Equivalent citations:` line, so 5,300 of the 2020s were
        # unresolvable as treatment targets — exactly the era an advocate is
        # most likely to be citing.
        neutral = _NEUTRAL_SELF.search(head)
        if neutral:
            keys = [citation_key(neutral.group(1))]
            source = "neutral"
    rec["citation_source"] = source
    rec["_citations"] = keys
    return rec


def extract_treatment(text: str, case_id: str, year: int | None,
                      resolve) -> list[tuple]:
    """Every (target, verb) this judgment states, with its span.

    Chronology is a FREE, HARD precision filter: a judgment cannot treat one
    decided after it. Applying it costs nothing and removes a whole class of
    mis-resolution silently.
    """
    out: list[tuple] = []
    seen: set[tuple[str, str]] = set()
    for m in _REPORTER.finditer(text):
        key = citation_key(m.group(0))
        target = resolve(key)
        if target is None or target[0] == case_id:
            continue
        target_id, target_year = target
        if year and target_year and target_year > year:
            continue      # cannot treat a later judgment
        # DIRECTION IS THE HARD PART, AND GETTING IT BACKWARDS IS THE WORST
        # FAILURE THIS INDEX CAN PRODUCE.
        #
        #   "...the said judgment was overruled by this Court in
        #    Land Acquisition Officer v. V. Narasaiah [(2001) ...]"
        #
        # names the OVERRULING case. Reading the verb near the citation marks
        # the leading authority as overruled — telling an advocate the case
        # they are about to rely on is dead when it is the one that killed
        # something else.
        #
        # There is no reliable way to disambiguate "overruled by X" from
        # "overruled X" with a window, so only the unambiguous direction is
        # taken: THE CITATION MUST PRECEDE THE VERB, as in "Ram Lal v. State
        # ... was overruled". Recall suffers and every surviving record points
        # the right way.
        window = text[m.end():m.end() + _WINDOW]
        verb = _VERB_RE.search(window)
        if not verb:
            continue
        between = window[:verb.start()]
        if re.search(r"\b(?:by|in)\b\s*$", between.strip()[-30:] or " "):
            continue          # "...overruled by <cite>" read backwards
        v = verb.group(0).lower()
        window = text[max(0, m.start() - 120):m.end() + _WINDOW]
        if (target_id, v) in seen:
            continue
        seen.add((target_id, v))
        out.append((target_id, case_id, year, v, _GRADE.get(v, "scope"),
                    " ".join(window.split())[:400]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not SOURCE.exists():
        sys.exit(f"the source judgments are not attached: {SOURCE}")
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        sys.exit(f"{out} already exists. Delete it deliberately to rebuild.")

    files = sorted(SOURCE.rglob("*.txt"))
    if args.limit:
        files = files[:args.limit]

    dst = sqlite3.connect(str(out))
    dst.executescript(SCHEMA)

    # ---- pass 1: headers, so every citation is resolvable before pass 2 ----
    t0 = time.time()
    by_key: dict[str, tuple[str, int | None]] = {}
    years: dict[str, int | None] = {}
    rows = []
    rejects: list[tuple] = []
    texts: dict[str, str] = {}
    with_bench = with_cits = with_parties = 0
    for i, p in enumerate(files, 1):
        text = p.read_text(encoding="utf8", errors="replace")
        rec = parse_header(text, p)
        texts[rec["case_id"]] = text
        years[rec["case_id"]] = rec["year"]
        rows.append((rec["case_id"], rec["source_file"], rec["court"], rec["year"],
                     rec["title"], rec["decided_on"], rec["author"],
                     rec["bench_size"], rec["bench"], rec["bench_source"],
                     rec["petitioner"], rec["respondent"],
                     rec["cites"], rec["cited_by"]))

        # THE REJECTS. Every field that could not be established, with the
        # reason and the era. An undifferentiated NULL cannot be worked; an
        # enumerated gap can, and this is what shows that bench parsing misses
        # a fifth of the 1950s and none of the 2010s.
        era = f"{(rec['year'] // 10) * 10}s" if rec["year"] else "unknown"
        if not rec["bench_size"]:
            reason = ("author named inline but the BENCH is not stated — "
                      "'Name, J.' after the JUDGMENT heading names who wrote "
                      "it, not who heard it, and counting it as a single judge "
                      "would demote every Division Bench whose author signed "
                      "alone"
                      if _INLINE_AUTHOR.search(text[:4000]) else
                      "no bench notation found in any of: Bench:, CORAM:, "
                      "HON'BLE list, signature block")
            rejects.append((rec["case_id"], "bench", reason, era, rec["source_file"]))
        if not rec["_citations"]:
            rejects.append((rec["case_id"], "citations",
                            "no `Equivalent citations:` line — this judgment "
                            "cannot be resolved as the target of a citation, so "
                            "its treatment can never be checked", era,
                            rec["source_file"]))
        if not rec["petitioner"]:
            rejects.append((rec["case_id"], "parties",
                            "no PETITIONER:/RESPONDENT: block", era,
                            rec["source_file"]))
        with_bench += bool(rec["bench_size"])
        with_parties += bool(rec["petitioner"])
        if rec["_citations"]:
            with_cits += 1
        for k in rec["_citations"]:
            if len(k) > 7:
                by_key.setdefault(k, (rec["case_id"], rec["year"]))
        if i % 5000 == 0:
            print(f"  headers {i:>7,}/{len(files):,}  ({time.time() - t0:.0f}s)",
                  flush=True)

    dst.executemany(
        "insert or replace into cases values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    dst.executemany("insert into rejects values (?,?,?,?,?)", rejects)
    dst.executemany("insert or replace into citations values (?,?)",
                    [(k, v[0]) for k, v in by_key.items()])
    dst.commit()
    print(f"  pass 1 done in {time.time() - t0:.0f}s")

    # ---- pass 2: treatment ------------------------------------------------
    t1 = time.time()
    resolve = by_key.get
    found = 0
    batch: list[tuple] = []
    for i, (case_id, text) in enumerate(texts.items(), 1):
        batch.extend(extract_treatment(text, case_id, years.get(case_id), resolve))
        if len(batch) >= 5000:
            dst.executemany("insert into treatment values (?,?,?,?,?,?)", batch)
            found += len(batch)
            batch.clear()
        if i % 5000 == 0:
            print(f"  treatment {i:>7,}/{len(texts):,}  ({time.time() - t1:.0f}s)",
                  flush=True)
    if batch:
        dst.executemany("insert into treatment values (?,?,?,?,?,?)", batch)
        found += len(batch)

    targets = dst.execute(
        "select count(distinct target_case_id) from treatment").fetchone()[0]
    adverse = dst.execute(
        "select count(distinct target_case_id) from treatment "
        "where grade='adverse'").fetchone()[0]

    dst.executemany("insert into identity values (?,?)", [
        ("built_at", time.strftime("%Y-%m-%dT%H:%M:%S")),
        ("source", str(SOURCE)),
        ("source_files", str(len(files))),
        ("cases", str(len(rows))),
        ("with_bench", str(with_bench)),
        ("with_citations", str(with_cits)),
        ("with_parties", str(with_parties)),
        ("citation_keys", str(len(by_key))),
        ("treatment_records", str(found)),
        ("targets_reached", str(targets)),
        ("targets_adverse", str(adverse)),
        ("verb_window_chars", str(_WINDOW)),
        ("rejects", str(len(rejects))),
        ("partial", "yes" if args.limit else "no"),
    ])
    dst.commit()
    dst.close()

    n = len(files)
    print()
    print(f"  source files            {n:>9,}")
    print(f"  with a bench            {with_bench:>9,}  ({with_bench / n:.1%})")
    print(f"  with citations          {with_cits:>9,}  ({with_cits / n:.1%})")
    print(f"  with party blocks       {with_parties:>9,}  ({with_parties / n:.1%})")
    print(f"  citation keys           {len(by_key):>9,}")
    print(f"  treatment records       {found:>9,}")
    print(f"  judgments reached       {targets:>9,}  ({targets / n:.1%})")
    print(f"  of those, ADVERSE       {adverse:>9,}  ({adverse / n:.1%})")
    print()
    print("  REJECTS — what could not be established, and why")
    for field, cnt in dst_counts(out):
        print(f"    {field:<12} {cnt:>7,}")
    print(f"  built in {time.time() - t0:.0f}s -> {out}")
    return 0


def dst_counts(path: pathlib.Path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return con.execute(
            "select field, count(*) from rejects group by 1 order by 2 desc").fetchall()
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
