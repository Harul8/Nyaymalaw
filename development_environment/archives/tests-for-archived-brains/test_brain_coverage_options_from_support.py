"""Native source choices derive from owned pending links or checked support.

These fixtures declare independent decisions, not semantic model accuracy.
Source-level eligibility does not replace the selected-portion admission gate.
"""

from copy import deepcopy

import pytest

from nm.brain import record_review as owner
from nm.shared.model_port import SchemaViolation, require_schema
from tests.test_brain_coverage_record_support import review

PRIMARY = "L1"
ALIAS = "P2S1"
PEER = "L2"
PEER_ALIAS = "P2S2"
UNRELATED = "L3"
REFERENCES = {
    PRIMARY: {"turn_id": "original-account", "role": "advocate",
              "quoted": "The clerk retained the parcel; the recipient denies its arrival."},
    PEER: {"turn_id": "later-account", "role": "advocate",
           "quoted": "The recipient cannot identify the final custodian."},
    UNRELATED: {"turn_id": "review-request", "role": "advocate",
                "quoted": "Examine the original account and the current record."},
}
REFERENCES[ALIAS] = deepcopy(REFERENCES[PRIMARY])
REFERENCES[PEER_ALIAS] = deepcopy(REFERENCES[PEER])
RECORDS = ("saved-record", "peer-record")
CANDIDATES = ("proposal", "peer-proposal", "held-proposal")


def options(**kwargs):
    return owner.coverage_representation_options(REFERENCES, **kwargs)


def empty_options(references=REFERENCES):
    return {source: {"record_ids": [], "candidate_ids": []} for source in references}


def record_proof(source=PRIMARY, *, portions=None, reference=None):
    catalogue = {"saved-local-source": deepcopy(
        REFERENCES[source] if reference is None else reference)}
    return {"review": review("saved-proposal", "saved-local-source", catalogue,
                             portions=portions),
            "source_references": catalogue}


def accounts():
    return {identity: set(REFERENCES) for identity in CANDIDATES}


def decisions(*, contextual=False):
    row = review("proposal", PRIMARY, REFERENCES)
    if contextual:
        account = row["account_check"]
        account["source_ids"].append(PEER)
        check = deepcopy(review("proposal", PEER, REFERENCES)["account_check"]["source_checks"][0])
        check["supports_proposal"] = False
        account["source_checks"].append(check)
    return {"proposal": row}


def selected(result, *, records=(), candidates=()):
    expected = empty_options()
    for source in (PRIMARY, ALIAS):
        expected[source] = {"record_ids": list(records), "candidate_ids": list(candidates)}
    assert result == expected


def test_empty_owned_catalogue_returns_empty_source_choices():
    assert owner.coverage_representation_options({}) == {}


@pytest.mark.parametrize("support", (None, {}))
def test_global_pools_without_checked_support_cannot_create_choices(support):
    assert options(record_ids=RECORDS, record_support=support, candidate_ids=CANDIDATES,
                   candidate_support=support) == empty_options()


def test_pending_candidate_uses_all_owned_account_sources_and_exact_aliases():
    account_ids = accounts()
    account_ids["proposal"] = {PRIMARY, PEER}
    result = options(candidate_ids=CANDIDATES, candidate_account_ids=account_ids,
                     pending_candidate_ids=("proposal",))
    expected = empty_options()
    for source in (PRIMARY, ALIAS, PEER, PEER_ALIAS):
        expected[source]["candidate_ids"] = ["proposal"]
    assert result == expected


@pytest.mark.parametrize("collection", (list, tuple, set, frozenset))
def test_pending_owned_source_collections_preserve_the_same_eligibility(collection):
    account_ids = {identity: collection((PRIMARY,)) for identity in CANDIDATES}
    selected(options(candidate_ids=CANDIDATES, candidate_account_ids=account_ids,
                     pending_candidate_ids=("proposal",)), candidates=("proposal",))


def test_reopened_candidate_does_not_remain_bound_to_its_prior_negative_read():
    prior = review("proposal", UNRELATED, REFERENCES)
    prior.update(verdict="reject", operation_supported=False)
    account_ids = accounts()
    account_ids["proposal"] = {PRIMARY, PEER}
    result = options(candidate_ids=CANDIDATES, candidate_account_ids=account_ids,
                     candidate_support={"proposal": prior}, pending_candidate_ids=("proposal",))
    assert result[UNRELATED]["candidate_ids"] == []
    assert all(result[source]["candidate_ids"] == ["proposal"]
               for source in (PRIMARY, ALIAS, PEER, PEER_ALIAS))


def test_settled_candidate_uses_positive_dependencies_and_excludes_contextual_aliases():
    result = options(candidate_ids=CANDIDATES, candidate_account_ids=accounts(),
                     candidate_support=decisions(contextual=True))
    selected(result, candidates=("proposal",))


