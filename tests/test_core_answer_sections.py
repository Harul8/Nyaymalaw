"""Answering dispute by dispute (owner decisions P25-P27, 19 Oct 2026; plan AN.2).

Scripted fixtures exercise code's loop: each section's tries, what is left out and the
review again of what remains, the note code builds where nothing survives, the check
across the sections with its labelled correction, the overview written last, the layout,
the board's records and exact replay. They do not show that a real reviewer finds real
problems, or that a real writer corrects them; bounded live runs measure that.
"""
import json
import threading
from copy import deepcopy

import pytest

from nm.core_engine import (
    answer_sections, calculation, checklist, matter_board, research, response_rendering, response_writer, turn,
)
from nm.core_engine.calls import CONFLICT_PURPOSE, REVIEW_PURPOSE, TurnCalls
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, ProviderUnavailable, SchemaViolation, Usage
from tests.test_core_response_writer import two_disputes
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture
from tests.test_core_turn import store  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a

#: What the scripted review finds misleading, by the marker a scripted writer puts in a paragraph.
FAULTS = {"UNSUPPORTED": "unsupported", "MISQUOTED": "misquoted"}


def _result(data, tier):
    return ModelResult(None, data, tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)


def paragraph(kind, text):
    return {"kind": kind, "text": text, "uses": []}


def written(dispute, round_):
    """A section that passes: its summary and a next step."""
    return [paragraph("summary", f"In short for {dispute}."),
            paragraph("next_step", f"Take the next step for {dispute} (round {round_}).")]


def reviewed_as(payload):
    """The scripted review (v10, P29): each paragraph or checklist item carrying a fault marker
    misleads; LEAVES marks something it could add; WHOLE a misleading statement tied to no
    paragraph; LIMIT a remark on the first time limit; SLIPS a review naming nothing real."""
    draft, misleading, better = payload["complete_draft_proposal"], [], []
    for unit in draft["units"]:
        misleading += [{"kind": kind, "where": [unit["id"]], "evidence": [],
                        "why": f"Synthetic {kind} finding in {unit['id']}."}
                       for marker, kind in FAULTS.items() if marker in unit["text"]]
        if "LEAVES" in unit["text"]:
            better.append({"where": [unit["id"]], "what": "U1 does not say which court hears it, which M1 asks."})
        if "WHOLE" in unit["text"]:
            misleading.append({"kind": "unsupported", "where": [], "evidence": [],
                               "why": "The section frames the matter as settled."})
        if "LIMIT" in unit["text"]:
            misleading.append({"kind": "unsupported", "where": ["T1"], "evidence": [],
                               "why": "T1 should run from the day the memo reached the client."})
        if "SLIPS" in unit["text"]:
            misleading.append({"kind": "misquoted", "where": ["U9", "D2", unit["id"]],
                               "evidence": [{"source_id": "P999", "quote": None}],
                               "why": f"Synthetic misquoted finding in {unit['id']}."})
    for part in draft.get("checklists", ()):
        misleading += [{"kind": "unsupported", "where": [item["id"]], "evidence": [],
                        "why": "Synthetic finding on the item."}
                       for item in part["items"] if "UNSUPPORTED" in item["need"]]
    return {"misleading": misleading, "could_be_better": better}


class Scripted:
    """Writes each section from its script of rounds, reviews by the markers above, and
    names in the check across the sections each paragraph marked CONFLICT."""

    def __init__(self, writes=None, *, overview=None, changes_advice=False, fail=(), refuse=(), withhold=()):
        self.writes, self.overview, self.changes_advice = writes or {}, overview, changes_advice
        self.fail, self.lock, self.calls, self.rounds = set(fail), threading.Lock(), [], {}
        self.refuse, self.withhold = set(refuse), set(withhold)

    def context_budget(self, tier): return 100_000

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        with self.lock:
            self.calls.append((prompt.operation, payload))
            key = ((payload["this_part"]["dispute"] or {}).get("id") if prompt.operation == "core_response_writer"
                   else "overview" if prompt.operation == "core_response_overview" else None)
            if key:
                self.rounds[key] = self.rounds.get(key, 0) + 1
            round_ = self.rounds.get(key)
        if prompt.operation in self.fail or (key, round_) in self.fail:
            raise ProviderUnavailable("Synthetic provider outage")
        if prompt.operation in self.refuse:
            from nm.shared.external_ai_contracts import ModelPermissionRefused
            raise ModelPermissionRefused("External model permission is required.")
        if prompt.operation in self.withhold:
            from nm.core_engine.calls import ReleaseWithheld
            raise ReleaseWithheld("G-CORE: synthetic owned evidence that cannot be trusted")
        if prompt.operation == "core_response_writer":
            script = self.writes.get(key)
            out = script(round_, payload) if script else written(key, round_)
            out = out if isinstance(out, dict) else {"units": out}
            return _result({"checklist": [], "time_limit_ids": [], **out}, tier)
        if prompt.operation == "core_response_overview":
            units = (self.overview(round_, payload) if self.overview else
                     [paragraph("summary", "Both disputes turn on the same agreement."),
                      paragraph("next_step", "Start with the first dispute.")])
            return _result({"units": units}, tier)
        if prompt.operation == "core_response_review":
            return _result(reviewed_as(payload), tier)
        if prompt.operation == "core_response_cross_check":
            named = [shown["id"] for section in payload["sections"] for shown in section["paragraphs"]
                     if "CONFLICT" in shown["text"]]
            return _result({"conflicts": [{"unit_ids": named, "changes_advice": self.changes_advice,
                                           "mismatch": "U2 says to file by Monday; the other section says Tuesday."}]
                            if named else []}, tier)
        raise AssertionError(prompt.operation)

    def payloads(self, operation, dispute=None):
        def mine(payload):
            if dispute is None:
                return True
            if operation == "core_response_writer":
                return (payload["this_part"]["dispute"] or {}).get("id") == dispute
            return (payload.get("what_you_review") or {}).get("dispute") == dispute
        return [payload for name, payload in self.calls if name == operation and mine(payload)]


