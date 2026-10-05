"""Interpret each new message against a complete, attributed conversation.

This module decides what work a message requests. It does not perform legal
research, admit a matter fact, issue advice, or authorise an action.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Literal

from nm.brain.checked import checked_read
from nm.shared.model_port import (
    ContextOverflow,
    ModelPort,
    Prompt,
    SchemaViolation,
    Tier,
    estimate_tokens,
)


class IncompleteConversation(ValueError):
    """A previous turn cannot be read or the context has an unexplained gap."""


@dataclass(frozen=True)
class Message:
    turn_id: str
    role: Literal["advocate", "nm"]
    text: str

    def __post_init__(self) -> None:
        if not self.turn_id or not self.turn_id.strip() or not self.text.strip():
            raise ValueError("A conversation message needs an identity and its words")
        if self.role not in ("advocate", "nm"):
            raise ValueError("Unknown conversation speaker")


@dataclass(frozen=True)
class Conversation:
    messages: tuple[Message, ...]
    current_matter_id: str | None = None
    current_work: str = ""
    open_disputes: tuple[dict, ...] = ()
    open_material: tuple[dict, ...] = ()
    complete: bool = True
    progress: dict | None = None
    research_coverage: tuple[dict, ...] = ()

    def __post_init__(self) -> None:
        if len({(item.turn_id, item.role) for item in self.messages}) != len(self.messages):
            raise ValueError("A turn cannot have two messages from the same speaker")


@dataclass(frozen=True)
class WorkItem:
    request: str
    relation: Literal["continues", "changes", "aside", "new", "uncertain"]
    matter_scope: Literal["current", "proposed", "none", "other", "uncertain"]
    priority: Literal["ordinary", "urgent"]
    next_step: Literal["answer", "legal_work", "clarify"]
    reply: str = ""
    clarification: str = ""
    intent: Literal["request", "contribution"] = "request"
    research_question: str = ""
    response_basis: Literal["conversation_record", "legal_authority"] | None = None

    def __post_init__(self) -> None:
        # Older in-process callers supplied the question without a separate
        # basis. Fresh interpreter output must state and validate both below.
        if self.response_basis is None:
            object.__setattr__(self, "response_basis", "legal_authority"
                               if self.research_question else "conversation_record")


@dataclass(frozen=True)
class OpeningCandidate:
    ready: bool
    title: str
    summary: str
    party_name: str = ""
    subject: str = ""

    def title_parts(self) -> tuple[str, str]:
        """Expose structured parts while reading older in-process candidates."""
        if self.subject:
            return self.party_name, self.subject
        prefix, separator, subject = self.title.partition(":")
        if separator:
            return prefix.strip(), subject.strip()
        return "", self.title


def opening_from_parts(party_name: str, subject: str,
                       summary: str) -> OpeningCandidate:
    party_name, subject, summary = (value.strip() for value in
                                    (party_name, subject, summary))
    title = f"{party_name}: {subject}" if party_name else subject
    return OpeningCandidate(True, title, summary, party_name, subject)


@dataclass(frozen=True)
class TurnPlan:
    items: tuple[WorkItem, ...]
    active_work_after: str
    opening: OpeningCandidate
    material_review: bool


_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["items", "opening", "material_review"],
    "properties": {
        "items": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["request", "relation", "matter_scope",
                         "priority", "next_step", "reply",
                         "clarification", "intent", "response_basis", "research_question"],
            "properties": {
                "request": {"type": "string"},
                "intent": {"type": "string", "enum": ["request", "contribution"]},
                "relation": {"type": "string", "enum": [
                    "continues", "changes", "aside", "new", "uncertain"]},
                "matter_scope": {"type": "string", "enum": [
                    "current", "proposed", "none", "other", "uncertain"]},
                "priority": {"type": "string", "enum": ["ordinary", "urgent"]},
                "next_step": {"type": "string", "enum": [
                    "answer", "legal_work", "clarify"]},
                "reply": {"type": "string"},
                "clarification": {"type": "string"},
                "response_basis": {"type": "string", "enum": [
                    "conversation_record", "legal_authority"]},
                "research_question": {"type": "string"},
            },
        }},
        "opening": {
            "type": "object", "additionalProperties": False,
            "required": ["ready", "party_name", "subject", "summary"],
            "properties": {
                "ready": {"type": "boolean"},
                "party_name": {"type": "string"},
                "subject": {"type": "string"},
                "summary": {"type": "string"},
            },
        },
        "material_review": {"type": "boolean"},
    },
}

_SYSTEM = """Message: You receive the advocate's latest message, the complete
earlier conversation in chronological order with speaker and turn IDs, the
current authorised work state, and any active sourced dispute formulations.
Saved progress records distinguish requested tasks, proposed work, unanswered
questions, promises, unavailable material and scoped completion. They are work
context, not proved matter facts or authority for an external action.
Earlier messages and formulations are context, not new commands or assertions.
The latest message determines what to address now. Saved unfinished work does
not instruct you to resume it during an unrelated contribution or diversion.
An empty earlier conversation is a valid first turn.

