"""Sources sit on the words they support, and each dispute's summary opens the answer
(owner decisions, 17 Oct 2026; writer v5, rendering v11). Scripted fixtures exercise the
admission, review view and rendering; they do not show a real writer chooses words well."""
import json
from copy import deepcopy

import pytest

from nm.core_engine import calculation, response_authorities, response_rendering, response_review, response_writer, turn
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Usage
from tests.test_core_response_authorities import Reader
from tests.test_core_response_rendering import Model as LegacyReviewModel, ready
from tests.test_core_response_review import Model as ReviewModel, positive, request
from tests.test_core_response_writer import PartModel, reference, two_disputes, unit

pytestmark = pytest.mark.class_a


class LinkedModel(PartModel):
    """The opening greets; each dispute's part opens with its summary, then one law
    paragraph whose held passage supports the words "the stated rule"."""
    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        with self.lock:
            self.seen.append(payload)
        dispute = (payload["this_part"]["dispute"] or {}).get("id")
        if dispute is None:
            units = [unit(self.sources, kind="greeting", text="Good morning.")]
        else:
            passage = payload["held_passages"]["passages"][0]
            use = {"source_id": passage["id"], "source_kind": passage["kind"], "words": "the stated rule"}
            if passage["kind"] == "judgment":
                use.update(role="court_reasoning", speaker=None, court_treatment={"status": "not_applicable"})
            units = [unit(self.sources, kind="summary", text=f"Act on {dispute} in time; I need the dates."),
                     {"kind": "law", "text": f"For {dispute}, the stated rule applies to these facts.",
                      "addresses": [reference(self.sources["t2:advocate"])], "uses": [use]}]
        return ModelResult(None, {"units": deepcopy(units)}, tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                           completion=Completion.COMPLETE)


def answer():
    ctx, record, sources = two_disputes()
    draft = response_writer.write(LinkedModel(sources), ctx, record, sources)
    authorities = response_authorities.check(ctx, record, sources, draft)
    execution = turn.execution_record(record)
    return ctx, record, sources, draft, authorities, execution


def test_each_source_names_the_words_it_supports_and_they_are_kept_where_they_stand():
    ctx, record, sources, draft, _, _ = answer()
    assert draft["contract"] == response_writer.CONTRACT == "core_response_writer_v5"
    law = next(unit for unit in draft["units"] if unit["kind"] == "law")
    words, = [use["words"] for use in law["uses"]]
    assert words == {"text": "the stated rule", "start": law["text"].index("the stated rule"),
                     "end": law["text"].index("the stated rule") + len("the stated rule")}
    assert [unit["kind"] for unit in draft["units"]] == ["greeting", "summary", "law", "summary", "law"]
    assert response_writer.validate(draft, ctx, sources) == draft
    # Words that are not in their unit, or blank, are refused for the bounded correction.
    for wrong in ("a rule nowhere in the text", "   "):
        changed = deepcopy(draft["proposal"])
        changed["units"][2]["uses"][0]["words"] = wrong
        with pytest.raises(SchemaViolation, match="not copied exactly"):
            response_writer.accept(changed, ctx, sources, parts=draft["parts"])


def test_the_reviewer_sees_the_words_each_source_is_linked_from():
    ctx, record, sources, draft, authorities, execution = answer()
    model = ReviewModel(positive(draft, requests=[request(ctx, draft)]))
    response_review.review(model, ctx, record, sources, draft, execution, authority_evidence=authorities)
    shown = json.loads(model.calls[0][0].user)["complete_draft_proposal"]["units"]
    assert [use["words"] for unit in shown for use in unit["uses"]] == ["the stated rule", "the stated rule"]
    assert "check that the source supports them" in " ".join(response_review.SYSTEM.split())


