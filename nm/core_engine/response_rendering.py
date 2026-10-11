"""Code-owned rendering of the exact independently accepted response version."""
from __future__ import annotations

from copy import deepcopy
import re

from nm.core_engine import response_authorities, response_review, response_writer
from nm.shared.citation_contracts import statute_title

LEGACY_CONTRACT = "core_response_rendering_v1"
#: Authority-bound rendering with each source under its stored title.
STORED_TITLE_CONTRACT = "core_response_rendering_v2"
#: v2 with statutes under their shown names (owner decisions, 10-11 Oct 2026).
SHOWN_NAME_CONTRACT = "core_response_rendering_v3"
#: v3 linking each source at the words that cite it, never a whole paragraph;
#: sources not cited by name follow the paragraph as markers (11 Oct 2026).
CONTRACT = "core_response_rendering_v4"
_LEGAL = {"provision", "judgment"}
_ROLES = {"provision": "legislative_text", "court_disposition": "court_conclusion",
          "court_reasoning": "court_reasoning", "party_submission": "party_submission",
          "quoted_authority": "quoted_authority", "uncertain": "unclear"}
_ROLE_LABELS = {"original_account": "Original account", "opposing_account": "Opposing account",
    "contract": "Quoted contract terms", "provision": "Legislative text",
    "party_submission": "Party submission", "court_reasoning": "Court reasoning",
    "court_disposition": "Court disposition", "quoted_authority": "Quoted authority",
    "uncertain": "Unresolved source role"}


def _statement(unit, use):
    treatment = use["treatment_source"]
    return {"assertion_statement": unit["text"],
        "assertion_role": _ROLES.get(use["role"], use["role"]),
        "source_role": use["role"], "support_excerpt": use["text"],
        "owner_label": use["speaker"], "owner_excerpt": "", "scope_excerpt": "",
        "source_treatment": use["treatment"].replace("_", " "),
        "treatment_excerpt": treatment["text"] if treatment else "", "reason": ""}


def _title(row, shown_names):
    """The reader's name for a source; statute words are never renamed."""
    if shown_names and row["kind"] == "provision":
        return statute_title(row["title"], row["source_identity"].get("act_id", ""))
    return row["title"]


def _sources(unit, catalogue, shown_names=False):
    statements = {}
    labels = {}
    for use in unit["uses"]:
        identity = use["source_id"]
        if catalogue[identity]["kind"] in _LEGAL:
            statements.setdefault(identity, []).append(_statement(unit, use))
            labels.setdefault(identity, _ROLE_LABELS[use["role"]])
        treatment = use["treatment_source"]
        if treatment is not None and catalogue[treatment["source_id"]]["kind"] in _LEGAL:
            identity = treatment["source_id"]
            # The exact treatment is selected independently. Its statement role is
            # not inferred from proximity, parser metadata or a party's own label.
            statements.setdefault(identity, []).append({
                "assertion_statement": treatment["text"], "assertion_role": "unclear",
                "source_role": "treatment_support", "support_excerpt": treatment["text"],
                "owner_label": None, "owner_excerpt": "", "scope_excerpt": "",
                "source_treatment": "not applicable", "treatment_excerpt": "", "reason": ""})
            labels.setdefault(identity, "Passage selected for court treatment")

    rendered = []
    for identity, uses in statements.items():
        row = catalogue[identity]
        verification = deepcopy(uses[0])
        related = []
        for related_id, related_uses in statements.items():
            source = catalogue[related_id]
            source_title = _title(source, shown_names)
            for index, statement in enumerate(related_uses):
                if related_id == identity and index == 0:
                    continue
                related.append({**deepcopy(statement), "source_id": related_id,
                    "title": source_title, "locator": source["locator"],
                    "assertion_statement": " · ".join(filter(None, [source_title,
                        source["locator"]])) + ": " + statement["assertion_statement"]})
        verification["context_statements"] = related
        title = _title(row, shown_names)
        rendered.append({"brain": True, "id": identity, "digest": row["digest"],
            "kind": row["kind"], "label": title, "title": title,
            # This is a reader label, never an invented paragraph/section number.
            "locator": row["locator"] or "Saved passage", "text": row["text"],
            "qualification": labels[identity] + ".", "verification": verification})
    return rendered


def _unique_span(text, phrase):
    if not phrase:
        return None
    start = text.find(phrase)
    if start < 0 or text.find(phrase, start + 1) >= 0:
        return None
    end = start + len(phrase)
    word = lambda char: char.isalnum() or char == "_"
    if (start and word(phrase[0]) and word(text[start - 1])
            or end < len(text) and word(phrase[-1]) and word(text[end])):
        return None
    return start, end


def _anchors(text, sources):
    owners = {}
    for index, source in enumerate(sources):
        title, locator = source["title"], source["locator"]
        phrases = {title, f"{title} {locator}", f"{title} · {locator}"}
        # Bare numbers cannot identify a cited passage rather than a date/amount.
        if locator and not locator.isdecimal() and locator != "Saved passage":
            phrases.add(locator)
        for phrase in phrases:
            if phrase:
                owners.setdefault(phrase, set()).add(index)
    candidates = []
    for phrase, indices in owners.items():
        span = _unique_span(text, phrase)
        if len(indices) == 1 and span is not None:
            candidates.append((span[0], span[1], phrase, next(iter(indices))))
    chosen, linked = [], set()
    for start, end, phrase, index in sorted(candidates, key=lambda c: (-(c[1] - c[0]), c[0], c[3])):
        if index in linked or any(start < prior[1] and end > prior[0] for prior in chosen):
            continue
        chosen.append((start, end, phrase, index))
        linked.add(index)
    if not chosen and sources:
        chosen = [(0, len(text), text, 0)]
    return [{"text": phrase, "source_id": sources[index]["id"], "source_index": index}
            for _, _, phrase, index in sorted(chosen)]


