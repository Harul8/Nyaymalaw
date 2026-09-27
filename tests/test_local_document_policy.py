"""Local document parsing is not permission to send originals off premises."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from nm.domain.media import MediaKind, Processor, Quarantine, admitted
from nm.domain.media_policy import ContractUnreadable, Route, load, refuse_request

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]
OPERATION = "local_document_text_extraction"


def test_policy_names_a_local_only_operation_without_widening_the_other_routes():
    contract = load()
    assert contract.local_only == frozenset({OPERATION})
    assert refuse_request(Route("local-reader", (OPERATION,), off_premises=False), contract) == []
    assert refuse_request(Route("cloud-reader", ("voice_identity",), off_premises=False), contract)
    assert refuse_request(Route("local-reader", (OPERATION,), configuration_known=False,
                                off_premises=False), contract)


@pytest.mark.parametrize("location", [True, None, 0, "false"])
def test_external_or_unestablished_locations_cannot_relabel_themselves_local(location):
    ordinary = Route("declared-reader", (OPERATION,), off_premises=False)
    assert refuse_request(ordinary) == []
    denied = refuse_request(Route("declared-reader", (OPERATION,),
                                  off_premises=location, consent_given=True))
    assert any("local processing" in reason for reason in denied)
    assert any("consent does not override" in reason for reason in denied)
    background = refuse_request(Route("declared-reader", ("transcription",),
                                      unavoidable=(OPERATION,), off_premises=location))
    assert any("local processing" in reason for reason in background)


def test_admission_does_not_hide_an_external_processor_behind_the_first_local_one():
    kwargs = dict(purpose="read for this fictional matter", authority="test advocate",
                  quarantine=Quarantine.RELEASED, operations=(OPERATION,))
    local = Processor("local-reader", False)
    admission = admitted("one", MediaKind.DOCUMENT, processors=(local,), **kwargs)
    assert admission.may_reach_reasoning()[0]
    for processors in ((), (Processor("cloud-reader", True),),
                       (local, Processor("another-reader", True)),
                       (Processor("unknown-reader", 0),)):
        with pytest.raises(ValueError, match="local processing"):
            admitted("one", MediaKind.DOCUMENT, processors=processors, **kwargs)


@pytest.mark.parametrize("constraint", [None, {}, [],
    {OPERATION: {"processing_location": "global"}},
    {"unapproved-operation": {"processing_location": "local_only"}},
    {OPERATION: {"processing_location": "local_only", "consent_overrides": True}}])
def test_unreadable_location_controls_are_denial_not_unconstrained_processing(tmp_path, constraint):
    catalog = json.loads((ROOT / "docs/blueprint/evaluations.json").read_text(encoding="utf8"))
    catalog["media_contract"]["operation_constraints"] = constraint
    path = tmp_path / "docs/blueprint/evaluations.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(catalog), encoding="utf8")
    with pytest.raises(ContractUnreadable, match="location constraint"):
        load(tmp_path)
