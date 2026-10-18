"""Sources sit on the words they support, and each dispute's summary opens the answer
(owner decisions, 17 Oct 2026; writer v5, rendering v11). From writer v7 and rendering v12
(18 Oct 2026, after the first live run) the writer links a source from its own words as
[words](ID), and a source it leaves unlinked is listed after its paragraph. Scripted
fixtures exercise the admission, review view and rendering; they do not show a real writer
chooses words well."""
import json
from copy import deepcopy

import pytest

from nm.core_engine import calculation, response_authorities, response_rendering, response_review, response_writer, turn
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Usage
from tests.test_core_response_authorities import Reader
from tests.test_core_response_rendering import Model as LegacyReviewModel, ready
from tests.test_core_response_review import Model as ReviewModel, positive, request
from tests.test_core_response_writer import PartModel, accept, reference, two_disputes, unaddressed, unit

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
            use = {"source_id": passage["id"], "source_kind": passage["kind"]}
            if passage["kind"] == "judgment":
                use.update(role="court_reasoning", speaker=None, court_treatment={"status": "not_applicable"})
            units = [unit(self.sources, kind="summary", text=f"Act on {dispute} in time; I need the dates."),
                     {"kind": "law", "text": f"For {dispute}, [the stated rule]({passage['id']}) applies to these facts.",
                      "uses": [use]}]
        unaddressed(units)
        return ModelResult(None, {"units": deepcopy(units), "checklist": [], "time_limit_ids": []}, tier,
                           "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)


def answer():
    ctx, record, sources = two_disputes()
    draft = response_writer.write(LinkedModel(sources), ctx, record, sources)
    authorities = response_authorities.check(ctx, record, sources, draft)
    execution = turn.execution_record(record)
    return ctx, record, sources, draft, authorities, execution


def test_each_source_is_linked_from_the_writers_own_words_where_they_stand():
    ctx, record, sources, draft, _, _ = answer()
    assert draft["contract"] == response_writer.CONTRACT == "core_response_writer_v9"
    law = next(unit for unit in draft["units"] if unit["kind"] == "law")
    assert law["text"] == "For D1, the stated rule applies to these facts."  # the markup taken out
    words, = [use["words"] for use in law["uses"]]
    assert words == {"text": "the stated rule", "start": law["text"].index("the stated rule"),
                     "end": law["text"].index("the stated rule") + len("the stated rule")}
    assert [unit["kind"] for unit in draft["units"]] == ["greeting", "summary", "law", "summary", "law"]
    assert response_writer.validate(draft, ctx, sources) == draft
    # A link to a source the unit does not use, a link with no words or no ID, and words given
    # beside the text are all refused for the bounded correction; no markup is ever shown.
    for wrong, match in ((lambda u: u.update(text="For D1, [the stated rule](P99) applies."), "does not use"),
                         (lambda u: u.update(text="For D1, [ ](P1) applies."), "needs words"),
                         (lambda u: u.update(text="For D1, [the stated rule]() applies."), "needs words"),
                         (lambda u: u["uses"][0].update(words="the stated rule"), "undeclared")):
        changed = deepcopy(draft["proposal"])
        wrong(changed["units"][2])
        with pytest.raises(SchemaViolation, match=match):
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
        "release": None}, ctx, elements)["rendering_contract"] == "core_response_rendering_v14"


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
    draft = accept({"units": units}, ctx, sources, parts=[{"dispute_id": None, "units": 2}])
    authorities = response_authorities.check(ctx, record, sources, draft)
    execution = turn.execution_record(record)
    review = response_review.review(ReviewModel(positive(draft, requests=[request(ctx, draft)])), ctx, record,
                                    sources, draft, execution, authority_evidence=authorities)
    elements = response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities)
    assert [(e["kind"], e["text"]) for e in elements] == [
        ("GREETING", "Good morning."), ("SUMMARY", "Nothing here needs a dispute of its own.")]


def test_v11_and_v12_refuse_a_draft_of_another_writer_version():
    ctx, record, sources, draft, legacy_review, execution = ready()
    authorities = response_authorities.check(ctx, record, sources, draft, provision_reader=Reader(record))
    review = response_review.review(LegacyReviewModel(legacy_review["proposal"]), ctx, record, sources, draft,
                                    execution=execution, authority_evidence=authorities)
    with pytest.raises(ValueError, match="only a writer v5 or v6 draft"):
        response_rendering.render(ctx, record, sources, draft, review, execution, authority_evidence=authorities,
                                  contract=response_rendering.WORDS_CONTRACT)
    with pytest.raises(ValueError, match="writer v7"):
        response_rendering.render(ctx, record, sources, draft, review, execution, authority_evidence=authorities)
    # The versions an earlier answer is replayed in still draw it.
    assert response_rendering.render(ctx, record, sources, draft, review, execution, authority_evidence=authorities,
                                     contract=response_rendering.HELD_CONTRACT)