def answered(model):
    """The answer of a two-dispute matter through the real loop, layout and replay."""
    ctx, record, sources = two_disputes()
    calls, worked, execution = TurnCalls(model), calculation.skipped(), turn.execution_record(record)
    sections, crossed, overview = answer_sections.answer(
        calls, ctx, record, sources, interpretation={"units": []}, execution=execution, worked=worked)
    elements = response_rendering.render_sections(ctx, record, sources, sections=sections, cross_check=crossed,
                                                  overview=overview, time_limits=worked,
                                                  contract=response_rendering.PRESENTED_CONTRACT)
    activity = {"contract": turn.CONTRACT, "interpretation": {"units": []}, "research": record,
                "sources": sources, "execution": execution, "calculation": worked,
                "rendering_contract": response_rendering.PRESENTED_CONTRACT,
                "sections": sections, "cross_check": crossed, "overview": overview}
    return ctx, elements, activity, calls


def kinds(elements):
    return [element["kind"] for element in elements]


def refused(activity, ctx, elements, change):
    forged = deepcopy(activity)
    change(forged)
    with pytest.raises((ValueError, KeyError, TypeError, SchemaViolation)):
        turn.validate_activity(forged, ctx, elements)


def test_each_dispute_is_answered_on_its_own_and_the_overview_is_written_last():
    model = Scripted()
    ctx, elements, activity, calls = answered(model)
    first, second = activity["sections"]
    assert (first["part"], first["dispute_id"], second["part"], second["dispute_id"]) == (1, "D1", 2, "D2")
    # Each section is written and reviewed on its own, with its own questions' held law.
    written_for = {payload["this_part"]["dispute"]["id"]: payload for payload in model.payloads("core_response_writer")}
    passages = {dispute: {p["text"] for p in payload["held_passages"]["passages"] if p["kind"] == "judgment"}
                for dispute, payload in written_for.items()}
    assert sorted(written_for) == ["D1", "D2"] and passages["D1"] and not passages["D1"] & passages["D2"]
    review = model.payloads("core_response_review", "Dispute 1")[0]
    assert review["what_you_review"] == {"piece": "one dispute's section", "dispute": "Dispute 1",
                                         "other_sections_answer": ["Dispute 2"]}
    assert {p["text"] for p in review["legal_sources"]["passages"] if p["kind"] == "judgment"} == passages["D1"]
    assert review["legal_sources"] == written_for["D1"]["held_passages"]
    # Each section's paragraphs and items are its own (P26): no ID is shared across sections.
    assert [unit["id"] for unit in first["reviewed"]["draft"]["units"]] == ["t2:s1b1", "t2:s1b2"]
    assert [unit["id"] for unit in second["reviewed"]["draft"]["units"]] == ["t2:s2b1", "t2:s2b2"]
    # Checked across, then the overview written last from the sections shown, and reviewed beside them.
    operations = [name for name, _ in model.calls]
    assert operations[4:] == ["core_response_cross_check", "core_response_overview", "core_response_review"]
    assert activity["cross_check"]["proposal"] == {"conflicts": []}
    shown = model.payloads("core_response_overview")[0]["sections_shown"]
    assert [section["dispute"] for section in shown] == ["Dispute 1", "Dispute 2"]
    assert shown[0]["paragraphs"][1] == {"kind": "next_step", "place": "next_steps",
                                         "text": "Take the next step for D1 (round 1)."}
    # From turn v8 the overview sees each dispute's row (P40).
    assert shown[0]["row"] == {"what_to_do": "In short for D1.", "have_ready": None, "by_when": None}
    overview_review = model.payloads("core_response_review")[-1]
    assert overview_review["what_you_review"]["piece"] == "the overview that opens the answer, written after its sections"
    assert overview_review["legal_sources"]["passages"] == [] and len(overview_review["sections_shown"]) == 2
    assert [unit["id"] for unit in activity["overview"]["reviewed"]["draft"]["units"]] == ["t2:ob1", "t2:ob2"]
    # Turn v8 (P40, P41): "In short" opens the answer with a row for each dispute and the line on
    # what to do first, then each section under its name and what to do, in its fixed order.
    assert kinds(elements) == ["IN_SHORT", "ROW", "ROW_ACTION", "ROW", "ROW_ACTION", "DO_FIRST", "TIES",
                               "HEADING", "SUBHEAD", "STEP", "HEADING", "SUBHEAD", "STEP"]
    assert [elements[i]["text"] for i in (7, 10)] == ["Dispute 1: In short for D1.", "Dispute 2: In short for D2."]
    assert [(e.get("section"), e.get("unit")) for e in elements] == [
        (None, None), (None, None), (1, 0), (None, None), (2, 0), ("overview", 1), ("overview", 0),
        (None, None), (1, None), (1, 1), (None, None), (2, None), (2, 1)]
    assert calls.metrics()["draft_corrections"] == 0
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_what_the_review_still_faults_after_three_tries_is_left_out_and_the_rest_checked_again():
    """Owner decision P25: the third try's faulted statement is dropped, never the section;
    what remains is reviewed again without it, and the advocate is told what and why."""
    def faulty(round_, payload):
        return [paragraph("summary", "In short for D2."),
                paragraph("next_step", f"MISQUOTED and UNSUPPORTED step (round {round_})."),
                paragraph("limitation", "What the research could not establish for D2.")]
    model = Scripted({"D2": faulty})
    ctx, elements, activity, calls = answered(model)
    section = activity["sections"][1]
    rewrites = [payload["correction"] for payload in model.payloads("core_response_writer", "D2")[1:]]
    assert len(rewrites) == 2 and all(told["purpose"] == REVIEW_PURPOSE for told in rewrites)
    assert rewrites[0]["mismatch"][0]["concerns"] == ["MISQUOTED and UNSUPPORTED step (round 1)."]
    trimmed, = section["trims"]
    assert trimmed["draft"]["dropped"] == ["t2:s2b2"] and section["fallback"] is None
    assert [unit["id"] for unit in trimmed["draft"]["units"]] == ["t2:s2b1", "t2:s2b3"]
    # The review of what remains is told what was left out.
    again = model.payloads("core_response_review", "Dispute 2")[-1]
    assert again["removed_statements"] == [{"kind": "next_step", "text": "MISQUOTED and UNSUPPORTED step (round 3)."}]
    # A misquotation is never shown; the note says what was left out and why, in code's words.
    assert "MISQUOTED" not in json.dumps(elements) and "Synthetic" not in json.dumps(elements)
    note = next(e for e in elements if e["kind"] == "NOTE")
    assert note["text"] == (
        "Left out of this section: 1 paragraph, because after the rewrites NM may make the independent check "
        "still found a problem in it. What was found: A statement was not supported by the words it relies on. A "
        "quotation did not match its source word for word. What remains was checked again without it.")
    assert kinds(elements)[-4:] == ["HEADING", "SUBHEAD", "RISK", "NOTE"]
    assert calls.used("s2") == 2 and calls.used("s1") == 0
    assert turn.validate_activity(activity, ctx, elements) == activity
    refused(activity, ctx, elements, lambda forged: forged["sections"][1].update(trims=[]))
    refused(activity, ctx, elements, lambda forged: forged["sections"][1].update(fallback={"reason": "found"}))