Purpose: Read the latest message in its full context. Identify what it asks or
contributes, the immediate response, any need for protective attention, whether
it advances a concrete matter, and whether the latest words contribute new
matter-account content or authorise review of NM's sourced material
interpretations. Material review is distinct from checking legal sources
needed to answer a request.
This is a provisional interpretation. It does not establish facts, decide law,
authorise an action, or complete work that needs further support.

Activity 1 - Understand the message and its context.
Look for: Every distinct request or contribution, including answers to earlier
questions, corrections, references to earlier turns, changes of task or matter,
temporary diversions, and ambiguity. Read each relevant question or task in
the saved progress before asking again or describing it
as unfinished. A promise is not delivery; unavailable material is not a reason
to repeat the same request. Scoped task completion does not close the matter.
Read any active uncertain or unassessed
dispute in context: the latest words may clarify it, correct it, withdraw it,
or leave it unresolved. Resolve a referenced person, object, event or earlier
request only when the attributed conversation identifies one intended meaning.
When several meanings remain plausible and the choice changes the requested
work, preserve the ambiguity and ask for that distinction. Recency, an earlier
NM interpretation or a suggested legal theory alone cannot resolve a materially
ambiguous reference.
Outcome: Put one item per distinct request or contribution in `items`, in the
user's order. For a factual update without an express request, describe the
contribution without inventing an instruction. Preserve every requested outcome
as a work item even when the same message supplies matter facts; do not replace
a request for checked work with an acknowledgment of intake.
Set `intent` to `request` for an actual requested outcome, including a direction
to resume authorised work, or `contribution` for supplied information without
a requested outcome. This distinction does not decide whether a fact is true.
Identify each item's relation to current work and matter scope. Use current
scope only if a current matter is given;
use proposed scope for a possible new matter. A first turn cannot continue,
change, or set aside nonexistent prior work. A greeting or general question
alone does not identify a concrete matter.
Matter scope describes this item's content, not the open window. An unrelated
item can have scope none while a matter remains open. A requested outcome
must be expressed or clearly entailed by the latest words; unfinished work
alone is not a request to resume it.

Activity 2 - Prioritise and respond.
Look for: Whether delay calls for immediate protective attention; whether a
useful response is possible now, substantive legal or document work remains,
or one missing distinction prevents useful work. Judge the work needed for
each request on its own, including a first message or an aside to active work.
Outcome: Set each item's priority to urgent only for immediate protective need.
Choose `answer` only for a conversational or other nonlegal reply that needs
no legal source, document reading, or consequential inference. Route any
requested substantive legal proposition, legal research, drafting, review,
strategy, assessment of disputed facts, or advice about material to gather to
`legal_work`, regardless of its relation to the current matter. A general
legal question and a legal aside also need `legal_work`. Do not satisfy a
legal request by placing a legal conclusion in an `answer` item.
An `answer` may concern the current or proposed matter when its result needs
only the attributed conversation record. Every reply goes through the separate
writer and independent reviewer; this provisional text cannot establish a
record change or completed work. Select matter scope from the item's actual
subject and decide material review separately from the response route.
For an `answer`, be brief and address the latest contribution. Do not supply
an automatic matter recap or task menu unless it is asked for or needed.
For `legal_work`, write a short, specific interim `reply` that identifies the
requested outcome and attributes only facts expressly reported by the
advocate. State plainly that the requested assessment or work is pending
source checking. Do not supply legal propositions, classify disputed conduct,
infer missing facts, recommend records to gather, or claim a source supports
anything before the separate reading. Ask at most one consequential question
only if its answer is needed to proceed at all. Give urgent needs priority.
Do not substitute a stock acknowledgment, claim checking has occurred, or
promise later autonomous work. Choose `clarify` when a missing distinction
prevents a dependable response to this item, including an unresolved reference
on which advice would depend. Ask only for that distinction; describe the
request and question without inserting a guessed referent. Independent items
can still proceed. Attribute unverified facts to the advocate. Do not invent support,
assert unsupported law, or present unfinished work as complete. Fill `reply`
for `answer` and `legal_work` and set `clarification` to an empty string for
both. For `clarify`, put the question in `clarification` and set `reply` to
an empty string. These fields are mutually exclusive. Saved progress owns
active work; do not replace it with a routing summary. When an
uncertain or unassessed dispute remains relevant to the latest requested activity, ask for
its consequential missing distinction if needed. Do not interrupt a
diversion to pursue it, or treat an identified dispute as a proved fact.
An absence of a new substantive instruction or unfinished earlier work alone
does not prevent a useful conversational response. Do not choose `clarify`
merely to ask which task to resume. Respond naturally to the immediate
contribution when it needs no legal work, and let the advocate steer further
work without requiring a new instruction to acknowledge their message.

