"""Writer ownership/shape checks. Fixtures do not establish semantic accuracy."""
from copy import deepcopy
import json

import pytest

from nm.core_engine.answer_sources import build
from nm.core_engine.response_writer import (
    CHECKLIST_CONTRACT, CONTRACT, LEGACY_CONTRACT, LINKS_CONTRACT, MAX_OUTPUT, PART_SCHEMA_V11, validate, write,
)
from nm.core_engine.response_writer import accept as admit
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContextOverflow, ModelError, ModelResult, SchemaViolation, Tier, Usage,
)
from tests.test_core_answer_sources import fixture

pytestmark = pytest.mark.class_a


def reference(source):
    return {"source_id": source["id"]}


def reference_v1(source):
    return {"source_id": source["id"], "quote": source["text"]}


def source_use_v1(source, **changes):
    return {**reference_v1(source), "role": "original_account", "speaker": None,
            "treatment": "not_applicable", "treatment_source": None, **changes}


def source_use_v2(source, **changes):
    result = {"source_id": source["id"], "source_kind": source["kind"]}
    if source["kind"] == "judgment":
        result.update(role="court_reasoning", speaker=None,
                      court_treatment={"status": "not_applicable"})
    result.update(changes)
    return result


def worded(uses, text):
    """Writer v5 (17 Oct 2026): each use names the words of its unit that it supports;
    a fixture's use supports its whole unit unless it says otherwise. In place, so a test
    may still change a use after building its unit."""
    for use in uses:
        use.setdefault("words", text)
    return uses


def unworded(uses):
    """An earlier writer version's uses, which name no words; in place."""
    for use in uses:
        use.pop("words", None)
    return uses


def checklisted(proposal, parts=1, *, limits="time_limit_ids"):
    """Writer v6 (18 Oct 2026): each part returns its checklist and the time limits it
    names (v7: by their IDs); a fixture's part returns none unless it says otherwise. In
    place."""
    proposal.setdefault("checklists", [{"checklist": [], limits: []} for _ in range(parts)])
    return proposal


def linked(units):
    """Writer v7 (18 Oct 2026): a unit links each source from its own words, [words](ID).
    A fixture's use that names its words is linked there instead, and uses naming the same
    words share one link; in place."""
    for unit in units if isinstance(units, list) else []:
        if not isinstance(unit, dict) or not isinstance(unit.get("text"), str):
            continue
        spans = {}
        for use in unit.get("uses") or []:
            if isinstance(use, dict) and isinstance(use.get("words"), str):
                spans.setdefault(use.pop("words"), []).append(use["source_id"])
        text, chosen = unit["text"], []
        for words, ids in spans.items():
            start = text.find(words) if words.strip() else -1
            if start >= 0 and not any(start < end and start + len(words) > begin for begin, end, _ in chosen):
                chosen.append((start, start + len(words), ids))
        out, last = [], 0
        for begin, end, ids in sorted(chosen):
            out += [text[last:begin], f"[{text[begin:end]}]({', '.join(ids)})"]
            last = end
        unit["text"] = "".join(out) + text[last:]
    return units


def unchecklisted(proposal):
    """An earlier writer version's proposal, which carries no checklists; in place."""
    proposal.pop("checklists", None)
    return proposal


def unaddressed(units):
    """Writer v8 (18 Oct 2026): a unit names no address; code records the latest message.
    In place."""
    for unit in units if isinstance(units, list) else []:
        if isinstance(unit, dict):
            unit.pop("addresses", None)
    return units


def part_output(data):
    """What one part's call returns under writer v8: its links in its text, no addresses;
    in place."""
    if isinstance(data, dict) and isinstance(data.get("units"), list):
        unaddressed(linked(data["units"]))
        data.setdefault("checklist", [])
        data.setdefault("time_limit_ids", [])
    return data