def test_where_nothing_survives_a_note_built_by_code_stands_in_the_section():
    """Owner decision P25: where the review still faults every statement of the section,
    code's own note takes its place: the facts as the advocate gave them, the law found in its
    own words, and what is open. The other section is shown as checked; nothing is withheld
    whole."""
    def whole(round_, payload):
        return [paragraph("summary", f"UNSUPPORTED answer for D2 (round {round_}).")]
    model = Scripted({"D2": whole})
    ctx, elements, activity, _ = answered(model)
    section = activity["sections"][1]
    assert section["fallback"] == {"reason": "found"} and section["trims"] == []
    assert activity["cross_check"] is None  # one section shown has nothing to be checked against
    note = next(e for e in elements if e["kind"] == "FALLBACK")
    assert note["disclosure"] and note["sources"] == []
    assert note["fallback"]["section"] == "Dispute 2" and note["fallback"]["facts"] == ["Find the applicable law"]
    assert note["fallback"]["questions"] == ["Which rule governs point 1 of dispute 2?"]
    assert "UNSUPPORTED" not in json.dumps(elements)
    record = two_disputes()[1]
    picked = {identity for work in record["plan"]["work"] if work["dispute"]["id"] == "D2"
              for identity in research.chosen(record).get(work["id"], [])}
    assert len(note["fallback"]["provisions"]) == len(picked)
    # The overview is told the dispute could not be written in full, and why.
    shown = model.payloads("core_response_overview")[0]["sections_shown"]
    assert shown[-1]["dispute"] == "Dispute 2" and "still found problems" in shown[-1]["not_written_in_full"]
    assert kinds(elements) == ["IN_SHORT", "ROW", "ROW_ACTION", "ROW", "DO_FIRST", "TIES", "HEADING", "SUBHEAD", "STEP",
                               "HEADING", "FALLBACK"]
    # Its row in In short says why it is not a full answer (P40).
    assert elements[3]["row"]["status"] == "note" and "still found problems" in elements[3]["row"]["why"]
    assert turn.validate_activity(activity, ctx, elements) == activity
    refused(activity, ctx, elements, lambda forged: forged["sections"][1].update(fallback={"reason": "service"}))
    # The board keeps the dispute's saved checklist, since its section gave none.
    records = checklist.records(ctx, activity)
    assert [dispute["id"] for dispute in records["checklist"]["disputes"]] == ["D1"]


def test_the_note_names_the_reason_found_in_code_s_words():
    def whole(round_, payload):
        return [paragraph("summary", f"UNSUPPORTED answer for D2 (round {round_}).")]
    _, elements, _, _ = answered(Scripted({"D2": whole}))
    note = next(e for e in elements if e["kind"] == "FALLBACK")
    assert note["text"].split("\n")[0] == (
        "Not a full answer on Dispute 2: after the rewrites NM may make, the checks still found problems in it that "
        "leaving statements out could not settle. What was found: A statement was not supported by the words it "
        "relies on. In its place, NM's code sets out what it can without writing the answer: the facts "
        "as you gave them, the provisions found for this dispute in their own words, and what NM's working "
        "understanding says is still open.")
    assert note["text"].split("\n")[1] == "What you told me: “Find the applicable law”."


def item(payload, need):
    """A checklist item tied to the first held passage of the section's own law."""
    passage = payload["held_passages"]["passages"][0]
    return {"need": need, "why": "The held law requires it.", "note": None, "group": "needed",
            "law": {"source_id": passage["id"], "quote": " ".join(passage["text"].split()[:4])},
            "carries": None, "status": "not_given", "evidence": None, "asked_words": []}


def test_a_checklist_item_still_faulted_is_left_out_by_what_it_needed():
    def listed(round_, payload):
        return {"units": written("D1", round_),
                "checklist": [item(payload, "UNSUPPORTED copy of the agreement"), item(payload, "The notice sent")]}
    ctx, elements, activity, _ = answered(Scripted({"D1": listed}))
    shown = answer_sections.shown(activity["sections"][0])
    assert [entry["need"] for entry in shown["draft"]["checklists"][0]["items"]] == ["The notice sent"]
    assert [unit["id"] for unit in shown["draft"]["units"]] == ["t2:s1b1", "t2:s1b2"]
    note = next(e for e in elements if e["kind"] == "NOTE")
    assert note["text"] == (
        "Left out of the checklist for Dispute 1: “UNSUPPORTED copy of the agreement”, because after the rewrites "
        "NM may make the independent check still found a problem in it. What was found: A statement was not "
        "supported by the words it relies on. The rest of this section was checked again without it.")
    # The board takes each section's checklist as shown, without what was left out.
    records = checklist.records(ctx, activity)
    disputes = {dispute["id"]: dispute for dispute in records["checklist"]["disputes"]}
    assert [entry["need"] for entry in disputes["D1"]["items"]] == ["The notice sent"]
    assert disputes["D2"]["items"] == []
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_what_a_section_still_leaves_out_after_its_tries_is_kept_under_how_nm_checked_it_and_holds_nothing_back():
    # What the review finds missing asks for one rewrite (P33, 21 Oct 2026; P25 gave it every
    # try); after it, it is kept under "How NM checked this answer" (P39, 24 Oct 2026), and
    # nothing is dropped for it.
    def leaving(round_, payload):
        return [paragraph("summary", "In short for D1."), paragraph("next_step", "LEAVES out the court.")]
    model = Scripted({"D1": leaving})
    ctx, elements, activity, calls = answered(model)
    assert calls.used("s1") == 1 and len(model.payloads("core_response_writer", "D1")) == 2
    assert activity["sections"][0]["trims"] == [] and activity["sections"][0]["fallback"] is None
    assert "NOTE" not in kinds(elements)
    assert elements[-1]["kind"] == "CHECKED" and elements[-1]["checked"] == [{"part": "Dispute 1", "suggestions": [
        {"kind": "better", "text": "a paragraph does not say which court hears it, which a message asks."}]}]
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_a_rewrite_that_brings_a_fault_gives_way_to_the_earlier_draft_that_passed():
    # Asked to add what the first draft left out, a rewrite may bring a fault of its own: the
    # first draft, which passed but for what it leaves out, is kept and its omission said.
    def worse(round_, payload):
        if round_ == 1:
            return [paragraph("summary", "In short for D1."), paragraph("next_step", "LEAVES out the court.")]
        return [paragraph("summary", "In short for D1."), paragraph("next_step", f"UNSUPPORTED court (round {round_}).")]
    ctx, elements, activity, calls = answered(Scripted({"D1": worse}))
    section = activity["sections"][0]
    assert calls.used("s1") == 2 and section["trims"] == [] and section["fallback"] is None
    assert [unit["text"] for unit in section["reviewed"]["draft"]["units"]] == ["In short for D1.",
                                                                                "LEAVES out the court."]
    assert "UNSUPPORTED" not in json.dumps(elements)
    assert elements[-1]["kind"] == "CHECKED" and "which court hears it" in json.dumps(elements[-1]["checked"])
    assert turn.validate_activity(activity, ctx, elements) == activity


