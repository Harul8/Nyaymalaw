# Dispute-separation component measurement

Each run made 42 GPT-4.1 Mini readings of seven saved or constructed briefs and
their variants. The counts measure dispute placement in this component, not the
quality of a complete served legal answer. Labels for the constructed briefs are
drafts pending owner review.

| Reader | Correct | Correct, asked | Wrong, said | Wrong, silent |
|---|---:|---:|---:|---:|
| Initial offline reader | 23 | 0 | 15 | 4 |
| Source-unit reader | 16 | 6 | 20 | 0 |
| Act-anchored reader | 20 | 10 | 11 | 1 |
| First explicit dispute definition | 18 | 8 | 16 | 0 |

The first explicit definition reduced silent errors in this sample but did not
improve total correct readings: 26/42 correct or correct with a question, against
30/42 for the act-anchored reader. The subsequent definition, party-role and
independent-reading changes in `nm/legal_brain/understand/dispute.py` have SHA256
`65fce619833e3769d70ecba4fd6acb4beca2cf3d165a4555d5a962dc8863e16e` and
**have not had a paid measurement**. The selected offline test suite passed.

Full local reports are retained outside Git because they reproduce named saved
matter sentences and IDs. Their SHA256 values identify the exact local evidence:

| Local report | SHA256 |
|---|---|
| `dispute-separation-labels.json` | `2c5224b2963545ef2dc42a9760f8b1f71d32c95e1dd56fee48218d5c737153f9` |
| `dispute-separation-labels-20260929T181909281111Z.json` | `fe144bf42eaba36a6524a30a9077c00b7213f207fc96d616a8b60cccb8459744` |
| `dispute-separation-labels-20260929T183803537721Z.json` | `ac0ac66f0c0d95da292bd634ce792e0ef7ca1926aa0bce9a6ae087841d3c6b7f` |
| `dispute-separation-labels-20260929T185023079587Z.json` | `b5251e6086f77fe03a1183779492f26dbfec6deca188cd5d99c613b66b3e1f9b` |

The original baseline charged USD 0.164347; the three later runs charged USD
0.318056, USD 0.187740 and USD 0.205745 respectively under separate USD 1 caps.
The first later total includes a reserved or unknown charge from a failed TLS
attempt. Spend ledgers and mutable checkpoints are local run state and are also
kept outside Git.
