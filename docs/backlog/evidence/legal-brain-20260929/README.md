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
| Short reader (one prompt, one call, one repair) | 33 | — | 1 | 8 |
| Short reader, first prompt tuning | 34 | — | 0 | 8 |
| Short reader, second prompt tuning | 34 | — | 0 | 8 |
| Second tuning, seven held-out golden-set briefs (35 readings) | 31 | — | 0 | 4 |
| Last tuning, the seven tuning briefs | 36 | — | 0 | 6 |
| Last tuning, the seven held-out golden-set briefs (35 readings) | 35 | — | 0 | 0 |

The first explicit definition reduced silent errors in this sample but did not
improve total correct readings: 26/42 correct or correct with a question, against
30/42 for the act-anchored reader. The later layered version (SHA256
`65fce619833e3769d70ecba4fd6acb4beca2cf3d165a4555d5a962dc8863e16e`) was never
measured; it was replaced on 30 September 2026 by the owner's decision to keep the
reader short and fix misses in the prompt.

The short reader (SHA256
`492767b2792ae7c1495dd68c3ffc0ea4e95ec675a2563274b0cc98bfde3e1703`) has no second
reading, so "correct, asked" does not arise. Its eight silent errors are two
patterns: the Farah Begum push during the gate argument joined to the gate dispute
(six of seven Farah readings), and the one-dispute flat purchase split into the
agreement and the refund of money paid (two of seven). Kavita was right on all six
readings. The one said error was refused twice for placing a sentence both in a
dispute and in the background. The prompt was then tuned for those three patterns
(SHA256 `4bbb6ed26abdf3cceab0bd21e8c51abf4ac3a6d23843f8540dc030d9022b2f63`).

The first tuning fixed the sentence placed twice. Still wrong: the push joined to
the gate on five of seven Farah readings, right on every reading without the
advocate's "First/Second/Third"; the flat purchase split where the advocate asked
for the flat "or" the money back, on two of seven; and one reversed Kavita reading
took the instructions, now first, as shared background. A second tuning addresses
those three in general words (SHA256
`ada5e2d22a925b180ac49b6a3da01263eb12751072f0fc55c103f21a224219e4`). The seven
briefs are now the set the prompt was tuned on, so a result on them alone no longer
shows that the prompt generalises.

The second tuning was therefore also read on seven HELD-OUT briefs, written from
golden-set scenarios GS-08, GS-09, GS-10, GS-12, GS-13, GS-14 and GS-16 after the
tuning, with the golden set's expected disputes. Every held-out separation was right
on every reading; the four misses are one pattern, the one-debt brief's closing
question ("Can we still sue for the money?") placed in the dispute rather than the
instructions. On the tuning briefs Kavita was right on all seven readings; Farah's
push stayed joined to the gate on four of seven, and the flat purchase split on four
of seven, its payment sentence made a dispute of its own.

The owner then chose one last tuning and to stop after it: a question the advocate
asks is an instruction even when it names the claim; a payment made under an
agreement is a fact of that agreement's dispute. That version (SHA256
`99aee1fa400ebddf377e2b49f028e0423b3812a52ec5e26aeadb4d8de6aa701b`) read the held-out
briefs right on all 35 readings. On the tuning briefs the flat purchase split once
in seven; Farah's push, numbered together with the gate by the advocate, stayed
joined to it on five of seven. That remaining error is visible to the advocate in
the numbered list of disputes and is corrected in a sentence. Tuning stopped here.

Full local reports are retained outside Git because they reproduce named saved
matter sentences and IDs. Their SHA256 values identify the exact local evidence:

| Local report | SHA256 |
|---|---|
| `dispute-separation-labels.json` | `2c5224b2963545ef2dc42a9760f8b1f71d32c95e1dd56fee48218d5c737153f9` |
| `dispute-separation-labels-20260929T181909281111Z.json` | `fe144bf42eaba36a6524a30a9077c00b7213f207fc96d616a8b60cccb8459744` |
| `dispute-separation-labels-20260929T183803537721Z.json` | `ac0ac66f0c0d95da292bd634ce792e0ef7ca1926aa0bce9a6ae087841d3c6b7f` |
| `dispute-separation-labels-20260929T185023079587Z.json` | `b5251e6086f77fe03a1183779492f26dbfec6deca188cd5d99c613b66b3e1f9b` |
| `dispute-separation-labels-20260930T050224719728Z.json` | `f73008304f36b551b4d1b129bafe8aeaa3af4d6181d690fcfad3dece4b6b8498` |
| `dispute-separation-labels-20260930T051231155640Z.json` | `d17a142c24634b5086af22de8c6e52181db435f64fe7d5cecd26e3e5d205c558` |
| `dispute-separation-labels-20260930T053150686509Z.json` | `2b0aca9180028ccf4c2f7645c3bfd2eb032bf06adb82f3e02faf93f4ccb8cc43` |
| `dispute-separation-labels-20260930T054524176820Z.json` | `46b880fd6e9c9ded29b5a614a6e5eb5b5438302ab4c7a9af779103368383a540` |

The original baseline charged USD 0.164347; the three later runs charged USD
0.318056, USD 0.187740 and USD 0.205745 respectively under separate USD 1 caps.
The first later total includes a reserved or unknown charge from a failed TLS
attempt. The short-reader runs charged USD 0.071814, USD 0.071990, USD 0.129900 and USD 0.131100. Spend ledgers and mutable
checkpoints are local run state and are also kept outside Git.