def corrected(text):
    def script(round_, payload):
        if (payload.get("correction") or {}).get("purpose") == CONFLICT_PURPOSE:
            return [paragraph("summary", "In short for D1."), paragraph("next_step", text)]
        return [paragraph("summary", "In short for D1."), paragraph("next_step", "File by Monday. CONFLICT")]
    return script


def test_a_section_corrected_after_the_check_across_the_sections_says_so_and_keeps_the_original():
    """Owner decision P27: the correction is reviewed first, the section carries a label
    saying what changed and why with the original to read, and a change to the advice is
    said at the top of the answer."""
    model = Scripted({"D1": corrected("File by Tuesday.")}, changes_advice=True)
    ctx, elements, activity, calls = answered(model)
    section = activity["sections"][0]
    assert activity["cross_check"]["proposal"]["conflicts"][0]["unit_ids"] == ["t2:s1b2"]
    assert section["edit"]["conflicts"] == [0] and answer_sections.edit_accepted(section["edit"])
    assert calls.used("e1") == 1
    edit_review = model.payloads("core_response_review", "Dispute 1")[-1]
    assert edit_review["conflicts_found"] == ["U2 says to file by Monday; the other section says Tuesday."]
    # The overview is written from the section as corrected.
    shown = model.payloads("core_response_overview")[0]["sections_shown"]
    assert shown[0]["paragraphs"][1]["text"] == "File by Tuesday."
    assert elements[0]["kind"] == "NOTICE" and elements[0]["text"] == (
        "Corrected after a check across the sections: the advice on Dispute 1 changed. What the check found: a "
        "paragraph says to file by Monday; the other section says Tuesday. The section on Dispute 1 below shows the "
        "correction, with the section as first shown kept under it.")
    label = next(e for e in elements if e["kind"] == "EDITED")
    assert label["edited"]["changes_advice"] is True
    assert [para["text"] for para in label["edited"]["original"]] == ["In short for D1.", "File by Monday. CONFLICT"]
    assert label["text"].startswith("Edited after a check across the sections. What it found:")
    following = next(e for e in elements[elements.index(label) + 1:] if e["kind"] == "STEP")
    assert following["text"] == "File by Tuesday." and following["section"] == 1
    assert turn.validate_activity(activity, ctx, elements) == activity
    refused(activity, ctx, elements, lambda forged: forged["sections"][0].update(edit=None))
    refused(activity, ctx, elements, lambda forged: forged["sections"][1].update(
        edit=deepcopy(forged["sections"][0]["edit"])))


def test_a_correction_that_does_not_pass_is_not_used_and_a_note_says_what_was_found():
    model = Scripted({"D1": corrected("File by UNSUPPORTED Wednesday.")})
    ctx, elements, activity, _ = answered(model)
    assert not answer_sections.edit_accepted(activity["sections"][0]["edit"])
    assert "EDITED" not in kinds(elements) and "Wednesday" not in json.dumps(elements)
    assert any(e["text"] == "File by Monday. CONFLICT" for e in elements)
    note = next(e for e in elements if e["kind"] == "NOTE")
    assert note["text"] == (
        "A check across the sections found that this section may not agree with another: a paragraph says to file "
        "by Monday; the other section says Tuesday. NM's correction did not pass the independent check, so this "
        "section is shown as first checked.")
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_a_check_across_the_sections_that_could_not_be_made_is_said_atop_the_answer():
    ctx, elements, activity, _ = answered(Scripted(fail={"core_response_cross_check"}))
    assert activity["cross_check"] == {"unavailable": "service"}
    assert elements[0]["kind"] == "NOTICE" and elements[0]["text"] == (
        "NM could not check the sections against each other this time (the AI service did not respond), so a "
        "conflict between them may not have been caught. Each section was checked on its own.")
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_an_overview_that_does_not_pass_is_left_out_and_said():
    def whole(round_, payload):
        return [paragraph("summary", f"UNSUPPORTED overview (round {round_}).")]
    model = Scripted(overview=whole)
    ctx, elements, activity, calls = answered(model)
    assert activity["overview"]["fallback"] == {"reason": "found"} and calls.used("o") == 2
    note = next(e for e in elements if e["kind"] == "NOTE")
    assert note["text"] == (
        "NM's line on what to do first is left out: after the rewrites NM may make, the checks "
        "still found problems in it that leaving statements out could not settle. Each dispute's section below was "
        "checked on its own.")
    assert kinds(elements)[:6] == ["IN_SHORT", "ROW", "ROW_ACTION", "ROW", "ROW_ACTION", "NOTE"]
    assert "UNSUPPORTED" not in json.dumps(elements)
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_a_service_failure_for_one_section_leaves_a_note_and_answers_the_rest():
    ctx, elements, activity, _ = answered(Scripted(fail={("D2", 1)}))
    assert activity["sections"][1]["fallback"] == {"reason": "service"}
    note = next(e for e in elements if e["kind"] == "FALLBACK")
    assert note["text"].startswith("Not a full answer on Dispute 2: the AI service did not respond.")
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_a_service_failure_for_every_section_saves_nothing():
    with pytest.raises(ProviderUnavailable):
        answered(Scripted(fail={"core_response_writer"}))


