"""Sealed repair selection for an original private interaction, never release.

The journal records which actual attempts an evaluation finished with. A
prefix alone cannot select a later answer, omit prior reservations or relabel a
failed original. Readers still run the current independent output owners.
"""

from __future__ import annotations

from datetime import datetime, timezone

from nm.legal_brain.orchestrate.loop_contracts import (
    LoopEvent,
    LoopIdentity,
    LoopMode,
    StepKind,
    digest,
)
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.work_the_file.original_instruction import read_original_instruction

PURPOSE = "finished_private_evaluation_not_client_release"
CHECKED_STOPS = frozenset(
    {"checks_complete_private_candidate", "interaction_checks_complete_private_candidate"}
)


def _saved(matter, turn_id, log=None, *, mode=LoopMode.SYNTHETIC):
    rows = [row for row in matter.loop_records if row.identity.turn_id == turn_id]
    if (
        len(rows) != 1
        or rows[0].identity.matter_id != matter.id
        or rows[0].identity.advocate_id != matter.advocate_id
        or rows[0].identity.mode is not mode
        or log is not None
        and log.read(rows[0].identity) != rows[0]
    ):
        raise ReviewRefused("The original evaluation has no exact owned saved attempt")
    return rows[0]


def record_repaired_evaluation(brain, result, original_turn_id):
    """Called only by trusted served composition after the actual bounded run."""
    if len(result.attempts) < 2:
        return
    first = result.attempts[0].record
    matter = brain.store.load(first.identity.matter_id)
    original = read_original_instruction(first)
    if first.identity.turn_id != original_turn_id or original.state != "recorded":
        raise ReviewRefused("A repaired evaluation needs its exact original instruction")
    attempts = []
    for index, outcome in enumerate(result.attempts):
        saved = _saved(matter, outcome.record.identity.turn_id, brain.log, mode=first.identity.mode)
        expected = original_turn_id if index == 0 else f"{original_turn_id}:repair:{index}"
        if (
            saved != outcome.record
            or not saved.terminal
            or saved.identity.turn_id != expected
            or read_original_instruction(saved).text != original.text
            or saved.events[-1].payload.get("released") is not False
        ):
            raise ReviewRefused("A repair cannot replace its instruction or actual attempt")
        attempts.append(
            {
                "turn_id": expected,
                "terminal": saved.events[-1].fingerprint,
                "identity": saved.identity.fingerprint,
            }
        )
    body = {
        "purpose": PURPOSE,
        "original_turn_id": original_turn_id,
        "original_instruction_identity": original.text_identity,
        "attempts": attempts,
        "stop": result.stop,
        "limitations": list(result.limitations),
        "budget": result.budget.as_dict(),
        "released": False,
        "client_ready": False,
    }
    identity = LoopIdentity(
        first.identity.matter_id,
        first.identity.advocate_id,
        f"{original_turn_id}:evaluation_result",
        digest(body),
        first.identity.principles_version,
        first.identity.tools_version,
        matter.version,
        first.identity.mode,
    )
    existing = [row for row in matter.loop_records if row.identity.turn_id == identity.turn_id]
    if existing:
        _resolve_evaluation_parent(matter, original_turn_id, brain.log, mode=first.identity.mode)
        if len(existing) != 1 or existing[0].events[-1].payload != body:
            raise ReviewRefused("A saved evaluation result cannot be replaced on replay")
        return
    start = LoopEvent.create(
        1,
        StepKind.START,
        datetime.now(timezone.utc).isoformat(),
        {"purpose": PURPOSE, "result_identity": digest(body)},
        identity.fingerprint,
    )
    brain.log.append(identity, start)
    stop = LoopEvent.create(
        2, StepKind.STOP, datetime.now(timezone.utc).isoformat(), body, start.fingerprint
    )
    brain.log.append(identity, stop)


def resolve_preview_parent(matter, original_turn_id, log=None):
    """Only a sealed completed evaluation chooses its actual repair descendant."""
    # Neutral recorded/synthetic evaluation journaling is not permission to
    # display recorded-client work in the separately approved fictional view.
    return _resolve_evaluation_parent(matter, original_turn_id, log, mode=LoopMode.SYNTHETIC)


