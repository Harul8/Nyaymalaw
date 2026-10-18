"""A section still flagged after the rewrites is held back alone (owner decision, 17 Oct
2026; gate G-SECTION). Scripted fixtures exercise code's release and replay; they do not
show that a real reviewer finds real problems."""
import pytest

from nm.core_engine import (research, response_authorities, response_rendering, response_review,
                            response_writer, turn, understanding)
from nm.core_engine.calls import ReleaseWithheld
from nm.shared.model_port import SchemaViolation
from tests.test_core_response_review import Model as ReviewModel, positive, request
from tests.test_core_response_writer import PartModel, two_disputes

pytestmark = pytest.mark.class_a

MISSING = "U3 gives the Article 54 alternatives but does not apply its fixed-date branch to M1."


def answer(model=None):
    """A three-section answer: the opening, then Dispute 1 and Dispute 2, a paragraph each."""
    ctx, record, sources = two_disputes()
    draft = response_writer.write(model or PartModel(sources), ctx, record, sources)
    return ctx, record, sources, draft


def verdict(ctx, draft, flagged=(), *, category="omission", mismatch=MISSING):
    """The review's proposal: the paragraphs at the flagged positions carry one finding."""
    data = positive(draft, requests=[request(ctx, draft)])
    if flagged:
        ids = [draft["units"][position]["id"] for position in flagged]
        data["verdict"] = "reject"
        for unit in data["units"]:
            if unit["unit_id"] in ids:
                unit["verdict"] = "rejected"
        data["findings"] = [{"category": category, "unit_ids": ids, "sources": [], "mismatch": mismatch}]
    return data


def reviewed(ctx, record, sources, draft, flagged=()):
    authorities = response_authorities.check(ctx, record, sources, draft)
    execution = turn.execution_record(record)
    review = response_review.review(ReviewModel(verdict(ctx, draft, flagged)), ctx, record, sources, draft,
                                    execution, authority_evidence=authorities)
    return authorities, execution, review


def test_a_flagged_section_is_held_back_and_said_so_in_its_place():
    ctx, record, sources, draft = answer()
    authorities, execution, review = reviewed(ctx, record, sources, draft, flagged=[2])
    assert not review["accepted"] and response_rendering.held_sections(draft, review) == [2]
    elements = response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities, held={"parts": [2], "date_findings": []})
    assert [e["kind"] for e in elements] == ["NOTICE", "QUESTION", "HEADING", "QUESTION", "HEADING", "HELD", "NOTICE"]
    assert elements[0]["text"] == (
        "This answer is incomplete: 1 of its 3 sections is held back below, because the independent check "
        "still found a problem in it after the rewrites NM may make. The sections shown were checked by the "
        "independent review.")
    held = elements[5]
    assert held["text"] == (
        "Held back: Dispute 2. After the rewrites NM may make, the independent check still found a problem in "
        "this section, so it is not shown. What the check found: Something the section needed was missing: a "
        "paragraph gives the Article 54 alternatives but does not apply its fixed-date branch to a message.")
    assert held["held"] == {"part": 2, "section": "Dispute 2",
                            "retry": "Please try the held-back section on Dispute 2 again."}
    assert elements[-1]["text"].startswith("Shall I try the held-back section again, or continue without it?")
    assert "Answer for D2?" not in str(elements)  # nothing of the held section is shown
    assert all(elements[i]["disclosure"] and elements[i]["sources"] == [] for i in (0, 5, 6))
    # Each paragraph shown names its own draft paragraph; the notices name none.
    assert [response_rendering.unit_index(elements, i) for i in (1, 3)] == [0, 1]
    for notice in (0, 2, 5, 6):
        with pytest.raises(IndexError):
            response_rendering.unit_index(elements, notice)


def test_a_held_opening_is_named_as_such_and_the_disputes_are_released():
    ctx, record, sources, draft = answer()
    authorities, execution, review = reviewed(ctx, record, sources, draft, flagged=[0])
    elements = response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities, held={"parts": [0], "date_findings": []})
    held = next(e for e in elements if e["kind"] == "HELD")
    assert held["held"]["section"] == response_rendering.OPENING
    assert [e["text"] for e in elements if e["kind"] == "QUESTION"] == ["Answer for D1?", "Answer for D2?"]


