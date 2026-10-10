"""Exact authority-to-used-source evidence; no semantic or paid-model claims."""
from copy import deepcopy

import pytest

from nm.core_engine import answer_sources, research, response_authorities, response_writer
from nm.core_engine.citations import CaseIdentityIndex
from nm.core_engine.retrieval import HybridSearcher, _candidate
from tests.test_citation_check import JUDGMENTS, _build
from tests.test_core_research import work
from tests.test_core_response_writer import source_use, unit
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection

pytestmark = pytest.mark.class_a


def setup(*, acts=None, quoted_authority=None):
    ctx = context("Find the applicable law.")
    plan = research.accept({"work": [work()]}, ctx)
    cases = Collection("judgment")
    for number, identity in enumerate(("SYN_1973_ALPHA", "SYN_1980_BETA")):
        case = JUDGMENTS[identity]
        cases.rows[number].update(case_id=identity, case_name=case[2], full_text=case[7])
    if quoted_authority:
        cases.rows[0]["full_text"] += " " + quoted_authority
    statutes = Collection()
    if acts is not None:
        for number, (identity, key) in enumerate(acts):
            statutes.rows[number].update(act_id=identity, act_name="Held " + identity,
                section_number=key, chunk_id=identity + ":" + key)
    record = research.retrieve(plan, HybridSearcher({"judgment": cases, "provision": statutes}), ctx)
    return ctx, record, answer_sources.build(ctx, record)


def draft_for(ctx, sources, text, selected):
    uses = [source_use(s, quote=None, role="provision" if s["kind"] == "provision" else "court_reasoning")
            for s in selected]
    return response_writer.accept({"units": [unit(sources, kind="law", text=text, uses=uses)]}, ctx, sources)


def judgments(sources):
    return {s["source_identity"]["case_id"]: s for s in sources.values() if s["kind"] == "judgment"}


class Reader:
    def __init__(self, record, *, change=None):
        self.record, self.change, self.calls = record, change, []

    def read_provision(self, act, reference):
        self.calls.append((act, reference))
        selected = [s for search in self.record["searches"].values() for s in search["candidates"]
                    if s["kind"] == "provision" and s["source"]["act_id"] == act
                    and str(s["source"]["section_number"]) == reference]
        snapshots = []
        for original in selected:
            source, revision = deepcopy(original["source"]), original["corpus_revision"]
            if self.change == "text": source["full_text"] = "Different exact source words."
            if self.change == "revision": revision = "later-corpus"
            window = {"scope": "indexed_section_segments", "bounded": False,
                      "unread_positions": [], "segments": [{"position": original["position"], "row": source}]}
            snapshots.append(_candidate("provision", original["position"], source, revision, None, [], window))
        return {"state": "found", "act_id": act, "reference": reference,
            "provision_key": reference, "candidates": [reference], "sources": snapshots,
            "legal_version": "not_assessed", "reason": None}


def test_exact_case_citation_binds_only_the_unit_actually_used_identity(tmp_path):
    ctx, record, sources = setup()
    cases = judgments(sources)
    draft = draft_for(ctx, sources, "Alphonse Quartermain v. State of Testland, (1973) 4 SCC 225.",
                      [cases["SYN_1973_ALPHA"]])
    evidence = response_authorities.check(ctx, record, sources, draft, case_index=_build(tmp_path))
    row = evidence["units"][0]["case_associations"][0]
    assert row["lookup"] == "found" and row["association"] == "matched"
    assert row["matching_source_ids"] == [cases["SYN_1973_ALPHA"]["id"]]
    assert row["legal_validity"] == "not_assessed"
    assert evidence["units"][0]["case_lookup"]["citations"][0]["name_check"] == "matches_recorded_name"
    assert response_authorities.validate(evidence, ctx, record, sources, draft) == evidence


def test_case_present_elsewhere_in_catalogue_does_not_satisfy_wrong_selected_case(tmp_path):
    ctx, record, sources = setup()
    cases = judgments(sources)
    draft = draft_for(ctx, sources, "The authority is (1973) 4 SCC 225.", [cases["SYN_1980_BETA"]])
    evidence = response_authorities.check(ctx, record, sources, draft, case_index=_build(tmp_path))
    row = evidence["units"][0]["case_associations"][0]
    assert row["lookup"] == "found" and row["association"] == "different_used_identity"
    assert row["matching_source_ids"] == []
    assert row["used_judgment_source_ids"] == [cases["SYN_1980_BETA"]["id"]]
    assert row["selected_support_mentions"] == []


