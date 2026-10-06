"""Mechanical scopes for proposed changes to attributed matter records.

The scope owner interprets original requests and contributions before record
candidates exist. This module binds those decisions; it does not decide whether
the scope interpretation, source support or record identity is semantically
correct. A reviewer cannot expand the resulting target/operation permissions.

Source selections offered as supporting evidence remain distinguishable from
canonical target passages attached for context. Selecting either never proves
support. No model call, storage write or projection is performed here.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from nm.shared.model_port import SchemaViolation

AUTHORITY_CONTRACT = "record_mutation_authority_v1"
BINDING_CONTRACT = "record_mutation_binding_v1"
RELATIONS = frozenset(("new", "adds", "corrects", "contradicts", "withdraws"))
_OWNER_FIELDS = frozenset(("matter_id", "advocate_id", "turn_id", "offer_digest"))
_PROPOSAL_FIELDS = frozenset(("request_index", "authority_kind", "authority_source_ids",
                              "target_scope", "target_ids", "permitted_relations"))


def _digest(value) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SchemaViolation("Mutation authority requires canonical JSON data") from exc
    return hashlib.sha256(encoded).hexdigest()


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise SchemaViolation(f"{name} requires a nonempty owned identity")
    return value


def _ids(values, name, *, nonempty=False):
    if (not isinstance(values, (tuple, list))
            or any(not isinstance(value, str) or not value.strip() for value in values)):
        raise SchemaViolation(f"{name} requires explicit identity selections")
    # An exact repeated reference carries no extra authority or meaning.
    result = sorted(set(values))
    if nonempty and not result:
        raise SchemaViolation(f"{name} requires at least one selected identity")
    return result


def _owner(owner):
    if not isinstance(owner, dict) or set(owner) != _OWNER_FIELDS:
        raise SchemaViolation("Mutation authority requires the complete turn owner")
    return {key: _text(owner[key], "owner." + key) for key in sorted(_OWNER_FIELDS)}


def _version(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SchemaViolation("Mutation authority requires a nonnegative snapshot version")
    return value


def _catalogues(target_catalogue, source_catalogue):
    if not isinstance(target_catalogue, dict) or not isinstance(source_catalogue, dict):
        raise SchemaViolation("Mutation authority requires owned record and source catalogues")
    targets, sources = deepcopy(target_catalogue), deepcopy(source_catalogue)
    for identity, record in targets.items():
        _text(identity, "target_catalogue key")
        if not isinstance(record, dict) or record.get("id") != identity:
            raise SchemaViolation("Mutation target catalogue has conflicting record identities")
    for identity, source in sources.items():
        _text(identity, "source_catalogue key")
        if (not isinstance(source, dict) or source.get("role") != "advocate"
                or not isinstance(source.get("turn_id"), str)
                or not source["turn_id"].strip()
                or not isinstance(source.get("quoted"), str) or not source["quoted"].strip()):
            raise SchemaViolation("Mutation authority requires exact original advocate sources")
    _digest(targets)
    _digest(sources)
    return targets, sources


def build_mutation_authorities(*, owner, expected_version, target_catalogue,
                              source_catalogue, proposals, request_indices=None):
    """Bind prior scope decisions to owned sources, targets and a fixed snapshot.

    ``proposals`` are scope-owner decisions, not extractor or reviewer output.
    ``request_indices`` should be the code-owned plan indices; omission is for
    isolated contract construction, not permission to accept invented requests.
    An account contribution can authorize a revision without an imperative or
    record_requirement. Whole-record examination must be declared explicitly.
    """
    canonical_owner = _owner(owner)
    version = _version(expected_version)
    targets, sources = _catalogues(target_catalogue, source_catalogue)
    if not isinstance(proposals, (list, tuple)):
        raise SchemaViolation("Mutation authority proposals require a declared sequence")
    permitted_indices = None
    if request_indices is not None:
        if (not isinstance(request_indices, (list, tuple, set, frozenset))
                or any(isinstance(item, bool) or not isinstance(item, int) or item < 0
                       for item in request_indices)):
            raise SchemaViolation("Mutation authority requires code-owned request indices")
        permitted_indices = set(request_indices)
    grants = []
    seen = set()
    for proposal in proposals:
        if not isinstance(proposal, dict) or set(proposal) != _PROPOSAL_FIELDS:
            raise SchemaViolation("Mutation scope decision has undeclared or missing fields")
        index = proposal["request_index"]
        if (isinstance(index, bool) or not isinstance(index, int) or index < 0
                or (permitted_indices is not None and index not in permitted_indices)):
            raise SchemaViolation("Mutation scope selects an unowned request index")
        kind = proposal["authority_kind"]
        if kind not in ("account_contribution", "interpretation_review"):
            raise SchemaViolation("Mutation scope has an unknown authority kind")
        authority_sources = _ids(proposal["authority_source_ids"], "authority_source_ids",
                                 nonempty=True)
        if not set(authority_sources) <= sources.keys():
            raise SchemaViolation("Mutation scope selects unowned authority sources")
        scope = proposal["target_scope"]
        selected_targets = _ids(proposal["target_ids"], "target_ids")
        if not set(selected_targets) <= targets.keys():
            raise SchemaViolation("Mutation scope selects unowned record targets")
        relations = _ids(proposal["permitted_relations"], "permitted_relations", nonempty=True)
        if not set(relations) <= RELATIONS:
            raise SchemaViolation("Mutation scope declares an unknown record operation")
        if scope == "reviewed_whole":
            if kind != "interpretation_review" or selected_targets:
                raise SchemaViolation(
                    "Whole-record scope requires review and no supplied target list")
            selected_targets = sorted(targets)
        elif scope != "exact":
            raise SchemaViolation("Mutation scope must declare exact or reviewed_whole")
        if (scope == "exact" and any(relation != "new" for relation in relations)
                and not selected_targets):
            raise SchemaViolation("A revision authority requires an owned target scope")
        grant = {
            "request_index": index, "authority_kind": kind,
            "authority_source_ids": authority_sources, "target_scope": scope,
            "target_ids": selected_targets, "permitted_relations": relations,
        }
        # Semantically identical declarations are not separate sources of authority.
        grant_key = _digest(grant)
        if grant_key in seen:
            continue
        seen.add(grant_key)
        grant["id"] = "mau_" + _digest({"owner": canonical_owner,
                                        "expected_version": version, "decision": grant})[:32]
        grants.append(grant)
    grants.sort(key=lambda row: (row["request_index"], row["id"]))
    ledger = {
        "contract": AUTHORITY_CONTRACT, "owner": canonical_owner,
        "expected_version": version,
        "snapshot_digest": _digest(targets), "source_digest": _digest(sources),
        "target_catalogue": targets, "source_catalogue": sources, "authorities": grants,
    }
    return {**ledger, "seal": _digest(ledger)}


def _checked_ledger(ledger):
    if not isinstance(ledger, dict) or set(ledger) != {
            "contract", "owner", "expected_version", "snapshot_digest", "source_digest",
            "target_catalogue", "source_catalogue", "authorities", "seal"}:
        raise SchemaViolation("Mutation authority ledger is absent or unreadable")
    body = {key: value for key, value in ledger.items() if key != "seal"}
    if ledger["contract"] != AUTHORITY_CONTRACT or ledger["seal"] != _digest(body):
        raise SchemaViolation("Mutation authority ledger changed after scope admission")
    _owner(ledger["owner"])
    _version(ledger["expected_version"])
    targets, sources = _catalogues(ledger["target_catalogue"], ledger["source_catalogue"])
    if (ledger["snapshot_digest"] != _digest(targets)
            or ledger["source_digest"] != _digest(sources)):
        raise SchemaViolation("Mutation authority catalogue dependencies changed")
    if not isinstance(ledger["authorities"], list):
        raise SchemaViolation("Mutation authority ledger has unreadable scopes")
    proposals = []
    for grant in ledger["authorities"]:
        if not isinstance(grant, dict) or set(grant) != {*_PROPOSAL_FIELDS, "id"}:
            raise SchemaViolation("Mutation authority ledger has an invalid scope")
        proposal = {key: value for key, value in grant.items() if key != "id"}
        if proposal["target_scope"] == "reviewed_whole":
            proposal = {**proposal, "target_ids": []}
        proposals.append(proposal)
    rebuilt = build_mutation_authorities(
        owner=ledger["owner"], expected_version=ledger["expected_version"],
        target_catalogue=targets, source_catalogue=sources, proposals=proposals)
    if rebuilt != ledger:
        raise SchemaViolation("Mutation authority ledger disagrees with its code-assigned scopes")
    return {row["id"]: row for row in ledger["authorities"]}


def _current_source_ids(current_source_reference, ledger):
    """Resolve only a code-owned identity whose exact original words still match."""
    reference_fields = {"turn_id", "role", "quoted"}
    if (not isinstance(current_source_reference, dict)
            or set(current_source_reference) not in (
                reference_fields, reference_fields | {"source_id"})
            or current_source_reference["turn_id"] != ledger["owner"]["turn_id"]
            or current_source_reference["role"] != "advocate"
            or not isinstance(current_source_reference["quoted"], str)
            or not current_source_reference["quoted"].strip()):
        raise SchemaViolation("Mutation scope selection requires the exact current advocate source")
    if "source_id" in current_source_reference:
        source_id = _text(current_source_reference["source_id"], "current source_id")
        source = ledger["source_catalogue"].get(source_id)
        selected_sources = ({source_id} if isinstance(source, dict) and all(
            source.get(key) == current_source_reference[key] for key in reference_fields)
                            else set())
    else:
        selected_sources = {
            identity for identity, source in ledger["source_catalogue"].items()
            if all(source.get(key) == current_source_reference[key]
                   for key in reference_fields)}
    if not selected_sources:
        raise SchemaViolation("Mutation scope selection has no owned current source")
    if len(selected_sources) != 1:
        raise SchemaViolation("Mutation operation has ambiguous current source identity")
    return selected_sources


def candidate_authority_ids(*, ledger, owner, snapshot_version, relation, target_ids,
                            current_source_reference):
    """Select the applicable scope union from a candidate's exact current source.

    This does not use appended prior references or the reviewer's claimed
    identity. References sharing a passage do not prove semantic association;
    they only delimit choices already made by the independent scope owner.
    Several independently authorised targets may need several scopes. Their
    union permits only the same operation for targets each grant already owns.
    An ambiguous original source identity remains unresolved; no first match is
    selected. Permission does not certify that combining accounts is faithful.
    """
    grants = _checked_ledger(ledger)
    if _owner(owner) != ledger["owner"]:
        raise SchemaViolation("Mutation authority belongs to a different turn owner")
    if _version(snapshot_version) != ledger["expected_version"]:
        raise SchemaViolation("Mutation authority belongs to a different record snapshot")
    selected_sources = _current_source_ids(current_source_reference, ledger)
    targets = _ids(target_ids, "target_ids")
    if (not isinstance(relation, str) or relation not in RELATIONS
            or (relation == "new" and targets)
            or (relation != "new" and not targets)
            or not set(targets) <= ledger["target_catalogue"].keys()):
        raise SchemaViolation("Mutation operation has incompatible or unowned record targets")
    applicable = [identity for identity, grant in grants.items()
                  if relation in grant["permitted_relations"]
                  and (not targets or set(targets).intersection(grant["target_ids"]))
                  and selected_sources.intersection(grant["authority_source_ids"])]
    represented = {target for identity in applicable for target in grants[identity]["target_ids"]}
    if not applicable or not set(targets) <= represented:
        raise SchemaViolation("Mutation operation exceeds its original source-linked scope")
    return sorted(applicable)


def authorize_mutation(*, ledger, owner, snapshot_version, authority_ids, relation,
                       target_ids, current_source_reference, supporting_source_ids,
                       attached_context_source_ids=()):
    """Validate scope before any preview/admission can retire a record.

    Supporting references are selections checked independently by the grounding
    owner. Automatically attached target context cannot fill an empty supporting
    selection. The same original passage may legitimately be selected as support
    and supplied as context, particularly in a repair using earlier evidence.
    """
    grants = _checked_ledger(ledger)
    if _owner(owner) != ledger["owner"]:
        raise SchemaViolation("Mutation authority belongs to a different turn owner")
    if _version(snapshot_version) != ledger["expected_version"]:
        raise SchemaViolation("Mutation authority belongs to a different record snapshot")
    selected = _ids(authority_ids, "authority_ids", nonempty=True)
    if not set(selected) <= grants.keys():
        raise SchemaViolation("Mutation selects unowned authority IDs")
    applicable_ids = candidate_authority_ids(
        ledger=ledger, owner=owner, snapshot_version=snapshot_version, relation=relation,
        target_ids=target_ids, current_source_reference=current_source_reference)
    if not set(selected) <= set(applicable_ids):
        raise SchemaViolation("Mutation authority does not apply to its selected current source")
    if not isinstance(relation, str) or relation not in RELATIONS:
        raise SchemaViolation("Mutation selects an unknown record operation")
    targets = _ids(target_ids, "target_ids")
    if ((relation == "new" and targets) or (relation != "new" and not targets)
            or not set(targets) <= ledger["target_catalogue"].keys()):
        raise SchemaViolation("Mutation operation has incompatible or unowned record targets")
    applicable = [grants[identity] for identity in selected
                  if relation in grants[identity]["permitted_relations"]]
    if not applicable or any(not any(target in grant["target_ids"] for grant in applicable)
                             for target in targets):
        raise SchemaViolation("Mutation operation exceeds its selected request/contribution scope")
    support = _ids(supporting_source_ids, "supporting_source_ids", nonempty=True)
    context = _ids(attached_context_source_ids, "attached_context_source_ids")
    source_ids = ledger["source_catalogue"].keys()
    if not set([*support, *context]) <= source_ids:
        raise SchemaViolation("Mutation selects unowned supporting or contextual sources")
    certificate = {
        "contract": BINDING_CONTRACT, "authority_seal": ledger["seal"],
        "owner": deepcopy(ledger["owner"]), "expected_version": ledger["expected_version"],
        "snapshot_digest": ledger["snapshot_digest"],
        "authority_ids": selected, "relation": relation, "target_ids": targets,
        "current_source_reference": deepcopy(current_source_reference),
        "supporting_source_ids": support, "attached_context_source_ids": context,
        "request_indices": sorted({grant["request_index"] for grant in applicable}),
    }
    return {**certificate, "seal": _digest(certificate)}


def validate_saved_mutation_authority(*, certificate, ledger, owner, snapshot_version,
                                     relation, target_ids, current_source_reference,
                                     supporting_source_ids,
                                     attached_context_source_ids=()):
    """Revalidate a versioned saved binding without inventing legacy authority.

    A historical turn supplies its original owner/snapshot version, not the
    present matter version. Storage ownership, full historical target catalogue
    integrity and atomic persistence remain the caller's contracts.
    """
    if not isinstance(certificate, dict) or certificate.get("contract") != BINDING_CONTRACT:
        raise SchemaViolation("A versioned mutation has no saved authority binding")
    checked = authorize_mutation(
        ledger=ledger, owner=owner, snapshot_version=snapshot_version,
        authority_ids=certificate.get("authority_ids"), relation=relation,
        target_ids=target_ids, current_source_reference=current_source_reference,
        supporting_source_ids=supporting_source_ids,
        attached_context_source_ids=attached_context_source_ids)
    if certificate != checked:
        raise SchemaViolation("Saved mutation differs from its source-linked authority binding")
    return deepcopy(checked)


def mutation_authority_mode(*, saved_contract, binding_present):
    """Keep genuinely older replay readable without certifying untracked effects.

    A caller must branch on the stored version, never downgrade a newly stamped
    turn merely because its mandatory binding is absent. This does not itself
    authorize a legacy mutation or upgrade an old interpretation to checked.
    """
    if saved_contract is None:
        if binding_present:
            raise SchemaViolation("Unversioned mutation has an unexpected authority binding")
        return "legacy_untracked"
    if saved_contract != AUTHORITY_CONTRACT or not binding_present:
        raise SchemaViolation("Versioned mutation requires its saved authority binding")
    return "bound"


def _record_value(record, name):
    """Read fields from an in-memory candidate or its durable proposal."""
    return record.get(name) if isinstance(record, dict) else getattr(record, name, None)


def _record_target_ids(record):
    field = ("related_dispute_ids" if _record_value(record, "kind") == "dispute"
             else "related_material_ids")
    return _ids(_record_value(record, field), field)


def _record_current_reference(record, ledger):
    recorded_turn = _record_value(record, "source_turn_id")
    if recorded_turn is not None and recorded_turn != ledger["owner"]["turn_id"]:
        raise SchemaViolation("Mutation proposal belongs to a different source turn")
    reference = {"turn_id": ledger["owner"]["turn_id"], "role": "advocate",
                 "quoted": _record_value(record, "quoted")}
    source_id = _record_value(record, "source_id")
    if source_id is not None or isinstance(record, dict) and "source_id" in record:
        reference["source_id"] = source_id
    return reference


def _record_context_ids(record, ledger):
    references = _record_value(record, "prior_references")
    if not isinstance(references, (list, tuple)):
        raise SchemaViolation("Mutation proposal has unreadable original source references")
    selected = set()
    for reference in references:
        role = _record_value(reference, "role")
        # NM words can explain chronology, but never supply attributed account
        # content or authority. Their existing transcript validation still applies.
        if role == "nm":
            continue
        if role != "advocate":
            raise SchemaViolation("Mutation context has an unknown original source role")
        original = {name: _record_value(reference, name)
                    for name in ("turn_id", "role", "quoted")}
        matching = {identity for identity, source in ledger["source_catalogue"].items()
                    if all(source.get(name) == value for name, value in original.items())}
        if not matching:
            raise SchemaViolation("Mutation context selects an unowned original advocate source")
        selected.update(matching)
    return sorted(selected)


def _record_support_ids(decision):
    """Retain only independently checked substantive supporting references.

    Selecting a source for review does not establish its support. Negative or
    instruction-only checks must not become factual support in the certificate.
    The verification owner validates meaning; this boundary preserves its
    explicit per-source result rather than relabelling all reviewed references.
    """
    account = decision.get("account_check")
    if not isinstance(account, dict) or not isinstance(account.get("source_checks"), list):
        raise SchemaViolation("Mutation support requires independent account source checks")
    selected = _ids(account.get("source_ids"), "account_check.source_ids")
    checked, support = set(), []
    for check in account["source_checks"]:
        if (not isinstance(check, dict) or not isinstance(check.get("source_id"), str)
                or check["source_id"] not in selected or check["source_id"] in checked
                or not isinstance(check.get("supplies_account_content"), bool)
                or not isinstance(check.get("supports_proposal"), bool)):
            raise SchemaViolation("Mutation support has an unreadable or conflicting source check")
        checked.add(check["source_id"])
        if check["supplies_account_content"] and check["supports_proposal"]:
            support.append(check["source_id"])
    if checked != set(selected):
        raise SchemaViolation("Mutation support checks do not cover their selected sources")
    return sorted(support)


def scoped_record_decisions(decisions, candidates, review_scope, *, binding_sink=None):
    """Apply independently declared scope before previews or record admission.

    Absence of a scope ledger retains the explicit old verification contract.
    An unreadable supplied ledger is an integrity failure, not a unit rejection.
    Scope failures on otherwise accepted candidates withhold only those units;
    the caller still applies its restoration-peer and final-coverage contracts.
    Bindings retain the factual support selected by independent record review.
    """
    if not isinstance(review_scope, dict):
        return decisions
    contract = review_scope.get("mutation_authority_contract")
    if contract is not None and contract != AUTHORITY_CONTRACT:
        raise SchemaViolation("Mutation review scope has an unknown authority contract")
    if "mutation_authorities" not in review_scope:
        if contract is not None:
            raise SchemaViolation("Versioned mutation review scope has no authority ledger")
        return decisions
    ledger = review_scope["mutation_authorities"]
    _checked_ledger(ledger)
    if _owner(review_scope.get("owner")) != ledger["owner"]:
        raise SchemaViolation("Mutation review scope belongs to a different turn owner")
    if not isinstance(decisions, dict) or not isinstance(candidates, dict):
        raise SchemaViolation("Mutation admission requires keyed candidates and decisions")
    if binding_sink is not None and not isinstance(binding_sink, dict):
        raise SchemaViolation("Mutation binding sink must be owned by the verification caller")
    admitted = {key: dict(row) for key, row in decisions.items()}
    for identity, candidate in candidates.items():
        decision = admitted.get(identity)
        if (not isinstance(decision, dict) or decision.get("verdict") != "accept"
                or _record_value(candidate, "relation") == "new"):
            continue
        try:
            reference = _record_current_reference(candidate, ledger)
            relation = _record_value(candidate, "relation")
            targets = _record_target_ids(candidate)
            authorities = candidate_authority_ids(
                ledger=ledger, owner=ledger["owner"],
                snapshot_version=ledger["expected_version"], relation=relation,
                target_ids=targets, current_source_reference=reference)
            support = _record_support_ids(decision)
            certificate = authorize_mutation(
                ledger=ledger, owner=ledger["owner"],
                snapshot_version=ledger["expected_version"], authority_ids=authorities,
                relation=relation, target_ids=targets, current_source_reference=reference,
                supporting_source_ids=support,
                attached_context_source_ids=_record_context_ids(candidate, ledger))
        except SchemaViolation as exc:
            admitted[identity] = {
                **decision, "verdict": "reject", "operation_supported": False,
                "admission_issue": "mutation_scope", "model_decision": deepcopy(decision),
                "reason": str(exc),
            }
            continue
        decision["mutation_authority"] = certificate
        if binding_sink is not None:
            binding_sink[identity] = deepcopy(certificate)
    return admitted


def bind_record_mutation(proposal, ledger, *, binding=None, supporting_source_ids=None):
    """Bind a durable linked proposal to its earlier admitted authority.

    Callers should pass the actual admitted binding. Explicit support selections
    are accepted for focused contract construction; they do not replace factual
    review. This adapter never invents support from automatically attached prior
    context, an extractor's intention or a positive reviewer verdict.
    """
    _checked_ledger(ledger)
    if not isinstance(proposal, dict):
        raise SchemaViolation("Saved mutation requires a readable proposal")
    relation = proposal.get("relation")
    reference = _record_current_reference(proposal, ledger)
    if "source_id" in reference:
        _current_source_ids(reference, ledger)
    if relation == "new":
        if binding is not None or proposal.get("mutation_authority") is not None:
            raise SchemaViolation("A new account has an unexpected revision authority binding")
        return None
    targets = _record_target_ids(proposal)
    context = _record_context_ids(proposal, ledger)
    certificate = binding if binding is not None else proposal.get("mutation_authority")
    if certificate is not None:
        support = (certificate.get("supporting_source_ids")
                   if isinstance(certificate, dict) else None)
        if supporting_source_ids is not None and _ids(
                supporting_source_ids, "supporting_source_ids") != support:
            raise SchemaViolation("Saved mutation changed its independently selected support")
        return validate_saved_mutation_authority(
            certificate=certificate, ledger=ledger, owner=ledger["owner"],
            snapshot_version=ledger["expected_version"], relation=relation,
            target_ids=targets, current_source_reference=reference,
            supporting_source_ids=support, attached_context_source_ids=context)
    if supporting_source_ids is None:
        raise SchemaViolation("Saved mutation has no admitted independent support binding")
    authorities = candidate_authority_ids(
        ledger=ledger, owner=ledger["owner"], snapshot_version=ledger["expected_version"],
        relation=relation, target_ids=targets, current_source_reference=reference)
    return authorize_mutation(
        ledger=ledger, owner=ledger["owner"], snapshot_version=ledger["expected_version"],
        authority_ids=authorities, relation=relation, target_ids=targets,
        current_source_reference=reference, supporting_source_ids=supporting_source_ids,
        attached_context_source_ids=context)


def validate_record_mutation(proposal, *, turn, execution, prior_words=None,
                             source_catalogue=None, target_catalogue=None):
    """Revalidate a durable proposal before it can retire any owned record.

    Full snapshot/catalogue equality belongs to the turn replay owner. Typed
    projections can supply their selected actual targets and original transcript
    words here. Genuinely older, unstamped turns remain explicitly untracked;
    removal of a mandatory binding from a stamped turn cannot downgrade it.
    """
    if not isinstance(proposal, dict) or not isinstance(turn, dict):
        raise SchemaViolation("Mutation replay requires an owned turn and proposal")
    if execution is not None and not isinstance(execution, dict):
        raise SchemaViolation("Mutation replay execution evidence is unreadable")
    execution = execution or {}
    contract = execution.get("mutation_authority_contract")
    ledger = execution.get("mutation_authorities")
    binding = proposal.get("mutation_authority")
    if contract is None:
        if ledger is not None or binding is not None:
            raise SchemaViolation("Unversioned mutation has unexpected authority evidence")
        return "legacy_untracked"
    if contract != AUTHORITY_CONTRACT:
        raise SchemaViolation("Saved mutation has an unknown authority contract")
    _checked_ledger(ledger)
    owner = {"matter_id": turn.get("matter_id"), "advocate_id": turn.get("advocate_id"),
             "turn_id": turn.get("turn_id"), "offer_digest": turn.get("offer_digest")}
    if _owner(owner) != ledger["owner"] or _owner(execution.get("owner")) != ledger["owner"]:
        raise SchemaViolation("Saved mutation authority disagrees with its actual turn owner")
    if _version(execution.get("expected_version")) != ledger["expected_version"]:
        raise SchemaViolation("Saved mutation authority disagrees with its execution snapshot")
    message = turn.get("message")
    if (not isinstance(message, str) or not isinstance(proposal.get("quoted"), str)
            or not proposal["quoted"].strip() or proposal["quoted"] not in message
            or proposal.get("source_turn_id") != turn.get("turn_id")):
        raise SchemaViolation("Saved mutation does not match the original current advocate words")
    reference = _record_current_reference(proposal, ledger)
    if "source_id" in reference:
        _current_source_ids(reference, ledger)
    if source_catalogue is not None:
        if not isinstance(source_catalogue, dict) or source_catalogue != ledger["source_catalogue"]:
            raise SchemaViolation("Saved mutation differs from its original source catalogue")
    if prior_words is not None:
        if not isinstance(prior_words, dict):
            raise SchemaViolation("Mutation replay requires original transcript words")
        words = {**prior_words, (turn["turn_id"], "advocate"): message}
        for source in ledger["source_catalogue"].values():
            original = words.get((source["turn_id"], source["role"]))
            if not isinstance(original, str) or source["quoted"] not in original:
                raise SchemaViolation("Saved mutation authority has no matching original source")
    if target_catalogue is not None:
        if not isinstance(target_catalogue, dict):
            raise SchemaViolation("Mutation replay requires the actual prior target catalogue")
        for identity in _record_target_ids(proposal):
            supplied = target_catalogue.get(identity)
            recorded = ledger["target_catalogue"].get(identity)
            # Turn-owned catalogues carry a typed wrapper; projections already
            # have the underlying attributed row. Neither changes its meaning.
            if isinstance(recorded, dict) and isinstance(recorded.get("record"), dict):
                recorded = recorded["record"]
            if isinstance(supplied, dict) and isinstance(supplied.get("record"), dict):
                supplied = supplied["record"]
            if not isinstance(supplied, dict) or supplied != recorded:
                raise SchemaViolation("Saved mutation target differs from the actual prior record")
    if proposal.get("relation") == "new":
        if binding is not None:
            raise SchemaViolation("A new account has an unexpected revision authority binding")
        return "new_account"
    mutation_authority_mode(saved_contract=contract, binding_present=binding is not None)
    bind_record_mutation(proposal, ledger, binding=binding)
    return "bound"


def model_review_scope(review_scope):
    """Present authorised choices without duplicating durable dependency data.

    Original transcripts, source treatments and current/linked records remain
    separate complete reviewer inputs. Only storage catalogues, hashes and seals
    are removed here; every scope permission and other meaningful scope field
    is retained. This is presentation for the model, never an admission ledger.
    The full code-owned scope remains the owner of coverage binding and replay.
    """
    if review_scope is None:
        return None
    if not isinstance(review_scope, dict):
        raise SchemaViolation("Independent account review needs a code-owned scope")
    contract = review_scope.get("mutation_authority_contract")
    if contract is not None and contract != AUTHORITY_CONTRACT:
        raise SchemaViolation("Mutation review scope has an unknown authority contract")
    if "mutation_authorities" not in review_scope:
        if contract is not None:
            raise SchemaViolation("Versioned mutation review scope has no authority ledger")
        return deepcopy(review_scope)
    ledger = review_scope["mutation_authorities"]
    _checked_ledger(ledger)
    if _owner(review_scope.get("owner")) != ledger["owner"]:
        raise SchemaViolation("Mutation review scope belongs to a different turn owner")
    if "mutation_scopes" in review_scope:
        raise SchemaViolation("Mutation review scope repeats its permission presentation")
    return {
        **{name: deepcopy(value) for name, value in review_scope.items()
           if name != "mutation_authorities"},
        "mutation_scopes": deepcopy(ledger["authorities"]),
    }


def model_mutation_context(value):
    """Clone model input while omitting only redundant mutation proof data.

    Complete original words and semantic data are preserved at every level.
    A typed mutation ledger must first pass its storage integrity contract; its
    presentation then retains the owner, snapshot version and exact permitted
    choices. This presentation is not an admission ledger and must not replace
    the full server context used for coverage, persistence or replay. Call once
    at a dispatch owner from that full context, not on an already lean ledger.
    """
    if isinstance(value, dict):
        if value.get("contract") == AUTHORITY_CONTRACT:
            _checked_ledger(value)
            return {name: deepcopy(value[name]) for name in (
                "contract", "owner", "expected_version", "authorities")}
        return {name: model_mutation_context(item) for name, item in value.items()}
    if isinstance(value, list):
        return [model_mutation_context(item) for item in value]
    if isinstance(value, tuple):
        return tuple(model_mutation_context(item) for item in value)
    return deepcopy(value)
