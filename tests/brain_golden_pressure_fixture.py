"""Golden repository passages with explicitly fabricated semantic owners.

No provider, browser, document download or legal corpus is used. The fixture
binds exact curated repository quotes to their source offsets; these are not
newly acquired judgment text or twenty authentic client files. All source-role,
coverage and semantic verdicts are declared by the scenario author.
"""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path

from nm.brain import turn as boundary
from nm.brain.material import addressed_sources
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage, require_schema
from tests import __file__ as test_package_file
from tests.brain_pressure_support import record_case
from tests.brain_reader_fixture import (
    fixture_representation_choices,
    fixture_scoped_coverage,
    fresh_review_reply,
    scripted_support_spans,
    source_portion_reply,
)
from tests.test_brain_golden_sources import validate_sources

ROOT = Path(test_package_file).resolve().parents[1]
PACKET_PATH = ROOT / "tests/fixtures/brain_golden_sources_20261006.json"

COMPOSITES = (
    ("GS-06", "GS-07", "GS-16"),
    ("GS-08", "GS-23", "GS-25"),
    ("GS-09", "GS-11", "GS-22"),
    ("GS-12", "GS-10", "GS-24"),
    ("GS-13", "GS-14"),
    ("GS-15", "GS-17"),
    ("GS-18", "GS-21"),
    ("GS-19", "GS-20"),
)

# These are independently declared dataset annotations, not a classifier.
EXAMINATION_PARTS = {
    "The debt looks time-barred on the invoices.",
    "Filed in time and still liable to fail.",
    "The injunction will not hold.",
}

# Independently authored atomic good proposals; original selected quotes stay
# intact in the input and are not rewritten to manufacture factual support.
ATOMIC_PROPOSITIONS = {
    "The buyer is in possession under an unregistered agreement.": [
        ("circumstance", "The buyer is in possession under the described agreement."),
        ("evidence", "The described agreement is unregistered."),
    ],
    "talaq was pronounced, there is a maintenance claim and a child of six": [
        ("event", "talaq was pronounced"),
        ("procedure", "there is a maintenance claim"),
        ("circumstance", "a child of six"),
    ],
    "neighbour grabbed his land and beat him up badly yesterday, injuring his knee": [
        ("event", "neighbour grabbed his land yesterday"),
        ("event", "neighbour beat him up badly yesterday"),
        ("circumstance", "the reported assault injured his knee"),
    ],
    "bounced on 3 March, we sent notice": [
        ("event", "bounced on 3 March"),
        ("procedure", "we sent notice"),
    ],
}
KIND_BY_PROSE = {
    "police picked up my client last night": "event",
    "around 11pm yesterday, Chikkadpally PS": "circumstance",
    "they say it is section 447": "position",
    "he was produced this morning": "procedure",
    "Remand extended for want of escort.": "procedure",
    "we act for the wife": "circumstance",
    "she has no income": "circumstance",
    "the husband says the 1986 Act limits everything to iddat": "position",
    "family wants a lump sum": "objective",
    "a fitter was dismissed": "event",
    "he has been encroaching since 2019": "event",
    "no, the wall is new, the strip was 2019": "circumstance",
    "notice went on 15 April": "procedure",
    "it is dated 15-4-1984": "evidence",
    "sorry, 15-4-2024": "evidence",
    "the original is with the seller's brother": "evidence",
    "he will not give it, can we say we lost it": "position",
    "I never signed it": "position",
    "I signed it but the consideration failed": "position",
    "their secretary signed, that is enough": "position",
    "there is a judgment against this exact point, leave it out": "position",
}

NON_ACCOUNT = {
    "request",
    "legal_proposition_in_scenario_rubric_not_client_fact",
    "scenario_rubric_about_attributed_opponent_argument",
    "scenario_rubric_describes_unresolved_evidence_availability",
}


@dataclass
class Dossier:
    id: str
    golden_ids: tuple[str, ...]
    message: str
    details: list[dict]
    source_roles: dict[str, str]
    source_quotes: dict[str, str]
    source_entries: list[dict]


def golden_sources() -> dict:
    packet = json.loads(PACKET_PATH.read_text())
    validate_sources(packet)
    return packet


