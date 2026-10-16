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
from nm.shared.citation_contracts import provision_label, statute_title
from nm.shared.model_port import SchemaViolation, require_schema

CONTRACT = "core_answer_sources_v1"
_LEGAL = {"provision", "judgment"}
#: Page text: held legal passages and the advocate's document pages (open items round, 16 Oct 2026).
_LAYOUT = _LEGAL | {"document"}
_CONTEXT_ROLES = {"original_account": "account", "nm_interpretation": "nm_context",
                  "service_status": "service", "supplied_document": "document"}
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


def _window(selected, picked):
    """The saved context a returned passage is read with.

    Research v8 (owner decision, 15 Oct 2026): a judgment paragraph the pick chose is read
    with the nearest stored paragraph either side, every other returned paragraph alone.
    Earlier records and provisions keep their whole saved window. A neighbour that could
    not be read stays an unread position, never a silent omission.
    """
    window = selected["context"]
    if picked is None or selected["kind"] != "judgment":
        return window
    position = selected["position"]
    around = sorted({s["position"] for s in window["segments"]} | set(window["unread_positions"]) - {position})
    keep = {position}
    if selected["id"] in picked:
        keep |= {max((p for p in around if p < position), default=position),
                 min((p for p in around if p > position), default=position)}
    return {"scope": "adjacent_indexed_segments" if len(keep) > 1 else "selected_indexed_segment",
            "bounded": window["bounded"],
            "unread_positions": [p for p in window["unread_positions"] if p in keep],
            "segments": [s for s in window["segments"] if s["position"] in keep]}


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
        # A document's page is shown under the document's name and page number.
        about = original.get("document") if role == "supplied_document" else None
        _add(sources, {"id": identity, "kind": _CONTEXT_ROLES[role],
            "text": original["text"], "speaker": original["speaker"],
            "record_role": role, "title": about["name"] if about else None,
            "locator": ("recording" if about.get("recording") else f"page {about['page']}") if about else None,
            "digest": _digest(original), "context_ids": [], "work_ids": [],
            "coverage": [], "source_identity": {
                "source_id": identity, "turn_id": original["turn_id"]}})
    for work in checked["plan"]["work"]:
        for selected in work["sources"]:
            memberships = sources[selected["source_id"]]["work_ids"]
            if work["id"] not in memberships:
                memberships.append(work["id"])

    positions = {}
    # v7 and v8 admit only the provisions the pick chose; judgments and earlier records
    # admit every returned candidate. v8 narrows how much of each judgment is read.
    admitted = research.admitted_provisions(checked)
    picked = research.picked_judgments(checked)
    for work_id, search in checked["searches"].items():
        for selected in search["candidates"]:
            if admitted is not None and selected["kind"] == "provision" and selected["id"] not in admitted:
                continue
            kind, revision = selected["kind"], selected["corpus_revision"]
            window = _window(selected, picked)
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
    """Select exact unique words from an owned tag without normalising text. Held legal
    passages and document pages keep their page line breaks, which a quote may meet
    with spaces; the selection is still the source's own words."""
    require_schema(reference, REFERENCE)
    identity = reference["source_id"]
    source = sources.get(identity)
    if source is None or source.get("id") != identity:
        raise SchemaViolation(_unknown(identity, sources))
    chosen = select_original(reference, {identity: {
        "source_id": identity, "text": source["text"]}}, layout=source["kind"] in _LAYOUT)
    return {key: chosen[key] for key in ("source_id", "start", "end", "text")}


def _unknown(identity, sources):
    """Why a selection names nothing (16 Oct 2026): the identifier, and what can be named,
    so a correction can repair it. Identifiers are code-made labels, not case words."""
    groups = {}
    for alias in aliases(sources):
        groups.setdefault(alias[0], []).append(alias)
    legal = ", ".join(f"{names[0]} to {names[-1]}" if len(names) > 1 else names[0] for names in groups.values())
    others = [tag for tag, row in sources.items() if row["kind"] not in _LEGAL]
    listed = ", ".join(others[:40]) + (" and more" if len(others) > 40 else "")
    return (f"Selected source_id {identity!r} is not in the owned answer catalogue. Name a legal passage by its "
            f"offered ID ({legal or 'none offered'}) and a message or document page by its own source_id "
            f"({listed or 'none'}); context, coverage, gap, fact and dispute labels are not sources.")


def aliases(sources):
    """Short offered IDs for legal passages (P1, P2, ... and J1, J2, ...).

    Hexadecimal source tags are long enough for a model to mistype and repeat
    through every presentation. From writer and review v3 the models see these
    instead. The map follows catalogue order, so replay re-derives it from the
    saved catalogue; durable records keep the owned source tags.
    """
    prefixes, counts, result = {"provision": "P", "judgment": "J"}, {}, {}
    for identity, row in sources.items():
        prefix = prefixes.get(row["kind"])
        if prefix:
            counts[prefix] = counts.get(prefix, 0) + 1
            result[f"{prefix}{counts[prefix]}"] = identity
    return result


def presentation(sources, *, aliased=False, compact=False, work_ids=None):
    """Model-only catalogue; share exact context and gaps, not their repeated proof.

    Original conversation is supplied apart. Complete canonical sources remain the
    admission and replay owner. Local presentation IDs never replace source tags,
    except that an aliased presentation names legal passages by their offered
    aliases, which admission maps back. A passage's neighbours are its ordered
    context group with that passage removed.

    compact (writer v4, review v5): each passage without the identity fields code
    alone uses (store position, document key, record role, empty speaker). work_ids:
    only the passages serving those research work items, with their groups and
    coverage, for writing one part of an answer; aliases stay those of the whole.
    """
    offered = {tag: alias for alias, tag in aliases(sources).items()} if aliased else {}
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
        if work_ids is not None and not set(row["work_ids"]) & set(work_ids):
            continue
        passage = deepcopy(row)
        passage.pop("digest")
        if row["kind"] == "provision":
            # The name the statute is shown under (owner decisions, 10-11 Oct 2026);
            # its words and the durable catalogue keep what the store holds.
            passage["title"] = statute_title(row["title"], row["source_identity"].get("act_id", ""))
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
                if shared.get("selected_source_id") in offered:
                    shared["selected_source_id"] = offered[shared["selected_source_id"]]
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
        passage["id"] = offered.get(row["id"], row["id"])
        if compact:
            for field in ("source_identity", "record_role", "speaker"):
                passage.pop(field)
        passages.append(passage)
    shown = {row["id"] for row in sources.values()
             if row["kind"] in _LEGAL and (work_ids is None or set(row["work_ids"]) & set(work_ids))}
    context_groups = {identity: [offered.get(member, member) for member in members if member in shown]
                      for identity, members in context_groups.items()}
    return {"passages": passages, "coverage_by_id": coverage_by_id,
            "gaps_by_id": gaps_by_id, "context_groups": context_groups}
