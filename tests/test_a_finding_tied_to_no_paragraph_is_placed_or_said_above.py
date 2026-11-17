"""Plan AN.51 (D201, 17 Nov 2026; the forensic review's F-06; the owner's P29): a finding that a piece misleads as a whole.

Before, a misleading finding the review tied to no paragraph was said beside the piece and the piece released. Review v13 (for
writer v15's sections and overview) asks the reviewer once, on the review tier, to name the paragraphs and words that carry it.
What it names is at fault like any finding that names its place: the paragraph goes back to the writer for a second look, and what
still misleads is cut or left out. What it still ties to none is shown above the piece under code's own notice that the review
found it misleading as a whole. A piece reviewed before v13 is shown as it was. Offline: scripted answers on an invented matter;
what the reviewer names in a real answer is for a live run.
"""
import json
from copy import deepcopy

import pytest

from nm.core_engine import (answer_sections, calculation, response_authorities, response_rendering, response_review,
                            response_writer, turn)
from nm.core_engine.calls import TurnCalls
from nm.shared.model_port import ProviderUnavailable, Tier, UsageLimitReached
from tests.test_core_answer_sections import Scripted, _result, paragraph
from tests.test_core_response_writer import two_disputes

pytestmark = pytest.mark.class_a

WHOLE = "The section frames the matter as settled."


def draft_and_deps(contract=response_review.PLACED_CONTRACT):
    ctx, record, sources = two_disputes()
    proposal = {"units": [{"kind": "summary", "text": "In short.", "uses": [], "place": "row_action"},
                          {"kind": "limitation", "text": "The claim is certain to succeed. It is filed in time.", "uses": [],
                           "place": "risks"}],
                "checklists": [{"checklist": [], "time_limit_ids": [], "by_when": None}]}
    draft = response_writer.accept(proposal, ctx, sources, contract=response_writer.CASED_CONTRACT,
                                   parts=[{"dispute_id": "D1", "units": 2}], section=1)
    authorities = response_authorities.check(ctx, record, sources, draft)
    deps = response_review._dependencies(ctx, record, sources, draft, None, authority_evidence=authorities, contract=contract)
    return (ctx, record, sources), draft, authorities, deps


def returned(*whole):
    return {"misleading": [{"kind": "unsupported", "where": [], "evidence": [], "why": why} for why in whole]
            + [{"kind": "unsupported", "where": ["U1"], "evidence": [], "why": "Placed already.", "words": ["In short"]}],
            "could_be_better": [], "keep_shown": []}


def test_what_the_one_more_look_names_is_checked_as_the_reviews_own_places_are():
    _, draft, _, deps = draft_and_deps()
    again = {"returned": {"places": [
        {"finding": 1, "where": ["U2", "T1", "P999"], "words": ["certain to succeed", "not in it"]},
        {"finding": 2, "where": [], "words": []},
        {"finding": 1, "where": ["U1"], "words": []}, {"finding": 7, "where": ["U1"], "words": []}]}}
    admitted = response_review._accept_v10(returned(WHOLE, "Another."), deps, response_review.PLACED_CONTRACT, again=again)
    first, second, placed_already = admitted["proposal"]["findings"]
    assert first["unit_ids"] == [draft["units"][1]["id"]]
    assert first["words"] == [{"unit_id": draft["units"][1]["id"], "text": "certain to succeed"}]
    assert second["unit_ids"] == [] and placed_already["unit_ids"] == [draft["units"][0]["id"]], "still whole; unchanged"
    assert admitted["placed"] == again and admitted["accepted"] is False
    asides = [entry["why"] for entry in admitted["proposal"]["set_aside"] if entry["where"].startswith("placing")]
    assert asides == ["names nothing in this piece: T1", "names nothing in this piece: P999",
                      "its words are not found in the paragraph or item it names: 'not in it'",
                      "names no finding tied to no place: 1", "names no finding tied to no place: 7"]
    # v12 admits as it did: no one more look, no record of one.
    _, _, _, v12 = draft_and_deps(response_review.WORDED_CONTRACT)
    assert "placed" not in response_review._accept_v10(returned(WHOLE), v12, response_review.WORDED_CONTRACT)