def test_the_reading_pane_finds_each_paragraph_in_its_own_section():
    # The saved-source route reads a paragraph's checks from its own section's draft (turn v6).
    from nm.app import api
    ctx, elements, activity, _ = answered(Scripted({"D1": corrected("File by Tuesday.")}))
    shown = [index for index, element in enumerate(elements) if "unit" in element]
    assert {elements[index]["section"] for index in shown} == {"overview", 1, 2}
    for index in shown:
        unit, evidence = api._shown_unit(activity, elements, index)
        assert unit["text"] == elements[index]["text"]
        assert [row["unit_id"] for row in evidence["units"]].count(unit["id"]) == 1
    with pytest.raises(IndexError):
        api._shown_unit(activity, elements, next(i for i, e in enumerate(elements) if e["kind"] == "EDITED"))


def test_the_most_urgent_section_comes_first_on_the_answer_and_on_the_board():
    """Owner decision P26: sections by the earliest last day among the worked-out time
    limits each names, then in the understanding's order."""
    def section(*names):
        return {"fallback": None, "edit": None, "trims": [],
                "reviewed": {"draft": {"checklists": [{"time_limit_ids": list(names)}]}}}
    worked = {"calculations": [{"working": {"last_day": "2026-12-01"}}, {"working": {"last_day": "2026-11-01"}}]}
    assert answer_sections.order([section("T1"), section("T2"), section(), section("T3")], worked) == [1, 0, 2, 3]
    disputes = [{"id": "D1", "name": "First"}, {"id": "D2", "name": "Second"}, {"id": "D3", "name": "Third"}]
    checklists = {"D1": {"name": "First", "time_limits": [{"last_day": "2026-12-01"}]},
                  "D2": {"name": "Second", "time_limits": [{"what": "Appeal", "not_assessed": "No date"}]},
                  "D3": {"name": "Third", "time_limits": [{"last_day": "2026-11-01"}]}}
    assert [d["id"] for d in matter_board._urgent(disputes, checklists)] == ["D3", "D1", "D2"]


def test_a_section_draft_owns_its_ids_and_replays_exactly_as_trimmed():
    ctx, record, sources = two_disputes()
    proposal = {"units": [paragraph("summary", "In short."), paragraph("next_step", "A step."),
                          paragraph("limitation", "A limit.")],
                "checklists": [{"checklist": [], "time_limit_ids": []}]}
    draft = response_writer.accept(proposal, ctx, sources, contract=response_writer.SECTION_CONTRACT,
                                   parts=[{"dispute_id": "D1", "units": 3}], section=1)
    assert draft["section"] == 1 and [unit["id"] for unit in draft["units"]] == ["t2:s1b1", "t2:s1b2", "t2:s1b3"]
    trimmed = response_writer.trim(draft, ["t2:s1b2"])
    again = response_writer.trim(trimmed, ["t2:s1b3"])
    assert again["dropped"] == ["t2:s1b2", "t2:s1b3"] and again["parts"] == [{"dispute_id": "D1", "units": 1}]
    assert response_writer.validate(again, ctx, sources) == again
    for wrong in (["t2:s1b1", "t2:s1b2", "t2:s1b3"], ["t2:s2b1"], []):
        with pytest.raises(ValueError):
            response_writer.trim(draft, wrong)
    forged = deepcopy(again)
    forged["dropped"] = ["t2:s1b2"]
    with pytest.raises(ValueError):
        response_writer.validate(forged, ctx, sources)
    with pytest.raises(ValueError):  # a v12 draft names its section; a v11 draft does not
        response_writer.accept(proposal, ctx, sources, contract=response_writer.SECTION_CONTRACT,
                               parts=[{"dispute_id": "D1", "units": 3}])


def test_the_overview_rests_on_the_sections_and_cites_no_held_law():
    ctx, record, sources = two_disputes()
    law = next(identity for identity, row in sources.items() if row["kind"] in ("provision", "judgment"))
    proposal = {"units": [{"kind": "analysis", "text": "The law settles both.",
                           "uses": [{"source_kind": sources[law]["kind"], "source_id": law}]}],
                "checklists": [{"checklist": [], "time_limit_ids": []}]}
    with pytest.raises(SchemaViolation, match="overview rests on the sections"):
        response_writer.accept(proposal, ctx, sources, contract=response_writer.SECTION_CONTRACT,
                               parts=[{"dispute_id": None, "units": 1}], section=response_writer.OVERVIEW)
    assert "The overview is given no legal passages and needs none: do not remark on that" in " ".join(
        response_writer.OVERVIEW_SYSTEM.split())


# --- the review withholds only what misleads (owner decision P29, 20 Oct 2026) -----------


def test_a_misleading_statement_tied_to_no_paragraph_is_said_beside_the_section_never_in_its_place():
    """A finding the review ties to no paragraph is the writer's to settle while the section's
    tries last; after them it is said beside the section, which is shown."""
    def framed(round_, payload):
        return [paragraph("summary", "In short for D2."), paragraph("next_step", f"WHOLE step (round {round_}).")]
    ctx, elements, activity, calls = answered(Scripted({"D2": framed}))
    section = activity["sections"][1]
    assert section["fallback"] is None and section["trims"] == [] and calls.used("s2") == 2
    assert any(e["text"] == "WHOLE step (round 3)." for e in elements)
    note = next(e for e in elements if e["kind"] == "NOTE")
    assert note["text"] == (
        "The independent check found that this section may mislead, in a way it did not tie to one paragraph, and "
        "the rewrites NM may make did not settle it: The section frames the matter as settled. Read this section "
        "with this in mind.")
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_a_review_s_slips_are_set_aside_and_never_cost_its_section():
    """The forensic of 20 Oct 2026: an ID naming nothing, a dispute's ID and a source not
    offered refused a v9 review whole. Under v10 each is set aside, saying why, and the
    finding still stands for the paragraph it names."""
    def slipping(round_, payload):
        return [paragraph("summary", "In short for D1."), paragraph("next_step", f"SLIPS step (round {round_}).")]
    ctx, elements, activity, calls = answered(Scripted({"D1": slipping}))
    section = activity["sections"][0]
    review = section["reviewed"]["review"]
    assert review["contract"] == "core_response_review_v11" and section["fallback"] is None
    assert [entry["why"] for entry in review["proposal"]["set_aside"]] == [
        "names nothing in this piece: U9", "names nothing in this piece: D2", "points to a source not offered: P999"]
    assert section["trims"][0]["draft"]["dropped"] == ["t2:s1b2"]  # the statement it misquotes, after the tries
    assert all(call["refused"] is None for call in calls.metrics()["calls"]
               if call["operation"] == "core_response_review")
    assert turn.validate_activity(activity, ctx, elements) == activity


