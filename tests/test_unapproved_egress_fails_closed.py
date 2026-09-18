"""PRIVILEGED MATERIAL GOES WHERE IT WAS APPROVED TO GO, OR NOWHERE. BK-85-AC1.

Every defect the first external review of this product found lived between a
correct module and the served path. Egress is that gap in its purest form: the
core composes an answer correctly, and then something hands a copy to a model
provider, a telemetry sink, a crash reporter or a support bundle. By the time
an audit reads the logs, the material has left.

THE CRITERION'S TWO MUTATIONS, run below: *enable a foreign processor* and
*send privileged text through diagnostic telemetry*. The expected failure is
that the route is rejected AND a content-free audit identifies the refusal —
both halves, because a refusal line quoting what it refused to send puts the
privileged text in the log, which is the place least likely to be noticed and
most likely to be shipped to a diagnostic service. The control would then
commit its own second mutation.

FAIL-CLOSED IS THE HALF USUALLY GOT WRONG. An unknown processor is not one
nobody wrote a rule for; it is one nobody approved. Most implementations treat
the first reading as the default and the request goes.
"""
from __future__ import annotations

import pytest
from nm.domain.egress import (
    HOME_REGION,
    NEVER_CLIENT_MATERIAL,
    DataClass,
    Policy,
    Processor,
    Route,
    Sink,
    audit_line,
    permitted,
    refuse,
)

pytestmark = pytest.mark.class_a

APPROVED = Processor(
    processor_id="model-in-1", region="in", purposes=(Sink.MODEL,),
    data_classes=(DataClass.OPERATIONAL, DataClass.CLIENT_MATTER),
    approval_id="ADOPT-07")
TELEMETRY = Processor(
    processor_id="telemetry-in-1", region="in", purposes=(Sink.TELEMETRY,),
    data_classes=(DataClass.OPERATIONAL,), approval_id="ADOPT-08")
POLICY = Policy(processors=(APPROVED, TELEMETRY))


def _route(**overrides) -> Route:
    base = {"sink": Sink.MODEL, "processor_id": "model-in-1",
            "purpose": Sink.MODEL,
            "data_classes": (DataClass.CLIENT_MATTER,), "size_bytes": 1200}
    base.update(overrides)
    return Route(**base)


# ============================ the negative control ==========================

def test_an_approved_route_is_permitted():
    """Without this, a policy that refused everything satisfies the rest of
    this file and the product cannot answer at all."""
    assert refuse(_route(), POLICY) == []
    assert permitted(_route(), POLICY)


# ======================= the criterion's two mutations ======================

def test_a_foreign_processor_is_refused_with_its_region_named():
    """*Enable a foreign processor.*"""
    foreign = Processor(processor_id="model-us-1", region="us",
                        purposes=(Sink.MODEL,),
                        data_classes=(DataClass.CLIENT_MATTER,),
                        approval_id="ADOPT-09")
    found = refuse(_route(processor_id="model-us-1"),
                   Policy(processors=(foreign,)))
    assert any("'us'" in p and "no legal review admits" in p for p in found), found


def test_privileged_text_can_never_reach_diagnostic_telemetry():
    """*Send privileged text through diagnostic telemetry.*

    Refused WHATEVER THE INVENTORY SAYS. A diagnostic pipeline is read by
    whoever is on call, retained by a vendor's default policy and forwarded to
    a crash aggregator, and none of that is a decision anybody made about a
    privileged brief.
    """
    everything = Processor(
        processor_id="telemetry-in-1", region="in", purposes=(Sink.TELEMETRY,),
        data_classes=tuple(DataClass), approval_id="ADOPT-08")
    found = refuse(
        _route(sink=Sink.TELEMETRY, processor_id="telemetry-in-1",
               purpose=Sink.TELEMETRY,
               data_classes=(DataClass.CLIENT_MATTER,)),
        Policy(processors=(everything,)))
    assert any("may never reach" in p for p in found), found


