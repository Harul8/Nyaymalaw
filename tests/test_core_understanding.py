"""Source admission and actual model input; no model-semantic claims from fixtures."""
import json
from copy import deepcopy

import pytest

from nm.core_engine.understanding import KINDS, accept as admit, select, source_catalogue, understand
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ContextOverflow, ModelError, ModelResult, SchemaViolation, Tier, Usage

pytestmark = pytest.mark.class_a


def test_owned_full_source_selection_cannot_introduce_copying_errors_or_normalize_words():
    original = {"source_id": "s1", "text": "the owner's words;\nunchanged wording. Again unchanged wording."}
    selected = select({"source_id": "s1", "quote": None}, {"s1": original})
    assert selected["text"] == original["text"]
    assert (selected["start"], selected["end"]) == (0, len(original["text"]))
    from nm.shared.model_port import SchemaViolation
    for quote in ("The owner's words", "unchanged wording."):
        with pytest.raises(SchemaViolation): select({"source_id": "s1", "quote": quote}, {"s1": original})
    with pytest.raises(SchemaViolation): select({"source_id": "foreign", "quote": None}, {"s1": original})
    with pytest.raises(SchemaViolation): select({"source_id": "s1", "quote": None}, {"s1": {**original, "text": ""}})


def context(text="Hello.", history=None):
    rows = history or []
    return {"position": "follow_up" if rows else "first", "conversation": rows,
            "latest": {"source_id": "t2:advocate", "turn_id": "t2", "speaker": "advocate",
                       "record_role": "original_account", "text": text},
            "current_records": {}, "saved_work": []}


def unit(quote="Hello.", **kw):
    return {"kind": "courtesy", "quote": quote, "meaning": "A greeting",
            "context": [], "requested_work": None, "desired_result": None,
            "unresolved": [], **kw}


def wire(proposal):
    """Fixtures specify a function; the actual model wire uses independent lists."""
    result = {key: [] for key in KINDS}
    for original in proposal["units"]:
        item = deepcopy(original)
        kind = item.pop("kind", "courtesy")
        key = next(key for key, value in KINDS.items() if value == kind)
        if key != "requests":
            for field in ("requested_work", "desired_result"):
                if item.get(field) is None: item.pop(field, None)
        result[key].append(item)
    return result


def accept(proposal, ctx):
    return admit(wire(proposal), ctx)


class Model:
    def __init__(self, data, *, budget=100_000, completion=Completion.COMPLETE):
        self.data, self.budget, self.completion, self.calls = wire(data), budget, completion, []

    def context_budget(self, tier): return self.budget

    def structured(self, prompt, schema, tier, **kwargs):
        self.calls.append((prompt, schema, tier, kwargs))
        return ModelResult(None, deepcopy(self.data), tier, "synthetic", "fixture",
                           Usage(1, 1, 0), 0, completion=self.completion)


def test_first_message_uses_only_opening_intro_and_one_call():
    model = Model({"units": [unit()]})
    out = understand(model, context())
    assert out["units"][0]["source"]["text"] == "Hello."
    assert out["semantic_review"] == "pending"
    assert len(model.calls) == 1
    prompt = model.calls[0][0]
    assert "opening message" in prompt.system
    assert "next message" not in prompt.system
    assert "position" not in json.loads(prompt.user)
    assert json.loads(prompt.user)["conversation"] == []


def test_complete_sustained_history_restrictions_and_saved_work_reach_call():
    rows = [{"source_id": f"t{i}:{speaker}", "turn_id": f"t{i}", "speaker": speaker,
             "record_role": "original_account" if speaker == "advocate" else "nm_interpretation",
             "text": f"Exact {i} {speaker}\nKEEP END {i}"}
            for i in range(1, 41) for speaker in ("advocate", "nm")]
    ctx = context("Continue that review.", rows)
    # Use a fresh latest identity; duplicate IDs are deliberately refused below.
    ctx["latest"].update(source_id="t41:advocate", turn_id="t41")
    ctx["current_records"] = {"restriction": "Do not contact anyone"}
    ctx["saved_work"] = [{"id": "w1", "status": "pending"}]
    model = Model({"units": [unit("Continue that review.", kind="request",
                                 requested_work="analysis", desired_result="Continue review",
                                 context=[{"source_id": "t40:advocate", "quote": "KEEP END 40"}])]})
    out = understand(model, ctx)
    payload = json.loads(model.calls[0][0].user)
    # Shown by short IDs in order (16 Oct 2026); the words and turns exactly as saved.
    assert payload["conversation"] == [{**row, "source_id": f"M{n}"} for n, row in enumerate(rows, 1)]
    assert payload["latest"]["source_id"] == "M81"
    assert payload["current_records"] == ctx["current_records"]
    assert payload["saved_work"] == ctx["saved_work"]
    assert "opening message" not in model.calls[0][0].system
    assert out["units"][0]["context"][0]["turn_id"] == "t40"


