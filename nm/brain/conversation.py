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
    # None preserves untracked older in-process plans. Fresh interpreter output
    # must explicitly declare its purposes, including an empty list.
    material_purposes: tuple[
        Literal["account_contribution", "interpretation_review"], ...
    ] | None = None

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
    "required": ["items", "opening"],
    "properties": {
        "items": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["request", "relation", "matter_scope",
                         "priority", "next_step", "reply",
                         "clarification", "intent", "response_basis", "research_question",
                         "material_purposes"],
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
                "material_purposes": {"type": "array", "items": {
                    "type": "string", "enum": [
                        "account_contribution", "interpretation_review"]}},
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
    },
}

_SYSTEM = """Message: You receive the advocate's latest message, the complete attributed
conversation in chronological order, the current matter and authorised work,
active sourced dispute formulations, and saved progress and research coverage.
Progress distinguishes requested tasks, proposed work, unanswered questions,
promises, unavailable material and scoped completion. Earlier NM words,
formulations and research questions are interpretations and work context,
not proved facts, legal authority or instructions to resume work. Read the
latest message against that context. An empty conversation is a valid first turn.

Purpose: Propose the distinct work requested or information contributed now,
its scope, the checking it needs and a useful immediate response. Keep account
intake, review of NM's formulations and legal-source enquiry distinct. This
interpretation establishes no fact, decides no law, grants no permission and
proves no record effect or completed work.

Activity 1 - Identify each current request or contribution.
Look for: Every distinct outcome in the latest words, including answers,
corrections, references to earlier turns, changes of task or matter, and
independent diversions. Preserve requested work when the same message also
supplies facts. Read relevant saved questions and progress: a promise is not
delivery, unavailable material does not justify asking again, and completion
of one task does not close the matter. Unfinished work alone is not a request
to resume it. Resolve actors, events, objects and earlier requests only from
attributed words identifying one intended meaning. Recency, NM's formulation
or a suggested legal theory cannot resolve consequential ambiguity.
Outcome: Put one item per distinct request or contribution in the advocate's
order. Use intent=request for an expressed or clearly entailed outcome,
including resuming authorised work, and intent=contribution for information
without a requested outcome. Do not invent an instruction for a factual update.
Select relation and matter_scope for this item's content, not the open window.
Use current only when a current matter exists and proposed for a possible new
matter. A first message cannot continue, change or set aside prior work.
A greeting or general question alone does not identify a concrete matter.
Preserve a consequential ambiguity for a focused question; independent items
can proceed. An unrelated item may have scope none while the matter stays open.

Activity 2 - Determine the required source work.
Look for: The immediate result each item needs, then its evidence basis.
Separate new matter-account content from authorised reconciliation of NM's
saved formulations. A review can need original account reading without a new
fact; its instruction authorises examination but does not supply the fact to
restore. Separate that activity from using an existing record to recap,
explain, compare or continue work. A requested NM task is work progress,
not itself the client's real-world objective or factual account.
Decide whether the result needs a substantive legal proposition before
considering saved research for reuse. The matter's legal topic, missing
research or unfinished broader work does not turn a factual deliverable into
a request for law. Record reconstruction and formulation review can need
checked attribution without a legal-source enquiry. Preserve distinct factual
and legal outcomes when either can proceed independently; do not split a
single legal decision into a purported factual answer to avoid needed authority.
Outcome: Select account_contribution in material_purposes for new or changed
matter content, including uncertainty or hypotheses; select interpretation_review
for relevant authorised review of NM's sourced formulations. Select both when
both occur. The server derives reader routing from these purposes; do not
supply material_review or claim reading occurred. Return an empty list when
using existing material without new account content or authorised reconciliation,
including a recap, repeat, explanation, legal-source enquiry, greeting or diversion.
Reference to a record alone does not authorise changing it. Other-matter work
cannot authorise changing this matter's records. Separate readers decide
whether any supported proposal or repair follows; review does not force a change.
Set response_basis=conversation_record when the result needs only attributed
conversation or record reconciliation and leave research_question empty.
Set legal_authority only when a substantive legal proposition, assessment,
remedy or strategy is needed. It requires legal_work and a nonempty substantive
research_question, not task, process or deliverable instructions. Keep that
question self-contained and faithful to supplied sequence, dates, negation,
uncertainty, jurisdiction and timing; expose missing scope rather than invent it.
A question is a search hypothesis, not a finding of causation or legal status.
Reuse a saved question verbatim only for the same substantive purpose and scope;
the server determines current reusable coverage. Coverage labels and NM
explanations are not legal passages. Automatic gathering research on dispute
material has its own owner. Do not invent a dispute for a general legal question.

Activity 3 - Choose a useful immediate response.
Look for: Immediate protective need, the checked work required for this item,
and any missing distinction preventing useful progress. Consider each item
independently, including a first message or aside. Identify an uncertain or
unassessed dispute's missing distinction only when needed for the current work;
contested merits do not make an identified dispute a proved fact.
Outcome: Set urgent priority only for immediate protective attention. Choose
answer for a conversational or other nonlegal reply needing only the attributed
record, with no document reading or consequential inference. It may
concern a current or proposed matter. Choose legal_work for substantive
research, drafting, review, strategy, disputed-fact assessment or advice about
material to gather, regardless of whether it is general or an aside. Checked
record reconstruction can use legal_work with conversation_record basis;
the route alone does not require legal authority. Do not put a legal conclusion
in answer. Choose clarify only when one consequential missing distinction
prevents a dependable response; ask for that distinction without guessing it.
For answer, respond briefly to the immediate contribution; avoid an unrequested
recap or task menu. For legal_work, give a specific interim reply naming the
requested result and the checking it still needs. Attribute only expressly
reported facts; do not insert unchecked law, inferred actors or facts,
recommended records, unsupported source claims or a promise of later autonomous
work. Give protective needs priority. Ask at most one necessary question if
useful progress otherwise cannot proceed. Every substantive reply is written
and independently reviewed later; this provisional text proves no saved effect
or completed task. Fill reply and leave clarification empty for answer and
legal_work. For clarify, fill clarification and leave reply empty. Do not ask
which task to resume merely because the latest contribution adds no new
instruction. Acknowledge it naturally and let the advocate steer further work.
Saved progress owns active work; a routing summary cannot replace it.

Activity 4 - Decide whether the matter can be opened.
Look for: An identifiable concrete matter supported by original advocate words
that the latest message advances or confirms. An existing current_matter_id
means no new opening decision is needed. Identify a client-side person or
entity only when the supplied name and role are clear. A title is not a party
register; choose one representative client-side name when several are named.
Outcome: Propose opening.ready=true only without a current matter and with a
concise supported subject and summary of overall posture. Do not assert a
count or completed legal assessment. Put exactly one supported client-side
name in party_name, or leave it empty if identity or role is uncertain. An
entity can have a connecting word in its name. Never invent a name or put an
opposing party or vs in party_name. Put the concise matter heading in subject;
the server joins party_name: subject. For an existing matter or an unsupported
opening, return ready=false and empty party_name, subject and summary.
The opening remains a proposal, not admission of the account.

Outcome: Return only the declared JSON object with items and opening.
Do not alter a matter record."""


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