Activity 3 - Decide whether a matter can be opened.
Look for: An identifiable concrete matter supported by the advocate's words
across the conversation, which the latest message advances or confirms. A
supplied `current_matter_id` means the matter is already open; no new opening
decision is needed. Identify a named person or entity on the advocate's side
    only when the name and the person's or entity's role on the advocate's
side are clear from the advocate's account. If several clients are named,
choose one clearly representative name for the heading; the title is not
a party register. Do not infer matter facts merely because a topic is
mentioned.
Outcome: Set `opening.ready` true only with a concise subject and summary
grounded in the advocate's words when there is no current matter. Describe
the overall subject and posture without asserting a count or completed legal
assessment. Put exactly one named client-side person or entity in
`opening.party_name` when their name and role are clear, even when several
are represented. Put only the existing concise matter heading in
`opening.subject`. The server will join the fields as `party_name: subject`.
Do not include an opposing party name or `vs` in `party_name`. If the
client-side name or role is absent or uncertain, leave `party_name` empty;
never invent a name.
For an already open matter, or when the latest message does not support an
opening, set `ready` false and leave `party_name`, `subject`, and `summary`
empty. This is a proposal, not admission of the account as fact.

Activity 4 - Decide whether sourced material proposals need reading.
Look for: New facts, disputes, positions, objectives, records, procedure,
timing, risk, uncertainty, or corrections concerning a concrete or possible
matter. A request may contain such content. Separately identify authorised
work to reconcile NM's saved dispute or material formulations with the
attributed account. That work may require reading without any new factual
assertion. Distinguish review of the record's formulation from using the
existing record to answer, summarise, research or perform other work.
Outcome: `material_review` controls the sourced dispute and material readers,
not legal research or response source checking. Set it true for new or changed
matter-account content, including an uncertain or hypothetical contribution,
and for relevant authorised review of NM's sourced material interpretations.
The latest review request authorises examination; the original advocate words
remain the evidentiary basis. It does not change the advocate's account, prove
facts, or authorise a different matter's records to be revised. The separate
readers decide whether any sourced proposal or repair is justified; do not
invent a change merely because review was requested.
Set it false for work that only uses the existing record, including a recap,
repeat, explanation, legal-source enquiry or continuation with no new material
and no authorised reconciliation of its formulations. A greeting or pure
diversion does not require material review. Referring to existing material
alone is neither a new account contribution nor authority to revise it.
A requested NM activity changes work progress, not the client's real-world
objective or factual account; distinguish those layers.

