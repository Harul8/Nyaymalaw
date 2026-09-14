"""A TOOL THAT WRITES EVIDENCE RECORDS CAN MANUFACTURE THEM.
BK-21-AC3, BK-42-AC1/AC9, BK-81-AC2, BK-85-AC5, BK-88-AC3.

WHAT THIS DEFENDS
-------------------
Twenty-two criteria carry a row no test can close, so `pipeline/quality/measure.py` gives
each one a command. That is useful and it is also the most dangerous thing in
the repository: the outstanding rows are exactly the ones that say this build
is not releasable, and a command that writes them is a command that can make
them go away.

So the tool is allowed to do two things and nothing else. It PREPARES a
protocol that confers nothing, or it PROMOTES an exact schema-2 record only
after the configured verifier authenticates both payload and authority. It may
never decide that something passed. The parametrised test below includes both
local names and plausible production-looking names: vocabulary is not proof.

    If that check ever comes out permissive, every NOT RUN in the register
    becomes a PASS somebody can type.

WHAT THIS SUITE CANNOT ESTABLISH
----------------------------------
That any measurement happened. It proves the machinery refuses; the rows stay
NOT RUN until somebody runs the commands somewhere real.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from nm.domain.deployment import (
    STRUCTURED_LEVELS,
    Candidate,
    EvidenceRecord,
    OperationState,
    refuse_record,
)

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
TODAY = "2026-09-14"


def _record(**kw) -> EvidenceRecord:
    base = dict(criterion="BK-42-AC3", level="production_measure",
                subject="a restore into an isolated environment",
                method="observed on the target", actor="ops-lead",
                observed_at=TODAY, result="PASS")
    base.update(kw)
    return EvidenceRecord(**base)


def _deployed() -> Candidate:
    return Candidate(commit="a" * 40, environment="ap-south-1-prod",
                     config_digest="cfg-1",
                     operation_state=OperationState.VERIFIED)


# ====== 1. a production measure cannot be written from this machine ========

@pytest.mark.parametrize("environment", Candidate.LOCAL + (
    "prod", "production", "ap-south-1-prod", " PROD ", "verified",
    "customer-live",
))
def test_no_environment_this_build_can_create_may_write_a_production_measure(
        environment):
    """THE ONE THAT MATTERS. Every outstanding production measure says this
    build is not releasable; a permissive answer here turns all of them into
    a PASS somebody can type."""
    here = Candidate(commit="a" * 40, environment=environment)
    why = refuse_record(_record(), about=here, observed=True)
    assert any("not a deployment" in one or "local" in one
               for one in why), (environment, why)


def test_domain_shape_alone_cannot_permit_a_pass_even_on_a_deployment():
    """Authentication is a verifier result, not another trusted boolean."""
    why = refuse_record(_record(), about=_deployed(), observed=True)
    assert any("domain object cannot authenticate" in one for one in why), why


def test_a_pass_nobody_observed_is_refused():
    why = refuse_record(_record(), about=_deployed(), observed=False)
    assert any("never from an intention" in one for one in why), why


def test_a_record_that_did_not_pass_needs_no_observation():
    """NOT_RUN is the honest default and must stay writable, or the register
    cannot record that a measurement is outstanding."""
    assert refuse_record(_record(result="NOT_RUN"), about=_deployed(),
                         observed=False) == ()


def test_the_default_result_is_not_run_and_not_pass():
    """The direction of the default is the whole argument: a record somebody
    forgot to fill in must read as unmeasured rather than as met."""
    assert EvidenceRecord(
        criterion="BK-1-AC1", level="counsel_review", subject="s",
        method="m", actor="a", observed_at=TODAY).result == "NOT_RUN"


# ============ 2. the other ways a record can be dishonest ==================

def test_a_review_of_ones_own_work_is_not_an_independent_one():
    why = refuse_record(
        _record(level="counsel_review", actor="ops-lead"),
        about=_deployed(), observed=True, operator="ops-lead")
    assert any("not an independent one" in one for one in why), why


def test_another_name_does_not_authenticate_a_review():
    why = refuse_record(
        _record(level="counsel_review", actor="senior counsel"),
        about=_deployed(), observed=True, operator="ops-lead")
    assert any("domain object cannot authenticate" in one for one in why), why


def test_a_plausible_record_without_authentication_is_still_refused():
    why = refuse_record(_record(), about=_deployed(), observed=True)
    assert any("cannot authenticate" in one for one in why), why


def test_an_undated_observation_cannot_be_bound_to_anything():
    why = refuse_record(_record(observed_at="recently"), about=_deployed(),
                        observed=True)
    assert any("not a date" in one for one in why), why


def test_a_level_that_is_not_a_signed_record_is_refused():
    """`domain_test` comes from running the test, not from writing a file.
    A record claiming one would be a test result nobody ran."""
    for level in ("domain_test", "integration_test", "browser_journey"):
        why = refuse_record(_record(level=level), about=_deployed(),
                            observed=True)
        assert any("not a structured evidence level" in one for one in why)
    assert set(STRUCTURED_LEVELS) == {
        "model_eval", "counsel_review", "production_measure"}


def test_every_field_of_a_record_is_required():
    for blanked in ("criterion", "level", "subject", "method", "actor",
                    "observed_at"):
        with pytest.raises(ValueError):
            _record(**{blanked: "   "})


# ============ 3. the tool itself refuses from here =========================

def _run(*argv) -> int:
    from pipeline.quality.measure import main

    return main(list(argv))


@pytest.mark.parametrize("environment", (
    "working_tree", "prod", "production", "ap-south-1-prod", " PROD ",
    "verified", "customer-live",
))
def test_the_command_only_prepares_a_protocol_for_any_typed_environment(
        monkeypatch, tmp_path, capsys, environment):
    """No vocabulary guess turns a command-line label into deployment proof."""
    from pipeline.quality import measure

    evidence, packs = tmp_path / "evidence", tmp_path / "packs"
    monkeypatch.setattr(measure, "EVIDENCE", evidence)
    monkeypatch.setattr(measure, "PACKS", packs)
    assert _run("--environment", environment, "production",
                "--criterion", "BK-42-AC3") == 0
    said = capsys.readouterr().out
    assert "remains UNVERIFIED" in said
    made = list(packs.iterdir())
    assert made, "the command did not produce its protocol"
    protocol = json.loads(made[0].read_text(encoding="utf-8"))
    assert "carries no PASS" in protocol["note"]
    assert not evidence.exists(), "a protocol command wrote evidence"


def _sealed(monkeypatch, tmp_path, **env):
    """Drive `seal` against a CONTROLLED environment.

    Hermetic on purpose. A first version read whatever the machine happened to
    hold and skipped when it held nothing -- and a skip inside Class-A is a
    node that did not pass wearing a green tick, which is the defect this file
    is about, one level up.
    """
    import os

    from pipeline.quality import measure

    monkeypatch.setattr(measure, "load_dotenv", lambda *a, **k: None,
                        raising=False)
    monkeypatch.setattr("nm.adapters.model.config.load_dotenv",
                        lambda *a, **k: None)
    for name in list(os.environ):
        if name == "NM_MATTER_KEY" or any(
                w in name.upper() for w in measure.CREDENTIAL):
            monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(measure, "EVIDENCE", tmp_path)
    return measure.main(["seal"]), tmp_path


def test_an_unset_seal_is_not_assessed_rather_than_passing(monkeypatch,
                                                           tmp_path, capsys):
    """BK-21-AC3 where no key is configured. An absent value cannot show a
    separation that was never at risk, so this is neither pass nor fail."""
    code, _ = _sealed(monkeypatch, tmp_path)
    assert code == 2
    assert "NOT ASSESSED" in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_a_shared_seal_fails_and_names_the_variable_not_the_value(
        monkeypatch, tmp_path, capsys):
    """The mutation BK-21-AC3 names: the previous .env, where the matter key
    equalled the model key."""
    secret = "sk-proj-the-same-string-in-two-places"
    code, _ = _sealed(monkeypatch, tmp_path, NM_MATTER_KEY=secret,
                      NM_MODEL_API_KEY=secret)
    assert code == 1
    said = capsys.readouterr().out
    assert "NM_MODEL_API_KEY" in said
    assert secret not in said
    assert "rotating first" in said
    assert not list(tmp_path.iterdir())


def test_a_separated_seal_is_observed_and_still_closes_nothing(
        monkeypatch, tmp_path, capsys):
    """THE POSITIVE CONTROL, and the honest limit beside it.

    The check passes and BK-21-AC3 stays BLOCKED, because its required method
    is a domain test and a hermetic Class-A node cannot carry a statement
    about whatever machine it runs on. A command that wrote a record here
    would be evidence of the wrong kind wearing the right name -- which is
    what `refuse_record` caught when this was first built the other way.
    """
    code, out = _sealed(monkeypatch, tmp_path,
                        NM_MATTER_KEY="a-seal-value-nothing-else-holds",
                        NM_MODEL_API_KEY="an-entirely-different-value")
    assert code == 0
    said = capsys.readouterr().out
    assert "OBSERVED" in said and "by digest" in said
    assert "STAYS BLOCKED" in said
    assert "a-seal-value" not in said
    assert "an-entirely-different-value" not in said
    assert not list(tmp_path.iterdir()), "the check must write no evidence"


def test_the_seal_command_never_puts_a_value_in_its_record():
    """The method line names the comparison, never the thing compared."""
    import inspect

    from pipeline.quality import measure

    source = inspect.getsource(measure.seal)
    assert "shares_value_with" in source
    assert "No value is printed" in source
    for leak in ("key}", "{key", "population}", "= key)"):
        assert leak not in source, leak


# ============ 4. the packs carry the protocol and confer nothing ===========

def test_the_review_pack_carries_the_declared_protocol(tmp_path, capsys):
    assert _run("review-pack", "--criterion", "BK-42-AC9") == 0
    pack = json.loads(
        (ROOT / ".nm" / "packs" / "BK-42-AC9-REVIEW-LEGAL.json")
        .read_text(encoding="utf-8"))
    protocol = next(
        row for row in json.loads(
            (ROOT / "docs/blueprint/evaluations.json").read_text(encoding="utf-8")
        )["manual_review_protocols"] if row["id"] == "REVIEW-LEGAL")
    assert pack["required_output_fields"] == protocol["required_output_fields"]
    assert pack["tasks"] == protocol["tasks"]
    assert "confers none" in pack["note"]


def test_an_incomplete_review_is_refused(monkeypatch, tmp_path, capsys):
    from pipeline.quality import measure

    monkeypatch.setattr(measure, "EVIDENCE", tmp_path / "evidence")
    signed = tmp_path / "signed.json"
    signed.write_text(json.dumps({
        "protocol": "REVIEW-LEGAL", "criterion": "BK-42-AC9",
        "decision": "pass", "scope": "the enabled scope",
        "reviewer_identity_and_qualification": "senior counsel",
    }), encoding="utf-8")
    assert _run("review-record", "--file", str(signed)) == 1
    said = capsys.readouterr().out
    assert "REFUSED" in said
    assert not measure.EVIDENCE.exists()


def test_a_review_that_decided_against_is_not_recorded_as_a_pass(
        monkeypatch, tmp_path, capsys):
    from pipeline.quality import measure

    monkeypatch.setattr(measure, "EVIDENCE", tmp_path / "evidence")
    protocol = next(
        row for row in json.loads(
            (ROOT / "docs/blueprint/evaluations.json").read_text(encoding="utf-8")
        )["manual_review_protocols"] if row["id"] == "REVIEW-LEGAL")
    signed = tmp_path / "signed.json"
    signed.write_text(json.dumps({
        "protocol": "REVIEW-LEGAL", "criterion": "BK-42-AC9",
        "decision": "rejected",
        **{f: "recorded" for f in protocol["required_output_fields"]},
    }), encoding="utf-8")
    assert _run("review-record", "--file", str(signed)) == 1
    assert "REFUSED" in capsys.readouterr().out
    assert not measure.EVIDENCE.exists()


def test_a_complete_looking_unsigned_review_cannot_be_promoted(
        monkeypatch, tmp_path, capsys):
    """Changing the actor's name is not independence and JSON is not a signature."""
    from pipeline.quality import measure

    monkeypatch.setattr(measure, "EVIDENCE", tmp_path / "evidence")
    source = tmp_path / "unsigned.json"
    source.write_text(json.dumps({
        "schema": 2, "criterion": "BK-42-AC9", "level": "counsel_review",
        "result": "PASS", "subject": "all enabled Indian legal scopes",
        "method": {"procedure": "REVIEW-LEGAL", "steps": ["reviewed"]},
        "actor": {"person_id": "somebody-else", "name": "Senior Counsel"},
        "authority": {"role": "Advocate", "basis": "claimed enrolment",
                      "evidence": {"ref": "made-up.json", "sha256": "0" * 64}},
        "rubric": {"identity": "REVIEW-LEGAL", "findings": [
            {"id": "scope", "result": "PASS", "basis": "claimed"}]},
        "population": {"count": 1, "described": "claimed scope"},
        "reservations": [], "observed_at": "2026-09-14T09:00:00+05:30",
        "subject_identity": {"kind": "external",
                             "valid_until": "2026-10-14T09:00:00+05:30"},
        "configuration_identity": "claimed-configuration",
        "attestation": {"ref": "made-up.json", "sha256": "0" * 64},
    }), encoding="utf-8")
    assert _run("review-record", "--file", str(source)) == 1
    said = capsys.readouterr().out
    assert "not authenticated evidence" in said
    assert not list(measure.EVIDENCE.glob("BK-42-AC9*"))


