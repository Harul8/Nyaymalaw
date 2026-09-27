"""A conversational preparation door, never an approval or external effect.

Reuse the actual drafting export digest and consequential-action state owner.
The only appended record is PREPARED. The atomic loop writer owns persistence;
an alleged destination must be exact supplied words, not a fabricated endpoint.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace

from nm.act import action, drafting
from nm.act.action_contracts import ActionProposal
from nm.legal_brain.orchestrate.loop_contracts import digest
from nm.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    PreparedToolResult,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.legal_brain.reason.source_writes import _parent
from nm.shared.json_values import same_json_value
from nm.shared.model_port import require_schema
from nm.work_the_file.file_mutation_contracts import FileMutation, neutral
from nm.work_the_file.original_instruction import read_original_instruction

NAME = "propose_action"
VERSION = "owned-prepared-action-only-v1"
SCHEMA = object_schema(
    {
        "package_id": {"type": "string", "minLength": 1},
        "destination_quote": {"type": ["string", "null"]},
    }
)


def _derive(matter, actor, turn_id, args):
    require_schema(args, SCHEMA)
    if matter.advocate_id != actor or len(args["package_id"]) > 200:
        raise ToolRefused("The exact current drafting file is not available to this actor.")
    parent = _parent(matter, turn_id, actor)
    call = parent.events[-1].payload["call"]
    original = read_original_instruction(parent)
    if (
        call["name"] != NAME
        or not same_json_value(call["arguments"], args)
        or original.state != "recorded"
    ):
        raise ToolRefused(
            "The preparation needs its actual reserved call and supplied instruction."
        )
    # Whole-file only: a package has no typed dispute membership. A narrowed
    # scope cannot acquire another dispute's drafting work by naming its ID.
    if parent.events[0].payload.get("scope_identity") != digest({"requested_issue_ids": []}):
        raise ToolRefused("An action package needs an explicitly admitted whole-file scope.")
    quote = args["destination_quote"]
    if quote is not None and (not quote.strip() or len(quote) > 2000 or quote not in original.text):
        raise ToolRefused("A proposed destination must be exact supplied words or remain absent.")
    packages = drafting.rows(matter)
    if (
        not same_json_value(
            [drafting.as_dict(row) for row in packages], neutral(matter.drafting_packages)
        )
        or len({row.package_id for row in packages}) != len(packages)
        or any(row.matter_id != matter.id for row in packages)
    ):
        raise ToolRefused("The complete drafting-package population is unreadable or ambiguous.")
    package = drafting.find(packages, args["package_id"])
    if package is None:
        raise ToolRefused("No exact owned drafting package was supplied.")
    previous = action.rows(matter)
    if (
        not same_json_value(
            [action.as_dict(row) for row in previous], neutral(matter.action_proposals)
        )
        or len({row.proposal_id for row in previous}) != len(previous)
        or any(row.matter_id != matter.id for row in previous)
    ):
        raise ToolRefused("The complete action-proposal population cannot be reconstructed.")
    exported = drafting.export(package)  # Pure content projection, not a delivery/export act.
    proposal_id = (
        "ap_"
        + digest(
            {"parent": parent.identity.fingerprint, "call": call["call_id"], "arguments": args}
        )[:32]
    )
    if any(row.proposal_id == proposal_id for row in previous):
        raise ToolRefused("This exact preparation is already recorded.")
    made = ActionProposal(
        proposal_id,
        matter.id,
        package.package_id,
        actor=actor,
        authority="",
        object=package.document,
        destination=quote or "",
        content_digest=exported["content_digest"],
    )
    after = replace(matter, action_proposals=(*matter.action_proposals, action.as_dict(made)))
    detail = {
        "proposal": action.projection(made),
        "package_version": package.version,
        "package_identity": digest(drafting.as_dict(package)),
        "instruction_identity": original.text_identity,
        "content_digest": exported["content_digest"],
        "destination_attributed": quote,
        "prepared_by": "product",
        "advocate_approval": False,
        "authority_established": False,
        "dispatched": False,
        "released": False,
        "client_ready": False,
    }
    return after, detail


@dataclass(frozen=True)
class PreparedActionMutation(FileMutation):
    turn_id: str
    proposed: dict

    def __post_init__(self):
        object.__setattr__(self, "proposed", deepcopy(self.proposed))
        super().__post_init__()

    def _validate_projection(self):
        # Reconstruct the entire one-field projection, not a model-authored
        # delta or permission flag. No base fact/thread field can change.
        if (
            self.before.id != self.after.id
            or self.before.version != self.after.version
            or self.after.advocate_id != self.advocate_id
        ):
            raise ToolRefused("A preparation cannot choose ownership or transaction version.")
        expected, _ = _derive(self.before, self.advocate_id, self.turn_id, self.proposed)
        if not same_json_value(
            neutral(asdict(expected)), neutral(asdict(self.after))
        ) or self.changed_fields != ("action_proposals",):
            raise ToolRefused("The prepared action differs from its exact existing content owners.")

    def _digest(self):
        return digest({"base": super()._digest(), "turn": self.turn_id, "proposed": self.proposed})


def action_proposal_tools(store):
    def prepare(args, context):
        matter = store.load(context.identity.matter_id)
        if (
            matter is None
            or matter.advocate_id != context.identity.advocate_id
            or matter.version != context.current_version
        ):
            raise ToolRefused("The current whole drafting file is not admitted to this context.")
        parent = _parent(matter, context.identity.turn_id, context.identity.advocate_id)
        original = read_original_instruction(parent)
        if parent.identity != context.identity or original.text != context.original_message:
            raise ToolRefused("The supplied instruction differs from this exact reserved turn.")
        after, detail = _derive(
            matter, context.identity.advocate_id, context.identity.turn_id, args
        )
        mutation = PreparedActionMutation(
            matter, after, matter.advocate_id, context.identity.turn_id, args
        )
        result = ToolEnvelope(
            NAME,
            VERSION,
            ToolKind.MATTER,
            ToolOutcome.RESULTS,
            Availability.AVAILABLE,
            Assessment.NOT_ASSESSED,
            {
                "matter_id": matter.id,
                "matter_version": matter.version,
                "snapshot": mutation.identity,
            },
            detail,
            "Preparation only. No authority, approval, export, filing or sending was granted.",
        )
        return PreparedToolResult(result, mutation)

    from nm.act.tool_propose_action import build_tool

    return (build_tool(prepare=prepare),)
