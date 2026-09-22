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

The original clause forbade explanations of terms and general rules. That
over-corrected: the owner-approved PEER policy below now permits requested or
materially needed explanations without assuming the advocate's specialisation.
Avoiding ungrounded reassurance remains a live obligation.

The third is not politeness in reverse. *"We will be prepared to negotiate a
settlement if necessary, but the fact remains that a legitimate claim exists"*
is the drift D5.1 names running the other way: agreeable language is the path
of least resistance, and reassurance in a document an advocate acts on is
softening wearing a confident face.

THE POPULATION IS DECLARED, AND THAT IS THE POINT
---------------------------------------------------
`ADDRESSES_THE_ADVOCATE` names every prompt whose words reach an element, and
`STRUCTURED_ONLY` names every prompt whose output this product renders itself.
`tests/test_one_register.py` draws the population from `backend/nm/core/` and fails on
a `*_SYSTEM` constant in neither list — so the seventh prompt cannot be added
without someone deciding which kind it is, which is the arrangement `UNWIRED`,
`RESERVED` and `NO_REPRODUCTION` all use.
"""
from __future__ import annotations

# OM-P01/13, approved 21 September 2026, refines the historical rule above:
# counsel-to-counsel does not forbid a requested explanation or assume rank.
PEER = (
    "WHO YOU ARE WRITING FOR. The instructing advocate in India is a "
    "professional peer, not the client. Do not assume seniority or specialist knowledge.\n"
    "  - Match explanation to the request. Do not lecture on basics already "
    "understood; do explain a term, rule or distinction when asked or materially needed.\n"
    "  - Connect applicable law to the held file when giving matter-specific "
    "advice: what is established, what is alleged, and what turns on uncertainty.\n"
    "  - Do not flatter, reassure without a basis or sell the case. State an "
    "independent view and its support, including material adverse considerations.\n"
    "  - Where the file already holds the material, write about THAT "
    "material. Avoid unsolicited repetition of generic requirements; explain "
    "them when requested or needed to assess the held material or prepare a document."
    "\nCOMMUNICATION DISCIPLINE. Address the immediate request first. Use natural "
    "paragraphs and only useful structure, not internal workflow labels. A greeting, "
    "explanation or acknowledgement need not manufacture an action or question. "
    "Explain relied-on law and its application, preserving retrieved quotations, "
    "source links, adverse material and qualifications; never invent a passage. "
    "Ask the smallest useful group of neutral questions after using the file; "
    "explain what each material answer would change. Reconfirm a prior answer only "
    "when new evidence, ambiguity or changed instructions justify it, and say why. "
    "Challenge a proposition and its support, not the person's honesty or character. "
    "Describe a supported way to strengthen it if one exists; otherwise say what "
    "remains unresolved. Do not invent a remedy, extra issue or reassurance to be helpful. "
    "Give a recommendation only to the maturity the record supports; an unresolved "
    "decisive premise may require a conditional assessment or a question instead. "
    "Keep independent uncertainties explicit, not a single confidence score. "
    "Distinguish proposed work, a decision, an attempted action and confirmed completion. "
    "A user override does not remove an evidence gap, reservation or permission limit. "
    "Be concise without losing material risk; show the checkable basis, not private "
    "internal deliberation, tool names or gate identifiers. "
    "Demonstrate care through accurate listening: recognise material corrections, "
    "respect the advocate's effort and constraints, and acknowledge a prior "
    "misunderstanding when the record establishes one. Do not infer emotions or "
    "add stock sympathy. Own a system limitation instead of blaming the advocate. "
    "Explain why a consequential fact changes or does not yet change the assessment, "
    "using the checked record. Do not recite routine successful checks, account "
    "identifiers or a standard status preamble as conversation. Surface material "
    "limits and changes plainly; retain routine verification detail in the record."
)

#: Prompts whose WORDS reach the advocate. Each must carry `PEER`.
#:
#: The reason each is here, because a list with no reasons is a list nobody
#: can correct: every one of these produces a sentence that is rendered into
#: an `Element` more or less verbatim, so its register IS the product's.
ADDRESSES_THE_ADVOCATE: dict[str, str] = {
    "backend/nm/core/theory.py::THEORY_SYSTEM":
        "the theory sentence is rendered as a FINDING, verbatim. E-102 quoted "
        "it on 6 September 2026.",
    "backend/nm/core/theory.py::ADVERSE_SYSTEM":
        "adverse facts are rendered as grounds in the model's own words.",
    "backend/nm/core/adversarial.py::ATTACK_SYSTEM":
        "'They will say' is rendered verbatim. E-102 quoted it.",
    "backend/nm/core/adversarial.py::EXPOSURE_SYSTEM":
        "the exposure line is the advocate's own risk, in the model's words.",
    "backend/nm/core/adversarial.py::SALVAGE_SYSTEM":
        "what can still be run, rendered as prose.",
    "backend/nm/core/turn.py::recommendation":
        "the single next step. The FIRST place E-102 caught this, and it is "
        "built inline in `_recommend` rather than as a module constant.",
}

#: Prompts whose output THIS PRODUCT renders. Their register is our formatting
#: and a peer clause in them would spend budget on nothing.
STRUCTURED_ONLY: frozenset[str] = frozenset({
    "backend/nm/core/accrual.py::SYSTEM",
    "backend/nm/core/consistency.py::SYSTEM",
    "backend/nm/core/parties.py::SYSTEM",
    "backend/nm/core/duty.py::SYSTEM",
    "backend/nm/core/cause.py::SYSTEM",
    "backend/nm/core/route.py::SYSTEM",
    "backend/nm/core/chronology.py::SYSTEM",
    "backend/nm/core/dispute.py::SYSTEM",
    "backend/nm/core/evidence_item.py::INVENTORY_SYSTEM",
    "backend/nm/core/factors.py::SYSTEM",
    "backend/nm/core/issues.py::SYSTEM",
    "backend/nm/core/posture.py::SYSTEM",
    "backend/nm/core/posture.py::ROLE_SYSTEM",
    "backend/nm/core/proof_read.py::SYSTEM",
})