def composite(index: int = 0) -> Dossier:
    packet = golden_sources()
    ids = COMPOSITES[index]
    entries = {entry["case_id"]: entry for entry in packet["entries"]}
    message_lines = [
        "Review the following combined rehearsal account and preserve the "
        "separate threads, attribution, chronology, uncertainty and requests."
    ]
    annotations = []
    for case_id in ids:
        entry = entries[case_id]
        for quote in entry["selected_exact_quotes"]:
            annotation = quote["annotation"]
            framing = (
                "Examination or requested work"
                if annotation in NON_ACCOUNT
                else "Attributed scenario account"
            )
            line = f"{case_id} {framing} ({annotation}): {quote['text']}"
            message_lines.append(line)
            annotations.append((line, case_id, annotation))
    message = "\n".join(message_lines)
    _, current, _ = addressed_sources((), message)
    roles = {}
    details = []
    for identity, exact in current.items():
        if identity == "L1":
            roles[identity] = "work_instruction"
            continue
        owners = [
            (line, case_id, annotation)
            for line, case_id, annotation in annotations
            if exact in line
        ]
        assert len(owners) == 1, (identity, exact, owners)
        _, case_id, annotation = owners[0]
        prose = exact.partition(": ")[2] if exact.startswith(case_id + " ") else exact
        if annotation in NON_ACCOUNT or prose in EXAMINATION_PARTS:
            roles[identity] = "examination_material"
            continue
        roles[identity] = "reported_matter_account"
        # The full owned span is retained as an attributed account. No court
        # finding, statutory conclusion or evidence availability is invented.
        propositions = ATOMIC_PROPOSITIONS.get(
            prose, [(KIND_BY_PROSE.get(prose, "circumstance"), prose)]
        )
        for kind, proposition in propositions:
            details.append(
                {
                    "kind": kind,
                    "statement": f"Supplied {case_id} ({annotation}): {proposition}",
                    "source_id": identity,
                    "basis": (
                        "attributed"
                        if "attributed" in annotation
                        or "factual" in annotation
                        or annotation == "scenario_description"
                        else "stated"
                    ),
                    "importance": "central",
                    "why_material": (
                        "This separately attributed contribution may affect this "
                        "thread; it does not establish truth or another thread."
                    ),
                    "assignment_ids": ["matter:discussion"],
                }
            )
    assert details
    return Dossier(
        f"COMPOSITE-{index + 1:02}",
        ids,
        message,
        details,
        roles,
        current,
        [deepcopy(entries[identity]) for identity in ids],
    )


def no_requirement():
    return {"kind": "none", "target_ids": [], "operation": "none", "success_condition": ""}