@pytest.mark.parametrize("flagged", [[1, 2], [0, 1, 2]])
def test_nothing_is_released_when_no_disputes_section_would_remain(flagged):
    ctx, record, sources, draft = answer()
    _, _, review = reviewed(ctx, record, sources, draft, flagged=flagged)
    assert response_rendering.held_sections(draft, review) is None


def test_a_finding_naming_no_paragraph_or_an_answer_without_sections_holds_nothing_back():
    _, _, _, draft = answer()
    whole = {"accepted": False, "proposal": {"findings": [
        {"category": "omission", "unit_ids": [], "sources": [], "mismatch": "A request has no answer."}]}}
    assert response_rendering.held_sections(draft, whole) is None
    flagged = {"accepted": False, "proposal": {"findings": [
        {"category": "omission", "unit_ids": [draft["units"][2]["id"]], "sources": [], "mismatch": "Missing."}]}}
    unsectioned = {key: value for key, value in draft.items() if key != "parts"}
    assert response_rendering.held_sections(unsectioned, flagged) is None
    assert response_rendering.held_sections(draft, {"accepted": True, "proposal": {"findings": []}}) == []


def test_a_release_record_must_match_what_the_checks_found():
    ctx, record, sources, draft = answer()
    authorities, execution, review = reviewed(ctx, record, sources, draft, flagged=[2])

    def render(**kw):
        return response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities, **kw)
    for wrong in ({"parts": [1], "date_findings": []}, {"parts": [], "date_findings": []}, {"parts": [2]},
                  {"parts": [2], "date_findings": [{"category": "grounding", "unit_ids": ["foreign"],
                                                    "sources": [], "mismatch": "x"}]}):
        with pytest.raises(ValueError):
            render(held=wrong)
    with pytest.raises(ValueError, match="accepted independent review"):
        render()
    with pytest.raises(ValueError, match="v10"):
        render(held={"parts": [2], "date_findings": []}, contract=response_rendering.AS_OF_CONTRACT)


def test_a_date_found_nowhere_holds_back_its_section_with_its_findings_kept():
    # The date check reads today's date, so its findings travel with the release.
    ctx, record, sources, draft = answer()
    authorities, execution, review = reviewed(ctx, record, sources, draft)
    dated = [{"category": "grounding", "unit_ids": [draft["units"][1]["id"]], "sources": [],
              "mismatch": "Dates stated here ...: 31 December 2028. Do not work out a date yourself."}]
    elements = response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities, held={"parts": [1], "date_findings": dated})
    held = next(e for e in elements if e["kind"] == "HELD")
    assert held["held"]["section"] == "Dispute 1"
    assert held["text"].endswith(
        "What the check found: A date was stated that is not in your messages or documents, the sources or the "
        "time limits code worked out.")


class Rounds(PartModel):
    """Each write says which round wrote it, so the released draft can be told apart."""
    def __init__(self, sources, counter):
        super().__init__(sources)
        self.counter = counter

    def structured(self, prompt, schema, tier, **kwargs):
        result = super().structured(prompt, schema, tier, **kwargs)
        for unit in result.data["units"]:
            unit["text"] = unit["text"].replace("?", f" (round {self.counter['writes']})?")
        return result


