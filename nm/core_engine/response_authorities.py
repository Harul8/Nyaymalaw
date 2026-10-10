"""Mechanical authority evidence bound to the exact draft and its used sources.

These checks do not decide the speaker, holding, applicability or legal currency.
An unresolved prose association is evidence for review, not an invented denial.
Replay rebinds the saved reports; it never substitutes the current corpus.
"""
from __future__ import annotations

from copy import deepcopy

from nm.core_engine import answer_sources, response_writer
from nm.core_engine.citations import CONTRACT as CITATION_CONTRACT
from nm.core_engine.citations import IndexUnavailable, check_citations
from nm.core_engine.retrieval import SearchUnavailable, _candidate, _digest
from nm.shared.citation_contracts import (
    ANY_PROVISION, ProvisionKeyState, bind_provision_key, find_reporter_citations,
)

CONTRACT = "core_response_authorities_v1"


class _UnavailableIndex:
    def scope(self):
        raise IndexUnavailable("The case identity checker is not configured")


def _dependencies(context, research_record, sources, draft):
    if answer_sources.build(context, research_record) != sources:
        raise ValueError("Authority catalogue differs from its owned research snapshot")
    response_writer.validate(draft, context, sources)
    return _digest({"context": context, "research": research_record,
                    "sources": sources, "draft": draft})


def _raw_sources(research_record):
    result = {}
    for search in research_record["searches"].values():
        for selected in search["candidates"]:
            for position, row in [(selected["position"], selected["source"]),
                    *((s["position"], s["row"]) for s in selected["context"]["segments"])]:
                unit = _candidate(selected["kind"], position, row,
                                  selected["corpus_revision"], None, [], {})
                result[unit["id"]] = unit
    return result


def _used(unit, sources):
    identities = []
    for use in unit["uses"]:
        identities.append(use["source_id"])
        if use["treatment_source"] is not None:
            identities.append(use["treatment_source"]["source_id"])
    return [sources[identity] for identity in dict.fromkeys(identities)
            if sources[identity]["kind"] in {"provision", "judgment"}]


def _read_key(row):
    return _digest([row["source"]["act_id"], _reference(row["source"])])


def _reference(row):
    return str(row.get("section_number") or "")


def _unavailable(act_id, reference, reason):
    return {"state": "unavailable", "act_id": act_id, "reference": reference,
            "provision_key": None, "candidates": [], "sources": [],
            "legal_version": "not_assessed", "reason": reason}


def _validate_readback(result, act_id, reference):
    if (not isinstance(result, dict) or set(result) != {
            "state", "act_id", "reference", "provision_key", "candidates", "sources",
            "legal_version", "reason"} or result["act_id"] != act_id
            or result["reference"] != reference or result["legal_version"] != "not_assessed"
            or result["state"] not in {"found", "ambiguous", "not_held", "unavailable"}
            or not isinstance(result["candidates"], list)
            or any(not isinstance(k, str) or not k for k in result["candidates"])
            or not isinstance(result["sources"], list)):
        raise ValueError("Provision readback differs from its owned Act/reference contract")
    if result["state"] != "found":
        if result["sources"] or result["provision_key"] is not None:
            raise ValueError("Unresolved provision readback cannot supply found sources")
        return
    binding = bind_provision_key(reference, tuple(dict.fromkeys(result["candidates"])))
    if (binding.state != ProvisionKeyState.BOUND or binding.key != result["provision_key"]
            or not result["sources"]):
        raise ValueError("Found provision readback has no unique exact key")
    for source in result["sources"]:
        rebuilt = _candidate(source["kind"], source["position"], source["source"],
            source["corpus_revision"], source["score"], source["query_ids"], source["context"])
        if (source != rebuilt or source["kind"] != "provision"
                or source["source"].get("act_id") != act_id
                or str(source["source"].get("section_number")) != binding.key):
            raise ValueError("Readback source does not belong to the exact selected provision")


