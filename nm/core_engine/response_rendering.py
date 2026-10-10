"""Code-owned rendering of the exact independently accepted response version."""
from __future__ import annotations

from copy import deepcopy

from nm.core_engine import response_authorities, response_review, response_writer

LEGACY_CONTRACT = "core_response_rendering_v1"
CONTRACT = "core_response_rendering_v2"
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


def _sources(unit, catalogue):
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
            for index, statement in enumerate(related_uses):
                if related_id == identity and index == 0:
                    continue
                related.append({**deepcopy(statement), "source_id": related_id,
                    "title": source["title"], "locator": source["locator"],
                    "assertion_statement": " · ".join(filter(None, [source["title"],
                        source["locator"]])) + ": " + statement["assertion_statement"]})
        verification["context_statements"] = related
        rendered.append({"brain": True, "id": identity, "digest": row["digest"],
            "kind": row["kind"], "label": row["title"], "title": row["title"],
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


def render(context, research_record, sources, draft, review, execution=None, *,
           authority_evidence=None, contract=CONTRACT):
    """No new prose; the declared version owns its exact reviewed dependencies."""
    if contract not in {LEGACY_CONTRACT, CONTRACT}:
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
    elements = []
    for unit in checked_draft["units"]:
        legal_sources = _sources(unit, sources)
        elements.append({"kind": unit["kind"].upper(), "text": unit["text"],
            "source": deepcopy(legal_sources[0]) if legal_sources else None,
            "sources": legal_sources,
            "refs": list(dict.fromkeys(source["locator"] for source in legal_sources)),
            "inline_citations": _anchors(unit["text"], legal_sources)})
    return elements
