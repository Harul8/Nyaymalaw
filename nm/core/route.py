"""B1 — is this a matter, or is it not? READ, never counted.

WHAT THIS REPLACES, AND WHY IT HAD TO GO
------------------------------------------
`classify_route` decided on two keyword lists and TWO LENGTH RULES, while its
own docstring said *"Route on WHAT THE MESSAGE DISCLOSES, never on its
length."* It routed on length three lines below that sentence:

    len(text.split()) <= 3   -> not a matter
    len(text.split()) > 25   -> a full brief

LENGTH CARRIES NO INFORMATION HERE. "bail" is one word and a case fact. "he
absconded" is two words and a case fact. "hi" is one word and a greeting. A
count cannot tell them apart because the difference is meaning, and the
advocate said so: *let the model decide whether it is a greeting or a case
fact — the model knows the context.*

The keyword lists went with them. `_MATTER_SIGNALS` was twenty-seven nouns and
`_ABOUT_NM` five phrases, and B-124 had already been the measured cost of the
second one: "what can you do about the limitation period on this suit?" was
routed away as a question about the product. Composing the two lists fixed
those four phrasings and left the shape — whichever list is consulted first
still decides, on words somebody thought of.

This is B-031 again, in a different place. The posture reader was a closed
list of ten exact phrases and `we act for the workman` was not among them; the
fix was a read, not a longer list.

WHAT A MISS COSTS, AND WHICH WAY IT FAILS
-------------------------------------------
The asymmetry is already recorded in `classify_route` and it is unchanged: *a
full workup on a question wastes time, while a matter read as a greeting is
negligent.* So `cannot_tell` resolves to MATTER, and a model that is
unavailable resolves to MATTER — the route never fails toward silence.

THREE STATES, and the third is the one that matters: `cannot_tell` is not
`not_matter`. A model that cannot decide has not decided, and the difference
is what stops a shrug from discarding a brief.
"""
from __future__ import annotations

from dataclasses import dataclass

from nm.domain.answer import Mode, Route
from nm.domain.text import snippet
from nm.domain.traceability import implements

#: THE THREE THINGS A ROUTE SAYS, named so nothing has to match prose.
#:
#: `_non_matter_answer` chose between two answers by re-running a keyword
#: list over the message -- the last `_ABOUT_NM` use in the product, and
#: a second place deciding a question the read had already decided.
ABOUT_THE_PRODUCT = "Taking this as a question about what I do, not a matter."
NOTHING_YET = "No matter disclosed yet."
A_MATTER = "Taking this as a matter. Say if I have that wrong."

#: A QUESTION OF LAW WITH NO MATTER BEHIND IT. Answered from the corpus,
#: cited, and nothing is written to any file -- which is the whole
#: difference between this and `matter`.
A_QUESTION_OF_LAW = "Taking this as a question of law, not a matter."

ROUTE_SCHEMA: dict = {
    "x-nm-read": "route",
    "type": "object",
    "properties": {
        "discloses": {
            "type": "string",
            "enum": ["matter", "question_of_law", "about_the_product",
                     "neither", "cannot_tell"],
            "description": (
                "`matter` if the message says ANYTHING about a real dispute, "
                "client, document, deadline or step -- however few words. "
                "'bail', 'he absconded' and 'ex parte decree' are all "
                "matters. `question_of_law` if it asks what the law IS, "
                "with no client and no dispute behind it -- 'what is the "
                "limitation for a suit for possession'. `about_the_product` "
                "if it asks what YOU can do. `neither` ONLY for a greeting "
                "or an acknowledgement with no content: 'hi', 'thanks', "
                "'ok'. `cannot_tell` if you genuinely cannot tell."),
        },
        "depth": {
            "type": "string",
            "enum": ["a_question", "a_full_brief"],
            "description": (
                "`a_full_brief` when the advocate has set out a situation for "
                "you to work through. `a_question` when they are asking one "
                "thing. NOT a judgement about length -- a long question is a "
                "question and a short brief is a brief."),
        },
        "why": {
            "type": "string",
            "description": "One clause, shown to the advocate.",
        },
    },
    "required": ["discloses", "depth", "why"],
    "additionalProperties": False,
}