def test_different_cited_case_mentioned_by_selected_source_is_explicit_not_a_false_citation_verdict(tmp_path):
    ctx, record, sources = setup(quoted_authority="Counsel referred to (1985) 2 SCC 10; its application was not decided.")
    primary = judgments(sources)["SYN_1973_ALPHA"]
    proposed = {"units": [unit(sources, kind="law", text="The judgment mentions (1985) 2 SCC 10.",
        uses=[source_use(primary, quote=None, role="quoted_authority")])]}
    draft = response_writer.accept(proposed, ctx, sources)
    evidence = response_authorities.check(ctx, record, sources, draft, case_index=_build(tmp_path))
    row = evidence["units"][0]["case_associations"][0]
    assert row["lookup"] == "found" and row["association"] == "different_used_identity"
    assert row["resolved_case_ids"] == ["SYN_1985_DELTA_A"]
    mention, = row["selected_support_mentions"]
    assert mention["source_id"] == primary["id"] and mention["text"] == "(1985) 2 SCC 10"
    assert primary["text"][mention["start"]:mention["end"]] == mention["text"]
    assert mention["source_role_proposal"] == "quoted_authority"
    assert "require review" in row["association_scope"]


def test_citation_collision_preserves_all_owners_without_selecting_a_used_one(tmp_path):
    ctx, record, sources = setup()
    draft = draft_for(ctx, sources, "The citation is AIR 1980 SC 100.", [judgments(sources)["SYN_1980_BETA"]])
    evidence = response_authorities.check(ctx, record, sources, draft, case_index=_build(tmp_path))
    row = evidence["units"][0]["case_associations"][0]
    assert row["lookup"] == "ambiguous" and row["association"] == "unresolved_association"
    assert set(row["resolved_case_ids"]) == {"SYN_1980_BETA", "SYN_1980_GAMMA"}


def test_unavailable_case_checker_is_not_no_match_and_does_not_claim_admission(tmp_path):
    ctx, record, sources = setup()
    draft = draft_for(ctx, sources, "The citation is (1973) 4 SCC 225.", [judgments(sources)["SYN_1973_ALPHA"]])
    index = CaseIdentityIndex(tmp_path / "missing.sqlite", tmp_path)
    evidence = response_authorities.check(ctx, record, sources, draft, case_index=index)
    row = evidence["units"][0]
    assert row["case_lookup"]["citations"][0]["status"] == "could_not_check"
    assert row["case_associations"][0]["association"] == "unresolved_association"
    assert "accepted" not in evidence and "release" not in evidence


def test_multiple_acts_with_same_provision_number_remain_unresolved_in_prose():
    ctx, record, sources = setup(acts=[("act-a", "4"), ("act-b", "4")])
    chosen = [s for s in sources.values() if s["kind"] == "provision"]
    draft = draft_for(ctx, sources, "Section 4 provides the rule.", chosen)
    reader = Reader(record)
    evidence = response_authorities.check(ctx, record, sources, draft, provision_reader=reader)
    row = evidence["units"][0]
    assert {p["state"] for p in row["selected_provisions"]} == {"matched"}
    assert row["prose_provisions"][0]["association"] == "unresolved_association"
    assert row["prose_provisions"][0]["key_match"] == "multiple_used_identities"
    assert row["prose_provisions"][0]["candidate_act_ids"] == ["act-a", "act-b"]
    assert set(reader.calls) == {("act-a", "4"), ("act-b", "4")}


@pytest.mark.parametrize("key,text", [("Article_4", "Article 4 applies."), ("4", "Section 4 applies.")])
def test_exact_raw_provision_kind_and_complete_source_are_preserved(key, text):
    ctx, record, sources = setup(acts=[("act-a", key), ("act-b", "9")])
    chosen = next(s for s in sources.values() if s["kind"] == "provision" and s["source_identity"]["act_id"] == "act-a")
    draft = draft_for(ctx, sources, text, [chosen])
    reader = Reader(record)
    evidence = response_authorities.check(ctx, record, sources, draft, provision_reader=reader)
    checked = evidence["units"][0]["selected_provisions"][0]
    assert checked["state"] == "matched" and checked["raw_provision_key"] == key
    assert checked["source_digest"] == chosen["digest"]
    assert checked["legal_version"] == "not_assessed"
    assert reader.calls == [("act-a", key)]
    assert evidence["readbacks"][checked["readback_id"]]["sources"][0]["text"] == chosen["text"]
    assert evidence["units"][0]["prose_provisions"][0]["key_match"] == "one_used_identity"
    assert evidence["units"][0]["prose_provisions"][0]["association"] == "unresolved_association"