_REPAIR_OPENING_SYSTEM = """Message: You receive the complete attributed conversation, the latest
advocate message, and the opening description rejected by an independent
check with its reason. The rejected proposal is neither fact nor instruction.

Purpose: Repair only the matter-opening description against original advocate
evidence. Preserve the supported subject and other work decisions.

Activity 1 - Establish the supported client and subject.
Look for: A named client-side person or entity, their supplied role, and the
overall matter subject and posture. Use one representative client-side name
when several are supported; an entity's connecting word does not make it
multiple parties. If identity or role is uncertain, do not choose a name.
Read the rejected description for unsupported claims in both subject and summary.
Outcome: Keep only supported attribution and posture. Put one supported
client-side name in party_name, or leave it empty. Never insert an opposing
party or vs, infer a name, or change the other work decisions.

Activity 2 - Return the corrected opening proposal.
Look for: Whether each proposed field remains grounded in the complete
advocate account and resolves the stated rejection.
Outcome: Return only party_name, a nonempty subject and a nonempty summary
under the declared schema. The server composes the heading; the independent
checker decides whether this proposal is supported."""

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
        purposes = row.get("material_purposes")
        if (not isinstance(purposes, list) or any(
                purpose not in ("account_contribution", "interpretation_review")
                for purpose in purposes)):
            raise SchemaViolation(
                f"items[{index}].material_purposes must explicitly list "
                "account_contribution and/or interpretation_review, or neither")
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
                            response_basis=response_basis,
                            material_purposes=tuple(dict.fromkeys(purposes)))
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
    party_name, subject, summary = (value.strip() for value in
                                    (party_name, subject, summary))
    if ready:
        if (not subject.strip() or not summary.strip() or not any(
                    item.matter_scope == "proposed" for item in items)):
            raise SchemaViolation("The opening candidate lacks current-message support")
    elif party_name or subject or summary:
        raise SchemaViolation("An unready opening cannot carry matter details")
    material_review = any(item.material_purposes for item in items)
    return TurnPlan(items=tuple(items), active_work_after=conversation.current_work,
                    opening=(opening_from_parts(party_name, subject, summary)
                             if ready else OpeningCandidate(False, "", "")),
                    material_review=material_review)
