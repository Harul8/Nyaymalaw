"""Is the CORPUS wrong, or is the classifier? Only a third party can say.

    python pipeline/quality/audit_labels.py --worksheet          # sample, read, list disputes
    python pipeline/quality/audit_labels.py --score              # after you have adjudicated

WHY THIS EXISTS
-----------------
`pipeline/indexing/classify_paragraphs.py` measured a model against the corpus's own
`paragraph_type` labels and reported that counsel's submission was being read
as the court's words 50% of the time. Then five of those thirty `arguments`
paragraphs were read by eye, and every one was MISLABELLED BY THE CORPUS:

    "learned Attorney-General is correct and it was within the competence
     of Parliament ..."                              -- the court AGREEING
    "JUDGMENT: CRIMINAL APPELLATE JURISDICTION ..."  -- a case header
    "A similar opinion was expressed by Sir George Jessel in Fisher v.
     Keane ..."                                      -- the court citing
    "13. The directive principles of State policy ... cannot in any way
     override or abridge the fundamental rights"     -- Champakam Dorairajan

So the eval could not tell model error from label error, and neither can any
comparison of the two against each other. THE TIE NEEDS A THIRD PARTY, and the
only one available is the advocate.

WHY THE ANSWER MATTERS MORE THAN THE INGESTION IT CAME FROM
-------------------------------------------------------------
`paragraph_type` is the attributability model. 14.8% of the corpus is excluded
as counsel's submission at build time and again at use; `RG-04` requires >= 0.40
of case paragraphs classified attributable and is a BLOCKING release criterion.
If those labels are wrong at a material rate then two things are already true
of the corpus in production, today, with nothing to catch either:

  * a judgment whose ratio is labelled `arguments` is HELD AND NEVER QUOTED --
    an invisible gap, indistinguishable to an advocate from the corpus not
    holding the case at all;
  * a submission labelled `ratio` is quoted AS THE COURT'S OWN WORDS, and
    every downstream guard passes, because the retrieval is self-consistent.

The second is the one that reaches a judge.

WHAT THIS DOES, AND WHAT IT REFUSES TO DO
-------------------------------------------
It samples, it reads each paragraph with the model, and where the two DISAGREE
it writes the paragraph and both answers into a worksheet for the advocate to
adjudicate. It does not decide. It cannot: that is the whole finding.

ONLY DISAGREEMENTS ARE LISTED, and that bound is honest rather than
convenient: where the corpus and the model agree they may still both be wrong,
and this measurement cannot see that. It is stated in the report rather than
left for someone to assume otherwise.

THE SCARCE RESOURCE IS THE ADVOCATE'S TIME, NOT THE MODEL CALLS. So the
worksheet is capped and weighted towards the classes that decide the question
-- `arguments` and the three attributable ones -- rather than spread evenly
over classes nobody is arguing about.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT))
from assurance.common._console import utf8_console  # noqa: E402

utf8_console()

from pipeline.indexing.classify_paragraphs import (  # noqa: E402
    ATTRIBUTABLE,
    KINDS,
    classify,
    sample_from_cases,
    sample_labelled,
    top_cited_cases,
)

OUT = ROOT / ".nm" / "label_audit"
WORKSHEET = OUT / "worksheet.md"

#: How many disputes an advocate is asked to settle. THE BINDING CONSTRAINT.
#: Forty is roughly half an hour of reading; four hundred would be a better
#: measurement that nobody completes, which measures nothing.
MAX_DISPUTES = 40

#: Where the answer lives. A dispute about `headnote` costs a citation; a
#: dispute about `arguments` versus `ratio` is the one that reaches a judge.
PRIORITY = (*ATTRIBUTABLE, "arguments")

# `(\S*)` AND NOT `(\S+)`. A blank VERDICT line must MATCH and capture
# nothing -- the empty case is "not adjudicated", which is a state this
# reports. With `+` the line would not match at all, the item and
# verdict counts would differ, and `--score` would abort on exactly the
# worksheet somebody had partly filled in.
VERDICT = re.compile(r"^[ 	]*VERDICT:[ 	]*(\S*)", re.M)
ITEM = re.compile(r"^## (\d+)\.\s+corpus=(\w+)\s+model=(\w+)\s*$", re.M)


def worksheet(sample: int, cases: int, court: str) -> int:
    if cases:
        ids = top_cited_cases(cases, court)
        print(f"  {len(ids)} most-cited {court} judgments")
        pairs = sample_from_cases(ids, max(1, sample // len(KINDS)))
    else:
        pairs = sample_labelled(sample)
    print(f"  sampled {len(pairs)} labelled paragraphs")
    print(f"  spending {len(pairs)} model calls")
    print()

    disputes = []
    agreed = 0
    for i, (text, corpus) in enumerate(pairs, 1):
        read = classify(text)
        if read == corpus:
            agreed += 1
        else:
            disputes.append((text, corpus, read))
        if i % 25 == 0:
            print(f"    {i}/{len(pairs)}", flush=True)

    # WEIGHTED, NOT TRUNCATED. Taking the first forty would take them in
    # sample order, which is class order, which would spend the advocate's
    # attention on whichever class happened to come first.
    disputes.sort(key=lambda d: (d[1] not in PRIORITY and d[2] not in PRIORITY))
    chosen = disputes[:MAX_DISPUTES]

    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Which is right — the corpus, or the read?",
        "",
        f"{len(pairs)} paragraphs sampled. {agreed} agreed, "
        f"{len(disputes)} disagreed. {len(chosen)} listed below, weighted "
        f"towards the classes that decide attribution.",
        "",
        "For each, write the class YOU judge correct on the VERDICT line.",
        f"One of: {', '.join(KINDS)}.",
        "",
        "Write `both-wrong` if neither is right. Leave it blank to skip —",
        "a skipped item is reported as unadjudicated, never as agreement.",
        "",
        "---",
        "",
    ]
    for n, (text, corpus, read) in enumerate(chosen, 1):
        lines += [
            f"## {n}. corpus={corpus} model={read}",
            "",
            "> " + text[:1200].replace("\n", " "),
            "",
            "VERDICT: ",
            "",
        ]
    WORKSHEET.write_text("\n".join(lines), encoding="utf8")

    print()
    print(f"  {agreed}/{len(pairs)} agreed, {len(disputes)} disputed")
    print(f"  {len(chosen)} written to {WORKSHEET.relative_to(ROOT)}")
    print()
    print("  Fill in the VERDICT lines, then: python pipeline/quality/audit_labels.py "
          "--score")
    return 0


def score() -> int:
    if not WORKSHEET.exists():
        sys.exit(f"no worksheet at {WORKSHEET}. Run --worksheet first.")
    text = WORKSHEET.read_text(encoding="utf8")

    items = ITEM.findall(text)
    verdicts = [v.strip() for v in VERDICT.findall(text)]
    if len(items) != len(verdicts):
        sys.exit(f"{len(items)} items and {len(verdicts)} VERDICT lines — the "
                 f"worksheet has been edited in a way this cannot read.")

    corpus_wrong = model_wrong = both_wrong = unadjudicated = 0
    dangerous = Counter()
    for (_, corpus, model), verdict in zip(items, verdicts, strict=True):
        if not verdict:
            unadjudicated += 1
            continue
        if verdict == "both-wrong":
            both_wrong += 1
            continue
        if verdict not in KINDS:
            sys.exit(f"{verdict!r} is not one of {KINDS}")
        if verdict != corpus:
            corpus_wrong += 1
            # THE DIRECTION THAT REACHES A JUDGE: the corpus calls something
            # attributable that the advocate says is a submission.
            if corpus in ATTRIBUTABLE and verdict == "arguments":
                dangerous["corpus attributes a submission"] += 1
            if corpus == "arguments" and verdict in ATTRIBUTABLE:
                dangerous["corpus hides a holding"] += 1
        if verdict != model:
            model_wrong += 1

    judged = len(items) - unadjudicated
    print()
    print(f"  {judged} of {len(items)} adjudicated"
          + (f", {unadjudicated} left blank" if unadjudicated else ""))
    if not judged:
        print("  Nothing to report. A blank worksheet is not a clean result.")
        return 1
    print()
    print(f"    the CORPUS was wrong    {corpus_wrong}/{judged} = "
          f"{corpus_wrong / judged:.0%}")
    print(f"    the MODEL was wrong     {model_wrong}/{judged} = "
          f"{model_wrong / judged:.0%}")
    print(f"    both wrong              {both_wrong}/{judged}")
    print()
    if dangerous:
        print("  AND THE DIRECTIONS THAT MATTER:")
        for what, n in dangerous.most_common():
            print(f"    {what:<34} {n}")
        print()
    print("  THIS MEASURES DISAGREEMENTS ONLY. Where the corpus and the read")
    print("  agreed they may both be wrong, and nothing here can see that —")
    print("  so these rates are a floor on the corpus's error, not an")
    print("  estimate of it.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worksheet", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--sample", type=int, default=210)
    ap.add_argument("--cases", type=int, default=0,
                    help="draw only from the N most-cited judgments")
    ap.add_argument("--court", default="Supreme Court")
    args = ap.parse_args()

    if args.score:
        return score()
    if args.worksheet:
        return worksheet(args.sample, args.cases, args.court)

    print("  --worksheet samples and lists the disputes; --score reads your")
    print("  verdicts back. Neither is run by default: the first spends model")
    print("  calls and the second spends your afternoon.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
