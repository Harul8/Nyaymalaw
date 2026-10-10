"""Fresh extraction retains its selected owned span when source words repeat."""
from dataclasses import asdict

import pytest

from nm.brain.conversation import Message
from nm.brain.disputes import extract_disputes
from nm.brain.material import extract_details, parse_material, resolve_sources
from nm.shared.model_port import SchemaViolation
from tests.test_brain_disputes import Model as DisputeModel
from tests.test_brain_disputes import dispute
from tests.test_brain_material_specialist import Model as DetailModel
from tests.test_brain_material_specialist import candidate
from tests.test_brain_material_verification import detail

REPEATED = "Sorry, Tuesday. Sorry, Tuesday."
ORIGINAL = "The event happened on Monday."


def test_source_resolution_keeps_the_selected_identity_and_exact_original_words():
    source = candidate(source_id="L2", scope="proposed")
    resolved, = resolve_sources([source], latest={"L1": "Sorry, Tuesday.",
                                                "L2": "Sorry, Tuesday."}, prior={})
    assert resolved["source_id"] == "L2" and resolved["quoted"] == "Sorry, Tuesday."
    assert source["source_id"] == "L2" and "quoted" not in source


@pytest.mark.parametrize("selected", ["L1", "L2"])
def test_detail_extraction_keeps_distinct_selected_span_id_without_an_extra_call(selected):
    row = candidate(source_id=selected, relation="corrects", prior_source_ids=["P1S1"])
    row["related_material_ids"] = ["date"]
    model = DetailModel({"details": [row]})
    (extracted,) = extract_details(
        model, earlier=(Message("old", "advocate", ORIGINAL),), latest=REPEATED,
        current_matter_id="matter", prior_material=({
            "id": "date", "kind": "event", "statement": ORIGINAL, "source_turn_id": "old",
            "quoted": ORIGINAL, "placement": "matter", "dispute_ids": [],
        },))
    assert len(model.calls) == 1
    assert extracted.source_id == selected and extracted.quoted == "Sorry, Tuesday."
    assert extracted.recorded("current", 1)["source_id"] == selected
    assert extracted.related_material_ids == ("date",)


@pytest.mark.parametrize("selected", ["L1", "L2"])
def test_dispute_extraction_uses_the_same_owned_source_identity_handoff(selected):
    row = dispute("Whether the revised event is disputed.", selected, relation="corrects",
                  prior_source_ids=["P1S1"], related=["issue"])
    model = DisputeModel([row])
    (extracted,) = extract_disputes(
        model, earlier=(Message("old", "advocate", ORIGINAL),), latest=REPEATED,
        current_matter_id="matter", prior_disputes=({
            "id": "issue", "statement": ORIGINAL, "source_turn_id": "old", "quoted": ORIGINAL,
        },))
    assert len(model.calls) == 1
    assert extracted.source_id == selected and extracted.quoted == "Sorry, Tuesday."
    assert extracted.recorded("current", 1)["source_id"] == selected


@pytest.mark.parametrize("identity", ["not-owned", "", 7, [], {}])
def test_parser_does_not_treat_a_fabricated_identity_as_a_valid_source(identity):
    row = asdict(detail("Sorry, Tuesday.", "The event happened on Tuesday."))
    row["prior_references"] = []
    row["source_id"] = identity
    with pytest.raises(SchemaViolation, match="source identity"):
        parse_material([row], latest=REPEATED, earlier=(), current_matter_id=None)


def test_owned_identity_cannot_be_reused_for_a_different_exact_passage():
    row = asdict(detail("An unrelated passage.", "A separate account is reported."))
    row.update(prior_references=[], source_id="L1")
    with pytest.raises(SchemaViolation, match="source identity"):
        parse_material([row], latest="Sorry, Tuesday. An unrelated passage. End.",
                       earlier=(), current_matter_id=None)


def test_genuine_quote_only_legacy_candidates_keep_their_previous_saved_shape():
    old = detail("An earlier source.", "The old attributed account.")
    assert old.source_id is None
    assert "source_id" not in old.recorded("old", 1)
    row = asdict(old)
    row["prior_references"] = []
    (parsed,) = parse_material([row], latest="An earlier source.", earlier=(),
                               current_matter_id=None)
    assert parsed.source_id is None and "source_id" not in parsed.recorded("old", 1)


