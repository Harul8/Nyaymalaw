"""Actual saved work/scope/read journals; private rationale is not client approval."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from nm.legal_brain.verify.brain_assessment import captured_retrievals
from nm.legal_brain.verify.brain_finalization import FinalizationService, SavedCheckReader
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.legal_brain.retrieve.coverage_contracts import CoveragePosition, CoverageState
from nm.legal_brain.orchestrate.loop_contracts import digest
from nm.legal_brain.communicate.working_explanation import (
    CONSISTENCY_NAME,
    CRITERIA,
    DUTY_NAME,
    RATIONALE_NAME,
    WORKING_RATIONALE_SCHEMA,
    WorkingExplanationService,
)
from nm.open_matter import screens
from nm.shared.authority_contracts import Act, capacity_for, permits
from nm.shared.budget_contracts import Completion
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_port import ModelResult, Tier, Usage
from nm.shared.model_scripted import ScriptedModelAdapter
from tests.test_working_record_is_source_owned_and_independently_scoped import _case

pytestmark = pytest.mark.class_a


class RationaleJudge(ScriptedModelAdapter):
    def __init__(self, mutation=lambda value: value, *, consistency=None, duty=None):
        super().__init__(
            ModelConfig(
                {
                    tier: TierConfig(tier, "scripted", "private-rationale-judge", None, None)
                    for tier in (Tier.ROUTINE, Tier.HARD, Tier.JUDGE)
                }
            )
        )
        self.mutation, self.consistency, self.duty = mutation, consistency, duty
        self.prompts = []

    def structured(self, prompt, schema, tier, **_kwargs):
        self.prompts.append(prompt)
        name = schema["x-nm-read"]
        if name == RATIONALE_NAME:
            assert schema == WORKING_RATIONALE_SCHEMA
            packet = json.loads(prompt.user)
            subject = packet["subject"]
            value = self.mutation(
                {
                    "subject_identity": packet["subject_identity"],
                    "entries": [
                        {
                            "id": row["id"],
                            "package_identity": row["package_identity"],
                            **{
                                criterion: {
                                    "assessed": True,
                                    "reason": "Controlled exact-word judgment",
                                    "response_quote": row["text"],
                                    "instruction_quote": subject["inventory"][
                                        "original_instruction"
                                    ],
                                    "supporting_words": [],
                                }
                                for criterion in CRITERIA
                            },
                        }
                        for row in subject["entries"]
                    ],
                }
            )
        elif name == "consistency":
            value = self.consistency or {
                "claim_id": "",
                "quoted": "",
                "why": "Actual controlled candidate has no typed contradiction",
            }
        elif name == "duty":
            value = self.duty or {"ground": "clear", "quoted": "", "why": "", "lawful_section": ""}
        else:
            raise AssertionError("Unowned rationale checker schema")
        return ModelResult(
            None,
            value,
            tier,
            self.provider,
            self.resolved_model(tier),
            Usage(40, 40, 0.02),
            0,
            completion=Completion.COMPLETE,
        )

    def empty_decisive(self):
        if not hasattr(self, "retrievals") or not self.retrievals:
            raise ValueError("Actual retrieval observer was not installed")
        return tuple(
            str(index) for index, result in enumerate(self.retrievals) if not result.findings
        )

    def refused_reads(self):
        if not hasattr(self, "retrievals") or not self.retrievals:
            raise ValueError("Actual retrieval observer was not installed")
        return tuple(str(index) for index, result in enumerate(self.retrievals) if result.missing)


def _service(
    tmp_path,
    *,
    complete=True,
    annotated=True,
    mutation=lambda value: value,
    consistency=None,
    duty=None,
    observed=False,
):
    store, outcome, owner, working, scope, scopejudge, _verifier = _case(
        tmp_path, annotate=annotated
    )
    reviewed = working.review(outcome, budget=outcome.budget)
    wanted = tuple(
        row["id"]
        for row in (*reviewed.inventory.payload["areas"], *reviewed.inventory.payload["needs"])
        if (row.get("area") == "act_passages" or row.get("reference", {}).get("kind") == "source")
    )
    scopejudge.needed = wanted
    scopejudge.covered = wanted if complete else ()
    scoped = scope.review(
        outcome, budget=reviewed.review.budget if reviewed.review else outcome.budget
    )
    judge = RationaleJudge(mutation, consistency=consistency, duty=duty)
    reader = SavedCheckReader(
        store=store,
        log=working.reviewer.log,
        model=judge,
        session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03,
        current_tools_version=lambda: outcome.record.identity.tools_version,
        current_principles_version=lambda: outcome.record.identity.principles_version,
        subject_packages=owner.packages,
        max_tokens=4096,
    )
    finalizer = FinalizationService(
        reader=reader,
        today=lambda: date(2026, 9, 27),
        jurisdiction="Controlled known primary source",
    )
    if observed:
        judge.retrievals, _needs = captured_retrievals(outcome)

        class DeclaredControlledCoverage:
            def position(self, jurisdiction):
                # One explicitly declared synthetic source; not real jurisdiction coverage.
                held = {
                    finding.locator for result in judge.retrievals for finding in result.findings
                }
                return CoveragePosition(
                    CoverageState.MET if held == {"held:rule:1"} else CoverageState.UNMET,
                    jurisdiction,
                    "Measured sole declared controlled source population",
                    "2026-09-27",
                    outcome.record.identity.tools_version,
                )

        finalizer.coverage = DeclaredControlledCoverage()
        finalizer.authority = lambda matter, _outcome: permits(
            matter.advocate_id,
            capacity_for(
                matter.advocate_id,
                matter.authority_bindings,
                0,
                datetime(2026, 9, 27, tzinfo=timezone.utc),
            ),
            Act.ADVISE,
        )
    service = WorkingExplanationService(
        reader=reader, working=working, scope=scope, finalizer=finalizer
    )
    return store, outcome, service, judge, scoped.budget


def test_full_actual_controlled_population_releases_only_exact_checked_private_rationale(
    tmp_path, monkeypatch
):
    from tests import test_working_record_is_source_owned_and_independently_scoped as fixtures

    setup = fixtures._setup

    def admitted_setup(path):
        values = setup(path)
        store = values[0]
        matter = store.load("mat_loop")
        controlled_screens = tuple(
            screens.Screen(
                kind,
                screens.ScreenState.CLEAR,
                detail="Explicit controlled fixture admission; not live screening",
            )
            for kind in screens.ScreenKind
        )
        store.commit(
            replace(matter, screens=controlled_screens, version=matter.version + 1),
            expected_version=matter.version,
        )
        return values

    monkeypatch.setattr(fixtures, "_setup", admitted_setup)
    store, outcome, service, _judge, budget = _service(tmp_path, observed=True)
    result = service.review(outcome, budget=budget)
    assert result.private_ready, [
        (row.gate_id, row.assessed, row.reason)
        for row in (*result.outputs, *result.boundaries)
        if row.assessed is not True
    ]
    assert len(result.outputs) == 18 and len(result.boundaries) == 6
    actual = service.working.recorded(outcome)
    claims = {
        row.package_identity: package.claim
        for row in actual.checked_annotations
        for package in actual.review.result.released
        if package.identity == row.package_identity
    }
    assert all(row.text == claims[row.package_identity] for row in result.entries)
    preview = result.preview()
    assert preview["state"] == "checked_private_rationale" and preview["entries"]
    assert not preview["client_ready"] and not preview["normal_cutover"]
    assert "Controlled exact-word judgment" not in json.dumps(preview)
    assert not store.load("mat_loop").turn_receipts and not store.transcripts_for("mat_loop")
    assert service.recorded(outcome).preview() == preview


def test_current_source_scope_and_rationale_still_keep_missing_native_checks_unavailable(tmp_path):
    store, outcome, service, judge, budget = _service(tmp_path)
    result = service.review(outcome, budget=budget)
    assert result.wording_checked and result.scope_complete
    assert len(result.outputs) == 18 and len(result.boundaries) == 6
    assert not result.private_ready and not result.entries
    assert not result.client_ready and not result.normal_cutover
    preview = result.preview()
    assert preview["state"] == "unavailable" and preview["entries"] == []
    assert preview["checks"]["expected"] == preview["checks"]["present"] == 24
    assert preview["checks"]["not_assessed"] > 0
    assert "Controlled exact-word judgment" not in json.dumps(preview)
    assert len(judge.prompts) == 3
    children = [
        row
        for row in store.load("mat_loop").loop_records
        if row.identity.turn_id.startswith("work-parent:check:working_explanation")
    ]
    assert {row.identity.turn_id.rsplit(":", 1)[-1] for row in children} == {
        CONSISTENCY_NAME,
        DUTY_NAME,
        RATIONALE_NAME,
    }
    assert all(
        row.events[0].payload["parent"] == outcome.record.events[-1].fingerprint for row in children
    )
    assert all(row.events[-1].payload["released"] is False for row in children)
    assert not store.load("mat_loop").turn_receipts and not store.transcripts_for("mat_loop")
    assert service.recorded(outcome).preview() == preview


@pytest.mark.parametrize("annotated", [True, False])
def test_missing_coverage_or_annotations_cannot_buy_an_explanation_check(tmp_path, annotated):
    _store, outcome, service, judge, budget = _service(
        tmp_path, complete=False, annotated=annotated
    )
    result = service.review(outcome, budget=budget)
    assert not result.private_ready and not result.entries and not judge.prompts
    assert result.budget == budget and result.model_steps == 0


@pytest.mark.parametrize("assessed", [False, None])
def test_private_deliberation_or_unknown_wording_never_reaches_preview(tmp_path, assessed):
    def mutate(value):
        value["entries"][0]["rationale_not_deliberation"]["assessed"] = assessed
        value["entries"][0]["rationale_not_deliberation"]["reason"] = "PRIVATE CHECKER SCRATCH"
        return value

    _store, outcome, service, _judge, budget = _service(tmp_path, mutation=mutate)
    result = service.review(outcome, budget=budget)
    assert not result.wording_checked and result.preview()["entries"] == []
    assert "PRIVATE CHECKER SCRATCH" not in json.dumps(result.preview())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: {**value, "subject_identity": digest("foreign")},
        lambda value: {
            **value,
            "entries": [{**value["entries"][0], "package_identity": digest("foreign")}],
        },
        lambda value: {
            **value,
            "entries": [
                {
                    **value["entries"][0],
                    "faithful": {
                        **value["entries"][0]["faithful"],
                        "response_quote": "INVENTED CLEAN WORDS",
                    },
                }
            ],
        },
    ],
)
def test_exact_whole_rationale_word_contract_cannot_be_forged(tmp_path, mutation):
    _store, outcome, service, _judge, budget = _service(tmp_path, mutation=mutation)
    with pytest.raises((ReviewRefused, ValueError)) as refused:
        service.review(outcome, budget=budget)
    assert refused.value.budget.spend.cost_usd > budget.spend.cost_usd


def test_shared_allowance_serial_children_and_cached_rationale_do_not_reset_or_charge_twice(
    tmp_path,
):
    store, outcome, service, judge, budget = _service(tmp_path)
    result = service.review(outcome, budget=budget)
    assert result.budget.spend.children == budget.spend.children + 3
    assert result.budget.spend.cost_usd == pytest.approx(budget.spend.cost_usd + 0.06)
    assert result.budget.max_cost_usd == budget.max_cost_usd
    starts = [
        row.events[0].payload["budget"]
        for row in store.load("mat_loop").loop_records
        if row.identity.turn_id.startswith("work-parent:check:working_explanation")
    ]
    assert starts[0]["spend"]["cost_usd"] == pytest.approx(budget.spend.cost_usd)
    assert starts[1]["spend"]["cost_usd"] == pytest.approx(budget.spend.cost_usd + 0.02)
    assert starts[2]["spend"]["cost_usd"] == pytest.approx(budget.spend.cost_usd + 0.04)
    assert service.recorded(outcome).budget.spend == result.budget.spend
    with pytest.raises(ReviewRefused, match="restore actual"):
        service.review(outcome, budget=budget)
    calls = len(judge.prompts)
    repeated = service.review(outcome, budget=result.budget)
    assert len(judge.prompts) == calls
    assert repeated.budget == result.budget and repeated.model_steps == 0


def test_no_model_allowance_keeps_checks_missing_and_rationale_private(tmp_path):
    _store, outcome, service, judge, budget = _service(tmp_path)
    result = service.review(outcome, budget=budget, max_model_calls=0)
    assert not judge.prompts and result.model_steps == 0
    assert result.budget == budget and result.preview()["entries"] == []
    assert len(result.outputs) == 18 and len(result.boundaries) == 6


def test_incomplete_rationale_schema_is_withheld_with_its_actual_cost(tmp_path):
    _store, outcome, service, _judge, budget = _service(
        tmp_path, mutation=lambda value: {**value, "entries": []}
    )
    result = service.review(outcome, budget=budget)
    assert not result.wording_checked and result.preview()["entries"] == []
    assert result.budget.spend.cost_usd == pytest.approx(budget.spend.cost_usd + 0.06)


def test_changed_source_owner_or_author_word_checker_cannot_reuse_a_positive_channel(tmp_path):
    _store, outcome, service, _judge, budget = _service(tmp_path)
    service.review(outcome, budget=budget)
    service.working.owner.source_current = lambda *_: False
    with pytest.raises(ReviewRefused):
        service.recorded(outcome)


def test_rationale_reader_must_use_the_actual_working_package_owner(tmp_path):
    _store, _outcome, service, _judge, _budget = _service(tmp_path)
    service.reader.subject_packages = lambda *_: ()
    with pytest.raises(ValueError, match="actual"):
        WorkingExplanationService(
            reader=service.reader,
            working=service.working,
            scope=service.scope,
            finalizer=service.finalizer,
        )