def test_the_refusal_audit_carries_no_client_material():
    """The second half of the expected failure, and the one a control most
    often breaks in the act of satisfying the first."""
    route = _route(sink=Sink.TELEMETRY, processor_id="telemetry-in-1",
                   purpose=Sink.TELEMETRY,
                   data_classes=(DataClass.RESTRICTED,))
    line = audit_line(route, refuse(route, POLICY))
    assert line.startswith("egress REFUSED")
    assert "telemetry-in-1" in line and "restricted" in line
    # The route, the reason and a size. Never a payload -- and `Route` has no
    # field that could carry one, which is the structural half of the same rule.
    assert not hasattr(route, "payload") and not hasattr(route, "text")
    assert "bytes=" in line


# ============================== fail closed =================================

@pytest.mark.parametrize("mutation,expected", [
    ({"processor_id": "nobody-listed"}, "not in the reviewed inventory"),
    ({"processor_id": ""}, "names no processor"),
    ({"data_classes": ()}, "declares no data classes"),
])
def test_an_absent_declaration_is_a_refusal_and_not_a_default(mutation, expected):
    """§9. An unknown processor is not one nobody wrote a rule for."""
    found = refuse(_route(**mutation), POLICY)
    assert any(expected in p for p in found), (mutation, found)


def test_an_inventory_entry_with_no_approval_is_a_list_somebody_typed():
    unapproved = Processor(processor_id="model-in-2", region="in",
                           purposes=(Sink.MODEL,),
                           data_classes=(DataClass.CLIENT_MATTER,),
                           approval_id="")
    found = refuse(_route(processor_id="model-in-2"),
                   Policy(processors=(unapproved,)))
    assert any("no approval" in p for p in found), found


def test_a_processor_approved_for_one_purpose_may_not_serve_another():
    found = refuse(_route(sink=Sink.INDEX, purpose=Sink.INDEX), POLICY)
    assert any("approved for ['model']" in p for p in found), found


def test_a_route_may_not_be_approved_for_one_thing_and_used_for_another():
    """The sink and the purpose must agree, or a model approval becomes a
    backup approval by relabelling one field."""
    found = refuse(_route(sink=Sink.BACKUP, purpose=Sink.MODEL), POLICY)
    assert any("may not be approved for one thing" in p for p in found), found


def test_a_dispatch_carrying_an_unapproved_data_class_is_refused():
    found = refuse(_route(data_classes=(DataClass.RESTRICTED,)), POLICY)
    assert any("restricted" in p for p in found), found


# ========================== the policy's own shape ==========================

def test_an_empty_policy_permits_nothing():
    """The state a fresh deployment is in. It must be closed, not open."""
    assert refuse(_route(), Policy()), "an empty inventory permitted a dispatch"


def test_a_foreign_region_needs_a_named_review_and_not_a_flag():
    """A boolean 'allow_foreign' is a switch somebody sets in an incident. An
    entry naming the review that admitted the region is a decision."""
    foreign = Processor(processor_id="model-sg-1", region="sg",
                        purposes=(Sink.MODEL,),
                        data_classes=(DataClass.CLIENT_MATTER,),
                        approval_id="ADOPT-10")
    closed = Policy(processors=(foreign,))
    assert refuse(_route(processor_id="model-sg-1"), closed)

    admitted = Policy(processors=(foreign,),
                      approved_foreign_regions={"sg": "counsel review 2026-09"})
    assert refuse(_route(processor_id="model-sg-1"), admitted) == []


def test_the_home_region_and_the_forbidden_sinks_are_stated_once():
    """`SECURITY_PRIVACY.md` §2.6 records India-region storage as PRODUCT
    POLICY and explicitly not a claim that the law requires it. This module
    enforces the policy without asserting the law."""
    assert HOME_REGION == "in"
    assert set(NEVER_CLIENT_MATERIAL) == {Sink.TELEMETRY, Sink.SUPPORT}


def test_every_sink_is_named_rather_than_defaulted():
    """A new destination is a change to the enum, not an unlisted default."""
    assert {s.value for s in Sink} == {
        "model", "media", "storage", "index", "backup", "support", "telemetry",
        "mail", "transcription"}
