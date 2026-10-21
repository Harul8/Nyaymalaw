"""Versioned exact source catalogue shared by answer preparation and checking.

This projection grants no factual or legal status. The original conversation and
research snapshots remain their own durable records; parser role labels are not
evidence about what a court decided.
"""
from __future__ import annotations

from copy import deepcopy
import json

from nm.core_engine import research
from nm.core_engine.retrieval import _candidate, _digest, in_force, offered
from nm.core_engine.understanding import (
    REFERENCE, conversation_aliases, renamed, select as select_original, source_catalogue,
)
from nm.shared.citation_contracts import provision_label, statute_title
from nm.shared.model_port import SchemaViolation, require_schema

CONTRACT = "core_answer_sources_v1"
_LEGAL = {"provision", "judgment"}
#: Page text: held legal passages and the advocate's document pages (open items round, 16 Oct 2026).
_LAYOUT = _LEGAL | {"document"}
_CONTEXT_ROLES = {"original_account": "account", "nm_interpretation": "nm_context",
                  "service_status": "service", "supplied_document": "document"}
_LINK_FIELDS = {"context_ids", "work_ids", "coverage", "found_by"}


def _add(sources, row):
    prior = sources.get(row["id"])
    if prior is None:
        sources[row["id"]] = deepcopy(row)
        return
    if ({k: v for k, v in prior.items() if k not in _LINK_FIELDS}
            != {k: v for k, v in row.items() if k not in _LINK_FIELDS}):
        raise ValueError("Source identity has conflicting content or provenance")
    for field in _LINK_FIELDS:
        for value in row.get(field, ()):
            if value not in prior.setdefault(field, []):
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
    # v11 (P31): the judgments chosen are read whole or as extracts (_judgments_read); a chosen
    # judgment that could not be read keeps the paragraphs chosen of it, as v8 read them.
    reads = checked["judgments"] if checked["contract"] in research.JUDGMENTS_READ else None
    unread = {entry["case_id"] for entries in (reads or {}).values() for entry in entries if "unread" in entry}
    for work_id, search in checked["searches"].items():
        # From search v9 a pick may choose a provision connected to a returned one (P32).
        for selected in offered(search):
            if admitted is not None and selected["kind"] == "provision" and selected["id"] not in admitted:
                continue
            if reads is not None and selected["kind"] == "judgment" and (
                    selected["id"] not in picked or selected["source"].get("case_id") not in unread):
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
                # P21 (19 Oct 2026): a passage of an Act India Code does not list as in force
                # carries the store's mark, which the writer, the review and the page read.
                if kind == "provision" and in_force(row) is not None:
                    units[-1]["in_force"] = in_force(row)
            identities = list(dict.fromkeys(unit["id"] for unit in units))
            coverage = {"work_id": work_id, "selected_source_id": selected["id"],
                "scope": window["scope"], "bounded": window["bounded"],
                "unread_positions": deepcopy(window["unread_positions"]),
                "gaps": [deepcopy(gap) for gap in search["issues"] if gap["kind"] == kind]}
            for unit in units:
                unit["context_ids"] = [identity for identity in identities if identity != unit["id"]]
                unit["coverage"] = [coverage]
                _add(sources, unit)
    if reads is not None:
        _judgments_read(checked, reads, sources, positions)
    _read_with(checked, sources)
    return sources