def accept(proposal, ctx, sources, **kwargs):
    """Admission as the writer's own, with a v6 or v7 proposal's checklists as checklisted
    gives and, for v7, its links as linked gives."""
    contract = kwargs.get("contract", CONTRACT)
    if contract in (CONTRACT, LINKS_CONTRACT, CHECKLIST_CONTRACT) and isinstance(proposal, dict):
        checklisted(proposal, len(kwargs.get("parts") or [None]),
                    limits="time_limits" if contract == CHECKLIST_CONTRACT else "time_limit_ids")
        if contract in (CONTRACT, LINKS_CONTRACT):
            linked(proposal.get("units"))
        if contract == CONTRACT:
            unaddressed(proposal.get("units"))
    return admit(proposal, ctx, sources, **kwargs)


def unit(sources, *, kind="question", text="Which part would you like clarified?", uses=None):
    return {"kind": kind, "text": text, "addresses": [reference(sources["t2:advocate"])],
            "uses": worded(uses or [], text)}


def unit_v1(sources, **kwargs):
    result = unit(sources, **kwargs)
    result["addresses"] = [reference_v1(sources["t2:advocate"])]
    unworded(result["uses"])
    return result


class Model:
    def __init__(self, data, *, budget=100_000, completion=Completion.COMPLETE, quarantine=False):
        self.data, self.budget, self.completion = data, budget, completion
        self.quarantine, self.calls = quarantine, []

    def context_budget(self, tier): return self.budget

    def structured(self, prompt, schema, tier, **kwargs):
        self.calls.append((prompt, schema, tier, kwargs))
        data = deepcopy(self.data)
        if prompt.operation == "core_response_writer":
            part_output(data)
        result = ModelResult(None, data, tier, "synthetic", "fixture",
                             Usage(1, 1, 0), 0, completion=self.completion)
        if self.quarantine: raise SchemaViolation("Rejected shape", rejected_result=result)
        return result


def test_complete_context_and_all_neighbouring_legal_words_reach_one_writer_call():
    history = [{"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
                "record_role": "original_account", "text": "No external contact. The allegation is disputed."}]
    ctx, record = fixture(history=history)
    ctx["current_records"] = {"reported_document": "not supplied"}
    ctx["saved_work"] = [{"id": "earlier-work", "state": "pending"}]
    sources = build(ctx, record)
    proposed = {"units": [unit(sources)]}
    model = Model(proposed)
    draft = write(model, ctx, record, sources, {"units": []}, {"operations": []})
    assert len(model.calls) == 1
    prompt, schema, tier, kwargs = model.calls[0]
    payload = json.loads(prompt.user)
    from nm.core_engine import answer_sources
    assert payload["original_context"] == answer_sources.shown_context(ctx, sources)  # short IDs, 16 Oct 2026
    assert payload["execution_evidence"] == {"operations": []}
    assert payload["interpretation_proposal"] == {"units": []}
    from nm.core_engine.answer_sources import aliases
    offered = aliases(sources)
    legal_aliases = {alias for alias in offered if alias[0] in "PJ"}
    assert {s["id"] for s in payload["held_passages"]["passages"]} == legal_aliases
    assert {offered[a] for a in legal_aliases} == {s["id"] for s in sources.values() if s["kind"] in {"provision", "judgment"}}
    # From 16 Oct 2026 every source travels by its short ID, messages included.
    assert not any(tag in prompt.user for tag in offered.values()), "sources travel by alias"
    assert any("Court rejected" in s["text"] for s in payload["held_passages"]["passages"])
    assert not any({"source_identity", "record_role"} & set(s) for s in payload["held_passages"]["passages"])
    # v4: the understanding and each question's outcome, not the plan's bookkeeping.
    understood = record["plan"]["proposal"]["understanding"]
    assert payload["research"]["understanding"] == understood and "plan_proposal" not in payload["research"]
    assert [q["work_id"] for q in payload["research"]["questions"]] == [w["id"] for w in record["plan"]["work"]]
    assert payload["this_part"] == {"part": 1, "of": 1, "opens_the_answer": True,
                                    "dispute": understood["disputes"][0], "other_parts": []}
    assert tier is Tier.HARD and kwargs == {"max_tokens": MAX_OUTPUT} and schema == PART_SCHEMA_V11
    assert prompt.operation == "core_response_writer"
    assert draft["contract"] == CONTRACT and draft["proposal"] == checklisted(unaddressed(proposed["units"]) and proposed)
    assert draft["parts"] == [{"dispute_id": understood["disputes"][0]["id"], "units": 1}]
    assert draft["units"][0]["id"] == "t2:b1"