def _resolve_evaluation_parent(matter, original_turn_id, log=None, *, mode):
    """Check the complete result in its original mode without granting a view."""
    root = _saved(matter, original_turn_id, log, mode=mode)
    rows = [
        row
        for row in matter.loop_records
        if row.identity.turn_id == f"{original_turn_id}:evaluation_result"
    ]
    if not rows:
        # Historical originals retain their exact behavior. An unfinished repair
        # chain does not grant a fallback to unsealed later text.
        return root, True
    saved = _saved(matter, rows[0].identity.turn_id, log, mode=mode)
    if (
        len(rows) != 1
        or len(saved.events) != 2
        or not saved.terminal
        or saved.events[0].kind is not StepKind.START
    ):
        raise ReviewRefused("The repair selection has no completed sealed outcome")
    body = saved.events[-1].payload
    try:
        if (
            set(body)
            != {
                "purpose",
                "original_turn_id",
                "original_instruction_identity",
                "attempts",
                "stop",
                "limitations",
                "budget",
                "released",
                "client_ready",
            }
            or body["purpose"] != PURPOSE
            or body["original_turn_id"] != original_turn_id
            or body["released"] is not False
            or body["client_ready"] is not False
            or saved.identity.offer_hash != digest(body)
            or saved.events[0].payload != {"purpose": PURPOSE, "result_identity": digest(body)}
            or not isinstance(body["limitations"], list)
            or not isinstance(body["attempts"], list)
            or not 2 <= len(body["attempts"]) <= 11
        ):
            raise ReviewRefused("The saved repair selection differs from its exact result")
        original = read_original_instruction(root)
        if original.state != "recorded" or body["original_instruction_identity"] != (
            original.text_identity
        ):
            raise ReviewRefused("The repair selection has changed original words")
        previous = None
        for index, reference in enumerate(body["attempts"]):
            expected = original_turn_id if index == 0 else f"{original_turn_id}:repair:{index}"
            attempt = _saved(matter, expected, log, mode=mode)
            if (
                not attempt.terminal
                or reference
                != {
                    "turn_id": expected,
                    "terminal": attempt.events[-1].fingerprint,
                    "identity": attempt.identity.fingerprint,
                }
                or attempt.events[-1].payload.get("released") is not False
                or read_original_instruction(attempt).text != original.text
                or attempt.identity.principles_version != root.identity.principles_version
                or attempt.identity.tools_version != root.identity.tools_version
            ):
                raise ReviewRefused("The saved result omits or substitutes an actual attempt")
            if previous is not None:
                _feedback_parent(attempt, previous, matter, log)
            previous = attempt
        return previous, body["stop"] in CHECKED_STOPS and not body["limitations"]
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ReviewRefused):
            raise
        raise ReviewRefused("The repair selection is incomplete or malformed") from exc


def _feedback_parent(attempt, previous, matter=None, log=None):
    """The captured diagnostic points at the actual immediately preceding work."""
    import json

    from nm.legal_brain.evaluate.brain_evaluation import CheckFeedback

    start = attempt.events[0].payload
    feedback = []
    for message in start["context"]["messages"]:
        try:
            value = json.loads(message["text"])
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and value.get("material_kind") in {
            "harness_check_feedback",
            "harness_check_continuation",
        }:
            feedback.append(value)
    if len(feedback) != 1:
        raise ReviewRefused("A selected repair lacks its exact admitted diagnostic parent")
    data = feedback[0]["data"]
    if feedback[0]["material_kind"] == "harness_check_continuation":
        _continuation_parent(attempt, previous, feedback[0], matter, log)
        return
    candidate = CheckFeedback(
        attempt.identity.matter_id,
        data["parent_turn"],
        data["parent_fingerprint"],
        tuple(tuple(row) for row in data["failures"]),
    )
    if (
        json.loads(candidate.text) != feedback[0]
        or start.get("feedback_identity") != candidate.identity
        or candidate.parent_turn_id != previous.identity.turn_id
        or candidate.parent_fingerprint != previous.events[-1].fingerprint
    ):
        raise ReviewRefused("The repair feedback does not bind the preceding actual failure")