@pytest.mark.parametrize("verdict", ("reject", "unassessed"))
def test_negative_or_unassessed_settled_candidate_has_no_representation_choices(verdict):
    prior = review("held-proposal", PRIMARY, REFERENCES)
    prior.update(verdict=verdict, operation_supported=False)
    assert options(candidate_ids=CANDIDATES, candidate_support={"held-proposal": prior}) == (
        empty_options())


def test_unused_legacy_rejection_needs_no_new_positive_support_portions():
    prior = review("held-proposal", PRIMARY, REFERENCES)
    prior.update(verdict="reject", operation_supported=False)
    prior["account_check"]["supported"] = False
    del prior["account_check"]["source_checks"][0]["support_spans"]
    assert options(candidate_ids=CANDIDATES, candidate_support={"held-proposal": prior}) == (
        empty_options())


def test_saved_record_uses_original_positive_proof_under_a_different_local_id():
    selected(options(record_ids=RECORDS, record_support={"saved-record": record_proof()}),
             records=("saved-record",))


@pytest.mark.parametrize("difference", ("turn", "quoted"))
def test_valid_saved_proof_for_a_different_original_identity_remains_unoffered(difference):
    original = deepcopy(REFERENCES[PRIMARY])
    original["turn_id" if difference == "turn" else "quoted"] += " distinct"
    result = options(record_ids=RECORDS,
                     record_support={"saved-record": record_proof(reference=original)})
    assert result == empty_options()


def test_alias_identity_ignores_source_purpose_presentation_metadata():
    references = deepcopy(REFERENCES)
    references[PRIMARY]["content_role"] = "reported_matter_account"
    references[ALIAS]["content_role"] = "uncertain"
    references[ALIAS]["reason"] = "An independent unresolved source-purpose proposal."
    selected(owner.coverage_representation_options(
        references, candidate_ids=CANDIDATES,
        candidate_account_ids={identity: {PRIMARY} for identity in CANDIDATES},
        pending_candidate_ids=("proposal",)), candidates=("proposal",))


def test_independent_record_and_candidate_peers_keep_their_own_source_choices():
    support = {"proposal": review("proposal", PRIMARY, REFERENCES),
               "peer-proposal": review("peer-proposal", PEER, REFERENCES)}
    result = options(record_ids=RECORDS, record_support={
        "saved-record": record_proof(), "peer-record": record_proof(PEER)},
        candidate_ids=CANDIDATES, candidate_support=support)
    assert set(result) == set(REFERENCES)
    for sources, record, candidate in (((PRIMARY, ALIAS), "saved-record", "proposal"),
                                       ((PEER, PEER_ALIAS), "peer-record", "peer-proposal")):
        for source in sources:
            assert result[source] == {"record_ids": [record], "candidate_ids": [candidate]}
    assert result[UNRELATED] == {"record_ids": [], "candidate_ids": []}


def test_choices_and_inputs_are_presentation_copies_not_canonical_review_metadata():
    records, candidates = {"saved-record": record_proof()}, decisions()
    account_ids = accounts()
    before = deepcopy((REFERENCES, records, candidates, account_ids))
    result = options(record_ids=RECORDS, record_support=records, candidate_ids=CANDIDATES,
                     candidate_account_ids=account_ids, candidate_support=candidates)
    selected(result, records=("saved-record",), candidates=("proposal",))
    assert (REFERENCES, records, candidates, account_ids) == before
    result[PRIMARY]["record_ids"].append("presentation-only")
    assert (REFERENCES, records, candidates, account_ids) == before
    assert result[ALIAS]["record_ids"] == ["saved-record"]


@pytest.mark.parametrize("kind", ("record", "candidate"))
def test_source_choice_does_not_certify_disjoint_selected_portion(kind):
    portions = [{"start": 0, "end": 28}]
    records = {"saved-record": record_proof(portions=portions)} if kind == "record" else {}
    candidates = {"proposal": review("proposal", PRIMARY, REFERENCES, portions=portions)}
    if kind == "record":
        candidates = {}
    native_choices = options(record_ids=RECORDS, record_support=records,
                             candidate_ids=CANDIDATES, candidate_support=candidates)
    record_ids = ["saved-record"] if kind == "record" else []
    candidate_ids = ["proposal"] if kind == "candidate" else []
    row = {"state": "complete", "reason": "The original account portions were examined.",
           "source_checks": [], "dispositions": []}
    for source, reference in REFERENCES.items():
        start = 30 if source == PRIMARY else 0
        end = len(reference["quoted"])
        row["source_checks"].append({
            "source_id": source, "content_purpose": "account",
            "substantive_spans": [{"start": start, "end": end}],
            "reason": "The fixture declares a substantive original portion."})
        row["dispositions"].append({
            "source_id": source, "start": start, "end": end,
            "status": "represented" if source == PRIMARY else "outside_scope",
            "record_ids": record_ids if source == PRIMARY else [],
            "candidate_ids": candidate_ids if source == PRIMARY else [],
            "reason": "The exact source-level representation was selected."})
    require_schema(row, owner.coverage_schema(
        tuple(REFERENCES), source_references=REFERENCES, record_ids=RECORDS,
        candidate_ids=CANDIDATES, representation_options=native_choices))
    with pytest.raises(SchemaViolation):
        owner.checked_coverage(
            row, tuple(REFERENCES), source_references=REFERENCES, record_ids=RECORDS,
            record_support=records, candidate_ids=CANDIDATES, candidate_support=candidates,
            admitted_candidate_ids=tuple(candidates))