@pytest.mark.parametrize("whole_source", [False, True])
def test_legacy_adjacent_court_treatment_is_bound_separately_to_same_owned_judgment(whole_source):
    ctx, record = fixture()
    sources = build(ctx, record)
    submission = next(s for s in sources.values() if s["kind"] == "judgment" and "Counsel" in s["text"])
    treatment = next(s for s in sources.values() if s["kind"] == "judgment" and "Court rejected" in s["text"])
    use = source_use_v1(submission, role="party_submission", speaker="Counsel",
                     treatment="rejected", treatment_source=reference_v1(treatment))
    proposal = {"units": [unit_v1(sources, kind="law", text="The submission was rejected.", uses=[use])]}
    if whole_source:
        proposal["units"][0]["addresses"][0]["quote"] = None
        use["quote"] = None
        use["treatment_source"]["quote"] = None
    draft = accept(proposal, ctx, sources, contract=LEGACY_CONTRACT)
    resolved = draft["units"][0]["uses"][0]
    assert resolved["source_id"] == submission["id"]
    assert resolved["text"] == submission["text"]
    assert resolved["start"] == 0 and resolved["end"] == len(submission["text"])
    assert resolved["treatment_source"]["source_id"] == treatment["id"]
    assert resolved["treatment_source"]["text"] == treatment["text"]
    assert resolved["role"] == "party_submission"  # Adoption/rejection never changes its role.
    assert "review" not in draft and "review" not in resolved
    assert validate(draft, ctx, sources) == draft


def test_whole_source_ids_resolve_full_attributed_accounts_without_recopied_words():
    history = [{"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
                "record_role": "original_account", "text": "First yes. Second yes."}]
    ctx, record = fixture(history=history)
    sources = build(ctx, record)
    item = unit(sources, kind="account", text="The earlier account contains two affirmations.",
                uses=[source_use_v2(sources["t1:advocate"])])
    model = Model({"units": [item]})
    draft = write(model, ctx, record, sources)
    assert len(model.calls) == 1
    accepted = draft["units"][0]
    assert accepted["addresses"][0] == {
        "source_id": "t2:advocate", "start": 0, "end": len(ctx["latest"]["text"]),
        "text": ctx["latest"]["text"]}
    assert accepted["uses"][0]["text"] == history[0]["text"]
    assert accepted["uses"][0]["start"] == 0
    assert accepted["uses"][0]["end"] == len(history[0]["text"])
    assert draft["proposal"]["units"][0]["uses"][0] == {"source_id": "t1:advocate", "source_kind": "account"}
    # Writer v7 (18 Oct 2026): the link the writer put in its own words becomes the source's
    # link, placed where those words stand once the markup is taken out.
    assert draft["proposal"]["units"][0]["text"] == "[The earlier account contains two affirmations.](t1:advocate)"
    assert accepted["text"] == "The earlier account contains two affirmations."
    assert accepted["uses"][0]["words"] == {"text": "The earlier account contains two affirmations.",
                                            "start": 0, "end": len("The earlier account contains two affirmations.")}
    assert validate(draft, ctx, sources) == draft