def test_recovery_reader_receives_lean_permissions_and_complete_original_sources():
    import json
    from copy import deepcopy

    from nm.brain.mutation_contracts import AUTHORITY_CONTRACT, build_mutation_authorities
    from tests.brain_reader_fixture import scripted_source_treatments

    earlier = (Message("old", "advocate", ORIGINAL),)
    target = {"id": "date", "kind": "event", "statement": ORIGINAL,
              "source_turn_id": "old", "quoted": ORIGINAL, "placement": "matter",
              "dispute_ids": []}
    owner = {"matter_id": "matter", "advocate_id": "advocate", "turn_id": "current",
             "offer_digest": "exact-offer"}
    grant = build_mutation_authorities(
        owner=owner, expected_version=1, target_catalogue={"date": target},
        source_catalogue=scripted_source_treatments(earlier, REPEATED),
        request_indices=[0], proposals=[{
            "request_index": 0, "authority_kind": "account_contribution",
            "authority_source_ids": ["L2"], "target_scope": "exact",
            "target_ids": ["date"], "permitted_relations": ["corrects"],
        }])
    recovery = {"review_scope": {
        "owner": owner, "requests": [], "mutation_authority_contract": AUTHORITY_CONTRACT,
        "mutation_authorities": grant,
    }, "missing_source_ids": ["L2"], "retained_proposals": [],
        "reason": "The selected original correction needs representation."}
    before = deepcopy(recovery)
    row = candidate(source_id="L2", relation="corrects", prior_source_ids=["P1S1"])
    row["related_material_ids"] = ["date"]
    model = DetailModel({"details": [row]})
    (extracted,) = extract_details(
        model, earlier=earlier, latest=REPEATED, current_matter_id="matter",
        prior_material=(target,), recovery_scope=recovery)
    payload = json.loads(model.calls[0][0].user)
    shown = payload["recovery_scope"]["review_scope"]["mutation_authorities"]
    assert set(shown) == {"contract", "owner", "expected_version", "authorities"}
    assert shown["authorities"] == grant["authorities"]
    assert "".join(span["text"] for span in payload["latest_message_spans"]) == REPEATED
    assert "".join(span["text"] for span in payload["earlier_conversation"][0][
        "source_spans"]) == ORIGINAL
    assert extracted.source_id == "L2" and len(model.calls) == 1
    assert recovery == before


EARLIER_CONTEXT = (
    "An example for analysis follows. The event happened on Monday. "
    "That was hypothetical. My own account follows. The event happened on Monday.")


def test_saved_identity_retains_the_later_account_instead_of_same_word_example():
    import json

    from tests.brain_reader_fixture import scripted_source_treatments

    earlier = (Message("old", "advocate", EARLIER_CONTEXT),)
    target = {"id": "date", "kind": "event", "statement": ORIGINAL,
              "source_turn_id": "old", "quoted": ORIGINAL, "placement": "matter",
              "dispute_ids": [], "source_id": "L5"}
    row = candidate(source_id="L1", relation="corrects", prior_source_ids=[])
    row["related_material_ids"] = ["date"]
    roles = {"P1S1": "examination_material", "P1S2": "examination_material",
             "P1S3": "examination_material", "P1S4": "work_instruction",
             "P1S5": "reported_matter_account"}
    treatments = scripted_source_treatments(earlier, "Sorry, Tuesday.", roles=roles)
    model = DetailModel({"details": [row]})
    (extracted,) = extract_details(
        model, earlier=earlier, latest="Sorry, Tuesday.", current_matter_id="matter",
        prior_material=(target,), source_treatments=treatments)
    payload = json.loads(model.calls[0][0].user)
    assert payload["active_material"][0]["source_ids"] == ["P1S5"]
    assert payload["source_treatments"]["P1S2"]["content_role"] == "examination_material"
    assert payload["source_treatments"]["P1S5"]["content_role"] == "reported_matter_account"
    assert extracted.prior_references[0].quoted == ORIGINAL and len(model.calls) == 1


@pytest.mark.parametrize("identity", ["L2", "L99", "foreign", "", 7, []])
def test_saved_original_source_identity_never_falls_back_to_another_quote_match(identity):
    from nm.brain.material import addressed_sources, saved_source_ids

    _, _, prior = addressed_sources((Message("old", "advocate", EARLIER_CONTEXT),), "Current.")
    target = {"source_id": identity, "source_turn_id": "old", "quoted": ORIGINAL}
    if identity == "L2":
        # An owned ordinal cannot be rejected merely for appearing earlier.
        # It is consequential only when it contradicts the stored exact quote.
        target["quoted"] = "An example for analysis follows."
    with pytest.raises(SchemaViolation, match="source identity"):
        saved_source_ids(target, prior)


def test_saved_quote_only_legacy_sources_retain_context_aliases_without_claiming_one_identity():
    from nm.brain.material import addressed_sources, saved_source_ids

    _, _, prior = addressed_sources((Message("old", "advocate", EARLIER_CONTEXT),), "Current.")
    assert saved_source_ids({"source_turn_id": "old", "quoted": ORIGINAL}, prior) == (
        "P1S2", "P1S5")
