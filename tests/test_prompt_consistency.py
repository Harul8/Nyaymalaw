"""DG-17: prompt/consumer contracts, not a claim of semantic model quality.

Positive controls accompany rejected model outputs. The inventory includes inline
and user-context builders, so a new prompt cannot silently escape this review.
"""

import ast
import calendar
import importlib
import json
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from nm.core import adversarial, chronology, posture, theory
from nm.core.conversation import PRINCIPLES, guided
from nm.core.date_resolution import resolve
from nm.core.turn import _with_screens
from nm.domain.answer import Answer, Element, ElementKind, Mode, Route
from nm.domain.matter import Basis, Fact, Posture, Provenance, Role, Side, Thread
from nm.domain.metrics import TurnMetrics
from nm.domain.quotable import Quotable
from nm.domain.register import PEER
from nm.ports.model import Prompt

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 9, 22)

# A reviewed population, not one inferred from whatever happened to run.
SITES = {
    "accrual:build_prompt",
    "adversarial:build_attack_prompt",
    "adversarial:build_exposure_prompt",
    "adversarial:build_salvage_prompt",
    "cause:build_prompt",
    "chronology:build_prompt",
    "consistency:build_prompt",
    "consistency:repair_prompt",
    "dispute:build_prompt",
    "dispute:fixed_allocation_repair",
    "duty:build_prompt",
    "evidence_item:build_inventory_prompt",
    "factors:build_prompt",
    "investigation:run",
    "issues:build_prompt",
    "parties:build_prompt",
    "posture:build_role_prompt",
    "posture:build_prompt",
    "proof_read:build_prompt",
    "route:build_prompt",
    "requirements:build_prompt",
    "step_dependency:build_prompt",
    "theory:build_adverse_prompt",
    "theory:build_theory_prompt",
    "turn:_recommend",
    "turn:_courtesy",
}


def _sites(root):
    found = {}
    for path in root.glob("*.py"):
        for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                count = sum(
                    isinstance(n, ast.Call)
                    and (
                        (isinstance(n.func, ast.Name) and n.func.id == "Prompt")
                        or (isinstance(n.func, ast.Attribute) and n.func.attr == "Prompt")
                    )
                    for n in ast.walk(fn)
                )
                if count:
                    found[f"{path.stem}:{fn.name}"] = count
    return found


def test_all_production_prompt_sites_are_in_the_reviewed_population(tmp_path):
    found = _sites(ROOT / "backend/nm/core")
    assert found == dict.fromkeys(SITES, 1), found
    # This guard can fail: neither an empty scope nor a new call is a green pass.
    assert _sites(tmp_path) != dict.fromkeys(SITES, 1)
    (tmp_path / "new.py").write_text(
        'def unreviewed():\n    return model.Prompt(system="new rule", user="data")\n',
        encoding="utf-8",
    )
    added = _sites(tmp_path)
    assert added == {"new:unreviewed": 1}
    assert {**found, **added} != dict.fromkeys(SITES, 1)


def test_composed_systems_have_one_policy_owner_and_no_known_conflicting_rules():
    reviewed = []
    for name in sorted({site.split(":")[0] for site in SITES}):
        module = importlib.import_module(f"nm.core.{name}")
        for key, value in vars(module).items():
            if key.endswith("SYSTEM") and isinstance(value, str):
                system = guided(Prompt(system=value, user="source data")).system
                assert system.count(PRINCIPLES) == 1
                assert system.count(PEER) <= 1
                for conflict in (
                    "if you know when that festival",
                    "choose the closest",
                    "Every adverse fact MUST be either",
                    "would actually make",
                    "Almost every 'you lose'",
                    "cannot name any, mark it absent",
                    "they can read the section",
                    "A message that continues any of this",
                ):
                    assert conflict.casefold() not in system.casefold(), (name, key, conflict)
                reviewed.append((name, key))
    assert len(reviewed) == 19, reviewed