@pytest.mark.parametrize("target", ["address", "source", "treatment"])
def test_legacy_explicit_paraphrase_is_not_silently_replaced_with_whole_source(target):
    ctx, record = fixture()
    sources = build(ctx, record)
    submission = next(s for s in sources.values() if s["kind"] == "judgment" and "Counsel" in s["text"])
    treatment = next(s for s in sources.values() if s["kind"] == "judgment" and "Court rejected" in s["text"])
    use = source_use_v1(submission, quote=None, role="party_submission", treatment="rejected",
                     treatment_source={"source_id": treatment["id"], "quote": None})
    item = unit_v1(sources, kind="law", uses=[use])
    item["addresses"][0]["quote"] = None
    if target == "address": item["addresses"][0]["quote"] = "Locate the applicable law."
    elif target == "source": use["quote"] = "Counsel argued that payment was due."
    else: use["treatment_source"]["quote"] = "The court disagreed with counsel."
    with pytest.raises(SchemaViolation): accept({"units": [item]}, ctx, sources, contract=LEGACY_CONTRACT)


@pytest.mark.parametrize("damage", ["foreign_source", "wrong_quote", "ambiguous_quote", "wrong_address"])
def test_legacy_invalid_or_ambiguous_reference_refuses_draft_without_silent_partial_salvage(damage):
    history = [{"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
                "record_role": "original_account", "text": "First yes. Second yes."}]
    ctx, record = fixture(history=history)
    sources = build(ctx, record)
    use = source_use_v1(sources["t1:advocate"])
    broken = unit_v1(sources, kind="account", uses=[use])
    if damage == "foreign_source": use["source_id"] = "other-matter:advocate"
    elif damage == "wrong_quote": use["quote"] = "First  yes."
    elif damage == "ambiguous_quote": use["quote"] = "yes."
    else: broken["addresses"] = [reference_v1(next(s for s in sources.values() if s["kind"] == "judgment"))]
    with pytest.raises(SchemaViolation): accept({"units": [unit_v1(sources), broken]}, ctx, sources, contract=LEGACY_CONTRACT)


def test_earlier_original_request_can_be_addressed_without_losing_latest_binding():
    history = [{"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
                "record_role": "original_account", "text": "Review the retained document."}]
    ctx, record = fixture(history=history)
    sources = build(ctx, record)
    prior = unit(sources)
    prior["addresses"] = [reference(sources["t1:advocate"])]
    # Up to writer v7 a unit named the message it answered, an earlier one among them.
    draft = accept(deepcopy({"units": [prior, unit(sources)]}), ctx, sources, contract=LINKS_CONTRACT)
    assert draft["units"][0]["addresses"][0]["source_id"] == "t1:advocate"
    with pytest.raises(SchemaViolation, match="latest"):
        accept(deepcopy({"units": [prior]}), ctx, sources, contract=LINKS_CONTRACT)
    # From v8 code records the latest message as every unit's address (owner, 18 Oct 2026).
    current = accept({"units": [prior]}, ctx, sources)
    assert [address["source_id"] for address in current["units"][0]["addresses"]] == ["t2:advocate"]


def test_legacy_factual_analysis_preserves_empty_optional_speaker_metadata():
    ctx, record = fixture()
    sources = build(ctx, record)
    use = source_use_v1(sources["t2:advocate"], speaker="  ")
    proposal = {"units": [unit_v1(sources, kind="analysis", text="Your request concerns the applicable law.", uses=[use])]}
    draft = accept(proposal, ctx, sources, contract=LEGACY_CONTRACT)
    assert draft["units"][0]["uses"][0]["speaker"] is None
    assert draft["units"][0]["uses"][0]["treatment_source"] is None
    assert proposal["units"][0]["uses"][0]["speaker"] == "  "


@pytest.mark.parametrize("damage", ["no_source", "different_case", "statutory_treatment"])
def test_claimed_court_treatment_needs_exact_owned_judgment_dependency(damage):
    ctx, record = fixture()
    sources = build(ctx, record)
    judgments = [s for s in sources.values() if s["kind"] == "judgment"]
    use = source_use_v2(judgments[0], role="party_submission",
                     court_treatment={"status": "adopted", "source": reference(judgments[1])})
    if damage == "no_source": use["court_treatment"]["source"] = None
    elif damage == "different_case": sources[judgments[1]["id"]]["source_identity"]["case_id"] = "other-case"
    else: use["court_treatment"]["source"] = reference(next(s for s in sources.values() if s["kind"] == "provision"))
    with pytest.raises(SchemaViolation):
        accept({"units": [unit(sources, kind="law", uses=[use])]}, ctx, sources)