def test_an_authenticated_exact_review_can_be_promoted(monkeypatch, tmp_path):
    """Positive control: the trust boundary is a gate, not a permanent wall."""
    from pipeline.quality import measure
    from tests.p03_evidence_support import TrustHarness

    evidence_dir, artifacts = tmp_path / "evidence", tmp_path / "artifacts"
    monkeypatch.setattr(measure, "EVIDENCE", evidence_dir)
    harness = TrustHarness(artifacts, base=ROOT)
    harness.verifier.configuration_identity = "test-trust-v1"
    now = datetime.now(timezone.utc)
    record = {
        "schema": 2, "criterion": "BK-42-AC9", "level": "counsel_review",
        "result": "PASS", "subject": "the enabled Indian legal scope",
        "method": {"procedure": "REVIEW-LEGAL", "steps": ["reviewed every input"]},
        "actor": {"person_id": "alice", "name": "A. Reviewer"},
        "authority": {"role": "Advocate", "basis": "State Bar enrolment",
                      "evidence": None},
        "rubric": {"identity": "REVIEW-LEGAL", "findings": [
            {"id": "scope", "result": "PASS", "basis": "all rows reviewed"}]},
        "population": {"count": 1, "described": "the enabled legal scope"},
        "reservations": [], "observed_at": now.isoformat(),
        "subject_identity": {"kind": "external",
                             "valid_until": (now + timedelta(days=7)).isoformat()},
        "configuration_identity": "test-trust-v1", "attestation": None,
    }
    record["authority"]["evidence"] = harness.authority(
        "authority.json", person="alice", role="Advocate",
        basis="State Bar enrolment", scopes=["evidence:counsel_review"], now=now)
    payload = {key: value for key, value in record.items() if key != "attestation"}
    record["attestation"] = harness.signed("attestation.json", payload, ("alice",))
    source = tmp_path / "signed-record.json"
    source.write_text(json.dumps(record), encoding="utf-8")

    assert measure._promote_verified(
        source, expected_level="counsel_review", verifier=harness.verifier) == 0
    promoted = json.loads(
        (evidence_dir / "BK-42-AC9-counsel_review.json").read_text(encoding="utf-8"))
    assert promoted == record