def _span(text, phrase):
    """The one place a phrase occurs, ignoring case, on word boundaries."""
    if not phrase or not phrase.strip():
        return None
    found = [m.span() for m in re.finditer(r"(?<![\w])" + re.escape(phrase) + r"(?![\w])", text, re.I)]
    return found[0] if len(found) == 1 else None


def _names(source):
    title = source["title"]
    names = {title}
    if title[:4].casefold() == "the ":
        names.add(title[4:])
    return {name for name in names if name.strip()}


# A sentence ends at terminal punctuation followed by space and a capital letter;
# "s. 170", "No. 5" and "Rs. 50,000" therefore stay inside their sentence.
_SENTENCE_END = re.compile(r"[.!?](?=\s+[A-Z(\"'“])")


def _sentence(text, start, end):
    begin = max((m.end() for m in _SENTENCE_END.finditer(text, 0, start)), default=0)
    after = _SENTENCE_END.search(text, end)
    return text[begin:after.start() + 1 if after else len(text)]


def _cited_words(text, sources, authority):
    """v4: link a source at the words that cite it and list the rest as markers.

    Words come from the authority checks (a case citation matched to one used
    judgment; a provision reference binding one used provision whose Act is
    named in the same sentence) and from a source's own name or locator found
    once, ignoring case. A name shared by several used sources, a bare number or
    the whole paragraph never becomes a link.
    """
    index = {source["id"]: number for number, source in enumerate(sources)}
    candidates = []
    for row in authority["case_associations"]:
        matched = {index[i] for i in row["matching_source_ids"] if i in index}
        if row["association"] == "matched" and len(matched) == 1:
            candidates.append((row["start"], row["end"], matched.pop(), 0))
    for row in authority["prose_provisions"]:
        matched = sorted(index[i] for i in row["candidate_source_ids"] if i in index)
        if row["key_match"] != "one_used_identity" or not matched:
            continue
        sentence = _sentence(text, row["start"], row["end"])
        if any(re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", sentence, re.I)
               for name in _names(sources[matched[0]])):
            candidates.append((row["start"], row["end"], matched[0], 0))
    owners = {}
    for number, source in enumerate(sources):
        locator = source["locator"]
        phrases = set(_names(source))
        if locator and locator != "Saved passage":
            phrases |= {f"{name}{joint}{locator}" for name in _names(source) for joint in (" ", " · ")}
            if not locator.isdecimal():
                phrases.add(locator)
        for phrase in phrases:
            owners.setdefault(phrase.casefold(), (phrase, set()))[1].add(number)
    for phrase, numbers in owners.values():
        span = _span(text, phrase)
        if len(numbers) == 1 and span is not None:
            candidates.append((span[0], span[1], next(iter(numbers)), 1))
    chosen, linked = [], set()
    for start, end, number, rank in sorted(candidates, key=lambda c: (c[3], -(c[1] - c[0]), c[0], c[2])):
        if (number in linked or (start, end) == (0, len(text))
                or any(start < prior[1] and end > prior[0] for prior in chosen)):
            continue
        chosen.append((start, end, number))
        linked.add(number)
    anchors = [{"text": text[start:end], "source_id": sources[number]["id"],
                "source_index": number, "start": start, "end": end}
               for start, end, number in sorted(chosen)]
    markers = [{"source_id": source["id"], "source_index": number}
               for number, source in enumerate(sources) if number not in linked]
    return anchors, markers


def render(context, research_record, sources, draft, review, execution=None, *,
           authority_evidence=None, contract=CONTRACT):
    """No new prose; the declared version owns its exact reviewed dependencies."""
    if contract not in {LEGACY_CONTRACT, STORED_TITLE_CONTRACT, SHOWN_NAME_CONTRACT, CONTRACT}:
        raise ValueError("Unknown response rendering contract")
    checked_draft = response_writer.validate(draft, context, sources)
    if contract == LEGACY_CONTRACT:
        if authority_evidence is not None or review.get("contract") != response_review.LEGACY_CONTRACT:
            raise ValueError("Legacy rendering requires its original review without authority enrichment")
        checked_review = response_review.validate(review, context, research_record,
            sources, checked_draft, execution=execution)
    else:
        if authority_evidence is None or review.get("contract") != response_review.CONTRACT:
            raise ValueError("Current rendering requires an authority-bound current review")
        checked_authorities = response_authorities.validate(authority_evidence, context,
            research_record, sources, checked_draft)
        checked_review = response_review.validate(review, context, research_record,
            sources, checked_draft, execution=execution, authority_evidence=checked_authorities)
    if not checked_review["accepted"]:
        raise ValueError("A response without accepted independent review cannot be rendered")
    authorities = ({row["unit_id"]: row for row in checked_authorities["units"]}
                   if contract == CONTRACT else {})
    elements = []
    for unit in checked_draft["units"]:
        legal_sources = _sources(unit, sources, shown_names=contract in {SHOWN_NAME_CONTRACT, CONTRACT})
        element = {"kind": unit["kind"].upper(), "text": unit["text"],
            "source": deepcopy(legal_sources[0]) if legal_sources else None,
            "sources": legal_sources,
            "refs": list(dict.fromkeys(source["locator"] for source in legal_sources))}
        if contract == CONTRACT:
            element["inline_citations"], element["citation_markers"] = _cited_words(
                unit["text"], legal_sources, authorities[unit["id"]])
        else:
            element["inline_citations"] = _anchors(unit["text"], legal_sources)
        elements.append(element)
    return elements