class GoldenModel:
    """Raw complete objects, strict whole-output schema, explicit semantic labels.

    hook runs BEFORE strict validation and logging. It may deliberately fabricate
    bad objects. The fixture never improves their meaning after a failed check.
    """

    def __init__(
        self,
        dossier: Dossier,
        variant="good",
        *,
        response_mode="substantive",
        requirement=None,
        mutation_scopes=None,
        reply=None,
        hook=None,
    ):
        self.dossier = dossier
        self.variant = variant
        self.response_mode = response_mode
        self.requirement = deepcopy(requirement or no_requirement())
        # Scope semantics are independently authored before any reader output.
        # No candidate footprint or reviewer acceptance can supply permission.
        if mutation_scopes is None and self.requirement["kind"] == "change":
            # The constructor's independently supplied requirement owns its
            # requested targets and operation even when extraction returns no
            # candidate. The curated rehearsal has one explicit review source.
            # Exact correction regressions supply their own contribution scope.
            _, current, _ = addressed_sources((), dossier.message)
            instructions = [identity for identity in current
                            if dossier.source_roles[identity] == "work_instruction"]
            assert len(instructions) == 1, "A request scope needs its declared original owner"
            mutation_scopes = [{
                "authority_kind": "interpretation_review",
                "authority_source_ids": instructions,
                "target_scope": "exact",
                "target_ids": list(self.requirement["target_ids"]),
                "permitted_relations": [self.requirement["operation"]],
            }]
        self.mutation_scopes = deepcopy(mutation_scopes or [])
        self.reply = reply or (
            "The supplied scenario accounts remain separately attributed. "
            "The requests and legal examination passages are not admitted facts."
        )
        self.hook = hook
        self.seen = []
        self.outputs = []
        self.turn_number = -1
        self.targeted_read = False
        self.owner_reconsidered = False
        self.operation_counts = {}
        self.selected_gap = dossier.details[-1]["source_id"]
        self.hallucinated_statement = (
            "The composite client received a final court judgment "
            "awarding an amount never mentioned in this account."
        )
        self.opening_summary = (
            "The advocate supplied distinct attributed scenario accounts for review."
        )
        self.semantic_decisions = {row["statement"]: True for row in dossier.details}
        self.semantic_decisions[self.opening_summary] = True
        self.semantic_decisions[self.hallucinated_statement] = False
        self.semantic_sources = {row["statement"]: row["source_id"] for row in dossier.details}
        self.semantic_sources[self.opening_summary] = dossier.details[0]["source_id"]
        self.semantic_sources[self.hallucinated_statement] = dossier.details[-1]["source_id"]
        self.semantic_attributes = {
            row["statement"]: {
                "kind": row["kind"],
                "basis": row["basis"],
                "placement": "matter",
                "dispute_ids": [],
                "matter_scope": "proposed",
            }
            for row in dossier.details
        }
        # This ordinary matrix independently requests material representation
        # without a new dispute obligation. The thread matrix overrides this
        # scope with its separately authored THREAD_ISSUES originals below.
        self.dispute_coverage_sources = set()

    def context_budget(self, tier):
        assert tier in (Tier.ROUTINE, Tier.JUDGE)
        return 100000

    def _interpret(self):
        return {
            "items": [
                {
                    "request": "Review the combined accounts and preserve their distinctions.",
                    "intent": "request",
                    "relation": "new",
                    "matter_scope": "proposed",
                    "priority": "ordinary",
                    "next_step": "answer",
                    "response_basis": "conversation_record",
                    "research_question": "",
                    "material_purposes": ["account_contribution", "interpretation_review"],
                    "record_requirement": deepcopy(self.requirement),
                    "mutation_scopes": deepcopy(self.mutation_scopes),
                    "response_mode": self.response_mode,
                }
            ],
            "opening": {
                "ready": True,
                "party_name": "",
                "subject": "Combined attributed scenario rehearsal",
                "summary": self.opening_summary,
            },
        }

    def _reader(self, operation, payload, schema):
        original = payload.get("original_input", payload)
        targeted = "recovery_scope" in original
        if targeted:
            self.targeted_read = True
        if operation == "extract_disputes":
            return {"new_items": [], "changes": []}
        if "repairs" in schema.get("properties", {}):
            replacements = {}
            for identity in schema["properties"]["repairs"]["properties"]:
                replacement = (
                    {"foreign": "Still not a proposal."}
                    if self.variant in ("persistent_bad", "foreign_source")
                    else deepcopy(self.dossier.details[-1])
                )
                replacements[identity] = {"proposals": [replacement]}
            return {"repairs": replacements}
        rows = deepcopy(self.dossier.details)
        if targeted:
            rows = [deepcopy(self.dossier.details[-1])]
            if self.variant == "empty_extract":
                rows = deepcopy(self.dossier.details)
        if self.variant in ("average_partial",) and not targeted:
            rows = rows[:-1]
        elif self.variant == "empty_extract" and not targeted:
            rows = []
        elif self.variant in ("malformed_sibling", "persistent_bad"):
            rows[-1] = {"foreign": "Malformed independently failed proposal."}
        elif self.variant == "foreign_source":
            rows[-1]["source_id"] = "OTHER-MATTER-SOURCE"
        elif self.variant == "hallucinated":
            rows[-1]["statement"] = self.hallucinated_statement
        return {"new_items": rows, "changes": []}

    def _record_review(self, operation, payload):
        original = payload.get("original_input", payload)
        verdicts = []
        for candidate in original["candidates"]:
            identity = candidate["candidate_id"]
            proposition = candidate.get("statement", candidate.get("summary", ""))
            assert proposition in self.semantic_decisions, (
                "Undeclared semantic fixture proposition",
                proposition,
            )
            accepted = self.semantic_decisions[proposition]
            source_ids = candidate.get("allowed_account_source_ids", [])
            assert proposition in self.semantic_sources, (
                "Undeclared semantic source label",
                proposition,
            )
            selected = [self.semantic_sources[proposition]]
            attributes = self.semantic_attributes.get(proposition, {})
            if attributes and any(
                candidate.get(key) != expected for key, expected in attributes.items()
            ):
                accepted = False
            if selected[0] not in source_ids:
                accepted = False
                selected = []
            source_conflict = (
                self.variant == "source_conflict"
                and not self.owner_reconsidered
                and self.selected_gap in selected
            )
            if source_conflict:
                accepted = False
            row = {
                "candidate_id": identity,
                "operation_supported": accepted,
                "verdict": "accept" if accepted else "reject",
                "reason": (
                    "The independently scripted judgment preserves the attributed account."
                    if accepted
                    else "The independently scripted judgment rejects this unsupported layer."
                ),
                "account_check": {
                    "content_role": "reported_matter_account"
                    if accepted or source_conflict
                    else "uncertain",
                    "supported": accepted or source_conflict,
                    "introduces_legal_analysis": False,
                    "source_ids": selected,
                    "source_checks": [
                        {
                            "source_id": source_id,
                            "supplies_account_content": True,
                            "supports_proposal": accepted or source_conflict,
                            "reason": "The original account supplies this attributed contribution.",
                        }
                        for source_id in selected
                    ],
                    "reason": "The account judgment separately checks original framing.",
                },
                "target_checks": [],
            }
            if operation == "verify_disputes":
                row["candidate_role"] = "independent_dispute"
            verdicts.append(row)
        result = {"verdicts": verdicts}
        if "coverage_source_ids" in original:
            missing = []
            if operation == "verify_material_grounding" and not self.targeted_read:
                if self.variant == "average_partial":
                    missing = [self.selected_gap]
                elif self.variant == "empty_extract":
                    missing = [row["source_id"] for row in self.dossier.details]
                elif self.variant in ("persistent_bad", "foreign_source", "hallucinated"):
                    missing = [self.selected_gap]
            # Persistent or hallucinated failures intentionally stay partial;
            # no fabricated all-clear conceals rejected account or unread rows.
            if operation == "verify_material_grounding" and self.variant in (
                "persistent_bad",
                "foreign_source",
                "hallucinated",
            ):
                missing = [self.selected_gap]
            result["coverage"] = {
                "state": "partial" if missing else "complete",
                "missing_source_ids": missing,
                "reason": (
                    "The scripted coverage owner identifies an owned missing contribution."
                    if missing
                    else "The independently scripted coverage owner declares the scope represented."
                ),
            }
        result = scripted_support_spans(original, result, scripted_source_account=True)
        if original.get("coverage_selection_contract") != "owned_account_dispositions_v2":
            return result
        # Corpus annotations independently own original purpose and this stage's
        # obligations. Resolve exact IDs before the raw hook; never repair an
        # adversarial writer, reviewer or classifier after its authored output.
        legacy_missing = set(result.get("coverage", {}).get("missing_source_ids", ()))
        decisions = {}
        issue_sources = self.dispute_coverage_sources
        for identity in original["coverage_source_ids"]:
            words = original["source_treatments"][identity]["quoted"]
            roles = {self.dossier.source_roles[key]
                     for key, exact in self.dossier.source_quotes.items() if exact == words}
            assert len(roles) == 1, (identity, words, roles)
            if next(iter(roles)) not in ("reported_matter_account", "reported_party_position"):
                decisions[identity] = "non_account"
            elif operation == "verify_disputes" and not any(
                    self.dossier.source_quotes[source] == words for source in issue_sources):
                decisions[identity] = "outside_scope"
            else:
                decisions[identity] = "account"
        choices = fixture_representation_choices(original, result)
        # Repeated unchanged words may be represented by the previously saved
        # authored proposition. This is a corpus-owned semantic judgment, not
        # a general inference that any record with a citation covers its source.
        for identity, purpose in decisions.items():
            if purpose != "account" or identity in legacy_missing:
                continue
            words = original["source_treatments"][identity]["quoted"]
            propositions = {
                row["statement"] for row in self.dossier.details
                if self.dossier.source_quotes[row["source_id"]] == words
            }
            for row in original.get("active_material", ()):
                if (row.get("id") in original.get("coverage_record_ids", ())
                        and row.get("statement") in propositions):
                    choices[identity]["record_ids"].append(row["id"])
        for identity in legacy_missing:
            choices[identity] = {"record_ids": [], "candidate_ids": []}
        result["coverage"] = fixture_scoped_coverage(
            original, result, source_decisions=decisions, representation_choices=choices)
        return result

    def _continuation(self, payload):
        units = []
        fresh = payload.get("response_expression_contract") == "evidence_expression_v1"
        for item in payload["work_items"]:
            index = item["request_index"]
            block_id = f"golden-block:{index}"
            outcome = {
                "status": "none",
                "block_id": "",
                "effect_ids": [],
                "current_record_ids": [],
                "reason": "",
            }
            if item["record_requirement"]["kind"] != "none":
                outcome = {
                    "status": "unresolved",
                    "block_id": block_id,
                    "effect_ids": [],
                    "current_record_ids": [],
                    "reason": "The scripted owner leaves the full record result unresolved.",
                }
            source_id = next(identity for identity, role in self.dossier.source_roles.items()
                             if role == "reported_matter_account")
            block = {
                "id": block_id, "kind": "completion", "text": self.reply,
                "span_ids": [source_id], "record_ids": [], "legal_source_ids": [],
                "inline_citations": [], "uncertainty": "reported",
            }
            if fresh:
                # Author the valid base object before hook. A hook adding false
                # prose now leaves a forbidden raw field for the public owner
                # to reject; no fixture conversion runs after that attack.
                block = {
                    "id": block_id, "kind": "completion", "uncertainty": "reported",
                    "evidence_expression": {
                        "operator": "record_result" if outcome["status"] != "none"
                        else "source_account",
                        "source_ids": [] if outcome["status"] != "none" else [source_id],
                        "record_ids": [], "focus": "none",
                    },
                }
            units.append(
                {
                    "request_index": index,
                    "blocks": [block],
                    "questions": [],
                    "next_work": [],
                    "sufficiency": {
                        "status": "partial" if outcome["status"] == "unresolved" else "complete",
                        "block_id": block_id,
                    },
                    "work_selector": "$new_task",
                    "progress_updates": [],
                    "record_outcome": outcome,
                }
            )
        return {"units": units}

    def _continuation_review(self, payload):
        result = []
        for unit in payload["units"]:
            outcome = unit["record_outcome"]["status"]
            result.append(
                {
                    "request_index": unit["request_index"],
                    "reason": "The scripted reply preserves scope and attributed uncertainty.",
                    "block_checks": [
                        {
                            "block_id": block["id"],
                            "requires_legal_support": False,
                            "verdict": "accept",
                            "reason": "This is the declared account-layer reply.",
                        }
                        for block in unit["blocks"]
                    ],
                    "proposal_checks": [],
                    "work_check": {
                        "existing_id": unit["work"]["existing_id"],
                        "scope_preserved": True,
                        "verdict": "accept",
                        "reason": "The scoped work identity is preserved.",
                    },
                    "progress_checks": [],
                    "question_resolutions": [],
                    "record_check": {
                        "outcome": ("not_requested" if outcome == "none" else "unfinished"),
                        "reason": "The scripted owner explicitly declares this result.",
                    },
                }
            )
        return {"accepted_units": result, "rejected_units": []}

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        operation = prompt.operation
        self.operation_counts[operation] = self.operation_counts.get(operation, 0) + 1
        if operation == "interpret_conversation":
            self.turn_number += 1
            data = self._interpret()
        elif operation == "classify_account_sources":
            original = payload.get("original_input", payload)
            roles = dict(self.dossier.source_roles)
            for message in original.get("earlier_conversation", []):
                if message["role"] != "advocate":
                    continue
                for span in message["source_spans"]:
                    matches = {
                        self.dossier.source_roles[key]
                        for key, exact in self.dossier.source_quotes.items()
                        if exact == span["text"].strip()
                    }
                    assert len(matches) == 1, (span, matches)
                    roles[span["id"]] = next(iter(matches))
            data = {
                "source_treatments": {
                    identity: {
                        "content_role": (
                            "examination_material"
                            if self.variant == "source_conflict" and identity == self.selected_gap
                            else roles[identity]
                        ),
                        "reason": "This source purpose is separately declared for this case.",
                    }
                    for identity in original["source_ids"]
                }
            }
            data = source_portion_reply(payload, data)
        elif operation == "reconsider_account_sources":
            self.owner_reconsidered = True
            original = payload.get("original_input", payload)
            data = {
                "source_treatments": {
                    identity: {
                        "content_role": self.dossier.source_roles[identity],
                        "reason": "The candidate-free owner rereads the original framing.",
                    }
                    for identity in original["source_ids"]
                }
            }
            data = source_portion_reply(payload, data)
        elif operation in ("extract_disputes", "extract_legal_details"):
            data = self._reader(operation, payload, schema)
        elif operation in ("verify_disputes", "verify_material_grounding"):
            data = self._record_review(operation, payload)
        elif operation == "continue_conversation":
            data = self._continuation(payload)
        elif operation == "verify_continuation":
            data = self._continuation_review(payload)
        else:
            raise AssertionError(f"Undeclared fabricated operation: {operation}")
        if self.hook is not None:
            data = self.hook(operation, payload, schema, deepcopy(data), self)
        data = fresh_review_reply(payload, data)
        self.seen.append(
            {
                "operation": operation,
                "tier": tier.value,
                "turn_number": self.turn_number,
                "input": deepcopy(payload),
            }
        )
        logged = {"operation": operation, "turn_number": self.turn_number, "output": deepcopy(data)}
        self.outputs.append(logged)
        result = ModelResult(
            text=None,
            data=deepcopy(data),
            tier=tier,
            provider="offline",
            model="explicit-golden-script",
            usage=Usage(0, 0, 0),
            latency_ms=0,
            completion=Completion.COMPLETE,
        )
        try:
            require_schema(data, schema)
        except SchemaViolation as error:
            logged["schema_valid"] = False
            logged["schema_error"] = str(error)
            raise SchemaViolation(str(error), rejected_result=result) from error
        logged["schema_valid"] = True
        return result