def scripted_turn(monkeypatch, reviews, model=None):
    """prepare() with the real rewrite loop, release and rendering; the stages before the
    writing and the two model calls are scripted. reviews: per review call, the flagged
    positions, or an exception to raise."""
    ctx, record, sources = two_disputes()
    counter = {"writes": 0, "reviews": 0}
    write, review = response_writer.write, response_review.review
    monkeypatch.setattr(understanding, "understand", lambda calls, context: {"units": []})
    monkeypatch.setattr(research, "plan", lambda calls, context, interpreted, progress=None: record["plan"])
    monkeypatch.setattr(research, "retrieve", lambda plan, searcher, context, model=None, progress=None: record)

    def scripted_write(calls, context, record_, sources_, *, keep=None, skip=(), **kw):
        counter["writes"] += 1
        return write((model or Rounds)(sources_, counter), context, record_, sources_, keep=keep, skip=skip)

    def scripted_review(calls, context, record_, sources_, draft, *, execution, authority_evidence,
                        held_back=None, **kw):
        step = reviews[counter["reviews"]]
        counter["reviews"] += 1
        if held_back is not None:
            counter.setdefault("held_back", []).append(held_back)
        if isinstance(step, Exception):
            raise step
        return review(ReviewModel(verdict(context, draft, step)), context, record_, sources_, draft, execution,
                      authority_evidence=authority_evidence, held_back=held_back)
    monkeypatch.setattr(response_writer, "write", scripted_write)
    monkeypatch.setattr(response_review, "review", scripted_review)

    class Calls:
        def context_budget(self, tier): return 100_000
    elements, activity, metrics = turn.prepare(Calls(), ctx, searcher=None)
    return ctx, elements, activity, metrics, counter


class Breaking(Rounds):
    """The first write's Dispute 2 section links a source it does not use; every section
    called is noted with the write that called it."""
    def structured(self, prompt, schema, tier, **kwargs):
        import json
        result = super().structured(prompt, schema, tier, **kwargs)
        dispute = (json.loads(prompt.user)["this_part"]["dispute"] or {}).get("id", "opening")
        self.counter.setdefault("called", []).append((self.counter["writes"], dispute))
        if dispute == "D2" and self.counter["writes"] == 1:
            result.data["units"][0]["text"] += " [An unoffered source](P999)."
        return result


def test_a_shape_correction_rewrites_only_the_section_that_failed(monkeypatch):
    """The fifth live run (18 Oct 2026): a rewrite of every section, after one section's
    misquotation, brought a new slip into one that had passed, and the answer was lost."""
    ctx, elements, activity, metrics, counter = scripted_turn(monkeypatch, [[]], model=Breaking)
    assert counter["writes"] == 2 and metrics["draft_corrections"] == 1
    assert sorted(called for write, called in counter["called"] if write == 2) == ["D2"]
    assert [unit["text"] for unit in activity["draft"]["units"]] == [
        "Answer for opening (round 1)?", "Answer for D1 (round 1)?", "Answer for D2 (round 2)?"]
    assert activity["release"] is None and turn.validate_activity(activity, ctx, elements) == activity


def test_the_turn_releases_the_checked_sections_after_the_rewrites_and_replays_them(monkeypatch):
    ctx, elements, activity, metrics, counter = scripted_turn(monkeypatch, [[2], [2], [2]])
    assert counter == {"writes": 3, "reviews": 3} and metrics["draft_corrections"] == 2
    assert activity["contract"] == turn.CONTRACT == "core_turn_v5"
    assert activity["release"] == {"parts": [2], "date_findings": []}
    assert [e["kind"] for e in elements] == ["NOTICE", "QUESTION", "HEADING", "QUESTION", "HEADING", "HELD", "NOTICE"]
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_a_failed_last_review_releases_the_draft_its_own_review_saw(monkeypatch):
    # The third review fails its shape and no correction is left: the second draft, with
    # the second review, is what is judged and released, never the unreviewed third.
    ctx, elements, activity, _, counter = scripted_turn(
        monkeypatch, [[2], [2], SchemaViolation("Synthetic review shape failure")])
    assert counter["writes"] == 3
    # Sections with no finding are kept as first written; the held one is the second round's.
    assert [e["text"] for e in elements if e["kind"] == "QUESTION"] == [
        "Answer for opening (round 1)?", "Answer for D1 (round 1)?"]
    assert activity["draft"]["units"][2]["text"] == "Answer for D2 (round 2)?"
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_what_concerns_more_than_the_sections_still_withholds_the_turn(monkeypatch):
    with pytest.raises(ReleaseWithheld, match="G-GROUND: omission"):
        scripted_turn(monkeypatch, [[1, 2], [1, 2], [1, 2]])