class Unusable(Scripted):
    """Dispute 1's review returns, the given number of times, output code can use nothing of."""

    def __init__(self, times, **kwargs):
        super().__init__(**kwargs)
        self.times = times

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        if (prompt.operation == "core_response_review" and self.times
                and (payload.get("what_you_review") or {}).get("dispute") == "Dispute 1"):
            self.times -= 1
            return _result({"misleading": "U1 misleads", "could_be_better": []}, tier)
        return super().structured(prompt, schema, tier, **kwargs)


def test_a_review_code_can_use_nothing_of_is_tried_once_more_on_its_own_allowance():
    ctx, elements, activity, calls = answered(Unusable(1))
    section = activity["sections"][0]
    assert section["fallback"] is None and calls.used("s1") == 0  # none of the section's rewrites
    reviews = [call for call in calls.metrics()["calls"] if call["operation"] == "core_response_review"]
    assert sum(call["correction"] for call in reviews) == 1 and calls.metrics()["draft_corrections"] == 1
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_a_review_that_stays_unusable_leaves_code_s_note_in_its_section_s_place():
    ctx, elements, activity, calls = answered(Unusable(2))
    section = activity["sections"][0]
    assert section["fallback"] == {"reason": "review"} and calls.used("s1") == 0
    note = next(e for e in elements if e["kind"] == "FALLBACK")
    assert note["text"].startswith("Not a full answer on Dispute 1: its independent check could not be completed.")
    # Both outputs code could use nothing of are kept, and the draft no review could check (P29).
    assert [entry["step"] for entry in section["refused"]] == ["review", "review", "unreviewed"]
    assert section["refused"][0]["returned"] == {"misleading": "U1 misleads", "could_be_better": [], "keep_shown": []}
    assert section["refused"][2]["why"] == "its independent check could not be completed"
    assert section["refused"][2]["returned"]["units"][0]["text"] == "In short for D1."
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_what_code_refused_is_kept_with_why_and_an_earlier_turn_replays_without_it():
    def faulty(round_, payload):
        out = written("D2", round_)
        if round_ == 1:
            out[1]["text"] += " [An unoffered source](P999)."
        return out
    ctx, elements, activity, _ = answered(Scripted({"D2": faulty}))
    kept, = activity["sections"][1]["refused"]
    assert kept["step"] == "writing" and kept["why"] == "The link"  # code's own words, never the writer's
    assert "[An unoffered source](P999)" in kept["returned"]["units"][1]["text"]
    assert activity["sections"][0]["refused"] == [] and activity["overview"]["refused"] == []
    assert turn.validate_activity(activity, ctx, elements) == activity
    refused(activity, ctx, elements, lambda forged: forged["sections"][1]["refused"][0].update(step="guessed"))
    refused(activity, ctx, elements, lambda forged: forged["sections"][1]["refused"][0].update(why=" "))
    refused(activity, ctx, elements, lambda forged: forged["sections"][0].pop("refused"))
    # A turn saved before P29 (v6) keeps no such record and is read as it was saved (P46): its
    # version and its rendering's are ones this code reads; a v8 turn is read with v18 only.
    earlier = deepcopy(activity)
    earlier.update(contract=turn.BY_DISPUTE_CONTRACT, rendering_contract=response_rendering.BY_DISPUTE_CONTRACT)
    assert turn.known_activity(earlier) and turn.known_activity(activity)
    assert not turn.known_activity({**activity, "rendering_contract": response_rendering.BY_DISPUTE_CONTRACT})
    assert not turn.known_activity({**earlier, "rendering_contract": response_rendering.PRESENTED_CONTRACT})


# --- what the advocate receives, served -------------------------------------------------


def scripted_answers(served, scripted):
    """The served turn's research, as before, for two disputes; its answering scripted."""
    served.model.disputes = 2
    research = served.model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation in ("core_response_writer", "core_response_overview", "core_response_review",
                                "core_response_cross_check"):
            return scripted.structured(prompt, schema, tier, **kwargs)
        return research(prompt, schema, tier, **kwargs)
    served.model.structured = structured


def test_the_served_answer_shows_the_note_in_a_section_s_place(served):
    """G-FALLBACK: the advocate receives code's note, said to be no full answer, where nothing
    of a section survived its rewrites; nothing is withheld whole."""
    served.model.reject = 3
    resp = served.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-1"})
    assert resp.status_code == 200, resp.text
    note, = [element for element in resp.json()["elements"] if element["kind"] == "FALLBACK"]
    assert note["text"].startswith("Not a full answer on Dispute 1: after the rewrites NM may make")
    assert note["fallback"]["facts"] == ["Inspect this reported account."]
    assert resp.json()["committed"] == "committed"
    reopened = served.client.get(f"/api/chats/{resp.json()['chat_id']}").json()["turns"][0]
    assert reopened["elements"] == resp.json()["elements"]


def test_the_served_answer_shows_a_corrected_section_under_its_label(served):
    """G-EDITED: the advocate receives the corrected section under its Edited label, with
    the original to read, and the change to the advice said at the top."""
    scripted_answers(served, Scripted({"D1": corrected("File by Tuesday.")}, changes_advice=True))
    resp = served.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-1"})
    assert resp.status_code == 200, resp.text
    elements = resp.json()["elements"]
    assert elements[0]["kind"] == "NOTICE" and elements[0]["text"].startswith(
        "Corrected after a check across the sections: the advice on Dispute 1 changed.")
    label, = [element for element in elements if element["kind"] == "EDITED"]
    assert label["edited"]["original"][1]["text"] == "File by Monday. CONFLICT"
    assert next(e for e in elements[elements.index(label) + 1:] if e["kind"] == "STEP")["text"] == "File by Tuesday."
    reopened = served.client.get(f"/api/chats/{resp.json()['chat_id']}").json()["turns"][0]
    assert reopened["elements"] == elements
    # The board lists the disputes as the answer shows them, each with its checklist.
    board = served.client.get(f"/api/chats/{resp.json()['chat_id']}/board").json()
    assert [dispute["id"] for dispute in board["disputes"]] == ["D1", "D2"]