def _judgments_read(checked, reads, sources, positions):
    """v11 (owner decision P31): each judgment a dispute chose, read whole or as an extract that
    says so, one source unit per paragraph, the paragraphs of one judgment read together; each
    marked with the questions whose search found it."""
    groups = research.dispute_work(checked["plan"])
    for dispute_id, entries in reads.items():
        work_ids = [work["id"] for work in groups[dispute_id]]
        for entry in entries:
            if "unread" in entry:
                continue
            found_by = {}
            for work_id in work_ids:
                for candidate in (checked["searches"].get(work_id) or {}).get("candidates", []):
                    if candidate["kind"] == "judgment" and candidate["source"].get("case_id") == entry["case_id"]:
                        found_by.setdefault(candidate["position"], []).append(work_id)
            owning = list(dict.fromkeys(w for found in found_by.values() for w in found)) or work_ids[:1]
            revision, units = entry["corpus_revision"], []
            for paragraph in entry["read"]:
                position, row = paragraph["position"], paragraph["row"]
                unit = _candidate("judgment", position, row, revision, None, [], {})
                key = ("judgment", revision, position)
                if key in positions and positions[key] != unit["id"]:
                    raise ValueError("Corpus position has conflicting saved source content")
                positions[key] = unit["id"]
                units.append({"id": unit["id"], "kind": "judgment", "text": unit["text"], "speaker": None,
                              "record_role": "retrieved_candidate", "title": unit["title"], "locator": unit["locator"],
                              "digest": _digest(row), "context_ids": [], "work_ids": list(owning), "coverage": [],
                              "source_identity": {"position": position, "corpus_revision": revision,
                                                  "case_id": row["case_id"], "chunk_id": row["chunk_id"]},
                              "found_by": list(found_by.get(position, []))})
            identities = [unit["id"] for unit in units]
            marked = [unit["id"] for unit in units if unit["found_by"]] or identities
            coverage = {"work_id": owning[0], "selected_source_id": marked[0],
                        "scope": "whole_judgment" if entry["whole"] else "judgment_extract",
                        "bounded": not entry["whole"], "unread_positions": [],
                        "held_paragraphs": entry["paragraphs"], "read_paragraphs": len(units),
                        "gaps": [deepcopy(gap) for work_id in owning
                                 for gap in (checked["searches"].get(work_id) or {}).get("issues", [])
                                 if gap["kind"] == "judgment"]}
            for unit in units:
                unit["context_ids"] = [identity for identity in identities if identity != unit["id"]]
                unit["coverage"] = [coverage]
                _add(sources, unit)


#: How an admitted provision stands to one it is read with, seen from each end.
_READ_WITH = {"names": ("names", "named_by"), "beside": ("beside", "beside")}


def _read_with(checked, sources):
    """Search v9 (owner decision P32, 20 Oct 2026): an admitted provision is read with the
    admitted provisions its Act connects to it, each saying how: it names the other, the
    other names it (with the words that do), or they stand beside each other. Catalogues of
    earlier searches carry no such field."""
    for search in checked["searches"].values():
        for edge in search.get("connections", ()):
            if edge["from"] not in sources or edge["to"] not in sources:
                continue
            forward, backward = _READ_WITH[edge["how"]]
            for here, there, how in ((edge["from"], edge["to"], forward), (edge["to"], edge["from"], backward)):
                relation = {"source_id": there, "how": how, "words": edge["words"]}
                read = sources[here].setdefault("read_with", [])
                if relation not in read:
                    read.append(relation)


def select(reference, sources, *, loose=False):
    """Select exact unique words from an owned tag without normalising text. Held legal
    passages and document pages keep their page line breaks, which a quote may meet
    with spaces; loose places a quotation whatever its case, spacing or typographic
    quotation marks (18 Oct 2026). The selection is still the source's own words.

    A quotation not in the source named but in exactly one passage read with it (another
    paragraph of the same judgment, another part of the same section) is refused naming
    that passage by its short ID (live run 6, 21 Oct 2026: a writer named J28 for words of
    the paragraph beside it three times, shown each time the nearest words of J28)."""
    require_schema(reference, REFERENCE)
    identity = reference["source_id"]
    source = sources.get(identity)
    if source is None or source.get("id") != identity:
        raise SchemaViolation(_unknown(identity, sources))
    try:
        chosen = select_original(reference, {identity: {
            "source_id": identity, "text": source["text"]}}, layout=source["kind"] in _LAYOUT, loose=loose)
    except SchemaViolation as exc:
        if not hasattr(exc, "near") or source["kind"] not in _LEGAL:
            raise
        raise _held_beside(exc, reference, source, sources, loose) from None
    return {key: chosen[key] for key in ("source_id", "start", "end", "text")}