def test_only_what_is_missing_is_explained_wrong_words_are_named_by_kind_only():
    # Nothing that failed is shown (17 Oct 2026): an omission says what is missing; any
    # other finding concerns words that were wrong, so only its kind is said.
    wrong = {"category": "grounding", "unit_ids": ["u"], "sources": [],
             "mismatch": "U2 says the limitation period ended on 31 December 2028."}
    missing = {"category": "omission", "unit_ids": ["u"], "sources": [], "mismatch": "No reply applies Article 54."}
    said = response_rendering.found_words([wrong, missing], where="the answer")
    assert said == ("A statement was not supported by the words it relies on. Something the answer needed was "
                    "missing: No reply applies Article 54.")
    assert "2028" not in said
    ctx, record, sources, draft = answer()
    authorities, execution, review = reviewed(ctx, record, sources, draft, flagged=[2])
    review["proposal"]["findings"][0]["category"] = "grounding"
    # A grounding finding: the section is held back and its words are never repeated.
    assert response_rendering.found_words(review["proposal"]["findings"]) == (
        "A statement was not supported by the words it relies on.")


class Misquoting(Rounds):
    """Dispute 2's section quotes its law with a word dropped in every write; every section
    called is noted with the write that called it."""
    misquoted = ("D2",)

    def structured(self, prompt, schema, tier, **kwargs):
        import json
        result = super().structured(prompt, schema, tier, **kwargs)
        dispute = (json.loads(prompt.user)["this_part"]["dispute"] or {}).get("id", "opening")
        self.counter.setdefault("called", []).append((self.counter["writes"], dispute))
        if dispute in self.misquoted:
            result.data["checklist"] = [{"need": "The exception the provision makes", "group": "needed",
                                         "law": {"source_id": "P1", "quote": "Complete provision including exception"},
                                         "carries": None, "status": "not_given", "evidence": None}]
        return result


class Unlinked(Misquoting):
    """Dispute 2's section links a source it does not use in every write."""
    def structured(self, prompt, schema, tier, **kwargs):
        import json
        result = Rounds.structured(self, prompt, schema, tier, **kwargs)
        dispute = (json.loads(prompt.user)["this_part"]["dispute"] or {}).get("id", "opening")
        self.counter.setdefault("called", []).append((self.counter["writes"], dispute))
        if dispute == "D2":
            result.data["units"][0]["text"] += " [An unoffered source](P999)."
        return result


def test_a_section_code_still_refuses_after_its_rewrite_is_held_back_and_the_rest_released(monkeypatch):
    """The seventh live run (18 Oct 2026) withheld a whole answer because one section's
    quotation was still not its source's words after the rewrite, though the other two had
    passed. Owner: "withhold only the failed part and pass the remaining part"."""
    ctx, elements, activity, metrics, counter = scripted_turn(monkeypatch, [[]], model=Misquoting)
    assert metrics["draft_corrections"] == 1
    assert [part["dispute_id"] for part in activity["draft"]["parts"]] == [None, "D1"]
    assert activity["release"] == {"parts": [], "date_findings": [],
                                   "unwritten": [{"dispute_id": "D2", "found": "quotation"}]}
    assert [e["kind"] for e in elements] == ["NOTICE", "QUESTION", "HEADING", "QUESTION", "HEADING", "HELD", "NOTICE"]
    assert elements[0]["text"] == (
        "This answer is incomplete: 1 of its 3 sections is held back below, because a check still found a "
        "problem in it after the rewrites NM may make. The sections shown were checked by the independent review.")
    assert elements[4]["text"] == "Dispute 2"
    assert elements[5]["text"] == (
        "Held back: Dispute 2. After the rewrites NM may make, NM's own checks still found a problem in this "
        "section, so it is not shown. What the checks found: A quotation did not match its source word for word.")
    assert elements[5]["held"] == {"part": None, "section": "Dispute 2",
                                   "retry": "Please try the held-back section on Dispute 2 again."}
    assert elements[-1]["text"].startswith("Shall I try the held-back section again, or continue without it?")
    # The review was told the section held back, and is bound to it on reopening.
    assert counter["held_back"] == [["D2"]]
    assert turn.validate_activity(activity, ctx, elements) == activity
    wrong = {**activity, "release": {"parts": [], "date_findings": []}}
    with pytest.raises(ValueError):
        turn.validate_activity(wrong, ctx, elements)