def test_the_answer_opens_then_says_in_short_then_each_dispute_with_its_links():
    ctx, record, sources, draft, authorities, execution = answer()
    review = response_review.review(ReviewModel(positive(draft, requests=[request(ctx, draft)])), ctx, record,
                                    sources, draft, execution, authority_evidence=authorities)
    elements = response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities)
    assert [(e["kind"], e["text"]) for e in elements] == [
        ("GREETING", "Good morning."),
        ("SUMMARY", "Act on D1 in time; I need the dates."), ("SUMMARY", "Act on D2 in time; I need the dates."),
        ("HEADING", "Dispute 1"), ("LAW", "For D1, the stated rule applies to these facts."),
        ("HEADING", "Dispute 2"), ("LAW", "For D2, the stated rule applies to these facts.")]
    for law in (elements[4], elements[6]):
        anchor, = law["inline_citations"]
        assert (anchor["text"], anchor["start"]) == ("the stated rule", law["text"].index("the stated rule"))
        assert anchor["source_id"] == law["sources"][anchor["source_index"]]["id"]
        assert law["citation_markers"] == []  # no chips after a paragraph
    # Each shown paragraph names its own draft paragraph, wherever it is placed.
    assert [response_rendering.unit_index(elements, i) for i in (0, 1, 2, 4, 6)] == [0, 1, 3, 2, 4]
    assert turn.validate_activity({"contract": turn.CONTRACT, "interpretation": {"units": []}, "research": record,
        "sources": sources, "draft": draft, "review": review, "execution": execution,
        "rendering_contract": response_rendering.CONTRACT, "authority_evidence": authorities,
        "calculation": calculation.skipped(),
        "release": None}, ctx, elements)["rendering_contract"] == "core_response_rendering_v11"


def test_a_held_sections_summary_is_held_with_it():
    ctx, record, sources, draft, authorities, execution = answer()
    held = [draft["units"][3]["id"], draft["units"][4]["id"]]  # Dispute 2's summary and law
    data = positive(draft, requests=[request(ctx, draft)])
    data["verdict"] = "reject"
    for row in data["units"]:
        if row["unit_id"] in held:
            row["verdict"] = "rejected"
    data["findings"] = [{"category": "omission", "unit_ids": held, "sources": [], "mismatch": "Missing a date."}]
    review = response_review.review(ReviewModel(data), ctx, record, sources, draft, execution,
                                    authority_evidence=authorities)
    elements = response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities, held={"parts": [2], "date_findings": []})
    assert [e["kind"] for e in elements] == ["NOTICE", "GREETING", "SUMMARY", "HEADING", "LAW", "HEADING", "HELD",
                                             "NOTICE"]
    assert "D2" not in " ".join(e["text"] for e in elements if e["kind"] != "HELD")


def test_a_summary_in_a_reply_with_no_dispute_part_stays_where_it_was_written():
    ctx, record, sources = two_disputes()
    units = [unit(sources, kind="greeting", text="Good morning."),
             unit(sources, kind="summary", text="Nothing here needs a dispute of its own.")]
    draft = response_writer.accept({"units": units}, ctx, sources, parts=[{"dispute_id": None, "units": 2}])
    authorities = response_authorities.check(ctx, record, sources, draft)
    execution = turn.execution_record(record)
    review = response_review.review(ReviewModel(positive(draft, requests=[request(ctx, draft)])), ctx, record,
                                    sources, draft, execution, authority_evidence=authorities)
    elements = response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities)
    assert [(e["kind"], e["text"]) for e in elements] == [
        ("GREETING", "Good morning."), ("SUMMARY", "Nothing here needs a dispute of its own.")]


def test_v11_refuses_a_draft_whose_sources_name_no_words():
    ctx, record, sources, draft, legacy_review, execution = ready()
    authorities = response_authorities.check(ctx, record, sources, draft, provision_reader=Reader(record))
    review = response_review.review(LegacyReviewModel(legacy_review["proposal"]), ctx, record, sources, draft,
                                    execution=execution, authority_evidence=authorities)
    with pytest.raises(ValueError, match="only a writer v5 draft"):
        response_rendering.render(ctx, record, sources, draft, review, execution, authority_evidence=authorities)
    # The versions an earlier answer is replayed in still draw it.
    assert response_rendering.render(ctx, record, sources, draft, review, execution, authority_evidence=authorities,
                                     contract=response_rendering.HELD_CONTRACT)
