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
    if (not isinstance(current_source_reference, dict)
            or set(current_source_reference) != {"turn_id", "role", "quoted"}
            or current_source_reference["turn_id"] != ledger["owner"]["turn_id"]
            or current_source_reference["role"] != "advocate"
            or not isinstance(current_source_reference["quoted"], str)
            or not current_source_reference["quoted"].strip()):
        raise SchemaViolation("Mutation scope selection requires the exact current advocate source")
    selected_sources = {
        identity for identity, source in ledger["source_catalogue"].items()
        if all(source.get(key) == value for key, value in current_source_reference.items())}
    if not selected_sources:
        raise SchemaViolation("Mutation scope selection has no owned current source")
    if len(selected_sources) != 1:
        raise SchemaViolation("Mutation operation has ambiguous current source identity")
    targets = _ids(target_ids, "target_ids")
    if (relation not in RELATIONS or (relation == "new" and targets)
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
    if relation not in RELATIONS:
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