def test_a_section_held_back_by_code_is_not_written_again_when_the_review_asks_for_a_rewrite(monkeypatch):
    ctx, elements, activity, metrics, counter = scripted_turn(monkeypatch, [[1], []], model=Unlinked)
    assert counter["writes"] == 4 and metrics["draft_corrections"] == 2
    # The review's rewrite wrote Dispute 1 alone: the held section is not written again.
    assert [called for write, called in counter["called"] if write == 4] == ["D1"]
    assert [unit["text"] for unit in activity["draft"]["units"]] == [
        "Answer for opening (round 1)?", "Answer for D1 (round 4)?"]
    assert activity["release"] == {"parts": [], "date_findings": [],
                                   "unwritten": [{"dispute_id": "D2", "found": "checks"}]}
    held = next(e for e in elements if e["kind"] == "HELD")
    assert held["text"].endswith("What the checks found: What was written did not pass NM's own checks of its "
                                 "form and sources.")
    assert counter["held_back"] == [["D2"], ["D2"]]
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_nothing_is_released_when_no_disputes_section_passes_code_checks(monkeypatch):
    class Both(Misquoting):
        misquoted = ("D1", "D2")
    with pytest.raises(SchemaViolation, match="not exact"):
        scripted_turn(monkeypatch, [[]], model=Both)


def partial(skip):
    """An answer written without the sections at skip, reviewed as told they are held back."""
    ctx, record, sources = two_disputes()
    draft = response_writer.write(PartModel(sources), ctx, record, sources, skip=skip)
    authorities = response_authorities.check(ctx, record, sources, draft)
    execution = turn.execution_record(record)
    layout = response_writer.parts(record)
    held_back = [layout[index]["dispute_id"] for index in sorted(skip)]
    review = response_review.review(ReviewModel(verdict(ctx, draft)), ctx, record, sources, draft, execution,
                                    authority_evidence=authorities, held_back=held_back)
    return ctx, record, sources, draft, authorities, execution, review


def test_a_held_opening_comes_first_and_the_disputes_follow_under_their_headings():
    ctx, record, sources, draft, authorities, execution, review = partial({0})
    elements = response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities, held={
                                             "parts": [], "date_findings": [],
                                             "unwritten": [{"dispute_id": None, "found": "checks"}]})
    assert [e["kind"] for e in elements] == ["NOTICE", "HELD", "HEADING", "QUESTION", "HEADING", "QUESTION", "NOTICE"]
    assert elements[1]["held"]["section"] == response_rendering.OPENING


def test_a_release_record_naming_code_held_sections_must_match_the_draft():
    ctx, record, sources, draft, authorities, execution, review = partial({2})

    def render(held, **kw):
        return response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities, held=held, **kw)
    assert render({"parts": [], "date_findings": [], "unwritten": [{"dispute_id": "D2", "found": "checks"}]})
    for unwritten in ([{"dispute_id": "D1", "found": "checks"}], [{"dispute_id": "D2", "found": "anything"}],
                      [], [{"dispute_id": "D2", "found": "checks"}, {"dispute_id": None, "found": "checks"}],
                      [{"dispute_id": "D2"}]):
        with pytest.raises(ValueError):
            render({"parts": [], "date_findings": [], "unwritten": unwritten})
    with pytest.raises(ValueError):  # the review was told of the held section and is bound to it
        render(None)
    with pytest.raises(ValueError):  # only v13 names sections code held back
        render({"parts": [], "date_findings": [], "unwritten": [{"dispute_id": "D2", "found": "checks"}]},
               contract=response_rendering.LISTED_CONTRACT)