class Reviewer:
    """Answers the review and its one more look from scripts, keeping each call; a script that is an exception is raised."""

    def __init__(self, review, places=None):
        self.review, self.places, self.seen = review, places, []

    def context_budget(self, tier):
        return 10 ** 6

    def structured(self, prompt, schema, tier, **kwargs):
        self.seen.append((prompt, schema, tier))
        given = self.review if prompt.operation == "core_response_review" else self.places
        if isinstance(given, Exception):
            raise given
        return _result(given, tier)


def reviewed(model):
    (ctx, record, sources), draft, authorities, _ = draft_and_deps()
    record_ = response_review.review(model, ctx, record, sources, draft, None, authority_evidence=authorities,
                                     contract=response_review.PLACED_CONTRACT)
    return record_, (ctx, record, sources, draft, authorities)


def test_the_reviewer_is_asked_once_on_its_tier_and_the_answer_replays():
    model = Reviewer(returned(WHOLE), {"places": [{"finding": 1, "where": ["U2"], "words": ["certain to succeed"]}]})
    record, (ctx, research, sources, draft, authorities) = reviewed(model)
    (review, _, _), (look, schema, tier) = model.seen
    assert (look.operation, look.system, schema, tier) == (
        "core_response_review_places", response_review.SYSTEM_PLACES, response_review.PLACES_SCHEMA, Tier.JUDGE)
    assert look.user.startswith(review.user) and json.loads(look.user.split(
        "What you found misleading and tied to no paragraph:\n")[1]) == [{"finding": 1, "why": WHOLE}]
    assert record["placed"] == {"returned": model.places} and record["proposal"]["findings"][0]["unit_ids"] == [
        draft["units"][1]["id"]]
    again = response_review.validate(json.loads(json.dumps(record)), ctx, research, sources, draft, authority_evidence=authorities)
    assert again == record
    for forged in ({**record, "placed": None}, {**record, "placed": {"returned": {"places": []}}},
                   {**record, "placed": {"failed": ""}}, {key: value for key, value in record.items() if key != "placed"}):
        with pytest.raises(ValueError):
            response_review.validate(forged, ctx, research, sources, draft, authority_evidence=authorities)


def test_nothing_is_asked_where_every_finding_names_its_place_and_a_failed_look_leaves_it_whole():
    model = Reviewer(returned())
    record, (ctx, research, sources, draft, authorities) = reviewed(model)
    assert len(model.seen) == 1 and record["placed"] is None
    assert response_review.validate(deepcopy(record), ctx, research, sources, draft, authority_evidence=authorities) == record
    with pytest.raises(ValueError):
        response_review.validate({**record, "placed": {"failed": "ProviderUnavailable"}}, ctx, research, sources, draft,
                                 authority_evidence=authorities)
    failed, _ = reviewed(Reviewer(returned(WHOLE), ProviderUnavailable("outage")))
    assert failed["placed"] == {"failed": "ProviderUnavailable"} and failed["proposal"]["findings"][0]["unit_ids"] == []
    assert response_review.validate(deepcopy(failed), ctx, research, sources, draft, authority_evidence=authorities) == failed
    # A usage limit is not a look that failed: it stops the review, as it stops any call.
    with pytest.raises(UsageLimitReached):
        reviewed(Reviewer(returned(WHOLE), UsageLimitReached("limit")))


class Placing(Scripted):
    """The scripted answer of tests/test_core_answer_sections.py, whose reviewer, asked where a finding tied to no paragraph
    lives, names the paragraph marked WHOLE (where=True) or none."""

    def __init__(self, writes, where):
        super().__init__(writes)
        self.where, self.placings = where, []

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation != "core_response_review_places":
            return super().structured(prompt, schema, tier, **kwargs)
        self.placings.append(tier)
        shown = json.loads(prompt.user.split("\n\nYour review:\n")[0])
        named = [unit["id"] for unit in shown["complete_draft_proposal"]["units"] if "WHOLE" in unit["text"]]
        return _result({"places": [{"finding": 1, "where": named if self.where else [],
                                    "words": ["WHOLE step"] if self.where else []}]}, tier)