def test_a_short_id_the_model_names_is_mapped_back_to_its_owned_source():
    rows = [{"source_id": "turn_9f3c-4c8d:advocate", "turn_id": "turn_9f3c-4c8d", "speaker": "advocate",
             "record_role": "original_account", "text": "The notice went out on 5 May."}]
    ctx = context("What did I say about the notice?", rows)
    model = Model({"units": [unit("What did I say about the notice?", kind="request", requested_work="analysis",
                                 desired_result="Recall the notice", context=[{"source_id": "M1", "quote": "5 May"}])]})
    out = understand(model, ctx)
    assert out["units"][0]["context"][0]["source_id"] == "turn_9f3c-4c8d:advocate"


def test_mixed_independent_requests_and_restriction_are_not_collapsed():
    ctx = context("Hello. Review my account. Find the law. Do not send anything.")
    proposal = {"units": [unit(),
        unit("Review my account.", kind="request", requested_work="analysis", desired_result="Review account"),
        unit("Find the law.", kind="request", requested_work="research", desired_result="Find relevant law"),
        unit("Do not send anything.", kind="restriction", meaning="No sending authority")]}
    out = accept(proposal, ctx)
    assert len(out["units"]) == 4
    assert len({u["id"] for u in out["units"]}) == 4
    assert not out["issues"]


@pytest.mark.parametrize("bad", [
    unit("Invented words"),
    unit(context=[{"source_id": "another:matter", "quote": "Hello."}]),
    unit(requested_work="drafting"),
    unit(kind="request"),
    {"quote": "Hello.", "kind": "courtesy"},
])
def test_failed_unit_keeps_independent_valid_peer(bad):
    out = accept({"units": [bad, unit()]}, context())
    assert len(out["units"]) == 1
    assert out["units"][0]["kind"] == "courtesy"
    assert len(out["issues"]) == 1
    assert out["status"] == "partial"


def test_ambiguous_repeated_words_need_larger_exact_selection():
    sources = source_catalogue(context("First yes. Second yes."))
    with pytest.raises(SchemaViolation, match="multiple occurrences"):
        select({"source_id": "t2:advocate", "quote": "yes"}, sources)
    selected = select({"source_id": "t2:advocate", "quote": "Second yes."}, sources)
    assert selected["start"] == 11


def test_altered_whitespace_is_not_silently_attributed():
    out = accept({"units": [unit("A B")]}, context("A\nB"))
    assert not out["units"]
    assert "not exact" in out["issues"][0]["mismatch"]


def page(text):
    return {"s1": {"source_id": "s1", "turn_id": "t1", "speaker": "advocate",
                   "record_role": "supplied_document", "text": text}}


def test_a_document_page_line_break_is_layout_and_the_held_words_are_kept():
    # Open items round, 16 Oct 2026: a quote's space may meet the page's line break.
    held = "The defendant shall, within thirty days from the date of service of \nsummons on him, present"
    selected = select({"source_id": "s1", "quote": "date of service of summons on him"}, page(held))
    assert selected["text"] == "date of service of \nsummons on him"
    assert held[selected["start"]:selected["end"]] == selected["text"]
    # Exact words are still found first, as earlier saved selections were.
    assert select({"source_id": "s1", "quote": "of \nsummons"}, page(held))["text"] == "of \nsummons"


@pytest.mark.parametrize("quote", ["ofsummons", "date of service of summons on her", "service, of summons"])
def test_layout_never_joins_words_or_changes_them(quote):
    with pytest.raises(SchemaViolation, match="not exact"):
        select({"source_id": "s1", "quote": quote}, page("date of service of \nsummons on him"))


def test_layout_still_refuses_a_quote_found_twice():
    with pytest.raises(SchemaViolation, match="multiple occurrences"):
        select({"source_id": "s1", "quote": "thirty days"}, page("thirty\ndays, or thirty  days"))


def test_typed_words_stay_strict_unless_the_caller_names_page_text():
    typed = {"s1": {**page("A\nB")["s1"], "record_role": "original_account"}}
    with pytest.raises(SchemaViolation, match="not exact"):
        select({"source_id": "s1", "quote": "A B"}, typed)
    assert select({"source_id": "s1", "quote": "A B"}, typed, layout=True)["text"] == "A\nB"
    with pytest.raises(SchemaViolation, match="not exact"):
        select({"source_id": "s1", "quote": "A B"}, page("A\nB"), layout=False)


def test_a_refused_quotation_carries_the_sources_own_words_nearest_to_it():
    """The seventh live run (18 Oct 2026): told only that its quotation of a held provision
    was not exact, a writer copied the same words again, two of them dropped. The refusal
    keeps its words and carries the source's own words nearest to the quotation, exactly
    as they stand, for a correction to copy from."""
    held = ("(1) Where the buyer refuses to pay for the goods, the seller may claim the price of the "
            "goods.\n(2)\nWhere the price is payable on a day certain, the seller may claim the price "
            "although the property has not passed.")
    quote = "the seller may claim the price.\n(2)\nWhere the price is payable on a day certain"
    with pytest.raises(SchemaViolation) as refused:
        select({"source_id": "s1", "quote": quote}, page(held))
    # Saved research plans keep a refusal's words and their replay compares them.
    assert str(refused.value) == f"Selected quote is not exact original source text: source_id='s1', quote={quote!r}"
    assert "the price of the goods.\n(2)\nWhere the price is payable on a day certain" in refused.value.near
    assert refused.value.near in held
    with pytest.raises(SchemaViolation) as nowhere:
        select({"source_id": "s1", "quote": "words found nowhere in it"}, page(held))
    assert nowhere.value.near is None


