"""Saved source-pane check projection; scripted fixtures do not prove legal accuracy."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.app import api
from nm.core_engine import response_authorities, response_rendering, response_review, response_writer, turn
from nm.core_engine.conversation import HEADER, chat_matter_id, commit_turn, digest, open_turn
from tests.test_citation_check import _build
from tests.test_core_authority_admission import use_statute
from tests.test_core_response_authorities import Reader, draft_for, judgments, setup
from tests.test_core_response_writer import source_use, unit
from tests.test_core_served import OWNER, served, source_url, successful
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a


def project(draft, evidence, selected, element=0):
    row = {"activities": {"contract": turn.CONTRACT, "draft": draft,
                           "authority_evidence": evidence}}
    return api._source_authority_inspection(row, element, selected)


@pytest.mark.parametrize("outcome", ["matched", "unavailable", "ambiguous", "not_held"])
def test_saved_provision_view_preserves_actual_outcome_without_new_checks(served, monkeypatch, outcome):
    use_statute(served, outcome)
    reply = successful(served)
    matter_id = chat_matter_id(OWNER, reply["chat_id"])
    before = deepcopy(served.store.load(matter_id))

    def no_lookup(*args, **kwargs):
        raise AssertionError("Source reopening cannot rerun authority checks")

    monkeypatch.setattr(response_authorities, "check", no_lookup)
    monkeypatch.setattr(served.app.legal_search.collections["provision"], "read_provision", no_lookup)
    read = served.client.get(source_url(reply))
    assert read.status_code == 200, read.text
    inspected = read.json()
    view = inspected.pop("authority_inspection")
    assert inspected == reply["elements"][0]["source"]
    assert view["state"] == "recorded" and view["activity_contract"] == turn.CONTRACT
    assert view["source_id"] == inspected["id"]
    expected = before.brain_chat[0]["activities"]["authority_evidence"]["units"][0]
    assert view["provision_checks"] == expected["selected_provisions"]
    assert view["provision_checks"][0]["state"] == outcome
    assert view["provision_checks"][0]["legal_version"] == "not_assessed"
    assert view["case_checks"] == [] and "status" not in view
    assert read.headers["cache-control"] == "no-store"
    assert served.store.load(matter_id) == before and len(served.model.calls) == 4


def test_retrieved_judgment_without_citation_check_is_not_assessed(served):
    reply = successful(served)
    for index, selected in enumerate(reply["elements"][0]["sources"]):
        read = served.client.get(source_url(reply, source=index)).json()
        view = read["authority_inspection"]
        assert view["source_id"] == selected["id"] and view["state"] == "not_assessed"
        assert not view["case_checks"] and not view["provision_checks"]
        assert "recorded" in view["reason"]
        assert read["verification"] == selected["verification"]


def test_legacy_saved_source_explicitly_has_no_authority_check(served, monkeypatch):
    context = open_turn(served.store, advocate_id=OWNER, message="Earlier account.", turn_id="old")
    original = context.payload()
    _, activity, metrics = turn.prepare(ScriptedModel(legal=True), original, searcher())
    activity.pop("authority_evidence")
    activity["contract"] = turn.LEGACY_CONTRACT
    activity["rendering_contract"] = response_rendering.LEGACY_CONTRACT
    dependencies = response_review._dependencies(original, activity["research"], activity["sources"],
        activity["draft"], activity["execution"], contract=response_review.LEGACY_CONTRACT)
    activity["review"] = response_review._accept(activity["review"]["proposal"], dependencies,
                                               contract=response_review.LEGACY_CONTRACT)
    elements = response_rendering.render(original, activity["research"], activity["sources"],
        activity["draft"], activity["review"], execution=activity["execution"],
        contract=response_rendering.LEGACY_CONTRACT)
    reply = commit_turn(served.store, context, elements=elements, activities=activity,
                        metrics=metrics, session_current=lambda: True)
    monkeypatch.setattr(response_authorities, "check", lambda *a, **kw: pytest.fail("No fresh check"))
    read = served.client.get(source_url(reply))
    assert read.status_code == 200, read.text
    view = read.json()["authority_inspection"]
    assert view["state"] == "not_assessed" and view["activity_contract"] == turn.LEGACY_CONTRACT
    assert view["case_checks"] == view["provision_checks"] == []
    assert "earlier response" in view["reason"]


def test_case_identity_name_and_quote_results_stay_separate_without_extra_passages(tmp_path):
    ctx, research, sources = setup()
    selected = judgments(sources)["SYN_1973_ALPHA"]
    draft = draft_for(ctx, sources,
        'Alphonse Quartermain v. State of Testland, (1973) 4 SCC 225: "Unsupported quotation."', [selected])
    evidence = response_authorities.check(ctx, research, sources, draft, case_index=_build(tmp_path))
    before = deepcopy(evidence)
    view = project(draft, evidence, selected)
    checked, = view["case_checks"]
    assert checked["lookup"] == "found"
    assert checked["name_check"] == "matches_recorded_name"
    assert checked["association"] == "matched"
    assert checked["legal_validity"] == "not_assessed" and "status" not in checked
    assert checked["quotes"] and all("excerpt" not in q for q in checked["quotes"])
    raw = evidence["units"][0]["case_lookup"]["citations"][0]
    assert checked["quotes"] == [{k: v for k, v in q.items() if k != "excerpt"} for q in raw["quotes"]]
    assert all(set(j) == {"case_id", "title", "court", "decided_on"} for j in checked["judgments"])
    checked["judgments"].clear()
    assert evidence == before


def test_secondary_citation_occurrence_remains_separate_from_primary_source_identity(tmp_path):
    ctx, research, sources = setup(quoted_authority="Counsel cited (1985) 2 SCC 10 without adoption.")
    selected = judgments(sources)["SYN_1973_ALPHA"]
    draft = response_writer.accept({"units": [unit(sources, kind="law",
        text="The passage mentions (1985) 2 SCC 10.",
        uses=[source_use(selected, quote=None, role="quoted_authority")])]}, ctx, sources)
    evidence = response_authorities.check(ctx, research, sources, draft, case_index=_build(tmp_path))
    checked, = project(draft, evidence, selected)["case_checks"]
    assert checked["lookup"] == "found" and checked["association"] == "different_used_identity"
    assert checked["matching_source_ids"] == []
    mention, = checked["selected_support_mentions"]
    assert mention["source_id"] == selected["id"] and mention["text"] == "(1985) 2 SCC 10"
    assert mention["source_role_proposal"] == "quoted_authority"
    assert "require review" in checked["association_scope"]


def test_view_filters_same_source_by_reply_unit_and_other_sources_by_identity(tmp_path):
    ctx, research, sources = setup()
    selected = judgments(sources)["SYN_1973_ALPHA"]
    other = judgments(sources)["SYN_1980_BETA"]
    units = [unit(sources, kind="law", text=text, uses=[source_use(source, quote=None)])
             for text, source in [("The authority is (1973) 4 SCC 225.", selected),
                                  ("The authority is AIR 1980 SC 100.", other)]]
    draft = response_writer.accept({"units": units}, ctx, sources)
    evidence = response_authorities.check(ctx, research, sources, draft, case_index=_build(tmp_path))
    assert project(draft, evidence, selected, 0)["case_checks"][0]["lookup"] == "found"
    other_view = project(draft, evidence, other, 1)
    assert other_view["case_checks"][0]["lookup"] == "ambiguous"
    assert other_view["unit_id"] == draft["units"][1]["id"]
    assert project(draft, evidence, selected, 1)["case_checks"] == []


def test_historical_snapshot_discrepancy_is_displayed_unchanged():
    ctx, research, sources = setup()
    selected = next(s for s in sources.values() if s["kind"] == "provision")
    draft = draft_for(ctx, sources, "The selected provision contains a qualification.", [selected])
    evidence = response_authorities.check(ctx, research, sources, draft, provision_reader=Reader(research))
    reader = Reader(research, change="text")
    evidence["readbacks"] = {key: reader.read_provision(row["act_id"], row["reference"])
                             for key, row in evidence["readbacks"].items()}
    reports = {row["unit_id"]: row["case_lookup"] for row in evidence["units"]}
    evidence["units"] = response_authorities._assemble(draft, sources,
        response_authorities._raw_sources(research), reports, evidence["readbacks"])
    evidence["bound_digest"] = response_authorities._digest(
        {key: value for key, value in evidence.items() if key != "bound_digest"})
    response_authorities.validate(evidence, ctx, research, sources, draft)
    check, = project(draft, evidence, selected)["provision_checks"]
    assert check["state"] == "different_snapshot" and check["legal_version"] == "not_assessed"


def test_unknown_saved_activity_cannot_release_presentation_enrichment(served):
    reply = successful(served)
    matter = served.store.load(chat_matter_id(OWNER, reply["chat_id"]))
    rows, metadata = deepcopy(matter.brain_chat), deepcopy(matter.intake_answers)
    rows[0]["activities"]["contract"] = "unknown_future_activity"
    rows[0]["digest"] = digest({k: v for k, v in rows[0].items() if k != "digest"})
    metadata[HEADER]["tail_digest"] = rows[0]["digest"]
    served.store.commit(replace(matter, brain_chat=rows, intake_answers=metadata,
                               version=matter.version + 1), expected_version=matter.version)
    response = served.client.get(source_url(reply))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "saved_response_unavailable"
    assert "authority_inspection" not in response.text and len(served.model.calls) == 4
