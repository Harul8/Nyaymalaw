"""Typed continuation of an original request after actual conditional-input review.

Construction alone grants nothing. The application must call validate at the
next run admission and retain its existing attempt/dispatch/resource bounds.
This service makes no model/tool call and does not claim the request completed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass

from nm.Archives.legal_brain.orchestrate.loop_contracts import digest
from nm.Archives.legal_brain.verify.brain_assessment import saved_package_reviews
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused, ReviewService, shared_review_budget
from nm.shared.json_values import same_json_value
from nm.work_the_file.original_instruction import read_original_instruction


@dataclass(frozen=True)
class CheckedInputReference:
    kind: str
    thread_id: str
    package_id: str
    package_identity: str
    parent_turn_id: str

    def __post_init__(self):
        if (
            any(
                type(row) is not str or not row.strip()
                for row in (self.kind, self.thread_id, self.package_id, self.parent_turn_id)
            )
            or type(self.package_identity) is not str
            or len(self.package_identity) != 64
            or any(char not in "abcdef0123456789" for char in self.package_identity)
        ):
            raise ValueError("A continuation reference retains its exact typed input owner")


@dataclass(frozen=True)
class CheckedInputContinuation:
    matter_id: str
    parent_turn_id: str
    parent_fingerprint: str
    original_message_identity: str
    selected_issue_ids: tuple[str, ...]
    input_references: tuple[CheckedInputReference, ...]

    def __post_init__(self):
        if (
            any(
                type(row) is not str or not row.strip()
                for row in (self.matter_id, self.parent_turn_id)
            )
            or any(
                type(row) is not str
                or len(row) != 64
                or any(char not in "abcdef0123456789" for char in row)
                for row in (self.parent_fingerprint, self.original_message_identity)
            )
            or type(self.selected_issue_ids) is not tuple
            or any(type(row) is not str or not row.strip() for row in self.selected_issue_ids)
            or len(set(self.selected_issue_ids)) != len(self.selected_issue_ids)
            or type(self.input_references) is not tuple
            or not self.input_references
            or any(type(row) is not CheckedInputReference for row in self.input_references)
            or len({(row.kind, row.package_id) for row in self.input_references})
            != len(self.input_references)
        ):
            raise ValueError(
                "A typed continuation needs an exact original parent and input population"
            )

    @property
    def text(self):
        return json.dumps(
            {
                "material_kind": "harness_check_continuation",
                "trust": "checked_conditional_inputs_not_new_instruction_or_fact",
                "data": {
                    **asdict(self),
                    "instruction": "Continue the unchanged original request proportionately "
                    "within its existing "
                    "scope and allowance. These exact conditional-input references require current "
                    "owner validation; they do not establish facts, authorize publication, demand "
                    "a calculation or establish that the pending request is complete.",
                },
            },
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )

    @property
    def identity(self):
        return digest({"matter": self.matter_id, "continuation": self.text})

    @property
    def client_ready(self):
        return False


class CheckedInputContinuationService:
    def __init__(
        self,
        *,
        reviewer: ReviewService,
        binding_owners: Mapping,
        current_tools_version,
        current_principles_version,
    ):
        if (
            not isinstance(reviewer, ReviewService)
            or not isinstance(binding_owners, Mapping)
            or not binding_owners
            or any(
                type(key) is not str or not key.strip() or not callable(owner)
                for key, owner in binding_owners.items()
            )
            or not callable(current_tools_version)
            or not callable(current_principles_version)
        ):
            raise ValueError("Continuation needs existing actual review and current binding owners")
        self.reviewer, self.binding_owners = reviewer, dict(binding_owners)
        self.current_tools_version, self.current_principles_version = (
            current_tools_version,
            current_principles_version,
        )

    def prepare(self, outcome, *, groups, original_message, selected_issue_ids, budget):
        parent = outcome.record
        if (
            not parent.terminal
            or self.reviewer.log.read(parent.identity) != parent
            or not self.reviewer.session_current()
            or self.current_tools_version() != parent.identity.tools_version
            or self.current_principles_version() != parent.identity.principles_version
            or type(groups) is not tuple
            or not groups
            or type(selected_issue_ids) is not tuple
            or any(type(row) is not str or not row.strip() for row in selected_issue_ids)
            or len(set(selected_issue_ids)) != len(selected_issue_ids)
        ):
            raise ReviewRefused("Continuation lost its exact completed current owned parent")
        original = read_original_instruction(parent)
        admitted = (
            parent.events[0].payload.get("context", {}).get("brief", {}).get("selected_issue_ids")
        )
        if (
            original.state != "recorded"
            or type(original_message) is not str
            or original.text != original_message
        ):
            raise ReviewRefused(
                "Continuation cannot change the original instruction or admitted scope"
            )
        matter = self.reviewer.store.load(parent.identity.matter_id)
        scope_identity = parent.events[0].payload.get("scope_identity")
        if scope_identity is not None:
            if (
                type(scope_identity) is not str
                or scope_identity
                != digest({"requested_issue_ids": sorted(set(selected_issue_ids))})
                or selected_issue_ids
                and not same_json_value(admitted, list(selected_issue_ids))
            ):
                raise ReviewRefused("Continuation cannot alter its sealed requested scope")
        elif not selected_issue_ids or not same_json_value(admitted, list(selected_issue_ids)):
            raise ReviewRefused("A legacy continuation has no authenticated whole-file scope")
        allowed_threads = (
            set(selected_issue_ids) if selected_issue_ids else {row.id for row in matter.threads}
        )
        current_budget = shared_review_budget(outcome, (), matter, self.reviewer.log, budget)
        if current_budget.spent_out:
            raise ReviewRefused("The unchanged whole-task allowance cannot fund continuation")
        references, seen = [], set()
        for group in groups:
            if (
                type(group) is not tuple
                or len(group) != 2
                or type(group[0]) is not str
                or group[0] not in self.binding_owners
                or group[0] in seen
                or type(group[1]) is not tuple
                or not group[1]
                or any(type(row) is not str or not row.strip() for row in group[1])
                or len(set(group[1])) != len(group[1])
            ):
                raise ReviewRefused(
                    "Continuation needs distinct exact registered input populations"
                )
            kind, ids = group
            seen.add(kind)
            owner = self.binding_owners[kind]
            bindings = owner(outcome, matter)
            if type(bindings) is not tuple or not bindings:
                raise ReviewRefused("The actual current input producer has no candidate population")
            packages = tuple(row.package for row in bindings)

            def current(saved, file, proposed, owner=owner):
                if tuple(row.package for row in owner(saved, file)) != proposed:
                    raise ReviewRefused("The exact conditional input population changed")

            self.reviewer._current(outcome, packages=packages, current_owner=current)
            actual = saved_package_reviews(outcome, packages, matter, self.reviewer.log)
            judge = (
                self.reviewer.verifier.model.provider,
                self.reviewer.verifier.model.resolved_model(self.reviewer.verifier.tier),
            )
            by_id = {row.package.id: row for row in bindings}
            if len(by_id) != len(bindings) or any(row not in by_id for row in ids):
                raise ReviewRefused(
                    "Requested inputs are missing or ambiguous in their actual owner"
                )
            for ident in ids:
                binding = by_id[ident]
                thread_id = binding.candidate["thread_id"]
                records = [row for row in actual.records if row.package_id == ident]
                if (
                    binding.package not in actual.result.released
                    or len(records) != 1
                    or (records[0].provider, records[0].model) != judge
                    or thread_id not in allowed_threads
                ):
                    raise ReviewRefused(
                        "Continuation lacks an exact current independent positive input"
                    )
                references.append(
                    CheckedInputReference(
                        kind, thread_id, ident, binding.package.identity, parent.identity.turn_id
                    )
                )
        continuation = CheckedInputContinuation(
            parent.identity.matter_id,
            parent.identity.turn_id,
            parent.events[-1].fingerprint,
            original.text_identity,
            selected_issue_ids,
            tuple(references),
        )
        if (
            self.reviewer.store.load(matter.id) != matter
            or self.reviewer.log.read(parent.identity) != parent
        ):
            raise ReviewRefused("The current owned file changed during continuation validation")
        return continuation

    def validate(self, continuation, outcome, *, original_message, selected_issue_ids, budget):
        if type(continuation) is not CheckedInputContinuation:
            raise ReviewRefused("A caller-authored continuation is not an admitted service result")
        kinds = tuple(dict.fromkeys(row.kind for row in continuation.input_references))
        groups = tuple(
            (
                kind,
                tuple(row.package_id for row in continuation.input_references if row.kind == kind),
            )
            for kind in kinds
        )
        actual = self.prepare(
            outcome,
            groups=groups,
            original_message=original_message,
            selected_issue_ids=selected_issue_ids,
            budget=budget,
        )
        if not same_json_value(json.loads(actual.text), json.loads(continuation.text)):
            raise ReviewRefused("The continuation differs from its actual current input references")
        return shared_review_budget(
            outcome,
            (),
            self.reviewer.store.load(outcome.record.identity.matter_id),
            self.reviewer.log,
            budget,
        )