def test_a_source_the_writer_does_not_link_is_listed_after_its_paragraph():
    ctx, record, sources = two_disputes()
    first, second = [row for row in sources.values() if row["kind"] == "provision"][:2]
    units = [{"kind": "law", "text": "[The provision](%s) applies to what you asked." % first["id"],
              "uses": [{"source_id": first["id"], "source_kind": "provision"},
                       {"source_id": second["id"], "source_kind": "provision"}]}]
    draft = response_writer.accept({"units": units, "checklists": [{"checklist": [], "time_limit_ids": []}]},
                                   ctx, sources, parts=[{"dispute_id": None, "units": 1}])
    authorities = response_authorities.check(ctx, record, sources, draft)
    execution = turn.execution_record(record)
    review = response_review.review(ReviewModel(positive(draft, requests=[request(ctx, draft)])), ctx, record,
                                    sources, draft, execution, authority_evidence=authorities)
    law, = response_rendering.render(ctx, record, sources, draft, review, execution, authority_evidence=authorities)
    assert law["text"] == "The provision applies to what you asked."
    assert [(anchor["text"], anchor["source_id"]) for anchor in law["inline_citations"]] == [
        ("The provision", first["id"])]
    # The second provision, used but not linked, follows the paragraph; the page folds it
    # under "Sources". Nothing the paragraph relies on is lost.
    assert [(marker["source_id"], law["sources"][marker["source_index"]]["id"])
            for marker in law["citation_markers"]] == [(second["id"], second["id"])]


def test_a_link_standing_alone_after_a_sentence_is_a_label_and_its_source_is_listed():
    """The second live run (18 Oct 2026) wrote most links as labels after sentences; they
    are taken out of the text and their sources listed, so no stray label reads as prose."""
    ctx, record, sources = two_disputes()
    first, second = [row for row in sources.values() if row["kind"] == "provision"][:2]
    text = (f"The provision applies to what you asked. [The applicable rule]({first['id']}) "
            f"[Its exception]({second['id']}) It has an [exception]({second['id']}).")
    units = [{"kind": "law", "text": text,
              "uses": [{"source_id": first["id"], "source_kind": "provision"},
                       {"source_id": second["id"], "source_kind": "provision"}]}]
    draft = response_writer.accept({"units": units, "checklists": [{"checklist": [], "time_limit_ids": []}]},
                                   ctx, sources, parts=[{"dispute_id": None, "units": 1}])
    law_unit, = draft["units"]
    assert law_unit["text"] == "The provision applies to what you asked. It has an exception."
    by_source = {use["source_id"]: use.get("words") for use in law_unit["uses"]}
    assert by_source[first["id"]] is None  # cited by a label only: listed beneath the paragraph
    assert by_source[second["id"]]["text"] == "exception"  # its link inside the sentence holds
    # A whole sentence written as a link is words of the text, not a label.
    whole = deepcopy(units)
    whole[0]["text"] = f"[The provision applies to what you asked.]({first['id']}) It has no other condition."
    kept = response_writer.accept({"units": whole, "checklists": [{"checklist": [], "time_limit_ids": []}]},
                                  ctx, sources, parts=[{"dispute_id": None, "units": 1}])
    assert kept["units"][0]["text"] == "The provision applies to what you asked. It has no other condition."
    assert kept["units"][0]["uses"][0]["words"]["text"] == "The provision applies to what you asked."


def test_a_link_may_name_its_sources_in_one_bracket_or_in_several():
    ctx, record, sources = two_disputes()
    first, second = [row for row in sources.values() if row["kind"] == "provision"][:2]
    for written in (f"({first['id']}, {second['id']})", f"({first['id']})({second['id']})"):
        units = [{"kind": "law", "text": f"It is enforceable [under the provisions]{written}.",
                      "uses": [{"source_id": first["id"], "source_kind": "provision"},
                           {"source_id": second["id"], "source_kind": "provision"}]}]
        draft = response_writer.accept({"units": units, "checklists": [{"checklist": [], "time_limit_ids": []}]},
                                       ctx, sources, parts=[{"dispute_id": None, "units": 1}])
        law_unit, = draft["units"]
        assert law_unit["text"] == "It is enforceable under the provisions."  # no markup left over
        assert [use["words"]["text"] for use in law_unit["uses"]] == ["under the provisions"] * 2


def test_a_link_separates_its_sources_with_a_semicolon_too_and_lists_a_source_it_names():
    """Forensic review, 18 Oct 2026: code decides what it can. A link naming its sources with
    ';' names both; a link to a held provision or message the paragraph did not also list
    lists it (the link names it); a judgment must still say how the court treated it."""
    ctx, record, sources = two_disputes()
    first, second = [row for row in sources.values() if row["kind"] == "provision"][:2]
    judgment = next(row for row in sources.values() if row["kind"] == "judgment")
    units = [{"kind": "law", "text": f"It is enforceable [under the provisions]({first['id']}; {second['id']}).",
              "uses": [{"source_id": first["id"], "source_kind": "provision"}]}]
    draft = response_writer.accept({"units": units, "checklists": [{"checklist": [], "time_limit_ids": []}]},
                                   ctx, sources, parts=[{"dispute_id": None, "units": 1}])
    law_unit, = draft["units"]
    assert law_unit["text"] == "It is enforceable under the provisions."
    assert [use["source_id"] for use in law_unit["uses"]] == [first["id"], second["id"]]
    assert [use["words"]["text"] for use in law_unit["uses"]] == ["under the provisions"] * 2
    assert response_writer.validate(draft, ctx, sources) == draft
    units[0]["text"] = f"It is enforceable [under the judgment]({judgment['id']})."
    with pytest.raises(SchemaViolation, match="does not use"):
        response_writer.accept({"units": units, "checklists": [{"checklist": [], "time_limit_ids": []}]},
                               ctx, sources, parts=[{"dispute_id": None, "units": 1}])