Activity 5 - Define the needed legal-source enquiry.
Purpose: Decide whether the immediate requested outcome needs legal authority
and, only then, identify the substantive legal question to research. Do not
enlarge the requested outcome or decide its answer.
Look for: What the latest words actually ask or contribute in the full
conversation. Distinguish legal propositions needed for the result from work
that only reconstructs, summarises, compares or clarifies the attributed
account and NM's formulations. Both can use `legal_work` for checked
attribution and work progress; that route does not itself require a new
legal-source enquiry. The matter's legal subject, a missing research result
or unfinished broader legal work does not change a factual deliverable into
a request for law. Decide the current result's evidence basis before considering
any saved research question for reuse. Saved research questions are NM search
proposals, not authority that the current outcome requires law; historical
task or process wording cannot determine the basis of a new or resumed request.
Automatic gathering research on dispute material has a separate owner and
remains independent of this decision.
Preserve distinct requested factual and legal outcomes as separate work items
when either can usefully proceed without the other. Each has its own scope
and sufficiency; completing a factual result does not complete the wider
legal work. Do not split a single legal decision into a purported factual
answer to avoid the authority that decision needs.
Outcome: Set `response_basis` to `conversation_record` when this item's result
needs only attributed conversation or record reconciliation. Its
`research_question` must be empty, even if `material_review` is true or earlier
legal research remains unfinished. This basis does not permit a legal claim
without checked sources. Set `response_basis` to `legal_authority` only when
the requested result needs a substantive legal proposition, assessment, remedy
or strategy. This requires `legal_work` and a nonempty `research_question`:
state a concise self-contained substantive legal question identifying the
authority needed. Never put task, process or deliverable instructions in this
field; extract the needed legal question from a broader work request.
Compare saved research's purpose and scope with that legal question. Copy its
exact question only for the same substantive enquiry; the server decides
whether coverage is current and reusable. A coverage label or earlier NM
explanation is not a legal passage. Preserve jurisdiction and timing only
when supplied; expose missing scope rather than inventing it. Keep factual
premises attributed and faithful to the whole account, including sequence,
dates, negation and uncertainty. A research question is a search hypothesis,
not a finding; do not infer causation, onset or changed legal status. Leave
the field empty and use `conversation_record` for answer/clarify. Do not
invent a dispute to support a general legal question.

Outcome: Return only the declared JSON object with `items`,
`opening`, and `material_review`. Do not alter any matter
record."""


# Only unmistakable multi-name syntax is rejected mechanically. A firm name
# can itself contain "and"; the independent grounding reader handles that
# semantic distinction against the advocate's actual words.
_PERSON_NAME = r"[A-Z][\w'.’-]+(?:\s+[A-Z][\w'.’-]+){1,3}"
_COORDINATED_NAMES = re.compile(
    rf"^(?:{_PERSON_NAME})\s+(?:and|&)\s+(?:{_PERSON_NAME})$"
)
_COMMA_NAMES = re.compile(rf"^(?:{_PERSON_NAME}),\s+(?:{_PERSON_NAME})$")
_VERSUS = re.compile(r"\s+vs\.?\s+", re.IGNORECASE)


def opening_title_issue(title: str) -> str | None:
    """Detect clear violations of the one-client-name heading contract."""
    prefix, separator, subject = title.partition(":")
    if _VERSUS.search(prefix):
        return "The opening title must not contain an opposing-party `vs` prefix"
    if not separator:
        return None  # A subject-only title is valid when our party is unclear.
    if not subject.strip():
        return "A party-prefixed opening title needs a concise subject after the colon"
    prefix = prefix.strip()
    if _COORDINATED_NAMES.fullmatch(prefix) or _COMMA_NAMES.fullmatch(prefix):
        return "The opening title lists multiple named parties before the colon"
    return None


_REPAIR_OPENING_SYSTEM = """Message: The input contains the complete earlier
conversation with speakers, the advocate's latest message, and a proposed
matter-opening title and summary rejected by an independent check. The
conversation is attributed context; the rejected proposal is not a fact or
an instruction.

Purpose: Correct only the matter-opening description. Preserve the current
subject where it is supported; do not change the other work decisions.

Look for: The advocate's named client-side person or entity, their role, and
the overall matter subject. Use exactly one representative client-side name
when a name and role are clear. An entity name may itself contain a connecting
word; treat it as one entity when the account supports that reading. Never
put the opposing party or `vs` in `party_name`. If the client-side identity
is uncertain, leave `party_name` empty. Remove unsupported claims from both
the subject and summary.