def _continuation_parent(attempt, previous, wire, matter, log):
    """Historical association is an actual reviewed input, not an authored PASS.

    This reader does not replace the current source/binding admission service.
    It reuses the shared positive interpreter against the actual captured prompt
    and response and refuses missing proof. No fake negative feedback is made.
    """
    import json

    from nm.legal_brain.orchestrate.checked_input_continuation import (
        CheckedInputContinuation,
        CheckedInputReference,
    )
    from nm.legal_brain.orchestrate.loop import _budget_from
    from nm.legal_brain.orchestrate.loop_contracts import LoopOutcome, StopReason
    from nm.legal_brain.verify.brain_assessment import saved_package_reviews
    from nm.legal_brain.verify.brain_release import _review_spend
    from nm.legal_brain.verify.recorded_package_subject import (
        recorded_input_bindings,
        recorded_package_subject,
    )
    from nm.shared.json_values import same_json_value

    if matter is None or not previous.terminal:
        raise ReviewRefused("A continuation history needs its actual owned review population")
    data = wire["data"]
    candidate = CheckedInputContinuation(
        data["matter_id"],
        data["parent_turn_id"],
        data["parent_fingerprint"],
        data["original_message_identity"],
        tuple(data["selected_issue_ids"]),
        tuple(CheckedInputReference(**row) for row in data["input_references"]),
    )
    start, prior = attempt.events[0].payload, previous.events[0].payload
    original = read_original_instruction(previous)
    scope = digest({"requested_issue_ids": sorted(set(candidate.selected_issue_ids))})
    prior_scope = prior.get("scope_identity")
    legacy_scope = (
        prior_scope is None
        and candidate.selected_issue_ids
        and same_json_value(
            prior["context"]["brief"]["selected_issue_ids"], list(candidate.selected_issue_ids)
        )
    )
    if (
        not same_json_value(json.loads(candidate.text), wire)
        or start.get("feedback_identity") != candidate.identity
        or candidate.matter_id != matter.id
        or candidate.parent_turn_id != previous.identity.turn_id
        or candidate.parent_fingerprint != previous.events[-1].fingerprint
        or original.state != "recorded"
        or candidate.original_message_identity != original.text_identity
        or read_original_instruction(attempt).text != original.text
        or prior_scope != scope
        and not legacy_scope
        or start.get("scope_identity") != scope
        or candidate.selected_issue_ids
        and (
            not same_json_value(
                prior["context"]["brief"]["selected_issue_ids"], list(candidate.selected_issue_ids)
            )
            or not same_json_value(
                start["context"]["brief"]["selected_issue_ids"], list(candidate.selected_issue_ids)
            )
        )
        or any(
            row.parent_turn_id != previous.identity.turn_id
            or matter.thread(row.thread_id) is None
            or candidate.selected_issue_ids
            and row.thread_id not in candidate.selected_issue_ids
            for row in candidate.input_references
        )
    ):
        raise ReviewRefused("The typed continuation changed its exact preceding parent or scope")

    class CapturedLog:
        # Read-only exact matter owner for historical callers without a live log.
        def read(self, identity):
            rows = [row for row in matter.loop_records if row.identity == identity]
            return rows[0] if len(rows) == 1 else None

    actual_log = log if log is not None else CapturedLog()
    outcome = LoopOutcome(
        StopReason(previous.events[-1].payload["reason"]),
        previous,
        _budget_from(previous.events[-1].payload["budget"]),
        previous.events[-1].payload["proposal"],
    )
    packages, identities, owned_bindings = [], {}, {}
    for reference in candidate.input_references:
        saved = _saved(
            matter,
            f"{previous.identity.turn_id}:verify:{reference.package_id}",
            actual_log,
            mode=previous.identity.mode,
        )
        package = recorded_package_subject(previous, saved, matter, actual_log)
        if package.id != reference.package_id or package.identity != reference.package_identity:
            raise ReviewRefused("A continuation has no exact actual reviewed input subject")
        key = (reference.kind, saved.identity.matter_version)
        if key not in owned_bindings:
            owned_bindings[key] = recorded_input_bindings(
                outcome, saved, matter, actual_log, reference.kind
            )
        exact = [
            row
            for row in owned_bindings[key]
            if row.package == package and row.candidate["thread_id"] == reference.thread_id
        ]
        if len(exact) != 1:
            raise ReviewRefused("A continuation changed its real exact selection producer or scope")
        if reference.package_id in identities:
            if identities[reference.package_id] != reference.package_identity:
                raise ReviewRefused("Continuation references disagree about one exact package")
            continue
        identities[package.id] = package.identity
        packages.append(package)
    reviewed = saved_package_reviews(outcome, tuple(packages), matter, actual_log)
    if any(package not in reviewed.result.released for package in packages):
        raise ReviewRefused("A continuation cannot substitute an authored or negative verdict")
    admitted, floor = start["budget"], reviewed.budget.as_dict()
    _review_spend(admitted["spend"])
    if (
        any(
            not same_json_value(admitted[key], floor[key])
            for key in ("max_ms", "max_tokens", "max_cost_usd", "max_children", "max_retries")
        )
        or any(admitted["spend"][key] < value for key, value in floor["spend"].items())
        or floor["cancelled_at"]
        and admitted["cancelled_at"] != floor["cancelled_at"]
    ):
        raise ReviewRefused("The continuation history reset its reviewed whole-task allowance")