@pytest.mark.parametrize("month", range(1, 13))
def test_named_calendar_dates_are_reproducible_across_months(month):
    expected = date(2024, month, 29)
    assert resolve(f"29 {calendar.month_name[month]} 2024", TODAY) == expected
    assert resolve(f"{calendar.month_abbr[month]} 29, 2024", TODAY) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "last Deepavali",
        "last Eid",
        "last year",
        "before the hearing",
        "29 February 2025",
        "03/04/2026",
        "March 4",
    ],
)
def test_memory_or_ambiguous_calendar_claims_cannot_become_dates(expression):
    assert resolve(expression, TODAY) is None
    rows = chronology.interpret(
        Quotable(turn=f"The event occurred {expression}."),
        TODAY,
        {
            "events": [
                {
                    "event": "event",
                    "date_expression": expression,
                    "resolved": "2026-04-03",
                    "documented": False,
                }
            ]
        },
    )
    assert rows[0].state is chronology.DateState.UNDATED and rows[0].refused


@pytest.mark.parametrize("days", [0, 1, 28, 365])
def test_relative_date_arithmetic_is_checked_not_accepted_from_the_model(days):
    expression = f"{days} days ago"
    actual = TODAY - timedelta(days=days)
    row = {
        "event": "event",
        "date_expression": expression,
        "resolved": actual.isoformat(),
        "documented": False,
    }
    quotable = Quotable(turn=f"The event occurred {expression}.")
    assert chronology.interpret(quotable, TODAY, {"events": [row]})[0].on == actual
    row["resolved"] = (actual + timedelta(days=1)).isoformat()
    assert chronology.interpret(quotable, TODAY, {"events": [row]})[0].on is None


@pytest.mark.parametrize("instruction", ["", "2026-09-01", "an instruction from the old file"])
def test_a_different_date_or_old_instruction_cannot_silently_replace_a_fact(instruction):
    row = {
        "event": "event",
        "date_expression": "2026-09-01",
        "resolved": "2026-09-01",
        "corrects": "fact_old",
        "correction_instruction": instruction,
        "documented": False,
    }
    q = Quotable(
        turn="A separate account says 2026-09-01.", file="an instruction from the old file"
    )
    assert (
        chronology.interpret(q, TODAY, {"events": [row]}, frozenset({"fact_old"}))[0].corrects == ""
    )
    q = Quotable(turn="Replace my earlier date with 2026-09-01.")
    row["correction_instruction"] = "Replace my earlier date"
    assert (
        chronology.interpret(q, TODAY, {"events": [row]}, frozenset({"fact_old"}))[0].corrects
        == "fact_old"
    )


def test_a_date_from_memory_cannot_be_admitted_as_a_new_current_statement():
    q = Quotable(turn="I have nothing to add.", file="The date was 2026-09-01.")
    row = {"event": "event", "date_expression": "2026-09-01", "resolved": "2026-09-01"}
    assert chronology.interpret(q, TODAY, {"events": [row]})[0].on is None


def test_calendar_overflows_fail_closed_without_crashing_the_turn():
    assert resolve("tomorrow", date.max) is None
    assert resolve("yesterday", date.min) is None
    assert resolve("9" * 5000 + " days ago", TODAY) is None


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"exposures": None},
        {"exposures": [None]},
        {
            "exposures": [
                {
                    "from_thread": "thr_a",
                    "to_thread": "thr_missing",
                    "what": "x",
                    "consequence": "y",
                }
            ]
        },
        {
            "exposures": [
                {"from_thread": "thr_a", "to_thread": "thr_a", "what": "x", "consequence": "y"}
            ]
        },
    ],
)
def test_invalid_cross_dispute_output_is_never_a_clean_bill(bad):
    result = adversarial.read_exposures(bad, ("thr_a", "thr_b"))
    assert result is None
    assert (
        adversarial.cross_thread(("thr_a", "thr_b"), result).state
        is adversarial.ExposureState.NOT_RUN
    )
    assert (
        adversarial.cross_thread(
            ("thr_a", "thr_b"), adversarial.read_exposures({"exposures": []}, ("thr_a", "thr_b"))
        ).state
        is adversarial.ExposureState.NONE_FOUND
    )


