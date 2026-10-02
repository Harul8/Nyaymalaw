"""Automatic dispute research is source-linked, scoped, and paid for once."""
from __future__ import annotations

import json

import pytest

from nm.brain.turn import BrainRefused, BrainService, BrainTurn
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContextOverflow,
    ModelResult,
    OutputTruncated,
    ProviderUnavailable,
    SchemaViolation,
    Tier,
    Usage,
)
from nm.shared.store_file_store import FileMatterStore

FIRST = ("The supplier retained our tools. "
         "The customer withheld payment for the tools.")
DETAIL = "I have a signed delivery receipt for the tools."
ASIDE = "Hello again."


def _route(message: str, *, first: bool = False, aside: bool = False) -> dict:
    return {
        "items": [{
            "request": message,
            "relation": "new" if first else "aside" if aside else "changes",
            "matter_scope": "proposed" if first else "none" if aside else "current",
            "priority": "ordinary",
            "next_step": "answer" if aside else "legal_work",
            "reply": "Hello." if aside else "I will check the record and applicable law.",
            "clarification": "",
        }],
        "active_work_after": FIRST,
        "material_review": not aside,
        "opening": {
            "ready": first,
            "party_name": "",
            "subject": "Tools and payment dispute" if first else "",
            "summary": "The advocate reports two contested obligations." if first else "",
        },
    }


class Model:
    provider = "offline"

    def __init__(self, routes: list[dict]):
        self.routes = iter(routes)
        self.calls: list[tuple[str, dict]] = []

    def context_budget(self, tier):
        return 100_000

    def resolved_model(self, tier):
        return "offline"

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        self.calls.append((prompt.operation, payload))
        if prompt.operation == "interpret_conversation":
            data = next(self.routes)
        elif prompt.operation == "extract_disputes":
            data = {"disputes": self._disputes(payload)}
        elif prompt.operation == "verify_disputes":
            data = {"verdicts": [{
                "candidate_id": row["candidate_id"],
                "candidate_role": "independent_dispute",
                "verdict": "accept",
                "reason": "The reported conduct identifies a distinct dispute.",
            } for row in payload["candidates"]]}
        elif prompt.operation == "extract_legal_details":
            data = {"details": self._details(payload)}
        elif prompt.operation == "verify_material_grounding":
            data = {"verdicts": [{
                "candidate_id": row["candidate_id"],
                "verdict": "accept",
                "reason": "The proposal follows the advocate's attributed words.",
            } for row in payload["candidates"]]}
        elif prompt.operation == "decompose_disputes":
            data = {"plans": [{
                "dispute_id": row["dispute"]["id"],
                "queries": [{"text": phrase}
                            for phrase in ("contested conduct and obligation",
                                           "applicable statutory condition",
                                           "judicial treatment and proof")],
            } for row in payload["disputes"]]}
        elif prompt.operation == "read_legal_requirements":
            data = {"requirements": [self._requirement(row)
                                     for row in payload["disputes"]]}
        elif prompt.operation == "verify_legal_requirements":
            data = {"decisions": [{
                "candidate_id": candidate["candidate_id"],
                "label_verdict": "faithful",
                "label_reason": "The short heading restates the supported need.",
                "material_checks": [{
                    "material_id": material_id,
                    "verdict": "addresses",
                    "reason": "The reported detail concerns the item.",
                } for material_id in candidate["material_ids"]],
                "verdict": "supported",
                "source_checks": [{
                    "source_id": source["id"], "verdict": "supported",
                    "scope_status": "no_special_condition",
                    "support_fragment_id": source["fragments"][0]["id"],
                    "scope_fragment_id": "",
                    "reason": "The passage directly supports this item.",
                } for source in candidate["sources"]],
                "reason": "The cited passage directly supports this item.",
            } for candidate in payload["candidates"]]}
        else:
            raise AssertionError(f"unexpected model call: {prompt.operation}")
        return ModelResult(
            text=None, data=data, tier=Tier.ROUTINE, provider="offline",
            model="offline", usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE,
        )

    @staticmethod
    def _disputes(payload: dict) -> list[dict]:
        words = "".join(span["text"] for span in payload["latest_message_spans"])
        if words != FIRST:
            return []
        rows = []
        for span, label in zip(payload["latest_message_spans"],
                               ("Supplier retained tools", "Customer withheld payment"),
                               strict=True):
            rows.append({
                "statement": f"Whether the conduct described as {label.lower()} is lawful.",
                "source_id": span["id"], "relation": "new",
                "matter_scope": "proposed", "basis": "stated",
                "importance": "central",
                "why_material": "It calls for a distinct practical conclusion.",
                "label": label, "identification": "identified",
                "clarification": "", "related_dispute_ids": [],
            })
        return rows

    @staticmethod
    def _details(payload: dict) -> list[dict]:
        words = "".join(span["text"] for span in payload["latest_message_spans"])
        if words != DETAIL:
            return []
        dispute_id = next(row["id"] for row in payload["active_disputes"]
                          if row["label"] == "Supplier retained tools")
        return [{
            "kind": "evidence",
            "statement": "The advocate reports holding a signed delivery receipt.",
            "source_id": payload["latest_message_spans"][0]["id"],
            "prior_source_ids": [], "relation": "new",
            "matter_scope": "current", "basis": "stated",
            "importance": "relevant",
            "why_material": "It may bear on the tools dispute.",
            "placement": "disputes", "dispute_ids": [dispute_id],
            "related_material_ids": [],
        }]

    @staticmethod
    def _requirement(row: dict) -> dict:
        dispute_id = row["dispute"]["id"]
        linked = row["material"]
        candidate = row["candidates"][1 if linked else 0]
        return {
            "dispute_id": dispute_id,
            "label": "Keep signed receipt" if linked else "Establish the obligation",
            "need": "Preserve the reported receipt." if linked
            else "Establish the disputed obligation from the record.",
            "why": "The cited judgment discusses the receipt." if linked
            else "The cited provision states a condition.",
            "force": "strengthening" if linked else "required",
            "source_ids": [candidate["id"]],
            "material_ids": [linked[0]["id"]] if linked else [],
        }