def _held_beside(refused, reference, source, sources, loose):
    """A quotation refused, told by the short IDs the writer reads, with the one passage read
    with the source named that holds those words exactly, if there is one."""
    holders = []
    for other in source.get("context_ids", ()):
        row = sources.get(other)
        if row is None:
            continue
        try:
            select_original({"source_id": other, "quote": reference["quote"]},
                            {other: {"source_id": other, "text": row["text"]}}, layout=row["kind"] in _LAYOUT,
                            loose=loose)
            holders.append(other)
        except SchemaViolation:
            continue
    if len(holders) != 1:
        return refused
    offered = {tag: alias for alias, tag in aliases(sources).items()}
    named, holder = offered.get(source["id"], source["id"]), offered.get(holders[0], holders[0])
    told = SchemaViolation(f"Selected quote is not exact original source text: source_id={named!r}, "
                           f"quote={reference['quote']!r}; those words stand in {holder!r}, read with it")
    told.near = None
    return told


def section_catalogue(context, research_record, sources, draft):
    """The catalogue a dispute's section was written from: its dispute's part of a research
    record that keeps disputes apart (research v10 on, several disputes; step 4), otherwise
    the whole answer's (live run 6: an overview's review re-bound a section's short IDs
    to the whole catalogue's and found its quotations in the wrong passages)."""
    parts = draft.get("parts") if isinstance(draft, dict) else None
    dispute_id = parts[0].get("dispute_id") if isinstance(parts, list) and parts and isinstance(parts[0], dict) else None
    if (research_record.get("contract") in research.BY_DISPUTE and dispute_id is not None
            and len(research.dispute_work(research_record["plan"])) > 1):
        return build(context, research.part_of(research_record, dispute_id))
    return sources


def _unknown(identity, sources):
    """Why a selection names nothing (16 Oct 2026): the identifier, and what can be named,
    so a correction can repair it. Identifiers are code-made labels, not case words."""
    groups = {}
    for alias in aliases(sources):
        groups.setdefault(alias.rstrip("0123456789"), []).append(alias)
    kinds = {"P": "provisions", "J": "judgments", "M": "messages", "DOC": "document pages"}
    named = "; ".join(f"{names[0]} to {names[-1]}" if len(names) > 1 else names[0] for names in groups.values())
    shown = ", ".join(kinds[prefix] for prefix in groups)
    return (f"Selected source_id {identity!r} is not in the owned answer catalogue. Name a source by the short ID "
            f"it is shown under ({named or 'none offered'}: {shown or 'none'}); context, coverage, gap, fact, "
            f"dispute and reply-unit labels are not sources.")


def aliases(sources):
    """Short offered IDs for legal passages (P1, P2, ... and J1, J2, ...), and from 16 Oct
    2026 for messages (M1, ...) and document pages (DOC1, ...).

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
    # Messages and document pages by short IDs too (16 Oct 2026): their owned IDs embed
    # a long random turn identifier, and a writer miscopied one in the owner's run.
    result.update(conversation_aliases((identity, row["kind"] == "document")
                                       for identity, row in sources.items() if row["kind"] not in _LEGAL))
    return result


def shown_context(context, sources):
    """The original conversation as the writer and the reviewer read it: every owned
    source ID shown by its short ID, the words exactly as saved."""
    return renamed(context, {identity: alias for alias, identity in aliases(sources).items()})


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
    coverage, for writing one part of an answer; aliases stay those of the whole. A
    provision's read_with (P32) names, by offered ID, the shown provisions it is read with.
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
        if "found_by" in passage:
            # P31: a paragraph of a judgment read whole or as an extract that search found.
            found = passage.pop("found_by")
            if found and (work_ids is None or set(found) & set(work_ids)):
                passage["found"] = True
        if "read_with" in passage:
            # P32: the provisions it is read with that this presentation shows, by their offered IDs.
            passage["read_with"] = [{**relation, "source_id": offered.get(relation["source_id"], relation["source_id"])}
                                    for relation in row["read_with"] if work_ids is None
                                    or set(sources[relation["source_id"]]["work_ids"]) & set(work_ids)]
            if not passage["read_with"]:
                del passage["read_with"]
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
