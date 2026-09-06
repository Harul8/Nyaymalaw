"""Who is being spoken to. One clause, and every prompt that addresses the
advocate carries it.

WHAT E-102 KEEPS CATCHING
--------------------------
The first verdict, 31 August 2026: *the register is instructional rather than
peer-to-peer.* The judge quoted the RECOMMENDATION. That was fixed by giving
the recommendation something specific to be about — the proof positions the
file already held — and by stopping the ground from reproducing the whole bare
Act.

The second verdict, 6 September 2026, on current code: STILL FAIL, and the
judge quoted somewhere else entirely.

    "The acknowledgment letter from 12 June 2024 is sufficient to reset the
     limitation period, as it explicitly admits the outstanding debt…"
    "Under the applicable law, a recovery action must be commenced within
     three years from the date the debt became due"
    "We will be prepared to negotiate a settlement if necessary, but the fact
     remains that a legitimate claim exists"

The first is the THEORY. The second and third are the ADVERSARIAL reads. Six
prompts in this product write prose an advocate reads, and exactly one of them
had a register rule.

That is CLAUDE.md §1 in its plainest form: stating a fix generally is not the
same as applying it generally, and the gap is where a year of whack-a-mole
lives. The fix was stated as "a peer register is a rule about subject matter"
and applied to one call site.

WHY A CLAUSE AND NOT AN ADJECTIVE
-----------------------------------
D5.1 is explicit that this family of problem needs A RULE, NOT A TONE
INSTRUCTION, and that a politeness layer bolted on is the kind of patch the
document forbids. "Sound like senior counsel" is an adjective; every prompt
here already said something like it and every one still failed.

So the clause says what may not be EXPLAINED, which is checkable by the writer
against their own sentence:

  * do not explain what a term means — they know
  * do not state the general rule, only what it does to THIS file
  * do not reassure

The third is not politeness in reverse. *"We will be prepared to negotiate a
settlement if necessary, but the fact remains that a legitimate claim exists"*
is the drift D5.1 names running the other way: agreeable language is the path
of least resistance, and reassurance in a document an advocate acts on is
softening wearing a confident face.

THE POPULATION IS DECLARED, AND THAT IS THE POINT
---------------------------------------------------
`ADDRESSES_THE_ADVOCATE` names every prompt whose words reach an element, and
`STRUCTURED_ONLY` names every prompt whose output this product renders itself.
`tests/test_one_register.py` draws the population from `nm/core/` and fails on
a `*_SYSTEM` constant in neither list — so the seventh prompt cannot be added
without someone deciding which kind it is, which is the arrangement `UNWIRED`,
`RESERVED` and `NO_REPRODUCTION` all use.
"""
from __future__ import annotations

PEER = (
    "WHO YOU ARE WRITING FOR. An instructing advocate in India, who has "
    "practised for years. Not their client, and not a student.\n"
    "  - Do not explain what a legal term means or what a section requires. "
    "They know, and the provisions are quoted elsewhere in this answer.\n"
    "  - Do not state the general rule. State only what it does to THIS "
    "file: what is established, what is not, and what turns on which.\n"
    "  - Do not reassure and do not sell the case. 'A legitimate claim "
    "exists' is not analysis, and confidence offered in place of a finding "
    "is the softening that loses cases.\n"
    "  - Where the file already holds the material, write about THAT "
    "material. What a compliant document would contain is the section "
    "restated, and they can read the section."
)

#: Prompts whose WORDS reach the advocate. Each must carry `PEER`.
#:
#: The reason each is here, because a list with no reasons is a list nobody
#: can correct: every one of these produces a sentence that is rendered into
#: an `Element` more or less verbatim, so its register IS the product's.
ADDRESSES_THE_ADVOCATE: dict[str, str] = {
    "nm/core/theory.py::THEORY_SYSTEM":
        "the theory sentence is rendered as a FINDING, verbatim. E-102 quoted "
        "it on 6 September 2026.",
    "nm/core/theory.py::ADVERSE_SYSTEM":
        "adverse facts are rendered as grounds in the model's own words.",
    "nm/core/adversarial.py::ATTACK_SYSTEM":
        "'They will say' is rendered verbatim. E-102 quoted it.",
    "nm/core/adversarial.py::EXPOSURE_SYSTEM":
        "the exposure line is the advocate's own risk, in the model's words.",
    "nm/core/adversarial.py::SALVAGE_SYSTEM":
        "what can still be run, rendered as prose.",
    "nm/core/turn.py::recommendation":
        "the single next step. The FIRST place E-102 caught this, and it is "
        "built inline in `_recommend` rather than as a module constant.",
}

#: Prompts whose output THIS PRODUCT renders. Their register is our formatting
#: and a peer clause in them would spend budget on nothing.
STRUCTURED_ONLY: frozenset[str] = frozenset({
    "nm/core/cause.py::SYSTEM",
    "nm/core/chronology.py::SYSTEM",
    "nm/core/dispute.py::SYSTEM",
    "nm/core/evidence_item.py::INVENTORY_SYSTEM",
    "nm/core/factors.py::SYSTEM",
    "nm/core/issues.py::SYSTEM",
    "nm/core/posture.py::SYSTEM",
    "nm/core/posture.py::ROLE_SYSTEM",
    "nm/core/proof_read.py::SYSTEM",
})
