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
`tests/test_one_register.py` draws the population from `nm/core/` and fails on
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

#: HOW THE REPLY IS WRITTEN, as guidance and never as a template. Owner, 28
#: September 2026: "give guiding principles to the model ... not hard
#: restrictions that would push the model to come up with formalic, templated
#: responses". The FIRM part is what a check enforces on the words shown
#: (`grounding.verify_reply`, the composer's coverage check); everything else is
#: the craft of a careful advocate, stated with its reason so it can be weighed.
#: No word counts, no required sections, no fixed sentences.
REPLY_CRAFT = (
    "WHAT IS FIRM -- each is checked on the words you write:\n"
    "  - Use only the checked work, the file and the retrieved passages you are given. "
    "Law, facts or authorities from anywhere else cannot be checked and the reply "
    "would not be released.\n"
    "  - Put in double quotation marks only words copied exactly from a passage or "
    "from the advocate's own message. A paraphrase in quotation marks is read as "
    "the source's words.\n"
    "  - Name a provision or a judgment only as the checked work names it.\n"
    "  - Every item marked MUST CONVEY reaches the advocate with its meaning intact: "
    "you may rephrase it, combine it or place it where it matters, but not drop, "
    "soften or strengthen it. Keep every date it states. If an item is best left in "
    "its own words -- a limit that names what could not be retrieved, for one -- "
    "carry it verbatim.\n"
    "  - Keep who said what: the advocate's instructions, what a document records, "
    "what the other side alleges and what is only inferred are different things.\n"
    "HOW A CAREFUL ADVOCATE WOULD WRITE IT -- guidance, weighed against the request:\n"
    "  - Start where the request is. If the work is blocked, say first what you need "
    "and why, because nothing else moves until it is answered. If they asked what to "
    "do, the step usually comes first. If they asked for an explanation or an "
    "assessment, give the answer, then the reasons.\n"
    "  - Write in paragraphs, to a colleague. Use structure only when the content has "
    "that shape -- several disputes, a sequence of steps -- because headings on a "
    "short answer make it read like a form.\n"
    "  - Let the length follow what was asked and what the file holds. A narrow "
    "question deserves a narrow answer; a full work-up deserves the full picture.\n"
    "  - Weave limits and uncertainty in where they bear on a point, rather than "
    "stacking caveats at the end, so the advocate sees what each one qualifies.\n"
    "  - When a passage carries the point, quote the words that decide it and say how "
    "they apply to this file; do not reproduce a whole section when a clause does "
    "the work.\n"
    "  - Do not re-explain what the conversation has already covered unless it has "
    "changed or the advocate asks again; say what is new.\n"
    "  - Never show internal labels, item numbers, gate names or the workings of this "
    "product; the advocate needs the substance and its basis.\n"
)

#: Prompts whose WORDS reach the advocate. Each must carry `PEER`.
#:
#: The reason each is here, because a list with no reasons is a list nobody
#: can correct: every one of these produces a sentence that is rendered into
#: an `Element` more or less verbatim, so its register IS the product's.
ADDRESSES_THE_ADVOCATE: dict[str, str] = {
    "nm/legal_brain/reason/theory.py::THEORY_SYSTEM":
        "the theory sentence is rendered as a FINDING, verbatim. E-102 quoted "
        "it on 6 September 2026.",
    "nm/legal_brain/reason/theory.py::ADVERSE_SYSTEM":
        "adverse facts are rendered as grounds in the model's own words.",
    "nm/legal_brain/reason/adversarial.py::ATTACK_SYSTEM":
        "'They will say' is rendered verbatim. E-102 quoted it.",
    "nm/legal_brain/reason/adversarial.py::EXPOSURE_SYSTEM":
        "the exposure line is the advocate's own risk, in the model's words.",
    "nm/legal_brain/reason/adversarial.py::SALVAGE_SYSTEM":
        "what can still be run, rendered as prose.",
    "nm/legal_brain/orchestrate/turn.py::recommendation":
        "the single next step. The FIRST place E-102 caught this, and it is "
        "built inline in `_recommend` rather than as a module constant.",
    "nm/legal_brain/communicate/compose.py::COMPOSE_SYSTEM":
        "writes the whole reply the advocate reads, from the checked findings "
        "(LB-76); every word of it is theirs to read.",
}

#: Prompts whose output THIS PRODUCT renders. Their register is our formatting
#: and a peer clause in them would spend budget on nothing.
STRUCTURED_ONLY: frozenset[str] = frozenset({
    "nm/legal_brain/reason/accrual.py::SYSTEM",
    "nm/legal_brain/verify/consistency.py::SYSTEM",
    "nm/legal_brain/understand/parties.py::SYSTEM",
    "nm/legal_brain/verify/duty.py::SYSTEM",
    "nm/legal_brain/reason/cause.py::SYSTEM",
    "nm/legal_brain/understand/route.py::SYSTEM",
    "nm/work_the_file/chronology.py::SYSTEM",
    "nm/legal_brain/understand/dispute.py::SYSTEM",
    "nm/work_the_file/evidence_item.py::INVENTORY_SYSTEM",
    "nm/legal_brain/reason/factors.py::SYSTEM",
    "nm/legal_brain/reason/issues.py::SYSTEM",
    "nm/legal_brain/understand/posture.py::SYSTEM",
    "nm/legal_brain/understand/posture.py::ROLE_SYSTEM",
    "nm/legal_brain/reason/proof_read.py::SYSTEM",
    # Its evidence-based reasons are private structured review records, not
    # conversational prose. Actual dispatch isolates the captured package and
    # carries no author conversation or peer-writing task.
    "nm/legal_brain/verify/verifier.py::VERIFY_SYSTEM",
    # Independent exact-word interaction judgments are private structured
    # records, not author prose. The actual judge receives the current peer
    # clause as a review standard; its reasons are never shown as conversation.
    "nm/legal_brain/verify/interaction_review.py::INTERACTION_REVIEW_SYSTEM",
    # Says where a composed reply conveys each item; its sentences are copied
    # from the reply and checked against it, never shown as its own words.
    "nm/legal_brain/communicate/compose.py::COMPOSE_CHECK_SYSTEM",
})