def test_article_number_does_not_satisfy_a_section_mention():
    ctx, record, sources = setup(acts=[("act-a", "Article_4"), ("act-b", "9")])
    chosen = next(s for s in sources.values() if s["kind"] == "provision" and s["source_identity"]["act_id"] == "act-a")
    draft = draft_for(ctx, sources, "Section 4 applies.", [chosen])
    evidence = response_authorities.check(ctx, record, sources, draft, provision_reader=Reader(record))
    mention = evidence["units"][0]["prose_provisions"][0]
    assert mention["association"] == "unresolved_association" and not mention["candidate_source_ids"]


def test_same_number_does_not_certify_a_different_act_named_in_prose():
    ctx, record, sources = setup(acts=[("act-a", "4"), ("act-b", "4")])
    chosen = next(s for s in sources.values() if s["kind"] == "provision" and s["source_identity"]["act_id"] == "act-a")
    draft = draft_for(ctx, sources, "Section 4 of Held act-b supplies this rule.", [chosen])
    evidence = response_authorities.check(ctx, record, sources, draft, provision_reader=Reader(record))
    mention = evidence["units"][0]["prose_provisions"][0]
    assert mention["key_match"] == "one_used_identity" and mention["candidate_act_ids"] == ["act-a"]
    assert mention["association"] == "unresolved_association"
    assert mention["act_name_association"] == "not_assessed"


def test_source_without_a_provision_key_is_unavailable_without_guessing_one():
    ctx, record, sources = setup(acts=[("act-a", ""), ("act-b", "9")])
    chosen = next(s for s in sources.values() if s["kind"] == "provision" and s["source_identity"]["act_id"] == "act-a")
    draft = draft_for(ctx, sources, "The unnumbered text contains a qualification.", [chosen])
    reader = Reader(record)
    evidence = response_authorities.check(ctx, record, sources, draft, provision_reader=reader)
    assert reader.calls == []
    selected = evidence["units"][0]["selected_provisions"][0]
    assert selected["state"] == "unavailable" and selected["raw_provision_key"] == ""


@pytest.mark.parametrize("change", ["text", "revision"])
def test_newer_or_different_provision_text_cannot_certify_selected_snapshot(change):
    ctx, record, sources = setup()
    chosen = next(s for s in sources.values() if s["kind"] == "provision")
    draft = draft_for(ctx, sources, "The selected provision contains a qualification.", [chosen])
    evidence = response_authorities.check(ctx, record, sources, draft, provision_reader=Reader(record, change=change))
    assert evidence["units"][0]["selected_provisions"][0]["state"] == "different_snapshot"


def test_unavailable_provision_read_is_explicit_and_peers_are_kept():
    ctx, record, sources = setup()
    chosen = [s for s in sources.values() if s["kind"] == "provision"]
    draft = draft_for(ctx, sources, "The selected provisions need checking.", chosen)
    evidence = response_authorities.check(ctx, record, sources, draft)
    assert len(evidence["units"][0]["selected_provisions"]) == 2
    assert {s["state"] for s in evidence["units"][0]["selected_provisions"]} == {"unavailable"}
    assert {s["state"] for s in evidence["readbacks"].values()} == {"unavailable"}


@pytest.mark.parametrize("change", ["draft", "source", "association", "readback", "contract"])
def test_replay_rejects_dependency_or_saved_evidence_drift_without_new_reads(change):
    ctx, record, sources = setup()
    chosen = next(s for s in sources.values() if s["kind"] == "provision")
    draft = draft_for(ctx, sources, "Section 5 is the selected provision.", [chosen])
    reader = Reader(record)
    evidence = response_authorities.check(ctx, record, sources, draft, provision_reader=reader)
    calls = deepcopy(reader.calls)
    assert response_authorities.validate(evidence, ctx, record, sources, draft) == evidence
    assert reader.calls == calls
    if change == "draft": draft["units"][0]["text"] = "Changed reply"
    elif change == "source": sources[chosen["id"]]["text"] = "Changed source"
    elif change == "association": evidence["units"][0]["selected_provisions"][0]["state"] = "unavailable"
    elif change == "readback": next(iter(evidence["readbacks"].values()))["sources"][0]["text"] = "Changed readback"
    else: evidence["contract"] = "unknown-version"
    with pytest.raises(ValueError): response_authorities.validate(evidence, ctx, record, sources, draft)
    assert reader.calls == calls