@pytest.mark.parametrize("kind", ["account", "law", "analysis"])
def test_substantive_units_need_dependencies(kind):
    ctx, record = fixture()
    sources = build(ctx, record)
    with pytest.raises(SchemaViolation, match="dependencies"):
        accept({"units": [unit(sources, kind=kind)]}, ctx, sources)


def test_reported_legal_opinion_is_not_held_legal_material():
    ctx, record = fixture()
    sources = build(ctx, record)
    with pytest.raises(SchemaViolation, match="held legal"):
        accept({"units": [unit(sources, kind="law", uses=[source_use_v2(sources["t2:advocate"])])]}, ctx, sources)


@pytest.mark.parametrize("addition", ["id", "url", "review", "status", "seal"])
def test_model_cannot_supply_rendering_or_review_proof_fields(addition):
    ctx, record = fixture()
    sources = build(ctx, record)
    item = unit(sources)
    item[addition] = "claimed proof"
    with pytest.raises(SchemaViolation): accept({"units": [item]}, ctx, sources)


def test_incomplete_provider_result_and_malformed_quarantine_are_not_salvaged():
    ctx, record = fixture()
    sources = build(ctx, record)
    for completion in (Completion.LENGTH_LIMITED, Completion.NOT_ESTABLISHED):
        model = Model({"units": [unit(sources)]}, completion=completion)
        with pytest.raises(ModelError, match="did not complete"): write(model, ctx, record, sources)
        assert len(model.calls) == 1
    for data in ({"units": []}, {"units": [unit(sources), {"text": "Missing fields"}]}):
        model = Model(data, quarantine=True)
        with pytest.raises(SchemaViolation): write(model, ctx, record, sources)
        assert len(model.calls) == 1


def test_catalogue_tampering_and_context_overflow_refuse_before_provider_call():
    ctx, record = fixture()
    sources = build(ctx, record)
    model = Model({"units": [unit(sources)]}, budget=1)
    with pytest.raises(ContextOverflow): write(model, ctx, record, sources)
    assert model.calls == []
    sources["t2:advocate"]["text"] = "Different original account."
    with pytest.raises(ValueError, match="owned context"): write(model, ctx, record, sources)
    assert model.calls == []


def test_no_arbitrary_length_or_keyword_heuristic_claims_semantic_correctness():
    ctx, record = fixture()
    sources = build(ctx, record)
    text = "I saved the correction. " * 200
    # This is a deliberate semantic error. Shape acceptance MUST NOT be confused
    # with permission to release it; independent review owns its meaning.
    draft = accept({"units": [unit(sources, kind="limitation", text=text)]}, ctx, sources)
    assert draft["units"][0]["text"] == text


def test_gap_scope_rule_reaches_the_writer_without_a_keyword_filter():
    # A search that did not return a source says nothing about what is held: an
    # 11 Oct answer said "the held material does not include" a lien provision the
    # corpus holds. The writer contract owns a gap's scope; a pinned-model replay
    # measures it. Shape acceptance stays neutral and review judges the meaning.
    ctx, record = fixture()
    sources = build(ctx, record)
    text = "The held material does not include a provision on this point."
    model = Model({"units": [unit(sources, kind="limitation", text=text)]})
    draft = write(model, ctx, record, sources)
    system = " ".join(model.calls[0][0].system.split())
    assert "what this research returned" in system
    assert "no such source is held" in system and "no such law exists" in system
    assert draft["units"][0]["text"] == text