def test_exposure_uses_substantive_positions_and_labels_its_output(tmp_path, monkeypatch):
    from nm.adapters.model.scripted import SCRIPTED_READS

    from tests.test_adversarial_on_a_served_turn import build

    engine, _ = build(tmp_path)
    threads = (
        Thread(id="thr_a", label="Recovery claim", chronology=("fact_a",)),
        Thread(id="thr_b", label="Cheque defence", chronology=("fact_b",)),
    )
    facts = tuple(
        Fact(
            id=f"fact_{letter}",
            statement=statement,
            provenance=Provenance(kind="advocate_statement", turn="turn"),
        )
        for letter, statement in (("a", "Money is due"), ("b", "Money was repaid"))
    )
    matter = SimpleNamespace(threads=threads, facts=facts)
    observed = []

    def read(user):
        observed.append(json.loads(user.split("THE DISPUTES ON THIS FILE:\n", 1)[1]))
        return json.dumps(
            {
                "exposures": [
                    {
                        "from_thread": "thr_a",
                        "to_thread": "thr_b",
                        "what": "thr_a asserts money is due",
                            "consequence": "thr_b disputes that position",
                            "from_fact": "fact_a", "to_fact": "fact_b",
                            "from_quote": "Money is due", "to_quote": "Money was repaid",
                    }
                ]
            }
        )

    monkeypatch.setitem(SCRIPTED_READS, "exposure", read)
    elements = engine._exposure(matter, TurnMetrics(turn_id="turn"))
    assert observed and all(p["facts"] for p in observed[0]["positions"])
    assert {f["statement"] for p in observed[0]["positions"] for f in p["facts"]} == {
        f.statement for f in facts
    }
    assert "Recovery claim" in elements[0].text and "thr_" not in elements[0].text
    assert not elements[0].disclosure, "model analysis cannot exempt itself from grounding"
    observed.clear()
    empty = engine._exposure(
        SimpleNamespace(threads=threads, facts=()), TurnMetrics(turn_id="empty")
    )
    assert not observed and "could not establish" in empty[0].text
    with pytest.raises(ValueError, match="unbound"):
        adversarial.labelled_text("thr_unknown asserts something", {"thr_a": "Claim"})


def test_scripted_exposure_double_reaches_a_positive_case_using_current_schema():
    from nm.adapters.model.scripted import scripted_exposure

    prompt = adversarial.build_exposure_prompt((("thr_a", "Recovery"), ("thr_b", "Cheque")))
    assert json.loads(scripted_exposure(prompt.user))["exposures"], (
        "old-format double silently returned empty"
    )


def _theory(**updates):
    row = {
        "theme": "A provisional position",
        "stance": "affirmative",
        "relief": "Requested relief",
        "explains": [],
        "concedes": [],
        "unresolved": [{"fact_id": "fact_a", "why": "Authenticity disputed"}],
        "revises_because": "The earlier interpretation was mistaken",
    }
    return {**row, **updates}


def test_unresolved_adverse_material_is_accounted_for_not_conceded_and_survives_storage():
    read = theory.read_theory(_theory(), "thr_a", Side.MOVING, ("fact_a",))
    assert read.theory and not read.theory.concedes and not read.theory.explains
    assert not theory.unaccounted(("fact_a",), read.theory)
    restored = theory.from_stored(asdict(read.theory))
    assert restored == read.theory and restored.revises_because
    assert restored.unresolved == {"fact_a": "Authenticity disputed"}


@pytest.mark.parametrize(
    "rows",
    [
        None,
        {},
        [None],
        [{"fact_id": "absent", "why": "reason"}],
        [{"fact_id": "fact_a", "why": ""}],
        [{"fact_id": "fact_a", "why": "x"}] * 2,
    ],
)
def test_malformed_unresolved_assessments_cannot_complete_a_theory(rows):
    read = theory.read_theory(_theory(unresolved=rows), "thr_a", Side.MOVING, ("fact_a",))
    assert read.theory is None and read.refused