def test_the_served_answer_keeps_what_could_be_better_under_how_nm_checked_it(served):
    """G-NOTED (P29, P39): the advocate receives, folded at the end of the answer, what the
    independent check says a section could add or put better; nothing is left out for it."""
    def leaving(round_, payload):
        return [paragraph("summary", "In short for D1."), paragraph("next_step", "LEAVES out the court.")]
    scripted_answers(served, Scripted({"D1": leaving}))
    resp = served.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-1"})
    assert resp.status_code == 200, resp.text
    elements = resp.json()["elements"]
    assert not [element for element in elements if element["kind"] == "NOTE"]
    checked, = [element for element in elements if element["kind"] == "CHECKED"]
    assert checked["text"] == "How NM checked this answer" and checked["checked"][0]["part"] == "Dispute 1"
    assert any(element["text"] == "LEAVES out the court." for element in elements)
    reopened = served.client.get(f"/api/chats/{resp.json()['chat_id']}").json()["turns"][0]
    assert reopened["elements"] == elements


# --- saved as it is shown (owner decision P27) -----------------------------------------

ANSWERING = ("core_response_writer", "core_response_overview", "core_response_review", "core_response_cross_check")


def through_turns(scripted):
    """The research of the turn tests for two disputes; the answering scripted."""
    from tests.test_core_turn import ScriptedModel
    model = ScriptedModel(legal=True, disputes=2)
    research = model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation in ANSWERING:
            return scripted.structured(prompt, schema, tier, **kwargs)
        return research(prompt, schema, tier, **kwargs)
    model.structured = structured
    return model


def held_now(store, turn_id="t1", chat_id=None):
    from nm.core_engine.conversation import chat_matter_id, shown_of, stored_chat
    return shown_of(store.load(chat_matter_id("owner", stored_chat("owner", chat_id, turn_id))))


def test_each_part_is_saved_with_the_conversation_as_it_is_shown_and_the_commit_replaces_it(store):
    from nm.core_engine.conversation import SHOWN, chat_matter_id
    from tests.test_core_turn import run
    seen, reported = {}, []

    def overview(round_, payload):
        seen["held"] = held_now(store)  # what the page can read while the overview is written
        return [paragraph("summary", "Both disputes turn on the same agreement.")]
    response = run(store, through_turns(Scripted(overview=overview)),
                   progress=lambda stage, **detail: reported.append((stage, detail)))
    held = seen["held"]
    assert held["turn_id"] == "t1" and held["message"] == "Hello."
    assert [saved["part"] for saved in held["activity"]["sections"]] == [1, 2]
    assert held["activity"]["waiting"] == [] and held["activity"]["overview"] is None
    assert [e["kind"] for e in held["elements"]].count("HEADING") == 2
    shown = [detail for stage, detail in reported if stage == "shown"]
    assert [detail["shown"] for detail in shown] == [1, 2, 3, 4] and {d["chat_id"] for d in shown} == {response["chat_id"]}
    # The commit replaces what was shown, in the same write; the version counts the turn.
    matter = store.load(chat_matter_id("owner", response["chat_id"]))
    assert SHOWN not in matter.intake_answers and len(matter.brain_chat) == 1
    assert matter.version == response["matter_version"] == matter.brain_chat[0]["state_version"]


def test_a_turn_that_stopped_after_showing_part_of_its_answer_is_saved_with_what_it_showed(store):
    from nm.core_engine.conversation import ConversationRefused
    from nm.shared.external_ai_contracts import ModelPermissionRefused
    from tests.test_core_turn import run
    with pytest.raises(ModelPermissionRefused):
        run(store, through_turns(Scripted(refuse={"core_response_overview"})))
    held = held_now(store)
    assert [saved["part"] for saved in held["activity"]["sections"]] == [1, 2]
    # The next message of the conversation saves it first, with what it showed.
    chat_id = held["request"]["chat_id"]
    later = run(store, through_turns(Scripted()), chat_id=chat_id, turn_id="t2", message="And the second?")
    assert later["committed"] == "committed" and held_now(store, "t2", chat_id) is None
    from nm.core_engine.conversation import chat_matter_id
    rows = turn.saved_rows(store.load(chat_matter_id("owner", chat_id)), "owner")
    first = rows[0]
    assert [row["turn_id"] for row in rows] == ["t1", "t2"]
    assert first["response"]["elements"][0]["text"].startswith("NM stopped before finishing this answer.")
    assert first["activities"]["overview"]["fallback"] == {"reason": "interrupted"}
    assert any(e["kind"] == "STEP" and "D1" in e["text"] for e in first["response"]["elements"])
    # Sent again, the stopped message is the saved answer it showed, never a second one.
    assert run(store, through_turns(Scripted()), chat_id=chat_id)["replayed"]
    with pytest.raises(ConversationRefused):
        run(store, through_turns(Scripted()), chat_id=chat_id, turn_id="t1", message="A different message.")


def test_the_same_message_sent_again_after_a_stop_is_answered_afresh(store):
    from nm.shared.external_ai_contracts import ModelPermissionRefused
    from tests.test_core_turn import run
    with pytest.raises(ModelPermissionRefused):
        run(store, through_turns(Scripted(refuse={"core_response_overview"})))
    chat_id = held_now(store)["request"]["chat_id"]
    again = run(store, through_turns(Scripted()))  # the same request: chat and turn as before
    assert again["committed"] == "committed" and again["chat_id"] == chat_id and held_now(store) is None
    assert not any(e["text"].startswith("NM stopped before") for e in again["elements"])
    assert [e["kind"] for e in again["elements"]][0] == "IN_SHORT"


def test_a_turn_withheld_whole_keeps_nothing_it_showed(store):
    from nm.core_engine.conversation import ConversationRefused
    from tests.test_core_turn import run
    with pytest.raises(ConversationRefused) as refused:
        run(store, through_turns(Scripted(withhold={"core_response_overview"})))
    assert refused.value.code == "answer_withheld"
    assert held_now(store) is None