@pytest.mark.parametrize("damage", ["text", "id", "reference", "contract", "extra_field"])
def test_saved_or_reviewed_draft_rebinds_all_projection_fields(damage):
    ctx, record = fixture()
    sources = build(ctx, record)
    draft = accept({"units": [unit(sources)]}, ctx, sources)
    assert validate(draft, ctx, sources) == draft
    if damage in {"text", "id"}: draft["units"][0][damage] = "Changed projection"
    elif damage == "reference": draft["units"][0]["addresses"][0]["end"] -= 1
    elif damage == "contract": draft["contract"] = "unrecognised"
    else: draft["review"] = "approved"
    with pytest.raises(ValueError): validate(draft, ctx, sources)


# --- v4: one part per dispute (owner decision, 15 Oct 2026) ------------------------------

class TwoDisputeLibrary:
    """Each dispute's question finds its own judgment paragraph."""
    @staticmethod
    def searcher():
        from nm.core_engine.retrieval import HybridSearcher
        from tests.test_current_brain_retrieval import Collection
        judgments = Collection("judgment")
        judgments.rows[1]["case_id"] = "other case"
        judgments.lexical = judgments.semantic = (
            lambda query, depth: [0] if "D1Q1" in query else [1] if "D2Q1" in query else [])
        return HybridSearcher({"provision": Collection(), "judgment": judgments})


def two_disputes():
    from nm.core_engine.research import accept as accept_plan, retrieve
    from tests.test_core_research import Model as ResearchModel, proposal as research_proposal
    from tests.test_core_understanding import context
    ctx = context("Find the applicable law.")
    record = retrieve(accept_plan(research_proposal(1, 2), ctx), TwoDisputeLibrary.searcher(), ctx,
                      model=ResearchModel())
    return ctx, record, build(ctx, record)


class PartModel:
    """Each part answers with one unit naming its dispute and records what it was shown."""
    def __init__(self, sources, *, broken=None):
        import threading
        self.sources, self.broken, self.seen, self.lock = sources, broken, [], threading.Lock()

    def context_budget(self, tier): return 100_000

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        with self.lock:
            self.seen.append(payload)
        dispute = (payload["this_part"]["dispute"] or {}).get("id", "opening")
        data = part_output({"units": [unit(self.sources, text=f"Answer for {dispute}?")]})
        if self.broken in (dispute, "every"):
            data["units"][0]["addresses"] = [{"source_id": "not offered"}]
        return ModelResult(None, data, tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                           completion=Completion.COMPLETE)


def test_each_dispute_is_written_in_its_own_part_seeing_only_its_own_sources():
    ctx, record, sources = two_disputes()
    model = PartModel(sources)
    draft = write(model, ctx, record, sources)
    shown = {(p["this_part"]["dispute"] or {}).get("id", "opening"): p for p in model.seen}
    assert sorted(shown) == ["D1", "D2", "opening"] and len(model.seen) == 3
    # The opening part: no dispute, no legal sources, names every dispute answered elsewhere.
    opening = shown["opening"]["this_part"]
    assert opening["opens_the_answer"] and opening["other_parts"] == ["Dispute 1", "Dispute 2"]
    assert shown["opening"]["held_passages"]["passages"] == [] and shown["opening"]["research"]["questions"] == []
    assert not shown["D1"]["this_part"]["opens_the_answer"] and shown["D1"]["this_part"]["other_parts"] == ["Dispute 2"]
    texts = {d: {p["text"] for p in shown[d]["held_passages"]["passages"] if p["kind"] == "judgment"} for d in ("D1", "D2")}
    assert texts["D1"] and texts["D2"] and not texts["D1"] & texts["D2"]
    from nm.core_engine import answer_sources
    assert all(p["original_context"] == answer_sources.shown_context(ctx, sources) for p in model.seen)
    assert draft["parts"] == [{"dispute_id": None, "units": 1}, {"dispute_id": "D1", "units": 1},
                              {"dispute_id": "D2", "units": 1}]
    assert [u["text"] for u in draft["units"]] == ["Answer for opening?", "Answer for D1?", "Answer for D2?"]
    assert [u["id"] for u in draft["units"]] == ["t2:b1", "t2:b2", "t2:b3"]
    assert validate(deepcopy(draft), ctx, sources) == draft