def test_same_proposition_cannot_be_both_conceded_and_unresolved():
    read = theory.read_theory(_theory(concedes=["fact_a"]), "thr_a", Side.MOVING, ("fact_a",))
    assert read.theory is None and read.refused


@pytest.mark.parametrize("role", [Role.NOT_APPLICABLE, Role.NOT_INSTITUTED, Role.UNSUPPORTED])
def test_known_non_litigating_status_never_grants_a_litigating_side(role):
    assert role.value in posture.ROLE_VALUES
    p = Posture(role=role, basis=Basis.STATED)
    assert p.side is Side.UNKNOWN and not p.resolved


def test_role_read_sees_the_material_instruction_after_a_long_account():
    tail = "The proceedings have not been instituted."
    prompt = posture.build_role_prompt("Our client", "source " * 1000 + tail)
    assert tail in prompt.user
    assert "closest" not in prompt.system


@pytest.mark.parametrize("mode", [Mode.EXPLANATION, Mode.ASSESSMENT])
def test_purpose_allows_a_finding_without_fabricating_action_but_not_a_block_bypass(mode):
    finding = Element(
        kind=ElementKind.FINDING,
        text="The evidence presently supports only a conditional assessment.",
    )
    answer = Answer(route=Route.MATTER, mode=mode, mode_statement="Assessment", elements=(finding,))
    assert answer.elements == (finding,)
    with pytest.raises(ValueError):
        Answer(
            route=Route.MATTER,
            mode=mode,
            mode_statement="Blocked",
            elements=(finding,),
            blocked=True,
        )
    with pytest.raises(ValueError):
        Answer(
            route=Route.MATTER,
            mode=Mode.SHORT_QUESTION,
            mode_statement="Next step",
            elements=(finding,),
        )
    question = Element(kind=ElementKind.QUESTION, text="A later intake question")
    assert _with_screens([finding, question], SimpleNamespace(rows=()), mode=mode)[0] is finding
    blocking = Element(kind=ElementKind.QUESTION, text="Permission is required", gate="G-POSTURE")
    assert _with_screens([finding, blocking], SimpleNamespace(rows=()), mode=mode)[0] is blocking