def test_the_page_reads_what_a_running_turn_has_shown_and_a_reopened_one_is_saved_with_it(served):
    """P26-P27 through the HTTP API: the progress says how much the answer has shown and in
    which conversation; the conversation holds what was shown while its turn is worked on;
    reopened once the turn stopped, it is saved with what it showed."""
    from nm.core_engine.conversation import stored_chat
    scripted_answers(served, Scripted(refuse={"core_response_overview"}))
    resp = served.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-1"})
    assert resp.status_code == 403
    chat_id = stored_chat(OWNER, None, "turn-1")
    progress = served.client.get("/api/turn-progress?turn_id=turn-1").json()
    assert progress["shown"] == 3 and progress["chat_id"] == chat_id
    # While the turn is still being worked on, the conversation holds what it has shown.
    served.app.turn_progress.report(OWNER, "turn-1", "writing_overview")
    reading = served.client.get(f"/api/chats/{chat_id}").json()
    assert reading["turns"] == [] and reading["pending"]["turn_id"] == "turn-1"
    assert [e["text"] for e in reading["pending"]["elements"] if e["kind"] == "HEADING"] == [
        "Dispute 1: In short for D1.", "Dispute 2: In short for D2."]
    board = served.client.get(f"/api/chats/{chat_id}/board").json()
    assert [dispute["id"] for dispute in board["disputes"]] == ["D1", "D2"]
    assert all("checklist" in dispute for dispute in board["disputes"])
    # Once it has stopped, reopening saves it with what it showed.
    served.app.turn_progress.end(OWNER, "turn-1", "stopped")
    reopened = served.client.get(f"/api/chats/{chat_id}").json()
    assert "pending" not in reopened and len(reopened["turns"]) == 1
    assert reopened["turns"][0]["elements"][0]["text"].startswith("NM stopped before finishing this answer.")
    assert reopened["matter_version"] == reopened["turns"][0]["matter_version"]


def test_a_page_that_knew_the_conversation_before_a_stop_can_send_the_message_again(store):
    from nm.core_engine.conversation import ConversationRefused
    from nm.shared.external_ai_contracts import ModelPermissionRefused
    from tests.test_core_turn import run
    first = run(store, through_turns(Scripted()))
    chat_id, version = first["chat_id"], first["matter_version"]
    with pytest.raises(ModelPermissionRefused):
        run(store, through_turns(Scripted(refuse={"core_response_overview"})), chat_id=chat_id, turn_id="t2",
            message="And next?", expected_version=version)
    assert held_now(store, "t2", chat_id)["base_version"] == version
    again = run(store, through_turns(Scripted()), chat_id=chat_id, turn_id="t2", message="And next?",
                expected_version=version)
    assert again["committed"] == "committed" and held_now(store, "t2", chat_id) is None
    # A page that knew an older conversation is still told it changed.
    with pytest.raises(ConversationRefused) as stale:
        run(store, through_turns(Scripted()), chat_id=chat_id, turn_id="t3", message="Later?",
            expected_version=version)
    assert stale.value.code == "stale_version"


# --- the first live run, 20 Oct 2026 -----------------------------------------------------

def section_review(proposal):
    """A section of the two-dispute matter, and what code makes of a review of it."""
    from nm.core_engine import response_authorities, response_review
    ctx, record, sources = two_disputes()
    draft = response_writer.accept({"units": [paragraph("summary", "In short."), paragraph("next_step", "A step.")],
                                    "checklists": [{"checklist": [], "time_limit_ids": []}]}, ctx, sources,
                                   contract=response_writer.SECTION_CONTRACT, parts=[{"dispute_id": "D1", "units": 2}],
                                   section=1)
    deps = response_review._dependencies(ctx, record, sources, draft, turn.execution_record(record),
                                         authority_evidence=response_authorities.check(ctx, record, sources, draft),
                                         contract=response_review.SECTION_CONTRACT)
    return response_review._accept(proposal, deps, contract=response_review.SECTION_CONTRACT)


def test_a_section_review_s_natural_slips_are_taken_as_meant_not_refused():
    """The first live run of answering dispute by dispute (20 Oct 2026) lost both sections:
    code refused each of four reviews, two after a correction. Offline, three natural slips
    were refused - a time limit's ID among the paragraphs a finding concerns, a rejection
    naming no problem, and a request called missing that names its paragraphs - two of them
    with a reason a correction could not act on."""
    from nm.shared.model_port import SchemaViolation as Refused
    ask = {"source_id": "M1", "quote": "Find the applicable law."}
    labelled = section_review({"verdict": "reject", "request_coverage": [], "findings": [
        {"category": "framing", "unit_ids": ["U1", "T3", "D2"], "sources": [], "mismatch": "U1 misstates T3."}]})
    assert labelled["proposal"]["findings"][0]["unit_ids"] == ["t2:s1b1"] and not labelled["accepted"]
    nothing = section_review({"verdict": "reject", "request_coverage": [], "findings": []})
    assert nothing["accepted"] and nothing["proposal"]["verdict"] == "accept"
    missing = section_review({"verdict": "reject", "findings": [], "request_coverage": [
        {"request": ask, "disposition": "missing", "unit_ids": ["U2"], "reason": "It names no Act."}]})
    assert missing["proposal"]["findings"] == [{"category": "omission", "unit_ids": ["t2:s1b2"], "sources": [ask],
                                                "mismatch": "It names no Act."}]
    # An ID that names nothing is still refused, and the refusal says which and what to name.
    with pytest.raises(Refused, match="Review names IDs that are not paragraphs or checklist items of this draft, or "
                                      "names one twice: U9. Name paragraphs as U1, U2 and checklist items as none"):
        section_review({"verdict": "reject", "request_coverage": [], "findings": [
            {"category": "grounding", "unit_ids": ["U9"], "sources": [], "mismatch": "x"}]})


def test_why_code_refused_an_output_is_kept_with_its_call_in_its_own_words_only():
    # The first live run could not tell why four reviews were refused.
    def faulty(round_, payload):
        out = written("D2", round_)
        if round_ == 1:
            out[1]["text"] += " [An unoffered source](P999)."
        return out
    _, _, activity, calls = answered(Scripted({"D2": faulty}))
    noted = [call["refused"] for call in calls.metrics()["calls"] if call["refused"]]
    assert noted == ["The link"]  # never the words the writer wrote
    assert all(call["refused"] is None for call in calls.metrics()["calls"] if call["operation"] != "core_response_writer")
