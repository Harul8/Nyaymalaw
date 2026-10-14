# Owner review links

Pages waiting for the owner's review. The Advocate build plan in
`docs/Nyaymalaw_Implementation_Plan.xlsx` remains the work queue; each entry
names the plan row it belongs to. Review pages are private to the owner.

## Judgment Authority Review (SEQ.3), added 14 October 2026

- Link: https://claude.ai/artifact/Qfu48xKNTdSH5R9NvqiHKv
- What: 22 legal questions from three test matters (GS-12 land and assault,
  DC03 arrest, DC13 talaq and maintenance) with 175 judgment paragraphs to mark
  as "Would rely on it", "Background only" or "Not relevant", plus a box per
  question for an expected authority that is missing.
- Why: a key of named judgments cannot judge the model's pick, because a
  different but sound authority scores as a miss. The marks measure, for the
  search's first six results and for the model's pick separately, how much is
  usable authority and how much is noise.
- Blind by design: paragraphs appear in a fixed neutral order; "Show how each
  was found" reveals the search place, the model's pick and its reason.
- After marking: ask Claude to read the marks back from the page's store and
  report the comparison.
- Source data: `outputs/decomposition-scratch/runs/jpick-inputs-top20.json` and
  `outputs/decomposition-scratch/runs/jpick-v1.json` (scratch, not tracked).

Also for the owner to confirm with this review: the proposed corrected judgment
key, `outputs/decomposition-scratch/judgment-key-v2.json` (scratch, not tracked).