class Search:
    def __init__(self, *, available: bool = True):
        self.available = available
        self.calls: list[tuple[dict, tuple[str, ...]]] = []

    def search_dispute(self, dispute: dict, queries: tuple[str, ...]) -> dict:
        self.calls.append((dispute, queries))
        if not self.available:
            return {"state": "unavailable", "candidates": [],
                    "diagnostics": ["Synthetic corpus is unavailable"]}
        dispute_id = dispute["id"]
        return {"state": "ok", "diagnostics": [], "candidates": [
            {"id": f"act:{dispute_id}", "kind": "provision",
             "title": "Synthetic Act", "locator": "section 3",
             "text": "The disputed obligation must be established."},
            {"id": f"case:{dispute_id}", "kind": "judgment",
             "title": "Synthetic Judgment", "locator": "paragraph 12",
             "text": "A signed receipt assisted proof in that case."},
        ]}


def _service(tmp_path, model: Model, search: Search):
    store = FileMatterStore(tmp_path, key="a-test-sealing-key")
    return BrainService(store, model, legal_search=search), store


def _send(brain: BrainService, message: str, turn_id: str, opened: dict | None = None):
    return brain.run(BrainTurn(
        advocate_id="adv", message=message, turn_id=turn_id,
        matter_id=opened["matter_id"] if opened else None,
        chat_id=opened["chat_id"] if opened else None,
    )).as_dict()