def test_a_correction_rewrites_only_the_part_a_finding_names():
    from nm.core_engine.response_writer import kept_parts
    ctx, record, sources = two_disputes()
    draft = write(PartModel(sources), ctx, record, sources)
    finding = {"category": "grounding", "unit_ids": [draft["units"][2]["id"]], "sources": [], "mismatch": "x"}
    kept = kept_parts(draft, [finding])
    assert list(kept) == [0, 1]
    again = PartModel(sources)
    corrected = write(again, ctx, record, sources, keep=kept)
    assert [p["this_part"]["dispute"]["id"] for p in again.seen] == ["D2"]
    assert [u["text"] for u in corrected["units"][:2]] == [u["text"] for u in draft["units"][:2]]
    assert kept_parts(draft, [{**finding, "unit_ids": []}]) == {}  # an omission reopens every part


def test_a_malformed_part_refuses_the_whole_draft_for_correction():
    ctx, record, sources = two_disputes()
    with pytest.raises(SchemaViolation) as refused:
        write(PartModel(sources, broken="D2"), ctx, record, sources)
    # The sections that pass code's checks on their own are kept for the correction, which
    # then writes only the one that failed (owner, 18 Oct 2026).
    assert sorted(refused.value.kept) == [0, 1]
    again = PartModel(sources)
    corrected = write(again, ctx, record, sources, keep=refused.value.kept)
    assert [p["this_part"]["dispute"]["id"] for p in again.seen] == ["D2"]
    assert [u["text"] for u in corrected["units"]] == ["Answer for opening?", "Answer for D1?", "Answer for D2?"]
    # A fault in every section keeps none.
    with pytest.raises(SchemaViolation) as everywhere:
        write(PartModel(sources, broken="every"), ctx, record, sources)
    assert everywhere.value.kept == {}


@pytest.mark.parametrize("change", ["count", "dispute", "empty", "extra"])
def test_a_changed_layout_cannot_replay(change):
    ctx, record, sources = two_disputes()
    draft = write(PartModel(sources), ctx, record, sources)
    forged = deepcopy(draft)
    if change == "count": forged["parts"][1]["units"] = 2
    elif change == "dispute": forged["parts"][1]["dispute_id"] = ""
    elif change == "empty": forged["parts"] = []
    else: forged["parts"][0]["title"] = "Written by code?"
    with pytest.raises(ValueError): validate(forged, ctx, sources)
    from nm.core_engine.response_writer import ALIAS_CONTRACT
    with pytest.raises(ValueError):
        accept(draft["proposal"], ctx, sources, contract=ALIAS_CONTRACT, parts=draft["parts"])


def test_the_writer_is_told_where_and_when_the_advocate_works(monkeypatch):
    """Owner decision, 15 Oct 2026: forum and today's date come from code, in India's time."""
    from datetime import date
    from nm.shared import clock_contracts
    monkeypatch.setattr(clock_contracts, "today", lambda now=None: date(2026, 10, 15))
    ctx, record, sources = two_disputes()
    model = PartModel(sources)
    write(model, ctx, record, sources)
    assert all(p["setting"] == {"advocate_practises_in": "Telangana, India", "today": "2026-10-15",
                                "weekday": "Thursday"} for p in model.seen)
    from nm.core_engine.research import conversation_text
    assert conversation_text(ctx).startswith(
        "Today is Thursday, 2026-10-15, where the advocate practises (Telangana, India).")


def test_counting_is_codes_and_the_legal_analysis_of_a_time_limit_is_the_writers():
    # 17 Oct 2026: "never work out a time limit yourself" read as "do not analyse limitation",
    # which the reviewer rightly rejected three times. The work is split plainly.
    from nm.core_engine.response_writer import SYSTEM
    words = " ".join(SYSTEM.split())
    assert "Counting is code's work: never count days" in words
    assert "The legal analysis of a time limit is yours" in words
    assert "Never count days or work out a time limit yourself" not in words
