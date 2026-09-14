"""Classify judgment paragraphs, and MEASURE THAT BEFORE INGESTING ANYTHING.

    python pipeline/indexing/classify_paragraphs.py --eval --sample 200   # measure first
    python pipeline/indexing/classify_paragraphs.py --plan                # what a run costs
    python pipeline/indexing/classify_paragraphs.py --run                 # classify staging

WHY THIS EXISTS AND WHY THE EVAL COMES FIRST
----------------------------------------------
A corpus chunk is ONE PARAGRAPH with a `paragraph_type`. Scraped judgments are
whole HTML pages, so ingestion means splitting and classifying -- and the
classification is not a formatting detail, it is the attributability model.

`arguments` is 14.8% of the corpus: COUNSEL'S SUBMISSION, which reads exactly
like a holding. It is excluded at build time AND at use, twice, deliberately.
A classifier that calls it `ratio` does not make the corpus slightly noisier;
it makes the product attribute a LOSING ADVOCATE'S SUBMISSION TO THE COURT,
and every downstream guard passes, because the retrieval is self-consistent.

From the first scraped judgment opened, unedited:

    "3. According to learned senior counsel Sri A.Sudarshan Reddy rejection of
     tender on the ground that solvency certificate ..."

That is `arguments`. It reads as a finding to anything that does not notice
the attributive phrase.

THE GROUND TRUTH ALREADY EXISTS, WHICH IS THE WHOLE POINT
-----------------------------------------------------------
`chunks.db` holds 1,015,780 case paragraphs that are ALREADY LABELLED. So the
error rate is not a matter of opinion and does not need a hand-built fixture:
sample the corpus's own labelled paragraphs, classify them blind, and compare.

    --eval --sample 200     costs 200 calls and answers the question
    --run                   costs ~67,000 and assumes the answer

Doing those in that order is the entire argument of this file.

WHAT THE EVAL REPORTS, AND WHICH NUMBER MATTERS
-------------------------------------------------
A confusion matrix, and then the one figure that decides whether this may be
used at all: **the rate at which `arguments` is classified as attributable**
(`ratio`, `reasoning` or `order`). Overall accuracy is the wrong headline --
a classifier can be 95% accurate and still route one submission in twenty into
the court's mouth, and those are not the same failure.

THE OTHER DIRECTION IS CHEAP AND MUST NOT BE TRADED AGAINST IT
----------------------------------------------------------------
Calling a genuine `ratio` paragraph `unknown` loses a citation. Calling
`arguments` a `ratio` invents one. Those costs are not symmetric and the
thresholds below are not symmetric either.

NOTHING HERE IS RUN AUTOMATICALLY
-----------------------------------
Both `--eval` and `--run` spend model calls. Long jobs are started by the
advocate.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "backend"))
from nm.ports.evidence import (  # noqa: E402
    ATTRIBUTABLE_LABELS,
    CORPUS_LABELS,
)

from assurance.common._console import utf8_console  # noqa: E402

utf8_console()

CORPUS = ROOT / "legal_database" / "vector_store" / "chunks.db"
STAGING = ROOT / ".nm" / "staging" / "judgments"

#: The corpus's own vocabulary. Not invented here -- measured from it, so a
#: classifier cannot emit a class the corpus has no meaning for.
KINDS = CORPUS_LABELS

#: What retrieval will attribute to the court. The rest is held and not
#: quoted. READ FROM THE CONTRACT: an eval whose notion of attributable
#: differs from the product's measures a product nobody ships.
ATTRIBUTABLE = ATTRIBUTABLE_LABELS

#: THE NUMBER THAT DECIDES WHETHER THIS MAY BE USED.
#:
#: One submission in a hundred entering the corpus as the court's own words is
#: already a lot -- it is a quotation an advocate may put in front of a judge.
#: This is a ceiling on the dangerous direction, not on overall accuracy.
MAX_ARGUMENTS_AS_ATTRIBUTABLE = 0.01

#: The cheap direction. Losing a real ratio to `unknown` costs a citation and
#: costs nobody their credibility, so the tolerance is an order of magnitude
#: looser -- deliberately, and stated so nobody "balances" the two later.
MAX_ATTRIBUTABLE_LOST = 0.15

#: WHOSE WORDS ARE THESE. Asked first, and on its own.
#:
#: The first prompt buried this among seven classes and read counsel's
#: submission as the court's analysis 15 times in 30. A paragraph misfiled
#: between `ratio` and `reasoning` is still the court speaking; a
#: submission filed as either is not, and only this question separates
#: them.
SPEAKERS = ("court", "counsel", "editor", "cannot_tell")

#: What the COURT is doing, asked only where the court is speaking.
FUNCTIONS = ("holding", "analysis", "direction", "narration")

#: The mapping is CODE. The model answers two questions; it is never asked
#: to remember what its own answers imply -- which is the rule it failed.
SPEAKER_KIND = {
    "counsel": "arguments",
    "editor": "headnote",
    "cannot_tell": "unknown",
}
FUNCTION_KIND = {
    "holding": "ratio",
    "analysis": "reasoning",
    "direction": "order",
    "narration": "facts",
}

SCHEMA = {
    "type": "object",
    "x-nm-read": "paragraph_kind",
    "properties": {
        # ORDER MATTERS. A model generating JSON in order answers the
        # speaker question before it has committed to anything else.
        "speaker": {"type": "string", "enum": list(SPEAKERS)},
        "function": {"type": "string", "enum": list(FUNCTIONS)},
        "because": {"type": "string"},
    },
    "required": ["speaker", "function", "because"],
    "additionalProperties": False,
}


def prompt(paragraph: str) -> str:
    """What the model is asked. TWO QUESTIONS, the important one first.

    ONE PARAGRAPH, no surrounding judgment: the corpus labels a paragraph
    on its own terms, and giving the whole judgment would let position do
    the work -- position being exactly what differs between a scraped page
    and a corpus chunk.
    """
    return (
        "Here is ONE PARAGRAPH from an Indian judgment. Answer two "
        "questions about it.\n\n"

        "FIRST — WHOSE WORDS ARE THESE?\n\n"
        "  court        the judge writing. The court's own voice.\n"
        "  counsel      A SUBMISSION, either side, which the court is\n"
        "               REPORTING rather than adopting. Signals: 'learned\n"
        "               counsel submitted', 'according to', 'it is\n"
        "               contended', 'Sri X appearing for the petitioner',\n"
        "               'it is argued'. THIS READS EXACTLY LIKE A HOLDING.\n"
        "               The court is quoting an argument, not making one.\n"
        "  editor       a headnote or summary written by a law reporter,\n"
        "               not by the court\n"
        "  cannot_tell  the paragraph does not settle it. A REAL ANSWER,\n"
        "               and the right one whenever the signals conflict or\n"
        "               the text is too short to carry them.\n\n"

        "This first question decides the most. A paragraph misfiled\n"
        "between a holding and analysis is still the court speaking. A\n"
        "submission filed as either puts a losing advocate's words into\n"
        "the court's mouth, and an advocate may quote it to a judge.\n\n"

        "SECOND — IF the court is speaking, what is it doing?\n\n"
        "  holding    deciding the point. What the case is authority for.\n"
        "  analysis   working towards that decision — construing a\n"
        "             provision, weighing authority, giving reasons.\n"
        "  direction  what the court orders: relief, costs, disposal,\n"
        "             directions to a party or a subordinate court.\n"
        "  narration  what happened. Facts, procedural history, the\n"
        "             record. The court recounting, not deciding.\n\n"

        "If the speaker is NOT the court, answer the second question with\n"
        "'narration' — it will be ignored.\n\n"

        "PARAGRAPH:\n{}\n".format(paragraph))

# ------------------------------------------------------------- the read ---

def _model():
    """The configured routine-tier model, built the way every other
    offline tool builds one -- through the composition root, so a tool
    cannot be pointed at a different provider from the product.
    """
    from nm.adapters.model.config import load, load_dotenv
    from nm.bootstrap.composition import build_model

    load_dotenv(ROOT / ".env")
    return build_model(load())


_CLIENT = None


def classify(paragraph: str) -> str:
    """One paragraph in, one class out.

    A READ THAT FAILS RETURNS `unknown`, NOT A GUESS. `unknown` is the
    honest answer to a question that could not be asked, and it is also
    the SAFE one: an unclassified paragraph is held and never quoted,
    where any other fallback would attribute something on the strength of
    a network error.

    It is counted in the matrix like any other answer, so a run where the
    model was unreachable shows up as a wall of `unknown` rather than as
    a quietly poor score.
    """
    global _CLIENT
    from nm.ports.model import ModelError, Prompt, Tier

    if _CLIENT is None:
        _CLIENT = _model()
    try:
        res = _CLIENT.structured(
            Prompt(system="You classify paragraphs of Indian judgments.",
                   user=prompt(paragraph)),
            SCHEMA, Tier.ROUTINE, max_tokens=120)
    except ModelError:
        return "unknown"
    data = res.data or {}
    speaker = (data.get("speaker") or "").strip()
    function = (data.get("function") or "").strip()

    # THE MAPPING, IN CODE. A speaker other than the court settles the
    # class outright, whatever the second answer said -- the model is
    # never asked to remember what its own answer implies.
    if speaker in SPEAKER_KIND:
        return SPEAKER_KIND[speaker]
    if speaker == "court":
        return FUNCTION_KIND.get(function, "unknown")
    # A speaker it would not name is not a court paragraph by default.
    return "unknown"

# ------------------------------------------------------------------- eval ---

def sample_labelled(n: int, seed: int = 7) -> list[tuple[str, str]]:
    """(paragraph, corpus label) pairs, STRATIFIED across the classes.

    A uniform sample is 26.7% `unknown` and 14.8% `arguments`, so a hundred
    rows would carry perhaps fifteen of the class this whole eval is about.
    Stratifying spends the sample where the answer lives.
    """
    if not CORPUS.exists():
        sys.exit(f"the corpus is not attached: {CORPUS}")
    per = max(1, n // len(KINDS))
    rng = random.Random(seed)
    buckets: dict[str, list[str]] = {k: [] for k in KINDS}

    con = sqlite3.connect(f"file:{CORPUS}?mode=ro", uri=True)
    try:
        for (blob,) in con.execute(
                "select blob from chunks where doc_type='case_law'"):
            b = json.loads(blob)
            kind = (b.get("paragraph_type") or "").strip()
            text = " ".join((b.get("full_text") or "").split())
            if kind not in buckets or len(text) < 80:
                continue
            # RESERVOIR, so the sample is not the first N rows of the file --
            # which would be one court, one year, one clerk's formatting.
            seen = buckets[kind]
            if len(seen) < per:
                seen.append(text)
            elif rng.random() < per / 1000:
                seen[rng.randrange(per)] = text
            if all(len(v) >= per for v in buckets.values()):
                break
    finally:
        con.close()

    out = [(t, k) for k, texts in buckets.items() for t in texts]
    rng.shuffle(out)
    return out



IDENTITY = ROOT / ".nm" / "identity.db"


def top_cited_cases(n: int, court: str) -> list[str]:
    """The `n` most-cited case ids for a court, from the identity index.

    A PREFIX MATCH ON THE COURT. The corpus spells the Supreme Court two
    ways -- 887,582 paragraphs under "Supreme Court of India" and 24 under
    "Supreme Court". Equality would drop one of them silently, which is
    the wrong-index defect this project has already paid for three times:
    a zero from the wrong key reads exactly like absence.
    """
    if not IDENTITY.exists():
        sys.exit(f"the identity index is not built: {IDENTITY}")
    con = sqlite3.connect(f"file:{IDENTITY}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select case_id from cases where court like ? and cited_by is not null "
            "order by cited_by desc limit ?", (court + "%", n)).fetchall()
    finally:
        con.close()
    return [r[0] for r in rows]


def sample_from_cases(case_ids: list[str], per_class: int,
                      seed: int = 7) -> list[tuple[str, str]]:
    """Labelled paragraphs drawn ONLY from the given cases.

    Stratified by label like the uniform sampler, because the question is
    still about the classes and not about the cases -- the cases only
    decide WHICH paragraphs are worth arguing over.

    `case_id` IS A REAL COLUMN, so this filters in SQL rather than parsing
    a million blobs to throw most of them away.
    """
    rng = random.Random(seed)
    buckets: dict[str, list[str]] = {k: [] for k in KINDS}
    con = sqlite3.connect(f"file:{CORPUS}?mode=ro", uri=True)
    try:
        marks = ",".join("?" * len(case_ids))
        cur = con.execute(
            f"select blob from chunks where doc_type='case_law' "
            f"and case_id in ({marks})", case_ids)
        for (blob,) in cur:
            b = json.loads(blob)
            kind = (b.get("paragraph_type") or "").strip()
            text = " ".join((b.get("full_text") or "").split())
            if kind not in buckets or len(text) < 80:
                continue
            seen = buckets[kind]
            if len(seen) < per_class:
                seen.append(text)
            elif rng.random() < per_class / 500:
                seen[rng.randrange(per_class)] = text
    finally:
        con.close()

    thin = [k for k, v in buckets.items() if len(v) < per_class]
    if thin:
        # SAID, NOT PADDED. A class these judgments barely contain is a
        # fact about them -- heavily-cited authorities carry little
        # `headnote` -- and quietly topping it up from elsewhere would
        # make the sample something other than what it claims to be.
        print("    thin classes in this set: "
              + ", ".join(f"{k}={len(buckets[k])}" for k in thin))

    out = [(t, k) for k, texts in buckets.items() for t in texts]
    rng.shuffle(out)
    return out

def report(pairs: list[tuple[str, str]], predicted: list[str]) -> int:
    """The confusion matrix, and the two numbers that decide the question."""
    truth = [k for _, k in pairs]
    # STRICT: a prediction list shorter than the truth list would
    # silently score only the rows that happened to line up, and
    # report a clean matrix for a run that dropped half its answers.
    matrix: Counter = Counter(zip(truth, predicted, strict=True))
    totals = Counter(truth)

    print()
    print("  CONFUSION MATRIX — rows are the corpus's label, columns the read")
    print()
    width = max(len(k) for k in KINDS) + 2
    print(" " * (width + 2) + "".join(f"{k[:9]:>11}" for k in KINDS))
    for actual in KINDS:
        if not totals[actual]:
            continue
        row = "".join(f"{matrix[(actual, p)]:>11}" for p in KINDS)
        print(f"  {actual:<{width}}{row}   (n={totals[actual]})")

    print()
    dangerous = sum(matrix[("arguments", p)] for p in ATTRIBUTABLE)
    n_args = totals["arguments"]
    rate = dangerous / n_args if n_args else 0.0
    print(f"  arguments read as attributable   {dangerous}/{n_args} = "
          f"{rate:.1%}   (ceiling {MAX_ARGUMENTS_AS_ATTRIBUTABLE:.1%})")

    lost = sum(matrix[(a, p)] for a in ATTRIBUTABLE
               for p in KINDS if p not in ATTRIBUTABLE)
    n_attr = sum(totals[a] for a in ATTRIBUTABLE)
    lost_rate = lost / n_attr if n_attr else 0.0
    print(f"  attributable lost to other       {lost}/{n_attr} = "
          f"{lost_rate:.1%}   (ceiling {MAX_ATTRIBUTABLE_LOST:.1%})")
    print()

    ok = True
    if rate > MAX_ARGUMENTS_AS_ATTRIBUTABLE:
        print("  REFUSED. Counsel's submission is being attributed to the")
        print("  court above the ceiling. This classifier must not ingest.")
        ok = False
    if lost_rate > MAX_ATTRIBUTABLE_LOST:
        print("  REFUSED. Too much genuine holding is being dropped; the")
        print("  corpus would grow while getting less useful.")
        ok = False
    if ok:
        print("  Both ceilings held on this sample. THAT IS NOT PERMISSION —")
        print("  it is one measured sample, and the ceiling on the dangerous")
        print("  direction is what to re-measure when the prompt changes.")
    return 0 if ok else 1


# ------------------------------------------------------------------- pages ---

_BLOCK = re.compile(r"<(?:p|pre)[^>]*>(.*?)</(?:p|pre)>", re.S)
_TAG = re.compile(r"<[^>]+>")


def paragraphs(html: str) -> list[str]:
    """The judgment's paragraphs, from the page's own markup.

    STRUCTURAL, NOT INFERRED. Indian Kanoon marks paragraphs with <p> and
    <pre>, so nothing here guesses where one ends — which matters, because a
    classifier fed half a paragraph is being asked a different question from
    the one the corpus labels answer.
    """
    start = html.find('<div class="judgments"')
    body = html[start:] if start >= 0 else html
    out = []
    for block in _BLOCK.findall(body):
        text = " ".join(_TAG.sub(" ", block).split())
        if len(text) >= 80:
            out.append(text)
    return out


def staged() -> list[Path]:
    return sorted(STAGING.rglob("IKWEB_*.json"))


def plan() -> None:
    files = staged()
    total = 0
    for f in files:
        try:
            total += len(paragraphs(json.loads(
                f.read_text(encoding="utf8"))["html"]))
        except Exception:                                     # noqa: BLE001
            continue
    print()
    print("  PLAN — no model call is made by this command.")
    print()
    print(f"    staged judgments      {len(files)}")
    print(f"    paragraphs to classify {total}")
    print(f"    one call each          {total} calls")
    print()
    print("  RUN `--eval --sample 200` FIRST. It costs 200 calls and measures")
    print("  the error rate against the corpus's own 1,015,780 labelled")
    print("  paragraphs. Classifying without that spends the larger number to")
    print("  find out what the smaller one would have told you.")
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", action="store_true",
                    help="measure against the corpus's own labels")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()

    if args.plan or not (args.eval or args.run):
        plan()
        if not (args.eval or args.run):
            print("  Nothing was run. --eval measures; --run classifies.")
        return 0

    if args.eval:
        pairs = sample_labelled(args.sample)
        print(f"  sampled {len(pairs)} labelled paragraphs from the corpus")
        print(f"  spending {len(pairs)} model calls")
        print()
        predicted = []
        for i, (text, _truth) in enumerate(pairs, 1):
            predicted.append(classify(text))
            if i % 25 == 0:
                print(f"    {i}/{len(pairs)}", flush=True)
        return report(pairs, predicted)

    print("  --run is refused until --eval has been run and its ceilings held.")
    print("  Ingesting on an unmeasured classifier is the one thing this file")
    print("  exists to prevent.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