@pytest.mark.parametrize("mode", ["explanation", "assessment"])
def test_purpose_reaches_the_served_answer_and_history_without_fabricating_a_recommendation(
    client, monkeypatch, mode
):
    from nm.adapters.model.scripted import SCRIPTED_READS, ScriptedModelAdapter
    from nm.edge.api import application

    monkeypatch.setitem(
        SCRIPTED_READS,
        "route",
        lambda _: json.dumps(
            {"discloses": "matter", "depth": mode, "why": "Only an explanation is requested"}
        ),
    )
    explanation = "The account alleges non-payment; that is not the same as documentary proof."
    original = ScriptedModelAdapter._respond
    composed = []

    def respond(self, prompt, tier):
        if "Answer the requested explanation or assessment" in (prompt.system or ""):
            composed.append(prompt)
            return explanation
        return original(self, prompt, tier)

    monkeypatch.setattr(ScriptedModelAdapter, "_respond", respond)
    monkeypatch.setitem(
        SCRIPTED_READS,
        "step_dependency",
        lambda user: json.dumps(
            {
                "step": json.loads(user)["step"],
                "dependence": "independent",
                "reason": "This response describes evidential status and directs no action.",
            }
        ),
    )
    result = client.post(
        "/api/turn",
        json={
            "message": "We act for the plaintiff supplier at Hyderabad. "
            "Explain the position on the unpaid goods.",
            "today": "2026-09-22",
        },
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["mode"] == mode
    assert composed and any(
        e["text"] == explanation and e["kind"] == "finding" for e in body["elements"]
    ), body
    assert not any(e["kind"] in {"action", "question"} for e in body["elements"]), body["elements"]
    history = client.get(f"/api/matters/{body['matter_id']}/transcript")
    assert history.status_code == 200 and mode in history.text and explanation in history.text
    assert application().store.transcripts_for(body["matter_id"])


def _descriptions(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "description":
                yield item
            else:
                yield from _descriptions(item)
    elif isinstance(value, list):
        for item in value:
            yield from _descriptions(item)


def test_actual_wire_schemas_do_not_reintroduce_the_old_prompt_instructions():
    from nm.core import accrual, evidence_item, factors, issues, proof_read
    from nm.ports.model import on_the_wire

    schemas = []
    forbidden = (
        "the status is `absent`",
        "required unless this is a denial",
        "question the court must answer",
        "article 54 runs from",
        "the whatsapp exchange",
        "the site engineer",
    )
    for name in sorted({site.split(":")[0] for site in SITES}):
        for key, schema in vars(importlib.import_module(f"nm.core.{name}")).items():
            if key.endswith("SCHEMA") and isinstance(schema, dict):
                descriptions = list(_descriptions(on_the_wire(schema)))
                for description in descriptions:
                    assert not any(term in description.casefold() for term in forbidden), (
                        name,
                        key,
                    )
                schemas.append((name, key))
    # Original 21, plus the dispute's answer contract and both requirement schemas.
    assert len(schemas) == 24, schemas
    assert ('requirements', 'SCHEMA') in schemas
    assert ('dispute', 'ANSWER_SCHEMA') in schemas
    closing = proof_read.PROOF_SCHEMA["properties"]["positions"]["items"]["properties"]
    assert "not_assessed" in closing["closing_material"]["description"]
    assert factors.FACTOR_SCHEMA["properties"]["in_writing"]["type"] == ["boolean", "null"]
    assert "cannot_tell" in factors.FACTOR_SCHEMA["properties"]["kind"]["enum"]
    assert "fact_id" in factors.build_prompt(Quotable(turn="context"), ()).user
    assert (
        "not_assessed" in evidence_item.INVENTORY_SYSTEM
        and "holder use unknown" in evidence_item.INVENTORY_SYSTEM
    )
    assert "advisory" in guided(issues.build_prompt(Quotable(turn="advisory work"))).system
    assert "Article 54" not in json.dumps(on_the_wire(accrual.ACCRUAL_SCHEMA))
    # A bad nested description remains visible at the actual transport boundary.
    bad = {
        "type": "object",
        "properties": {"nested": {"type": "string", "description": "the status is `absent`"}},
    }
    assert any(term in d.casefold() for d in _descriptions(on_the_wire(bad)) for term in forbidden)


@pytest.mark.parametrize("value", [None, "false", 0, {}])
def test_unknown_writing_never_becomes_an_oral_admission_or_a_legal_negative(value):
    from nm.core import factors

    from tests.test_factors import S18

    statement = "The other party admitted the outstanding amount."
    fact = Fact(
        id="fact_admission",
        statement=statement,
        provenance=Provenance(kind="advocate_statement", turn="turn"),
        date=date(2024, 6, 12),
    )
    row = {
        "kind": "acknowledgment",
        "fact_id": fact.id,
        "quoted": statement,
        "in_writing": value,
        "why": "The form is not supplied",
    }
    result = factors.read(row, (fact,), Quotable(turn=statement), {"18": S18}, TODAY)
    assert result.state == "not_assessed" and not result.factors
    assert "was not in writing" not in result.why_not
    assert "does not restart" not in result.why_not
    assert factors.read({}, (), Quotable(turn="nothing usable"), {}, None).state == "not_assessed"


@pytest.mark.parametrize("prior", [Role.NOT_INSTITUTED, Role.NOT_APPLICABLE])
def test_explicit_filing_progresses_but_inferred_progress_and_side_reversal_do_not(prior):
    before = Posture(role=prior, basis=Basis.STATED, client_described_as="client A")
    filed = before.enrich(Role.PLAINTIFF, Basis.STATED, source_fact="fact_filing")
    assert filed.role is Role.PLAINTIFF and filed.resolved and not filed.conflicts
    assert filed.client_described_as == before.client_described_as
    assert filed.source_fact == "fact_filing" and filed.version == before.version + 1
    inferred = before.enrich(Role.PLAINTIFF, Basis.INFERRED)
    assert inferred.role is prior and inferred.conflicts
    opposite = filed.enrich(Role.DEFENDANT, Basis.STATED)
    assert opposite.role is Role.PLAINTIFF and opposite.conflicts


@pytest.mark.parametrize("completion", ["complete", "length_limited", "not_established"])
def test_advice_repair_must_be_complete_before_it_can_be_used(tmp_path, monkeypatch, completion):
    from dataclasses import replace

    from nm.core.consistency import Claim
    from nm.domain.budget import Completion
    from nm.ports.model import Tier

    from tests.test_adversarial_on_a_served_turn import build

    engine, _ = build(tmp_path)
    model = engine._model
    response = model.complete(Prompt(system="controlled", user="source"), Tier.ROUTINE)
    response = replace(response, text="Preserve it only if", completion=Completion(completion))
    monkeypatch.setattr(model, "complete", lambda *args, **kwargs: response)
    text = engine._repair_step(
        "old step",
        Claim("test", "Known computed fact"),
        SimpleNamespace(why="The old step contradicts the fact"),
        TurnMetrics(turn_id="repair"),
    )
    assert text == (response.text if completion == "complete" else "")


@pytest.mark.parametrize("role", [Role.NOT_APPLICABLE, Role.NOT_INSTITUTED])
@pytest.mark.parametrize("mode", ["explanation", "a_question"])
def test_no_proceeding_does_not_force_a_filed_role_for_source_only_explanation(
    client, monkeypatch, role, mode
):
    from nm.adapters.model.scripted import SCRIPTED_READS

    message = (
        "I act for Client A. No proceeding has been instituted. Explain the relevant provisions."
    )
    monkeypatch.setitem(
        SCRIPTED_READS,
        "posture",
        lambda _: json.dumps(
            {
                "states_client": True,
                "role": role.value,
                "role_basis": "stated",
                "client_described_as": "Client A",
                "opponent": "",
                "quoted": message,
            }
        ),
    )
    monkeypatch.setitem(
        SCRIPTED_READS,
        "role",
        lambda _: json.dumps({"role": role.value, "why": "Expressly no proceeding"}),
    )
    monkeypatch.setitem(
        SCRIPTED_READS,
        "route",
        lambda _: json.dumps(
            {"discloses": "matter", "depth": mode, "why": "A bounded explanation is requested"}
        ),
    )
    response = client.post("/api/turn", json={"message": message, "today": "2026-09-22"})
    assert response.status_code == 200, response.text
    body = response.json()
    text = " ".join(e["text"] for e in body["elements"])
    assert "Did they file" not in text and "party moving, or the party answering" not in text
    assert not any(e["kind"] == "action" for e in body["elements"])
    if mode == "explanation":
        assert not body["blocked"], body
        assert "limited source explanation" in text
        assert not any(e["kind"] == "question" for e in body["elements"])
    else:
        assert body["blocked"] and "G-POSTURE" in body["blocked_reason"]


def test_an_advisory_issue_can_be_admitted_without_a_court_or_an_opponent():
    from nm.core import issues

    statement = "I need advice on the proposed agreement before execution."
    result = issues.read(
        {
            "issues": [
                {
                    "statement": "What does the proposed obligation require?",
                    "kind": "legal",
                    "runs_against": "unknown",
                    "quoted": statement,
                    "restates": "",
                }
            ]
        },
        "thr_advisory",
        Quotable(turn=statement),
    )
    assert len(result.issues) == 1 and not result.refused
    assert result.issues[0].runs_against is Side.UNKNOWN