def answered(model):
    """The two-dispute answer through the real loop on writer v15, as a new turn writes it, rendered and checked as saved."""
    ctx, record, sources = two_disputes()
    calls, worked, execution = TurnCalls(model), calculation.skipped(), turn.execution_record(record)
    sections, crossed, overview = answer_sections.answer(
        calls, ctx, record, sources, interpretation={"units": []}, execution=execution, worked=worked,
        contract=response_writer.CASED_CONTRACT)
    elements = response_rendering.render_sections(ctx, record, sources, sections=sections, cross_check=crossed,
                                                  overview=overview, time_limits=worked,
                                                  contract=response_rendering.CASED_CONTRACT)
    activity = {"interpretation": {"units": []}, "research": record, "sources": sources, "execution": execution,
                "calculation": worked, "sections": sections, "cross_check": crossed, "overview": overview}
    answer_sections.validate(activity, ctx, record, sources, worked, looked=True)
    return elements, sections


def test_a_finding_the_reviewer_then_places_goes_back_to_the_writer_like_any_other():
    def framed(round_, payload):
        return [paragraph("summary", "In short for D2."),
                paragraph("next_step", "WHOLE step, as first written." if round_ == 1 else "A plain step.")]
    model = Placing({"D2": framed}, where=True)
    elements, sections = answered(model)
    assert model.placings == [Tier.JUDGE]
    look, = sections[1]["looks"]
    assert [fault["why"] for fault in look["faults"]] == [WHOLE], "the second look was at what the reviewer named"
    texts = [element["text"] for element in elements]
    assert "A plain step." in texts and not any("WHOLE" in text for text in texts), "the paragraph was looked at again"
    assert not any("may mislead" in text for text in texts), "nothing is said of the piece as a whole"
    assert sections[1]["reviewed"]["review"]["contract"] == response_review.PLACED_CONTRACT
    assert sections[1]["reviewed"]["review"]["placed"] is None, "the paragraph written again misleads in no way, so none was asked"


def test_a_finding_still_tied_to_no_paragraph_stands_above_the_section_in_codes_words():
    def framed(round_, payload):
        return [paragraph("summary", "In short for D2."), paragraph("next_step", "WHOLE step.")]
    elements, sections = answered(Placing({"D2": framed}, where=False))
    assert sections[1]["fallback"] is None, "the section is shown"
    texts = [element["text"] for element in elements]
    notice = ("NM's independent review found that this section may mislead as a whole: asked where, it could not tie this to "
              f"any paragraph. {WHOLE} Read this section with this in mind.")
    assert texts.count(notice) == 1 and texts.index(notice) < texts.index("WHOLE step.") < len(texts)
    heading = next(index for index, element in enumerate(elements) if element["kind"] == "HEADING"
                   and element["text"].startswith("Dispute 2"))
    assert heading < texts.index(notice), "under the section's heading, above its paragraphs"
    assert not any(text.startswith("The independent check found that this section may mislead") for text in texts)


def test_a_piece_reviewed_before_v13_is_shown_as_it_was():
    (ctx, record, sources), draft, authorities, deps = draft_and_deps(response_review.WORDED_CONTRACT)
    review = response_review._accept_v10(returned(WHOLE), deps, response_review.WORDED_CONTRACT)
    piece = {"draft": draft, "authority_evidence": authorities, "review": review, "date_findings": []}
    assert response_rendering._misleads_above(piece, "this section") == []
    beside, = response_rendering._misleads_beside(piece, "this section")
    assert beside["text"].startswith("The independent check found that this section may mislead, in a way it did not tie")
    placed = {**piece, "review": response_review._accept_v10(returned(WHOLE), draft_and_deps()[3],
                                                             response_review.PLACED_CONTRACT, again={"failed": "incomplete"})}
    assert response_rendering._misleads_beside(placed, "this section") == []
    assert len(response_rendering._misleads_above(placed, "this section")) == 1


def test_the_one_more_look_is_asked_in_plain_words_and_in_a_loop():
    words = " ".join(response_review.SYSTEM_PLACES.split())
    for part in ("Message:", "Purpose:", "Outcome:", "Work in a loop", "NM acts on what misleads paragraph by paragraph",
                 "Give where empty for a finding that truly concerns the piece as a whole"):
        assert part in words, part