def _provision(source, raw, readback):
    original = raw[source["id"]]
    row = original["source"]
    reference = _reference(row)
    _validate_readback(readback, row["act_id"], reference)
    state, reason = readback["state"], readback["reason"]
    if state == "found":
        same = [s for s in readback["sources"] if s["id"] == source["id"]]
        if (len(same) == 1 and same[0]["content_digest"] == source["digest"]
                and same[0]["corpus_revision"] == source["source_identity"]["corpus_revision"]):
            state, reason = "matched", "The selected exact source is present in this owned provision readback"
        else:
            state, reason = "different_snapshot", "Readback does not contain the same selected source identity and digest"
    return {"source_id": source["id"], "kind": "provision", "act_id": row["act_id"],
            "raw_provision_key": reference, "corpus_revision": original["corpus_revision"],
            "position": original["position"], "source_digest": source["digest"],
            "readback_id": _read_key(original), "state": state, "reason": reason,
            "legal_version": "not_assessed"}


def _selected_mentions(unit, keys):
    mentions = []
    for use in unit["uses"]:
        selections = [(use, use["role"])]
        if use["treatment_source"] is not None:
            selections.append((use["treatment_source"], "court_treatment_support"))
        for selected, role in selections:
            for citation in find_reporter_citations(selected["text"]):
                if set(citation.keys).intersection(keys):
                    mentions.append({"source_id": selected["source_id"],
                        "start": selected["start"] + citation.start,
                        "end": selected["start"] + citation.end, "text": citation.text,
                        "keys": list(citation.keys), "source_role_proposal": role})
    return mentions


def _case_rows(unit, used, report):
    if (not isinstance(report, dict) or report.get("contract") != CITATION_CONTRACT
            or not isinstance(report.get("citations"), list)):
        raise ValueError("Case citation evidence has no owned checking contract")
    expected = [(c.text, c.start, c.end, list(c.keys)) for c in find_reporter_citations(unit["text"])]
    actual = [(c["text"], c["start"], c["end"], c["keys"]) for c in report["citations"]]
    if expected != actual:
        raise ValueError("Case citation evidence does not describe this exact reply unit")
    judgments = [s for s in used if s["kind"] == "judgment"]
    rows = []
    for found in report["citations"]:
        cases = list(dict.fromkeys(j["case_id"] for j in found["judgments"]))
        matching = [s["id"] for s in judgments if s["source_identity"]["case_id"] in cases]
        if found["lookup"] == "found" and len(cases) == 1:
            association = "matched" if matching else (
                "different_used_identity" if judgments else "unresolved_association")
        else:
            association = "unresolved_association"
        rows.append({"citation_id": found["id"], "text": found["text"],
            "start": found["start"], "end": found["end"], "lookup": found["lookup"],
            "association": association, "resolved_case_ids": cases,
            "used_judgment_source_ids": [s["id"] for s in judgments],
            "matching_source_ids": matching,
            "selected_support_mentions": _selected_mentions(unit, found["keys"]),
            "association_scope": "Identity comparison only; a selected source may cite a different authority. Mention, speaker, reliance and legal effect require review",
            "legal_validity": "not_assessed"})
    return rows


def _prose_provisions(unit, used, raw):
    """Recognise shared syntax only; numbers never select an Act or decide law."""
    provisions = [s for s in used if s["kind"] == "provision"]
    rows = []
    for match in ANY_PROVISION.finditer(unit["text"]):
        text = match.group(0)
        matching = []
        for source in provisions:
            row = raw[source["id"]]["source"]
            if not _reference(row):
                continue
            binding = bind_provision_key(text, (_reference(row),))
            if binding.state == ProvisionKeyState.BOUND:
                matching.append(source)
        owners = {(s["source_identity"]["act_id"], _reference(raw[s["id"]]["source"]))
                  for s in matching}
        rows.append({"text": text, "start": match.start(), "end": match.end(),
            "association": "unresolved_association",
            "key_match": "one_used_identity" if len(owners) == 1 else "multiple_used_identities" if owners else "none",
            "act_name_association": "not_assessed",
            "candidate_source_ids": [s["id"] for s in matching],
            "candidate_act_ids": sorted({act for act, _ in owners}),
            "reason": "Matching reference syntax identifies candidates only; the intended Act and purpose of this prose mention remain unassessed"})
    return rows