def wire(wired, monkeypatch, model, *, recovery_limit=8):
    from nm.app import api

    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    monkeypatch.setattr(wired, "legal_search", None)

    class LimitedService(boundary.BrainService):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs, recovery_limit=recovery_limit)

    monkeypatch.setattr(api, "BrainService", LimitedService)


def release(client, wired, monkeypatch, model, identity, *, recovery_limit=8, opened=None):
    wire(wired, monkeypatch, model, recovery_limit=recovery_limit)
    body = {"message": model.dossier.message, "turn_id": identity}
    if opened is not None:
        body.update(matter_id=opened["matter_id"], chat_id=opened["chat_id"])
    response = client.post("/api/turn", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    saved = wired.store.load(
        data["matter_id"] or boundary.chat_matter_id("adv_demo", data["chat_id"])
    )
    conversation, _, _ = boundary._current_records(wired.store, saved)
    return data, saved, conversation


def evidence(
    identity,
    model,
    data,
    saved,
    expected,
    observed,
    *,
    scenario="faulty",
    protection_status="passed",
    claim_scope="mechanical",
    notes="",
):
    report = record_case(
        identity,
        boundary="POST /api/turn -> strict raw fabricated output -> independent checks "
        "-> atomic FileMatterStore save -> reopened record -> released reply",
        user_passage=model.dossier.message,
        model_outputs=model.outputs,
        calls=model.seen,
        expected=expected,
        observed=observed,
        scenario=scenario,
        protection_status=protection_status,
        claim_scope=claim_scope,
        notes=(
            "Semantic source, account, coverage and prose verdicts are explicitly fabricated; "
            "these tests qualify admission/recovery/save/release wiring, not real-model accuracy. "
            "Repository curated scenario spines are exact and hash-bound, not verbatim court "
            "findings or one authentic merged client file. " + notes
        ),
    )
    report["source_qualification"] = {
        "golden_case_ids": model.dossier.golden_ids,
        "source_entries": model.dossier.source_entries,
        "source_packet_sha256": hashlib.sha256(PACKET_PATH.read_bytes()).hexdigest(),
    }
    report["released_response"] = deepcopy(data)
    report["reopened_saved_matter"] = asdict(saved)
    directory = os.environ.get("NM_PRESSURE_EVIDENCE_DIR")
    if directory:
        (Path(directory) / (identity + ".json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n"
        )
    return report


# Each entry is a separately authored issue and source selection. Some curated
# scenarios contain no adverse conduct: their invented disputes are rejected,
# leaving accurate general material untouched. We do not manufacture a contested
# right merely to populate the board for every composite.
THREAD_ISSUES = (
    [
        (
            "GS-06",
            "police picked up my client last night",
            "Reported police custody",
            "What contested custody protection arises from the reported police pickup?",
            True,
        ),
        (
            "GS-07",
            "Remand extended for want of escort.",
            "Reported remand extension",
            "What challenge concerns the remand extension reportedly caused by lack of escort?",
            True,
        ),
        (
            "GS-16",
            "Two trespasses on one file: one in March 2024, one last week.",
            "Reported March trespass",
            "What independently contested conduct concerns the trespass reported in March 2024?",
            True,
        ),
        (
            "GS-16",
            "Two trespasses on one file: one in March 2024, one last week.",
            "Reported recent trespass",
            "What independently contested conduct concerns the trespass reported last week?",
            True,
        ),
    ],
    [
        (
            "GS-08",
            "the husband says the 1986 Act limits everything to iddat",
            "Contested maintenance position",
            "What maintenance claim is disputed by the husband's reported iddat-limit position?",
            True,
        ),
        (
            "GS-25",
            "their secretary signed, that is enough",
            "Invented Board refusal",
            "The Board refused sanction for this transaction.",
            False,
        ),
    ],
    [
        (
            "GS-09",
            "accused on a cheque he drew;",
            "Reported cheque accusation",
            "What accusation concerns the cheque the described accused drew?",
            True,
        ),
        (
            "GS-09",
            "respondent-employer in a dismissal;",
            "Reported employer dismissal thread",
            "What dismissal claim concerns the described respondent-employer?",
            True,
        ),
        (
            "GS-09",
            "tenant resisting eviction;",
            "Reported tenant eviction thread",
            "What eviction claim is resisted by the described tenant?",
            True,
        ),
        (
            "GS-09",
            "complainant in an assault on him;",
            "Reported assault complaint",
            "What claim concerns the assault on the described complainant?",
            True,
        ),
        (
            "GS-09",
            "plaintiff in his own recovery",
            "Reported recovery claim",
            "What recovery claim concerns the described plaintiff?",
            True,
        ),
        (
            "GS-11",
            "a fitter was dismissed",
            "Reported fitter dismissal",
            "What independently contestable dismissal concerns the reported fitter?",
            True,
        ),
    ],
    [
        (
            "GS-12",
            "neighbour grabbed his land and beat him up badly yesterday, injuring his knee",
            "Reported land grabbing",
            "What independently contested conduct concerns the neighbour's reported land grabbing?",
            True,
        ),
        (
            "GS-12",
            "neighbour grabbed his land and beat him up badly yesterday, injuring his knee",
            "Reported neighbour assault",
            "What claim concerns the neighbour's reported assault yesterday?",
            True,
        ),
        (
            "GS-10",
            "An eviction and a recovery between the same landlord and tenant are **two threads**.",
            "Reported landlord eviction",
            "What eviction claim concerns the described landlord and tenant?",
            True,
        ),
        (
            "GS-10",
            "An eviction and a recovery between the same landlord and tenant are **two threads**.",
            "Reported landlord recovery",
            "What recovery claim concerns the described landlord and tenant?",
            True,
        ),
    ],
    [
        (
            "GS-13",
            "bounced on 3 March, we sent notice",
            "Reported cheque bounce",
            "What contested cheque obligation follows the reported bounce and notice chronology?",
            True,
        )
    ],
    [
        (
            "GS-15",
            "sorry, 15-4-2024",
            "Invented instrument denial",
            "The seller denies signing this instrument.",
            False,
        )
    ],
    [
        (
            "GS-18",
            "he will not give it, can we say we lost it",
            "Reported original-record withholding",
            "What contested access concerns the original the reported custodian will not give?",
            True,
        )
    ],
    [
        (
            "GS-20",
            "The buyer is in possession under an unregistered agreement.",
            "Invented buyer eviction",
            "The seller forcibly evicted the buyer yesterday.",
            False,
        )
    ],
)


class ThreadGoldenModel(GoldenModel):
    """Explicitly owned disputes, semantic thread labels and a foreign-ID sibling."""

    def __init__(self, dossier):
        super().__init__(dossier, variant="thread_assignment")
        index = int(dossier.id.rsplit("-", 1)[1]) - 1
        self.issue_specs = THREAD_ISSUES[index]
        self.issue_rows = []
        self.dispute_coverage_sources = set()
        self.assignment_labels = {row["statement"]: [] for row in dossier.details}
        for case_id, exact_words, label, statement, accepted in self.issue_specs:
            source_ids = [
                identity
                for identity, exact in dossier.source_quotes.items()
                if exact_words in exact and (exact.startswith(case_id + " ") or case_id == "GS-09")
            ]
            assert len(source_ids) == 1, (case_id, exact_words, source_ids)
            source_id = source_ids[0]
            self.issue_rows.append(
                {
                    "statement": statement,
                    "source_id": source_id,
                    "basis": "attributed",
                    "importance": "central",
                    "why_material": "This issue has its own reported conduct and conclusion.",
                    "matter_scope": "proposed",
                    "label": label,
                    "identification": "identified",
                    "clarification": "",
                }
            )
            self.semantic_decisions[statement] = accepted
            self.semantic_sources[statement] = source_id
            if not accepted:
                continue
            self.dispute_coverage_sources.add(source_id)
            for detail in dossier.details:
                # The author supplies this relation in the fixture corpus.
                # Matching original quoted words here binds its exact ID only;
                # it is not a production classifier or a factual endorsement.
                if detail["source_id"] == source_id:
                    self.assignment_labels[detail["statement"]].append(label)
        # Additional independently declared same-thread contextual contributions.
        contextual_labels = {
            0: {"GS-06": ["Reported police custody"]},
            1: {"GS-08": ["Contested maintenance position"]},
            3: {"GS-12": ["Reported land grabbing"]},
            4: {"GS-13": ["Reported cheque bounce"]},
            6: {"GS-18": ["Reported original-record withholding"]},
        }.get(index, {})
        for detail in dossier.details:
            if self.assignment_labels[detail["statement"]]:
                continue
            for case_id, labels in contextual_labels.items():
                if detail["statement"].startswith("Supplied " + case_id + " "):
                    self.assignment_labels[detail["statement"]] = labels[:]
        if index == 2:
            for detail in dossier.details:
                if detail["statement"].startswith("Supplied GS-22 "):
                    self.assignment_labels[detail["statement"]] = [
                        "Reported cheque accusation",
                        "Reported employer dismissal thread",
                    ]
        if index == 3:
            # Both acts share an original quote but are assigned independently.
            for detail in dossier.details:
                if "neighbour grabbed his land yesterday" in detail["statement"]:
                    self.assignment_labels[detail["statement"]] = ["Reported land grabbing"]
                elif (
                    "neighbour beat him up badly yesterday" in detail["statement"]
                    or "the reported assault injured his knee" in detail["statement"]
                ):
                    self.assignment_labels[detail["statement"]] = ["Reported neighbour assault"]
        self.selected_assignment_ids = {}

    def _reader(self, operation, payload, schema):
        if operation == "extract_disputes":
            return {"new_items": deepcopy(self.issue_rows), "changes": []}
        original = payload.get("original_input", payload)
        if "repairs" in schema.get("properties", {}):
            # The invalid foreign assignment is a duplicate of an independently
            # retained valid row. Explicitly omit that failed duplicate only.
            return {
                "repairs": {
                    identity: {"proposals": []}
                    for identity in schema["properties"]["repairs"]["properties"]
                }
            }
        targets = original["assignment_targets"]
        rows = deepcopy(self.dossier.details)
        for row in rows:
            labels = self.assignment_labels[row["statement"]]
            identities = []
            for label in labels:
                matches = [
                    target["id"]
                    for target in targets
                    if target.get("record", {}).get("label") == label
                ]
                assert len(matches) == 1, (label, matches)
                identities.append(matches[0])
            row["assignment_ids"] = identities or ["matter:discussion"]
            self.selected_assignment_ids[row["statement"]] = identities
            self.semantic_attributes[row["statement"]].update(
                placement="disputes" if identities else "matter", dispute_ids=identities
            )
        wrong = deepcopy(rows[-1])
        wrong["assignment_ids"] = ["FOREIGN-UNOWNED-DISPUTE"]
        rows.append(wrong)
        return {"new_items": rows, "changes": []}
