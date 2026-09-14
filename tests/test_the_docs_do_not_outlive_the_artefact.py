"""A DOCUMENT'S CLAIM ABOUT AN ARTEFACT IS A CLAIM ABOUT THE FILESYSTEM.

B-141. `docs/BACKLOG.md` carried BK-4 -- *`pipeline/indexing/build_authority_index.py` has
never been run* -- for eight days after the index was built. Measured on
7 September 2026:

    .nm/authority.db          1,097 MB, built_at 2026-08-30T07:51:38
    partial                   no
    indexed_paragraphs        451,548 of 1,015,780
    readiness("authorities")  readable
    a live search             ANSWERED, 40 binding findings

Everything downstream inherited it. The row was quoted as a live blocker in
five separate reports, and a phase table written the same morning said
`authorities` *waits on the index build (BK-4)* -- which was false when it was
typed.

WHY THIS IS NOT JUST A STALE NOTE
-----------------------------------
This project's whole discipline is that a claim is measured, and CLAUDE.md
says so four different ways. The failure was not carelessness about a
document; it was trusting a document about a FACT THAT COULD HAVE BEEN
CHECKED IN ONE LINE, repeatedly, in the one repository whose rules exist
against exactly that.

The general form, and it is what this file checks: **a live document may not
assert that a build artefact is absent while the artefact is on disk.** The
artefact is the authority; the sentence is a copy of it, and a copy that
cannot be refuted goes stale silently.

WHAT THIS DELIBERATELY DOES NOT DO
------------------------------------
It does not require the index to exist. Not building it is a legitimate state
-- it is a long job the advocate runs, and `readiness()` reports
`INDEX NOT BUILT` honestly when it has not. What is refused is the two being
out of step in the direction that misleads.
"""
from __future__ import annotations

import pathlib
import re
import sqlite3

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Documents that BIND, from CLAUDE.md's authority chain. `development_environment/archives/` is
#: excluded by that same chain: it is reference and is explicitly not live.
LIVE_DOCS = (
    "CLAUDE.md",
    "docs/BACKLOG.md",
    "docs/BASELINE.md",
)

def _file_exists(path: pathlib.Path) -> bool:
    """Presence for an artefact that IS its file."""
    return path.exists()


def _holds_embeddings(path: pathlib.Path) -> bool:
    """Presence for an artefact whose file proves nothing on its own.

    `.code-review-graph/graph.db` existed for weeks with zero vectors in it,
    so a `path.exists()` test here would assert that semantic search works
    from the moment the graph is first built. **Presence is a measured
    property of the contents, not a stat on the path** -- the RG-01 lesson in
    CLAUDE.md, where a count taken from the wrong index read exactly like
    absence and blocked a release.

    A missing table is "not built", which is a legitimate live claim.
    """
    if not path.exists():
        return False
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return bool(con.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])
    except sqlite3.Error:
        return False
    finally:
        con.close()


#: (the artefact, phrases that assert it does not exist, what PRESENT means).
#:
#: The phrases are matched case-insensitively against the whole document, so a
#: sentence explaining that the claim was WRONG has to avoid them -- which is
#: right: "has never been run" is the sentence that went stale, and a document
#: repeating it verbatim while the file sits on disk is the defect whether or
#: not a later paragraph corrects it.
ABSENCE_CLAIMS = (
    (".nm/authority.db", (
        "build_authority_index.py` has never been run",
        "the authority index has never been run",
        "the index has never been built",
    ), _file_exists),
    # 9 September 2026. CLAUDE.md carried "Semantic search (embeddings) | NOT
    # WORKING" and "embeddings are deliberately deferred" while 2,572 vectors
    # sat in graph.db -- the same shape as B-141, one artefact over.
    (".code-review-graph/graph.db", (
        "semantic search (embeddings) | **not working**",
        "embeddings are deliberately deferred",
        "without embeddings there is no conceptual search",
    ), _holds_embeddings),
)


def test_no_live_document_says_an_artefact_is_absent_while_it_is_on_disk():
    """THE RULE B-141 EARNED.

    Run against the real tree rather than a fixture, because the artefact IS
    the thing under test. A synthetic file would prove the regex works.
    """
    wrong = []
    for rel, phrases, is_present in ABSENCE_CLAIMS:
        if not is_present(ROOT / rel):
            continue                      # not built is a legitimate state
        for doc in LIVE_DOCS:
            path = ROOT / doc
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            for phrase in phrases:
                if phrase.lower() in text:
                    wrong.append(f"{doc}: {phrase!r} — but {rel} exists")

    assert not wrong, (
        "these documents say an artefact is missing and it is on disk:\n  "
        + "\n  ".join(wrong)
        + "\n\nThe artefact is the authority and the sentence is a copy of "
          "it. BK-4 carried this exact claim for eight days after the index "
          "was built, and five reports repeated it.")


@pytest.mark.parametrize("stale", [
    "pipeline/indexing/build_authority_index.py` has never been run",          # B-141
    "| Semantic search (embeddings) | **NOT WORKING** — see below",  # 9 Sep 2026
    "**Embeddings are deliberately deferred, not forgotten.**",      # 9 Sep 2026
])
def test_the_check_can_see_a_stale_claim(stale):
    """THE POSITIVE CONTROL. A checker that always returns [] passes a sweep
    identically -- B-049, on every commit for weeks.

    Every row of ABSENCE_CLAIMS needs one: a phrase list that does not contain
    the sentence which actually went stale is a check that would not have
    caught the defect it was written for.
    """
    assert any(phrase.lower() in stale.lower()
               for _, phrases, _ in ABSENCE_CLAIMS for phrase in phrases), (
        f"{stale!r} is a sentence this repository actually shipped while the "
        "artefact was on disk, and no phrase in ABSENCE_CLAIMS matches it")


def test_the_recorded_paragraph_count_matches_the_corpus_arithmetic():
    """B-141's second half, and the first diagnosis of it was wrong.

    `BASELINE.md` stated 451,553 and I recorded that the total contradicted
    its own rows. IT DID NOT. The `ratio` row said 144,744 where the corpus
    holds 144,739, and the total was faithfully consistent with the wrong row
    -- which is the harder kind to catch, because adding the rows up CONFIRMS
    it. Two independent sources put ratio at 144,739: a direct count over the
    1,015,780 case-law chunks, and the built index's own `indexed_paragraphs`
    of 451,548.

    SO THIS ASSERTS INTERNAL CONSISTENCY, and would not have caught B-141.
    That is stated rather than papered over: the row itself is a measured
    fact and belongs in a class C eval against the corpus, which takes
    minutes. What this refuses is the cheap failure -- a total edited without
    its rows, or a row edited without its total -- which is what happens next
    time someone corrects one number by hand.
    """
    text = (ROOT / "docs" / "BASELINE.md").read_text(encoding="utf-8")

    rows = {}
    for kind in ("ratio", "reasoning", "order"):
        m = re.search(rf"\|\s*`{kind}`\s*\|\s*([\d,]+)\s*\|", text)
        assert m, f"the {kind} row is gone from BASELINE.md"
        rows[kind] = int(m.group(1).replace(",", ""))

    m = re.search(r"\*\*Attributable total:\s*([\d,]+)", text)
    assert m, "the attributable total is gone from BASELINE.md"
    stated = int(m.group(1).replace(",", ""))

    assert stated == sum(rows.values()), (
        f"BASELINE.md states {stated:,} and its own rows sum to "
        f"{sum(rows.values()):,} ({rows}). The rows are measured; the total "
        f"is arithmetic, and it is the total that has been wrong.")