SYSTEM = (
    "You read the first line an Indian advocate types and decide ONE thing: "
    "does it disclose a matter?\n\n"
    "A MATTER IS ANYTHING ABOUT A REAL DISPUTE -- a client, a document, a "
    "date, a court, a step taken or needed. LENGTH IS NOT EVIDENCE. 'bail' is "
    "a matter. 'he absconded' is a matter. 'ex parte decree' is a matter. A "
    "long paragraph about what you can do is not.\n\n"
    "`neither` IS ONLY FOR AN EMPTY COURTESY: 'hi', 'thanks', 'ok'. If the "
    "words carry any fact about a case, it is a matter.\n\n"
    "A QUESTION OF LAW IS ITS OWN ANSWER, and it is not a matter. 'What is "
    "the limitation for a suit for possession of immovable property' names "
    "no client, no opponent and no dates -- it asks what the law says. An "
    "advocate asking that wants the provision and the citation, not to be "
    "asked whose side they are on. If the same sentence carries a client or "
    "a fact, it is a MATTER.\n\n"
    "BUT AN OPEN FILE WINS. If anything is already on the file, a question "
    "about the law is a question about THAT MATTER and the answer is "
    "`matter` -- an advocate four turns into a possession suit who asks 'what "
    "is the limitation' is asking about their suit, not about the law in "
    "the abstract. `question_of_law` is for a question that arrives with no "
    "file behind it.\n\n"
    "IF YOU CANNOT TELL, SAY SO. Do not guess `neither` -- a matter read as a "
    "greeting is discarded, and nothing is written to the file."
)


@dataclass(frozen=True)
class ReadRoute:
    """THREE STATES. `examined=False` is not `neither`."""

    route: Route = Route.MATTER
    mode: Mode = Mode.SHORT_QUESTION
    statement: str = A_MATTER
    examined: bool = False
    why: str = ""

    @property
    def state(self) -> str:
        if not self.examined:
            return "not_assessed"
        return self.route.value


@implements("B1")
def build_prompt(message: str, on_file: str = ""):
    """The message, and WHAT IS ALREADY ON THE FILE.

    AN OPEN MATTER IS PART OF WHAT THE TURN DISCLOSES. An advocate five turns
    in who types "and now?" has not stopped talking about their matter, and
    the old rule discarded that turn: NON_MATTER writes nothing to any file.

    THE FILE ITSELF, NOT A FLAG. This took a boolean -- "a matter is already
    open" -- which is the fact without the content, and
    `test_every_model_call_in_a_turn_receives_the_file` caught it the moment
    the route became a read. "And what is the limitation on that?" is plainly
    a follow-up about the Kukatpally possession suit if you can see the file,
    and an unanswerable fragment if you cannot.

    The account is CONTEXT here and nothing is quoted from it, so no
    `Quotable` is needed: this read produces a verdict, not a span.
    """
    from nm.ports.model import Prompt

    context = (f"ALREADY ON THIS FILE. A message that continues any of this is "
               f"part of the matter, however short:\n{on_file.strip()[:1200]}"
               f"\n\n" if on_file.strip() else "")
    return Prompt(system=SYSTEM,
                  user=f"{context}The advocate typed:\n{message.strip()[:1200]}")


@implements("B1")
def interpret(said: dict) -> ReadRoute:
    """The model's answer, or the SAFE DIRECTION.

    Every refusal lands on MATTER, and that is the asymmetry `classify_route`
    has recorded since it was written: a full workup on a question wastes
    time, while a matter read as a greeting is negligent -- and NON_MATTER
    writes nothing to any file, so the turn is gone.
    """
    if not isinstance(said, dict):
        return ReadRoute(examined=False, why="the route read returned no object")

    raw = str(said.get("discloses") or "").strip().lower()
    depth = str(said.get("depth") or "").strip().lower()
    why = snippet(said.get("why"), 160)
    mode = Mode.FULL_BRIEF if depth == "a_full_brief" else Mode.SHORT_QUESTION

    if raw == "about_the_product":
        return ReadRoute(
            route=Route.NON_MATTER, mode=Mode.SHORT_QUESTION,
            statement=ABOUT_THE_PRODUCT,
            examined=True, why=why)

    if raw == "question_of_law":
        # NON_MATTER, SO NOTHING IS WRITTEN TO ANY FILE -- and answered from
        # the corpus rather than with a blurb. GS-02's counterexample is
        # `impose matter apparatus; ask for parties, posture or documents`,
        # so this must not route to MATTER; and its requirement is a cited
        # answer, so it must not stop at NOTHING_YET either.
        return ReadRoute(
            route=Route.NON_MATTER, mode=Mode.SHORT_QUESTION,
            statement=A_QUESTION_OF_LAW, examined=True, why=why)

    if raw == "neither":
        # A COURTESY ON AN OPEN MATTER IS STILL A COURTESY, and answering it
        # with a workup is the other half of the same rudeness.
        return ReadRoute(
            route=Route.NON_MATTER, mode=Mode.SHORT_QUESTION,
            statement=NOTHING_YET, examined=True, why=why)

    # `matter`, `cannot_tell`, and anything out of vocabulary. AMBIGUITY
    # RESOLVES TO MATTER -- stated here rather than left to the enum, because
    # it is the whole safety argument.
    return ReadRoute(
        route=Route.MATTER, mode=mode,
        statement=A_MATTER,
        examined=True, why=why)
