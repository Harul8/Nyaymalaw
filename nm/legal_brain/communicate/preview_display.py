"""Sealed private display acknowledgements, never client delivery or truth.

The browser acknowledgement establishes only that an authenticated client said
it rendered an exact checked preview. It does not prove human attention. A
historical question stays historical even if its legal basis subsequently moves.
No unseen proposal is treated as an already delivered question.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from nm.legal_brain.orchestrate.loop import _budget_from
from nm.legal_brain.orchestrate.loop_contracts import LoopMode, StepKind, StopReason, digest
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.budget_contracts import Spend
from nm.shared.model_port import Usage
from nm.work_the_file.file_mutation_contracts import neutral

PURPOSE = "private_preview_display_acknowledgement_not_client_advice"


def scope_payload(scope):
    return {"approval_reference": scope.approval_reference, "advocate_id": scope.advocate_id,
            "matter_ids": sorted(scope.matter_ids), "mode": scope.mode.value}


def _record(matter, turn_id):
    rows = [row for row in matter.loop_records if row.identity.turn_id == turn_id]
    if (len(rows) != 1 or not rows[0].terminal
            or rows[0].identity.matter_id != matter.id
            or rows[0].identity.advocate_id != matter.advocate_id
            or rows[0].identity.mode is not LoopMode.SYNTHETIC):
        raise ReviewRefused("A preview display lacks its exact private saved parent/proof")
    return rows[0]


def interaction_text(parent, proof):
    """Reconstruct the actual historical reviewed words, not an authored flag."""
    from nm.legal_brain.verify.brain_finalization import CheckRead
    from nm.legal_brain.verify.interaction_review import (
        COMMUNICATION_PROTOCOL_VERSIONS,
        communication_contract,
        communication_requires_work,
    )
    from nm.legal_brain.verify.interaction_subject import InteractionSubject

    stop = parent.events[-1].payload
    reason = StopReason(stop["reason"])
    if reason not in (StopReason.QUESTION, StopReason.CONVERSATION):
        raise ReviewRefused("The displayed record is not an interaction subject")
    start, checked = proof.events[0].payload, proof.events[-1].payload
    contracts = [(version, communication_contract(version))
                 for version in COMMUNICATION_PROTOCOL_VERSIONS]
    matches = [(version, contract) for version, contract in contracts
               if proof.identity.turn_id == f"{parent.identity.turn_id}:check:{contract[0]}"
               and start.get("schema") == contract[1]]
    if len(matches) != 1:
        raise ReviewRefused("The historical interaction has no exact owned review protocol")
    version, (_name, schema, build_prompt, interpret) = matches[0]
    if (proof.identity.matter_id != parent.identity.matter_id
            or proof.identity.advocate_id != parent.identity.advocate_id
            or proof.identity.mode is not parent.identity.mode
            or proof.identity.principles_version != parent.identity.principles_version
            or proof.identity.tools_version != parent.identity.tools_version
            or start.get("parent") != parent.events[-1].fingerprint
            or checked.get("released") is not False
            or checked.get("stop") != StopReason.PROPOSAL.value):
        raise ReviewRefused("The displayed interaction has no exact owned communication review")
    try:
        packet = json.loads(start["prompt"]["user"])
        payload = dict(packet["subject"])
        payload["kind"] = reason.value  # The judge was deliberately blind to author-selected kind.
        subject = InteractionSubject(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                                 allow_nan=False, separators=(",", ":")))
        if communication_requires_work(version):
            from nm.legal_brain.orchestrate.work_receipts import require_work_receipts

            require_work_receipts(payload, parent)
        text = stop["proposal"]["question" if reason is StopReason.QUESTION else "text"]
        started = [event.payload for event in proof.events if event.kind is StepKind.MODEL_STARTED]
        returned = [event.payload for event in proof.events
                    if event.kind is StepKind.MODEL_RETURNED]
        if (subject.identity != packet["subject_identity"]
                or payload["parent"] != parent.events[-1].fingerprint
                or payload["parent_identity"] != parent.identity.as_dict()
                or payload["proposed_text"] != text or len(started) != 1 or len(returned) != 1):
            raise ReviewRefused("The displayed words lack their actual completed review population")
        dispatch, result = started[0], returned[0]["result"]
        originals = [event.payload["prompt"]["user"] for event in parent.events
                     if event.kind is StepKind.MODEL_STARTED]
        source_ids = [row["id"] for row in payload["quote_sources"]]
        expected_prompt = neutral(asdict(build_prompt(subject, subject.sources["principles"])))
        expected_offer = digest({"parent": parent.events[-1].fingerprint,
            "prompt": expected_prompt, "schema": schema, "tier": "judge",
            "provider": dispatch["provider"], "model": dispatch["model"],
            "max_tokens": dispatch["max_tokens"]})
        if (len(source_ids) != len(set(source_ids)) or not originals
                or payload["original_instruction"] != originals[0]
                or payload["principles_version"] != parent.identity.principles_version
                or payload["selected_issue_ids"] != parent.events[0].payload[
                    "context"]["brief"]["selected_issue_ids"]
                or start["prompt"] != expected_prompt or dispatch["prompt"] != expected_prompt
                or proof.identity.offer_hash != expected_offer):
            raise ReviewRefused("The historical check differs from its actual dispatched subject")
        authors = {(event.payload.get("provider"), event.payload.get("model"))
                   for event in parent.events if event.kind is StepKind.MODEL_STARTED}
        if (result["completion"] != "complete" or result.get("downgraded_from") is not None
                or result["data"] != checked["data"]
                or result["tier"] != "judge" or dispatch["tier"] != "judge"
                or result["provider"] != dispatch["provider"]
                or result["model"] != dispatch["model"]
                or (result["provider"], result["model"]) in authors
                or start["prompt"].get("operation") != expected_prompt["operation"]):
            raise ReviewRefused("The displayed interaction was not independently checked")
        spend = Spend(**checked["spend"])
        usage = Usage(**result["usage"])
        if (spend.tokens != usage.tokens_in + usage.tokens_out
                or spend.cost_usd != usage.cost_usd or spend.retries != result["retries"]
                or spend.children != 1):
            raise ReviewRefused("The historical review lost its actual received spend")
        reviewed = interpret(subject, CheckRead(checked["data"], checked["reason"], spend, 1),
            _budget_from(stop["budget"]).spend_on(spend), proof.identity.turn_id)
        if not reviewed.checked or reviewed.candidate_text != text:
            raise ReviewRefused("A displayed interaction must have a full positive wording review")
        return text, payload["checked_snapshot"]
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ReviewRefused):
            raise
        raise ReviewRefused("The historical interaction display contract is incomplete") from exc


def display_binding(parent, proof, paragraphs, scope, *, checked_snapshot):
    """Exact text is held by its parent/proof; the acknowledgement stores hashes."""
    words = [{"text": row.text, "references": list(row.references)} for row in paragraphs]
    body = {"purpose": PURPOSE, "parent_turn_id": parent.identity.turn_id,
        "parent": parent.events[-1].fingerprint, "parent_identity": parent.identity.fingerprint,
        "proof_turn_id": proof.identity.turn_id, "proof": proof.events[-1].fingerprint,
        "proof_identity": proof.identity.fingerprint,
        "checked_snapshot": checked_snapshot, "words_identity": digest(words),
        "kind": parent.events[-1].payload["reason"], "scope": scope,
        "scope_identity": digest(scope)}
    return {**body, "display_identity": digest(body)}


def displayed_questions(matter, *, before_version: int, selected_issue_ids: tuple[str, ...]):
    """Only actual earlier display receipts, not every private question candidate.

    Versions anchor this population at the current parent admission. Later UI
    acknowledgements cannot silently alter the exact already dispatched subject.
    """
    if type(before_version) is not int or before_version < 1:
        raise ValueError("Displayed-question history needs an exact admitted file version")
    result = []
    for saved in matter.loop_records:
        if (not saved.identity.turn_id.endswith(":preview_seen") or not saved.terminal
                or saved.identity.matter_version + len(saved.events) > before_version):
            continue
        if (saved.identity.matter_id != matter.id
                or saved.identity.advocate_id != matter.advocate_id
                or saved.identity.mode is not LoopMode.SYNTHETIC
                or len(saved.events) != 2):
            raise ReviewRefused("Private display history has a foreign or ambiguous receipt")
        start, stop = saved.events[0].payload, saved.events[-1].payload
        if (set(start) != {"binding", "tested_matter_version"}
                or start["tested_matter_version"] != saved.identity.matter_version
                or set(stop) != {"state", "display_identity", "released", "client_ready"}
                or stop["state"] != "recorded" or stop["released"] is not False
                or stop["client_ready"] is not False):
            raise ReviewRefused("A display receipt cannot establish a client release")
        binding = start["binding"]
        if not isinstance(binding, dict):
            raise ReviewRefused("A display acknowledgement needs its exact checked identity")
        from nm.legal_brain.evaluate.evaluation_history import resolve_preview_parent

        parent, checked = resolve_preview_parent(
            matter, saved.identity.turn_id.removesuffix(":preview_seen"))
        if not checked:
            raise ReviewRefused("Displayed repaired words lack their complete checked evaluation")
        proof = _record(matter, binding.get("proof_turn_id"))
        scope = binding.get("scope")
        if (not isinstance(scope, dict) or set(scope) != {
                "approval_reference", "advocate_id", "matter_ids", "mode"}
                or not isinstance(scope["approval_reference"], str)
                or not scope["approval_reference"].strip()
                or scope["advocate_id"] != matter.advocate_id or scope["mode"] != "synthetic"
                or not isinstance(scope["matter_ids"], list)
                or not scope["matter_ids"] or matter.id not in scope["matter_ids"]
                or len(set(scope["matter_ids"])) != len(scope["matter_ids"])):
            raise ReviewRefused("A display receipt lacks its finite original private scope")
        if parent.events[-1].payload["reason"] != StopReason.QUESTION.value:
            # Non-question displays do not populate the asked-question context.
            continue
        text, snapshot = interaction_text(parent, proof)
        from nm.legal_brain.communicate.reviewed_preview import PreviewParagraph

        expected = display_binding(parent, proof, (PreviewParagraph(text, ()),), scope,
                                   checked_snapshot=snapshot)
        if (binding != expected or saved.identity.offer_hash != digest(expected)
                or stop["display_identity"] != expected["display_identity"]
                or saved.identity.principles_version != parent.identity.principles_version
                or saved.identity.tools_version != parent.identity.tools_version):
            raise ReviewRefused("The saved display differs from its exact reviewed question")
        issues = parent.events[0].payload["context"]["brief"]["selected_issue_ids"]
        if issues and selected_issue_ids and not set(issues) & set(selected_issue_ids):
            continue
        result.append({"turn_id": parent.identity.turn_id, "text": text,
            "display_identity": binding["display_identity"], "acknowledged_at": saved.events[-1].at,
            "selected_issue_ids": issues,
            "state": "historical_private_preview_display_not_current_legal_validity"})
    return tuple(result)