def _assemble(draft, sources, raw, reports, readbacks):
    units = []
    expected_reads = set()
    if set(reports) != {u["id"] for u in draft["units"]}:
        raise ValueError("Authority evidence must account for each exact reply unit")
    for unit in draft["units"]:
        used = _used(unit, sources)
        provisions = []
        for source in used:
            if source["kind"] == "provision":
                key = _read_key(raw[source["id"]])
                expected_reads.add(key)
                provisions.append(_provision(source, raw, readbacks[key]))
        report = reports[unit["id"]]
        units.append({"unit_id": unit["id"], "case_lookup": deepcopy(report),
            "case_associations": _case_rows(unit, used, report),
            "selected_provisions": provisions,
            "prose_provisions": _prose_provisions(unit, used, raw),
            "limits": ["Case syntax recognition is limited to the retained reporter formats; names without a reporter are not independently resolved here",
                "Provision syntax recognition does not establish the intended Act, legal applicability or current validity",
                "Exact source identity and quotation lookup do not establish speaker, holding or court treatment"]})
    if set(readbacks) != expected_reads:
        raise ValueError("Provision evidence includes missing or unselected readbacks")
    return units


def check(context, research_record, sources, draft, *, case_index=None, provision_reader=None):
    """No model call. Produce evidence; the turn owner controls review and release."""
    binding = _dependencies(context, research_record, sources, draft)
    raw, readbacks, reports = _raw_sources(research_record), {}, {}
    for unit in draft["units"]:
        reports[unit["id"]] = check_citations(unit["text"], case_index or _UnavailableIndex())
        for source in _used(unit, sources):
            if source["kind"] != "provision":
                continue
            original = raw[source["id"]]
            key = _read_key(original)
            if key in readbacks:
                continue
            row = original["source"]
            act_id, reference = row["act_id"], _reference(row)
            if not reference:
                result = _unavailable(act_id, reference, "The held source has no explicit provision key")
            elif provision_reader is None:
                result = _unavailable(act_id, reference, "The exact provision reader is not configured")
            else:
                try:
                    result = provision_reader.read_provision(act_id, reference)
                except (OSError, ValueError, SearchUnavailable) as exc:
                    result = _unavailable(act_id, reference, type(exc).__name__)
            _validate_readback(result, act_id, reference)
            readbacks[key] = deepcopy(result)
    record = {"contract": CONTRACT, "dependency_digest": binding,
              "units": _assemble(draft, sources, raw, reports, readbacks), "readbacks": readbacks}
    record["bound_digest"] = _digest(record)
    return record


def validate(record, context, research_record, sources, draft):
    """Bind saved reports to the original evidence without a new lookup or upgrade."""
    if (not isinstance(record, dict) or set(record) != {
            "contract", "dependency_digest", "units", "readbacks", "bound_digest"}
            or record["contract"] != CONTRACT
            or record["dependency_digest"] != _dependencies(context, research_record, sources, draft)
            or not isinstance(record["units"], list) or not isinstance(record["readbacks"], dict)):
        raise ValueError("Authority evidence does not belong to this exact draft and source snapshot")
    reports = {u["unit_id"]: u["case_lookup"] for u in record["units"]}
    units = _assemble(draft, sources, _raw_sources(research_record), reports, record["readbacks"])
    body = {k: v for k, v in record.items() if k != "bound_digest"}
    if units != record["units"] or _digest(body) != record["bound_digest"]:
        raise ValueError("Saved authority evidence or its associations changed")
    return deepcopy(record)