@pytest.mark.parametrize("fault", (
    "references_not_map", "empty_source_id", "invalid_speaker", "missing_quoted",
    "record_id_empty", "candidate_id_boolean", "pending_foreign", "pending_missing_accounts",
    "accounts_not_map", "accounts_missing_candidate", "accounts_foreign_candidate",
    "accounts_invalid_collection", "accounts_foreign_source", "accounts_invalid_source",
    "records_not_map", "records_foreign_owner", "records_foreign_field",
    "candidates_not_map", "candidates_foreign_owner", "candidate_wrong_owner",
    "candidate_foreign_selected_source", "candidate_foreign_checked_source",
    "positive_missing_portions", "positive_boolean_endpoint", "negative_foreign_source",
))
def test_choices_reject_unowned_or_malformed_claimed_dependencies(fault):
    references = deepcopy(REFERENCES)
    kwargs = {"record_ids": RECORDS, "record_support": {"saved-record": record_proof()},
              "candidate_ids": CANDIDATES, "candidate_account_ids": accounts(),
              "candidate_support": decisions(), "pending_candidate_ids": ()}
    if fault == "references_not_map":
        references = []
    elif fault == "empty_source_id":
        references[""] = references.pop(PRIMARY)
    elif fault == "invalid_speaker":
        references[PRIMARY]["role"] = "nm"
    elif fault == "missing_quoted":
        del references[PRIMARY]["quoted"]
    elif fault == "record_id_empty":
        kwargs["record_ids"] = (*RECORDS, "")
    elif fault == "candidate_id_boolean":
        kwargs["candidate_ids"] = (*CANDIDATES, False)
    elif fault == "pending_foreign":
        kwargs["pending_candidate_ids"] = ("foreign",)
    elif fault == "pending_missing_accounts":
        kwargs.update(pending_candidate_ids=("proposal",), candidate_account_ids=None)
    elif fault == "accounts_not_map":
        kwargs["candidate_account_ids"] = []
    elif fault == "accounts_missing_candidate":
        del kwargs["candidate_account_ids"]["held-proposal"]
    elif fault == "accounts_foreign_candidate":
        kwargs["candidate_account_ids"]["foreign"] = {PRIMARY}
    elif fault == "accounts_invalid_collection":
        kwargs["candidate_account_ids"]["proposal"] = PRIMARY
    elif fault == "accounts_foreign_source":
        kwargs["candidate_account_ids"]["proposal"] = {"foreign"}
    elif fault == "accounts_invalid_source":
        kwargs["candidate_account_ids"]["proposal"] = {False}
    elif fault == "records_not_map":
        kwargs["record_support"] = []
    elif fault == "records_foreign_owner":
        kwargs["record_support"]["foreign"] = record_proof()
    elif fault == "records_foreign_field":
        kwargs["record_support"]["saved-record"]["candidate_ids"] = ["proposal"]
    elif fault == "candidates_not_map":
        kwargs["candidate_support"] = []
    elif fault == "candidates_foreign_owner":
        kwargs["candidate_support"]["foreign"] = review("foreign", PRIMARY, references)
    elif fault == "candidate_wrong_owner":
        kwargs["candidate_support"]["proposal"]["candidate_id"] = "peer-proposal"
    elif fault == "candidate_foreign_selected_source":
        kwargs["candidate_support"]["proposal"]["account_check"]["source_ids"] = ["foreign"]
    elif fault == "candidate_foreign_checked_source":
        kwargs["candidate_support"]["proposal"]["account_check"]["source_checks"][0][
            "source_id"] = "foreign"
    elif fault == "positive_missing_portions":
        del kwargs["candidate_support"]["proposal"]["account_check"]["source_checks"][0][
            "support_spans"]
    elif fault == "positive_boolean_endpoint":
        kwargs["candidate_support"]["proposal"]["account_check"]["source_checks"][0][
            "support_spans"][0]["start"] = False
    else:
        decision = kwargs["candidate_support"]["proposal"]
        decision.update(verdict="reject", operation_supported=False)
        decision["account_check"]["source_ids"] = ["foreign"]
    before = deepcopy((references, kwargs))
    with pytest.raises(SchemaViolation):
        owner.coverage_representation_options(references, **kwargs)
    assert (references, kwargs) == before