def test_the_tabletop_pack_carries_the_reviewed_clocks(capsys):
    from nm.domain.incident import load_clocks

    assert _run("tabletop-pack") == 0
    pack = json.loads((ROOT / ".nm" / "packs" / "incident-tabletop.json")
                      .read_text(encoding="utf-8"))
    assert {c["clock_id"] for c in pack["reviewed_clocks"]} == {
        c.clock_id for c in load_clocks(ROOT)}
    assert "may not notify anybody" in pack["note"]
    assert any("does not answer the page" in i for i in pack["injects"])


def test_an_exercise_with_nobody_in_it_is_refused(tmp_path, capsys):
    done = tmp_path / "exercise.json"
    done.write_text(json.dumps({
        "exercise_id": "ex-1", "scenario_id": "unauthorised-export",
        "scenario_version": 3, "conducted_at": "2026-09-14T09:00:00+05:30",
        "timeline": {"occurred_at": "2026-09-14T08:00:00+05:30",
                     "detected_at": "2026-09-14T08:45:00+05:30",
                     "noticed_at": "2026-09-14T09:00:00+05:30"},
        "rotas": [], "participants": [],
    }), encoding="utf-8")
    assert _run("tabletop-record", "--file", str(done)) == 1
    assert "not a rehearsal of one" in capsys.readouterr().out