def test_identified_disputes_are_batched_and_requirements_keep_exact_sources(tmp_path):
    model = Model([_route(FIRST, first=True), _route(DETAIL),
                   _route(ASIDE, aside=True)])
    search = Search()
    brain, store = _service(tmp_path, model, search)

    first = _send(brain, FIRST, "first")
    assert first["metrics"]["llm_calls"] == 9
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "extract_disputes", "verify_disputes",
        "extract_legal_details", "verify_material_grounding",
        "decompose_disputes", "read_legal_requirements",
        "verify_legal_requirements", "verify_legal_requirements"]
    assert len(search.calls) == 2
    assert all(len(queries) == 3 for _, queries in search.calls)
    first_read = first["requirements_read"]
    assert len(first_read) == 2
    assert all(item["state"] == "ok" and len(item["rows"]) == 1
               for item in first_read)
    assert all(item["rows"][0]["record_status"] == "not_mentioned"
               for item in first_read)
    assert all(item["rows"][0]["sources"][0]["text"] ==
               "The disputed obligation must be established."
               for item in first_read)
    assert "I will check the record and applicable law" not in first["elements"][0]["text"]
    assert "Establish the obligation" in first["elements"][0]["text"]
    plans = next(payload for operation, payload in model.calls
                 if operation == "decompose_disputes")
    assert [row["text"] for row in plans["conversation"] if
            row["role"] == "advocate"] == [FIRST]
    assert len(plans["disputes"]) == 2

    second = _send(brain, DETAIL, "second", first)
    assert second["metrics"]["llm_calls"] == 7
    assert len(search.calls) == 3
    assert search.calls[-1][0]["label"] == "Supplier retained tools"
    assert len(second["requirements_read"]) == 1
    assert second["requirements_read"][0]["rows"][0]["record_status"] == "mentioned"
    assert second["requirements_read"][0]["rows"][0]["sources"][0]["text"] == \
        "A signed receipt assisted proof in that case."
    second_plan = [payload for operation, payload in model.calls
                   if operation == "decompose_disputes"][1]
    assert [row["text"] for row in second_plan["conversation"] if
            row["role"] == "advocate"] == [FIRST, DETAIL]
    assert len(second_plan["disputes"]) == 1

    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record
    from nm.brain.requirements_state import requirements_record

    saved = store.load(first["matter_id"])
    disputes = proposed_disputes(saved)
    material = material_record(saved, disputes=disputes)
    requirements = requirements_record(saved, disputes=disputes, material=material)
    assert requirements["state"] == "ok"
    assert set(requirements["status_by_dispute"].values()) == {"ok"}
    by_label = {dispute["label"]: requirements["by_dispute"][dispute["id"]]
                for dispute in disputes["rows"]}
    assert by_label["Supplier retained tools"][0]["label"] == "Keep signed receipt"
    assert by_label["Customer withheld payment"][0]["label"] == \
        "Establish the obligation"

    before = len(model.calls), len(search.calls)
    aside = _send(brain, ASIDE, "third", first)
    assert aside["metrics"]["llm_calls"] == 1
    assert (len(model.calls), len(search.calls)) == (before[0] + 1, before[1])
    replay = _send(brain, ASIDE, "third", first)
    assert replay["replayed"] and replay["metrics"]["llm_calls"] == 0
    assert (len(model.calls), len(search.calls)) == (before[0] + 1, before[1])


def test_unavailable_corpus_never_yields_a_requirement(tmp_path):
    model = Model([_route(FIRST, first=True)])
    search = Search(available=False)
    brain, store = _service(tmp_path, model, search)

    opened = _send(brain, FIRST, "first")
    assert opened["metrics"]["llm_calls"] == 6
    assert [operation for operation, _ in model.calls][-1] == "decompose_disputes"
    assert len(search.calls) == 2
    assert len(opened["requirements_read"]) == 2
    assert all(row["state"] == "unavailable" and row["rows"] == []
               for row in opened["requirements_read"])

    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record
    from nm.brain.requirements_state import requirements_record

    saved = store.load(opened["matter_id"])
    disputes = proposed_disputes(saved)
    material = material_record(saved, disputes=disputes)
    projected = requirements_record(saved, disputes=disputes, material=material)
    assert projected["state"] == "ok"
    assert all(value == "unavailable" for value in
               projected["status_by_dispute"].values())
    assert all(rows == [] for rows in projected["by_dispute"].values())
    assert "Synthetic corpus is unavailable" in projected["diagnostics"]