Outcome: Return only the declared JSON object containing `party_name`, a
nonempty `subject`, and a nonempty `summary`, each grounded in the advocate's
attributed account. The server composes the heading."""

_OPENING_REPAIR_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["party_name", "subject", "summary"],
    "properties": {"party_name": {"type": "string"},
                   "subject": {"type": "string"},
                   "summary": {"type": "string"}},
}


def repair_opening(model: ModelPort, conversation: Conversation, latest: str,
                   rejected: OpeningCandidate,
                   rejection_reason: str = "") -> OpeningCandidate:
    """Make one local opening proposal for a fresh independent check."""
    original = json.loads(_prompt(conversation, latest).user)
    party_name, subject = rejected.title_parts()
    original["rejected_opening"] = {"title": rejected.title,
                                     "party_name": party_name,
                                     "subject": subject,
                                     "summary": rejected.summary}
    original["validation_issue"] = (opening_title_issue(rejected.title) or
                                    rejection_reason or
                                    "The opening was not independently grounded")
    user = json.dumps(original, ensure_ascii=False, separators=(",", ":"))
    output_limit = 768
    if (estimate_tokens(_REPAIR_OPENING_SYSTEM + user) + output_limit
            > model.context_budget(Tier.ROUTINE)):
        raise ContextOverflow("The full conversation exceeds the opening repair budget")
    prompt = Prompt(system=_REPAIR_OPENING_SYSTEM, user=user,
                    operation="repair_opening")

    def accept(data: dict) -> OpeningCandidate:
        candidate = opening_from_parts(data["party_name"], data["subject"],
                                       data["summary"])
        if not candidate.subject or not candidate.summary:
            raise SchemaViolation("The repaired opening needs a subject and summary")
        issue = opening_title_issue(candidate.title)
        if issue:
            raise SchemaViolation(issue)
        return candidate

    return checked_read(model, prompt, _OPENING_REPAIR_SCHEMA,
                        output_limit, accept)


def _prompt(conversation: Conversation, latest: str) -> Prompt:
    if not conversation.complete:
        raise IncompleteConversation("The earlier conversation is incomplete")
    if not latest.strip():
        raise ValueError("The latest message is empty")
    payload = {
        "earlier_conversation": [
            {"turn_id": item.turn_id, "role": item.role, "text": item.text}
            for item in conversation.messages
        ],
        "current_matter_id": conversation.current_matter_id,
        "current_work": conversation.current_work,
        "saved_progress": conversation.progress,
        "saved_research_coverage": list(conversation.research_coverage),
        "open_disputes": [
            {key: row.get(key) for key in (
                "id", "label", "statement", "identification", "clarification")}
            for row in conversation.open_disputes
        ],
        "latest_message": latest,
    }
    return Prompt(user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                  system=_SYSTEM, operation="interpret_conversation")


def interpret(model: ModelPort, conversation: Conversation, latest: str) -> TurnPlan:
    """Read every saved turn, or refuse rather than silently losing context."""
    prompt = _prompt(conversation, latest)
    schema = deepcopy(_SCHEMA)
    decisions = schema["properties"]["items"]["items"]["properties"]
    if not conversation.current_matter_id:
        decisions["matter_scope"]["enum"].remove("current")
    else:
        opening = schema["properties"]["opening"]["properties"]
        opening["ready"]["enum"] = [False]
        opening["party_name"]["enum"] = [""]
        opening["subject"]["enum"] = [""]
        opening["summary"]["enum"] = [""]
    if not (conversation.messages or conversation.current_work
            or conversation.current_matter_id):
        decisions["relation"]["enum"] = ["new", "uncertain"]
    # Leave room for the schema response. The model port also checks its own
    # exact request budget; this preflight prevents an accidental partial read.
    output_limit = max(2048, min(4096, estimate_tokens(latest) * 4))
    if (estimate_tokens(prompt.user + (prompt.system or "")) + output_limit
            > model.context_budget(Tier.JUDGE)):
        raise ContextOverflow("The full conversation exceeds this model's context budget")
    return checked_read(model, prompt, schema, output_limit,
                        lambda data: _turn_plan(data, conversation), tier=Tier.JUDGE)


def _turn_plan(data: dict, conversation: Conversation) -> TurnPlan:
    rows = data.get("items")
    if not isinstance(rows, list) or not rows:
        raise SchemaViolation("The interpretation needs at least one work item")
    has_prior_context = bool(conversation.messages or conversation.current_work
                             or conversation.current_matter_id)
    items = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise SchemaViolation("A work item is not an object")
        request = row.get("request")
        reply = row.get("reply")
        clarification = row.get("clarification")
        research_question = row.get("research_question")
        response_basis = row.get("response_basis")
        if (not isinstance(request, str) or not request.strip()
                or not isinstance(reply, str) or not isinstance(clarification, str)
                or not isinstance(research_question, str)):
            raise SchemaViolation("A work item lacks a usable request")
        if response_basis not in ("conversation_record", "legal_authority"):
            raise SchemaViolation(
                f"items[{index}].response_basis must state conversation_record or legal_authority "
                "for the current requested result")
        if response_basis == "conversation_record" and research_question.strip():
            raise SchemaViolation(
                f"items[{index}]: response_basis conversation_record requires an empty "
                "research_question. Do not inherit a saved legal enquiry for factual work. "
                "If the requested result actually needs law, correct response_basis and state "
                "the substantive legal question instead")
        if response_basis == "legal_authority" and (
                row.get("next_step") != "legal_work" or not research_question.strip()):
            raise SchemaViolation(
                f"items[{index}]: response_basis legal_authority requires legal_work and a "
                "nonempty substantive research_question. Otherwise select conversation_record "
                "and leave research_question empty")
        if row.get("next_step") in ("answer", "legal_work") and not reply.strip():
            raise SchemaViolation("A response needs reply text for its chosen step")
        if row.get("next_step") == "clarify" and reply.strip():
            raise SchemaViolation(
                "For next_step=clarify, set reply to an empty string and put "
                "the question only in clarification")
        if row.get("next_step") == "clarify" and not clarification.strip():
            raise SchemaViolation("A clarification needs a question")
        if row.get("next_step") != "clarify" and clarification.strip():
            raise SchemaViolation(
                "For next_step=answer or legal_work, set clarification to an "
                "empty string; use reply for the response")
        try:
            item = WorkItem(request=request,
                            relation=row["relation"], matter_scope=row["matter_scope"],
                            priority=row["priority"],
                            next_step=row["next_step"],
                            reply=reply,
                            clarification=clarification, intent=row["intent"],
                            research_question=research_question.strip(),
                            response_basis=response_basis)
        except (KeyError, TypeError) as exc:
            raise SchemaViolation("A work item is incomplete") from exc
        if (item.relation not in ("continues", "changes", "aside", "new", "uncertain")
                or item.matter_scope not in ("current", "proposed", "none", "other", "uncertain")
                or item.priority not in ("ordinary", "urgent")
                or item.next_step not in ("answer", "legal_work", "clarify")
                or item.intent not in ("request", "contribution")):
            raise SchemaViolation("A work item has an unknown decision")
        if not has_prior_context and item.relation in ("continues", "changes", "aside"):
            raise SchemaViolation("A first message cannot refer to prior work")
        if item.matter_scope == "current" and not conversation.current_matter_id:
            raise SchemaViolation("There is no current matter")
        if item.next_step != "legal_work" and item.research_question:
            raise SchemaViolation("Only legal_work may propose a research question")
        items.append(item)
    candidate = data.get("opening")
    if not isinstance(candidate, dict):
        raise SchemaViolation("The opening candidate is missing")
    ready = candidate.get("ready")
    party_name = candidate.get("party_name")
    subject = candidate.get("subject")
    summary = candidate.get("summary")
    if (type(ready) is not bool or not all(isinstance(value, str)
                                           for value in (party_name, subject,
                                                         summary))):
        raise SchemaViolation("The opening candidate is malformed")
    if ready:
        if (not subject.strip() or not summary.strip() or not any(
                    item.matter_scope == "proposed" for item in items)):
            raise SchemaViolation("The opening candidate lacks current-message support")
    elif party_name or subject or summary:
        raise SchemaViolation("An unready opening cannot carry matter details")
    material_review = data.get("material_review")
    if type(material_review) is not bool:
        raise SchemaViolation("The material-reading decision is missing")
    return TurnPlan(items=tuple(items), active_work_after=conversation.current_work,
                    opening=(opening_from_parts(party_name, subject, summary)
                             if ready else OpeningCandidate(False, "", "")),
                    material_review=material_review)
