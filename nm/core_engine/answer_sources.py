"""Versioned exact source catalogue shared by answer preparation and checking.

This projection grants no factual or legal status. The original conversation and
research snapshots remain their own durable records; parser role labels are not
evidence about what a court decided.
"""
from __future__ import annotations

from copy import deepcopy
import json

from nm.core_engine import research
from nm.core_engine.retrieval import _candidate, _digest
from nm.core_engine.understanding import (
    REFERENCE, select as select_original, source_catalogue,
)
from nm.shared.citation_contracts import provision_label
from nm.shared.model_port import SchemaViolation, require_schema

CONTRACT = "core_answer_sources_v1"
_LEGAL = {"provision", "judgment"}
_CONTEXT_ROLES = {"original_account": "account", "nm_interpretation": "nm_context",
                  "service_status": "service"}
_LINK_FIELDS = {"context_ids", "work_ids", "coverage"}


def _add(sources, row):
    prior = sources.get(row["id"])
    if prior is None:
        sources[row["id"]] = deepcopy(row)
        return
    if ({k: v for k, v in prior.items() if k not in _LINK_FIELDS}
            != {k: v for k, v in row.items() if k not in _LINK_FIELDS}):
        raise ValueError("Source identity has conflicting content or provenance")
    for field in _LINK_FIELDS:
        for value in row[field]:
            if value not in prior[field]:
                prior[field].append(deepcopy(value))


def build(context, research_record):
    """Validate original dependencies, then assign one tag per exact source unit."""
    checked = research.validate(research_record, research_record["plan"], context)
    sources = {}
    for identity, original in source_catalogue(context).items():
        role = original.get("record_role")
        if (role not in _CONTEXT_ROLES or any(
                not isinstance(original.get(field), str) or not original[field]
                for field in ("speaker", "turn_id"))):
            raise ValueError("Conversation source has no owned provenance")
        _add(sources, {"id": identity, "kind": _CONTEXT_ROLES[role],
            "text": original["text"], "speaker": original["speaker"],
            "record_role": role, "title": None, "locator": None,
            "digest": _digest(original), "context_ids": [], "work_ids": [],
            "coverage": [], "source_identity": {
                "source_id": identity, "turn_id": original["turn_id"]}})
    for work in checked["plan"]["work"]:
        for selected in work["sources"]:
            memberships = sources[selected["source_id"]]["work_ids"]
            if work["id"] not in memberships:
                memberships.append(work["id"])

    positions = {}
    for work_id, search in checked["searches"].items():
        for selected in search["candidates"]:
            kind, revision = selected["kind"], selected["corpus_revision"]
            window = selected["context"]
            units = []
            for position, row in [(selected["position"], selected["source"]),
                    *((s["position"], s["row"]) for s in window["segments"])]:
                unit = _candidate(kind, position, row, revision, None, [], {})
                key = (kind, revision, position)
                if key in positions and positions[key] != unit["id"]:
                    raise ValueError("Corpus position has conflicting saved source content")
                positions[key] = unit["id"]
                document_field = "act_id" if kind == "provision" else "case_id"
                if not isinstance(row.get(document_field), str) or not row[document_field]:
                    raise ValueError("Legal source has no owned document identity")
                units.append({"id": unit["id"], "kind": kind,
                    "text": unit["text"], "speaker": None,
                    "record_role": "retrieved_candidate", "title": unit["title"],
                    "locator": provision_label("", unit["locator"]) if kind == "provision"
                               else unit["locator"],
                    "digest": _digest(row), "context_ids": [], "work_ids": [work_id],
                    "coverage": [], "source_identity": {
                        "position": position, "corpus_revision": revision,
                        document_field: row[document_field], "chunk_id": row["chunk_id"]}})
            identities = list(dict.fromkeys(unit["id"] for unit in units))
            coverage = {"work_id": work_id, "selected_source_id": selected["id"],
                "scope": window["scope"], "bounded": window["bounded"],
                "unread_positions": deepcopy(window["unread_positions"]),
                "gaps": [deepcopy(gap) for gap in search["issues"] if gap["kind"] == kind]}
            for unit in units:
                unit["context_ids"] = [identity for identity in identities if identity != unit["id"]]
                unit["coverage"] = [coverage]
                _add(sources, unit)
    return sources


def select(reference, sources):
    """Select exact unique words from an owned tag without normalising text."""
    require_schema(reference, REFERENCE)
    identity = reference["source_id"]
    source = sources.get(identity)
    if source is None or source.get("id") != identity:
        raise SchemaViolation("Selected source_id is not in the owned answer catalogue")
    chosen = select_original(reference, {identity: {
        "source_id": identity, "text": source["text"]}})
    return {key: chosen[key] for key in ("source_id", "start", "end", "text")}


def presentation(sources):
    """Model-only catalogue; share exact context and gaps, not their repeated proof.

    Original conversation is supplied apart. Complete canonical sources remain the
    admission and replay owner; local presentation IDs never replace source tags.
    A passage's neighbours are its ordered context group with that passage removed.
    """
    passages, coverage_by_id, coverage_keys = [], {}, {}
    gaps_by_id, gap_keys, context_groups = {}, {}, {}

    def key(value):
        # All fields participate; absent metadata, differing gaps and ordered lists
        # must remain distinct. Full strings avoid a digest collision as well.
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False)

    for row in sources.values():
        if row["kind"] not in _LEGAL:
            continue
        passage = deepcopy(row)
        passage.pop("digest")
        passage["source_identity"] = {field: value for field, value in passage["source_identity"].items()
                                      if field not in {"chunk_id", "corpus_revision"}}
        neighbours = passage.pop("context_ids")
        context_id = next((identity for identity, members in context_groups.items()
            if row["id"] in members and [m for m in members if m != row["id"]] == neighbours), None)
        if context_id is None:
            context_id = f"context:{len(context_groups) + 1}"
            context_groups[context_id] = [row["id"], *neighbours]
        passage["context_group_id"] = context_id
        coverage = passage.pop("coverage")
        passage["coverage_ids"] = []
        for entry in coverage:
            coverage_key = key(entry)
            if coverage_key not in coverage_keys:
                identity = f"coverage:{len(coverage_by_id) + 1}"
                coverage_keys[coverage_key] = identity
                shared = deepcopy(entry)
                if "gaps" in shared:
                    shared["gap_ids"] = []
                    for gap in shared.pop("gaps"):
                        gap_key = key(gap)
                        if gap_key not in gap_keys:
                            gap_id = f"gap:{len(gaps_by_id) + 1}"
                            gap_keys[gap_key] = gap_id
                            gaps_by_id[gap_id] = gap
                        shared["gap_ids"].append(gap_keys[gap_key])
                coverage_by_id[identity] = shared
            passage["coverage_ids"].append(coverage_keys[coverage_key])
        passages.append(passage)
    return {"passages": passages, "coverage_by_id": coverage_by_id,
            "gaps_by_id": gaps_by_id, "context_groups": context_groups}