def test_rejected_dispute_proposal_does_not_hide_accepted_peer(tmp_path):
    class OneRejectedProposal(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            if prompt.operation == "verify_disputes":
                payload = json.loads(prompt.user)
                self.calls.append((prompt.operation, payload))
                return ModelResult(
                    text=None,
                    data={"verdicts": [{
                        "candidate_id": row["candidate_id"],
                        "candidate_role": "evidence_gap_or_question" if index == 0
                        else "independent_dispute",
                        "verdict": "reject" if index == 0 else "accept",
                        "reason": "Independent attributed decision.",
                    } for index, row in enumerate(payload["candidates"])]},
                    tier=tier, provider="offline", model="offline",
                    usage=Usage(0, 0, 0), latency_ms=0,
                    completion=Completion.COMPLETE)
            return super().structured(prompt, schema, tier,
                                      max_tokens=max_tokens)

    model = OneRejectedProposal([_route(FIRST, first=True)])
    brain, store = _service(tmp_path, model, Search())

    opened = _send(brain, FIRST, "one-rejected")
    from nm.brain.dispute_state import proposed_disputes

    saved = store.load(opened["matter_id"])
    rows = proposed_disputes(saved)["rows"]
    assert [row["label"] for row in rows] == ["Customer withheld payment"]
    assert len(opened["requirements_read"]) == 1
    assert opened["requirements_read"][0]["state"] == "ok"
    assert opened["metrics"]["llm_calls"] == 8


def test_dispute_verifier_outage_refuses_before_turn_is_saved(tmp_path):
    class VerificationUnavailable(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            if prompt.operation == "verify_disputes":
                raise ProviderUnavailable("synthetic verification outage")
            return super().structured(prompt, schema, tier,
                                      max_tokens=max_tokens)

    model = VerificationUnavailable([_route(FIRST, first=True)])
    brain, store = _service(tmp_path, model, Search())

    with pytest.raises(BrainRefused) as refusal:
        _send(brain, FIRST, "unverified-opening")
    assert refusal.value.committed == "not_committed"
    assert store.list_for("adv").matters == ()


def test_one_verifier_failure_keeps_other_disputes_checked_work(tmp_path):
    class OneVerificationFailure(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            if prompt.operation == "verify_legal_requirements":
                payload = json.loads(prompt.user)
                if payload["dispute"]["label"] == "Supplier retained tools":
                    self.calls.append((prompt.operation, payload))
                    raise OutputTruncated("synthetic verifier response incomplete")
            return super().structured(prompt, schema, tier,
                                      max_tokens=max_tokens)

    model = OneVerificationFailure([_route(FIRST, first=True)])
    brain, store = _service(tmp_path, model, Search())

    opened = _send(brain, FIRST, "first")
    assert opened["metrics"]["llm_calls"] == 9
    reads = opened["requirements_read"]
    failed, checked = reads
    assert failed["state"] == "unavailable" and failed["rows"] == []
    assert "OutputTruncated" in failed["diagnostics"][0]
    assert checked["state"] == "ok" and len(checked["rows"]) == 1
    assert checked["rows"][0]["sources"][0]["text"] == \
        "The disputed obligation must be established."
    reply = opened["elements"][0]["text"]
    assert "Establish the obligation (Customer withheld payment)" in reply
    assert "Establish the obligation (Supplier retained tools)" not in reply
    assert "incomplete for 1 dispute" in reply

    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record
    from nm.brain.requirements_state import requirements_record

    saved = store.load(opened["matter_id"])
    disputes = proposed_disputes(saved)
    material = material_record(saved, disputes=disputes)
    projected = requirements_record(saved, disputes=disputes, material=material)
    assert projected["status_by_dispute"][failed["dispute_id"]] == "unavailable"
    assert projected["by_dispute"][failed["dispute_id"]] == []
    assert projected["status_by_dispute"][checked["dispute_id"]] == "ok"
    assert len(projected["by_dispute"][checked["dispute_id"]]) == 1


@pytest.mark.parametrize("operation", [
    "decompose_disputes", "read_legal_requirements"])
@pytest.mark.parametrize("failure", [
    SchemaViolation, ContextOverflow, OutputTruncated])
def test_content_local_batch_failure_keeps_other_disputes_research(
        tmp_path, operation, failure):
    class OneDisputeFails(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            if prompt.operation == operation:
                payload = json.loads(prompt.user)
                original = payload.get("original_input", payload)
                if any(row["dispute"]["label"] == "Supplier retained tools"
                       for row in original["disputes"]):
                    self.calls.append((prompt.operation, original))
                    raise failure("synthetic content-local failure")
            return super().structured(prompt, schema, tier,
                                      max_tokens=max_tokens)

    model = OneDisputeFails([_route(FIRST, first=True)])
    brain, store = _service(tmp_path, model, Search())
    opened = _send(brain, FIRST, "first")

    failed, checked = opened["requirements_read"]
    assert failed["state"] == "unavailable" and failed["rows"] == []
    assert failure.__name__ in failed["diagnostics"][0]
    assert checked["state"] == "ok" and len(checked["rows"]) == 1
    assert "Establish the obligation (Customer withheld payment)" in \
        opened["elements"][0]["text"]
    assert "incomplete for 1 dispute" in opened["elements"][0]["text"]
    assert opened["metrics"]["llm_calls"] == (
        12 if failure is SchemaViolation else 10)

    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record
    from nm.brain.requirements_state import requirements_record

    saved = store.load(opened["matter_id"])
    disputes = proposed_disputes(saved)
    material = material_record(saved, disputes=disputes)
    projected = requirements_record(saved, disputes=disputes, material=material)
    assert projected["status_by_dispute"][failed["dispute_id"]] == "unavailable"
    assert projected["status_by_dispute"][checked["dispute_id"]] == "ok"
    assert len(projected["by_dispute"][checked["dispute_id"]]) == 1


@pytest.mark.parametrize("operation", [
    "decompose_disputes", "read_legal_requirements"])
def test_provider_outage_does_not_fan_out_into_dispute_retries(
        tmp_path, operation):
    class SharedOutage(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            if prompt.operation == operation:
                self.calls.append((prompt.operation, json.loads(prompt.user)))
                raise ProviderUnavailable("synthetic shared outage")
            return super().structured(prompt, schema, tier,
                                      max_tokens=max_tokens)

    model = SharedOutage([_route(FIRST, first=True)])
    brain, _ = _service(tmp_path, model, Search())
    opened = _send(brain, FIRST, "first")

    assert opened["metrics"]["llm_calls"] == (
        6 if operation == "decompose_disputes" else 7)
    assert sum(name == operation for name, _ in model.calls) == 1
    assert len(opened["requirements_read"]) == 2
    assert all(read["state"] == "unavailable" and not read["rows"]
               for read in opened["requirements_read"])


def test_invalid_one_dispute_projection_preserves_other_checked_read(
        tmp_path, monkeypatch):
    from nm.brain import turn as brain_turn

    original = brain_turn._legal_reads

    def one_damaged_read(*args, **kwargs):
        reads = original(*args, **kwargs)
        reads[0]["rows"][0]["sources"][0]["verification"]["support_excerpt"] = \
            "Words absent from the saved source passage"
        return reads

    monkeypatch.setattr(brain_turn, "_legal_reads", one_damaged_read)
    model = Model([_route(FIRST, first=True)])
    brain, store = _service(tmp_path, model, Search())
    opened = _send(brain, FIRST, "first")

    assert opened["metrics"]["llm_calls"] == 9
    assert len(opened["requirements_read"]) == 1
    surviving = opened["requirements_read"][0]
    assert surviving["rows"][0]["label"] == "Establish the obligation"
    assert "Establish the obligation (Customer withheld payment)" in \
        opened["elements"][0]["text"]

    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record
    from nm.brain.requirements_state import requirements_record

    saved = store.load(opened["matter_id"])
    disputes = proposed_disputes(saved)
    material = material_record(saved, disputes=disputes)
    projected = requirements_record(saved, disputes=disputes, material=material)
    assert projected["status_by_dispute"][surviving["dispute_id"]] == "ok"
    assert len(projected["by_dispute"][surviving["dispute_id"]]) == 1


def test_corrupt_saved_source_hides_only_its_disputes_requirements(tmp_path):
    model = Model([_route(FIRST, first=True)])
    brain, store = _service(tmp_path, model, Search())
    opened = _send(brain, FIRST, "first")
    saved = store.load(opened["matter_id"])
    reads = saved.brain_chat[0]["response"]["requirements_read"]
    damaged_id = reads[0]["dispute_id"]
    sound_id = reads[1]["dispute_id"]
    reads[0]["rows"][0]["sources"][0]["text"] = ""

    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record
    from nm.brain.requirements_state import requirements_record

    disputes = proposed_disputes(saved)
    material = material_record(saved, disputes=disputes)
    projected = requirements_record(saved, disputes=disputes, material=material)
    assert projected["state"] == "incomplete"
    assert projected["status_by_dispute"][damaged_id] == "unavailable"
    assert projected["by_dispute"][damaged_id] == []
    assert projected["status_by_dispute"][sound_id] == "ok"
    assert len(projected["by_dispute"][sound_id]) == 1


def test_saved_verifier_excerpts_are_rechecked_against_source_text(tmp_path):
    model = Model([_route(FIRST, first=True)])
    brain, store = _service(tmp_path, model, Search())
    opened = _send(brain, FIRST, "first")
    saved = store.load(opened["matter_id"])
    reads = saved.brain_chat[0]["response"]["requirements_read"]
    damaged_id = reads[0]["dispute_id"]
    sound_id = reads[1]["dispute_id"]
    source = reads[0]["rows"][0]["sources"][0]
    source["verification"]["support_excerpt"] = "Words absent from the passage"

    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record
    from nm.brain.requirements_state import requirements_record

    disputes = proposed_disputes(saved)
    material = material_record(saved, disputes=disputes)
    projected = requirements_record(saved, disputes=disputes, material=material)
    assert projected["status_by_dispute"][damaged_id] == "unavailable"
    assert projected["by_dispute"][damaged_id] == []
    assert projected["status_by_dispute"][sound_id] == "ok"


def test_partial_search_retains_verified_rows_and_diagnostics(tmp_path):
    model = Model([_route(FIRST, first=True)])
    brain, store = _service(tmp_path, model, Search())
    opened = _send(brain, FIRST, "first")
    saved = store.load(opened["matter_id"])
    read = saved.brain_chat[0]["response"]["requirements_read"][0]
    read["state"] = "partial"
    read["diagnostics"] = ["judgment search unavailable"]

    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record
    from nm.brain.requirements_state import requirements_record

    disputes = proposed_disputes(saved)
    material = material_record(saved, disputes=disputes)
    projected = requirements_record(saved, disputes=disputes, material=material)
    dispute_id = read["dispute_id"]
    assert projected["status_by_dispute"][dispute_id] == "partial"
    assert len(projected["by_dispute"][dispute_id]) == 1
    assert projected["diagnostics_by_dispute"][dispute_id] == [
        "judgment search unavailable"]


def test_pre_verification_legal_items_are_not_displayed_as_checked(tmp_path):
    model = Model([_route(FIRST, first=True)])
    brain, store = _service(tmp_path, model, Search())
    opened = _send(brain, FIRST, "first")
    saved = store.load(opened["matter_id"])
    reads = saved.brain_chat[0]["response"]["requirements_read"]
    old_id = reads[0]["dispute_id"]
    current_id = reads[1]["dispute_id"]
    reads[0].pop("verification")

    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record
    from nm.brain.requirements_state import requirements_record

    disputes = proposed_disputes(saved)
    material = material_record(saved, disputes=disputes)
    projected = requirements_record(saved, disputes=disputes,
                                    material=material)
    assert projected["status_by_dispute"][old_id] == "unavailable"
    assert projected["by_dispute"][old_id] == []
    assert projected["status_by_dispute"][current_id] == "ok"
    assert projected["by_dispute"][current_id]
    assert "saved legal items predate independent source verification" in \
        projected["diagnostics"]


def test_served_matter_board_exposes_short_requirements_beneath_disputes(
        client, wired, monkeypatch):
    model = Model([_route(FIRST, first=True)])
    wired.legal_search = Search()
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    served = client.post("/api/turn", json={"message": FIRST,
                                            "turn_id": "requirements-first"})
    assert served.status_code == 200, served.text
    opened = served.json()
    assert opened["metrics"]["llm_calls"] == 9

    board_response = client.get(f"/api/matters/{opened['matter_id']}")
    assert board_response.status_code == 200, board_response.text
    board = board_response.json()
    dispute_rows = board["proposed_disputes"]["rows"]
    requirements = board["requirements_record"]
    assert len(dispute_rows) == 2
    assert requirements["state"] == "ok"
    assert all(requirements["status_by_dispute"][row["id"]] == "ok"
               for row in dispute_rows)
    assert all(requirements["by_dispute"][row["id"]][0]["label"] ==
               "Establish the obligation" for row in dispute_rows)
    assert all(requirements["by_dispute"][row["id"]][0]["sources"][0]["kind"]
               == "provision" for row in dispute_rows)