def test_quoted_instruction_stays_information_and_nm_reference_keeps_role():
    earlier = {"source_id": "t1:nm", "turn_id": "t1", "speaker": "nm",
               "record_role": "nm_interpretation", "text": "NM's disputed interpretation"}
    text = 'The letter says "send it now".'
    proposal = {"units": [unit(text, kind="information", meaning="Reported letter wording",
        context=[{"source_id": "t1:nm", "quote": earlier["text"]}])]}
    out = accept(proposal, context(text, [earlier]))
    assert out["units"][0]["requested_work"] is None
    assert out["units"][0]["context"][0]["record_role"] == "nm_interpretation"


def test_overflow_never_trims_or_calls():
    model = Model({"units": [unit()]}, budget=100)
    with pytest.raises(ContextOverflow): understand(model, context("Long " * 100))
    assert not model.calls


def test_unfinished_result_never_admitted_or_retried_locally():
    model = Model({"units": [unit()]}, completion=Completion.NOT_ESTABLISHED)
    with pytest.raises(ModelError, match="did not complete"): understand(model, context())
    assert len(model.calls) == 1


def test_duplicate_source_identity_and_inconsistent_position_refused_before_call():
    ctx = context()
    ctx["conversation"] = [deepcopy(ctx["latest"])]
    model = Model({"units": [unit()]})
    with pytest.raises(ValueError): understand(model, ctx)
    assert not model.calls
    ctx = context()
    ctx["position"] = "follow_up"
    with pytest.raises(ValueError): understand(model, ctx)
    assert not model.calls


def test_completed_shape_rejection_is_checked_per_unit_not_silently_accepted():
    class Quarantined(Model):
        def structured(self, *args, **kwargs):
            result = super().structured(*args, **kwargs)
            raise SchemaViolation("bad unit", rejected_result=result)
    model = Quarantined({"units": [{"quote": "Hello."}, unit()]})
    out = understand(model, context())
    assert [u["id"] for u in out["units"]] == ["t2:u2"]
    assert out["issues"][0]["unit"] == "t2:u1"
    assert out["semantic_review"] == "pending"


def test_empty_interpretation_cannot_prove_the_message_was_read():
    with pytest.raises(SchemaViolation, match="empty interpretation"):
        admit({key: [] for key in KINDS}, context())


def test_a_loose_selection_places_a_quotation_whatever_its_case_spacing_or_quotation_marks():
    """The tenth live run (18 Oct 2026): a review quoted "our client presented it" where the
    advocate wrote "Our client presented it", and the answer was withheld. Where asked (the
    answer's checklist, the review's references), code places the quotation and keeps the
    source's own words; words, punctuation and their order stay as quoted."""
    typed = {"s1": {"source_id": "s1", "record_role": "original_account",
                    "text": "First, a cheque. Our client presented it on 1 September 2026; the bank’s memo says ‘Funds Insufficient’."}}
    selected = select({"source_id": "s1", "quote": "our client  presented it on 1 September 2026"}, typed, loose=True)
    assert selected["text"] == "Our client presented it on 1 September 2026"
    marks = select({"source_id": "s1", "quote": "the bank's memo says 'Funds Insufficient'"}, typed, loose=True)
    assert marks["text"] == "the bank’s memo says ‘Funds Insufficient’"
    with pytest.raises(SchemaViolation, match="not exact"):  # strict unless asked, as before
        select({"source_id": "s1", "quote": "our client presented it"}, typed)
    for wrong in ("our client presented it on 2 September 2026", "client, presented it on 1 September", "A CHEQUE"):
        with pytest.raises(SchemaViolation):  # changed words or punctuation, or too short to place
            select({"source_id": "s1", "quote": wrong}, typed, loose=True)
    twice = {"s1": {**typed["s1"], "text": "The notice was sent. the notice was sent."}}
    with pytest.raises(SchemaViolation, match="multiple occurrences"):
        select({"source_id": "s1", "quote": "THE NOTICE WAS SENT"}, twice, loose=True)


def test_the_interpretation_keeps_a_part_quoted_with_a_slip_of_case_or_spacing():
    # Forensic review, 18 Oct 2026: a part of the interpretation quoted "find the law for me"
    # where the advocate wrote "Find the law for me" was silently dropped as an issue.
    ctx = context("Please summarise my account. Find the law for me.")
    out = accept({"units": [unit("find the law  for me.", kind="request", requested_work="research",
                                 desired_result="Relevant law")]}, ctx)
    assert not out["issues"] and out["units"][0]["source"]["text"] == "Find the law for me."
