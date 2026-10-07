"""Construct fresh reply expressions from owned evidence, never writer wording.

This certifies the words and references used in rendering. Selecting relevant
evidence, interpreting a passage and applying law remain reviewed judgments.
Legacy replies are not retrospectively certified by this contract.
"""
from __future__ import annotations

from copy import deepcopy

from nm.brain.legal_requirements import source_verification_valid
from nm.shared.model_port import SchemaViolation, require_schema

EVIDENCE_EXPRESSION_CONTRACT = "evidence_expression_v1"
OPERATORS = ("source_account", "checked_legal", "comparison", "question",
             "next_work", "limitation", "acknowledgment", "record_result")
FOCUSES = ("none", "actor", "event", "chronology", "attribution", "certainty",
           "meaning", "availability")


def _ids(choices) -> dict:
    values = list(choices)
    return {"type": "array", "items": {"type": "string", **(
        {"enum": values} if values else {})}, **({"maxItems": 0} if not values else {})}


def expression_schema(spans: dict, records: dict, sources: dict | None = None, *,
                      generation: bool = False) -> dict:
    """Offer applicable fresh choices without changing canonical v1 validation.

    Rendering still checks ownership, distinct selections and complete evidence.
    The generation branches prevent mechanically impossible combinations;
    they certify neither source meaning nor requested sufficiency.
    """
    schema = {"type": "object", "additionalProperties": False,
            "required": ["operator", "source_ids", "record_ids", "focus"],
            "properties": {
                "operator": {"type": "string", "enum": list(OPERATORS)},
                "source_ids": _ids(spans), "record_ids": _ids(records),
                "focus": {"type": "string", "enum": list(FOCUSES)}}}
    if sources:
        schema["properties"]["legal_source_ids"] = _ids(sources)
        schema["required"].append("legal_source_ids")
    if generation:
        branches = []
        for operator in OPERATORS:
            branch = deepcopy(schema)
            fields = branch["properties"]
            fields["operator"]["enum"] = [operator]
            fixed = operator in ("acknowledgment", "record_result")
            fields["source_ids"] = _ids(
                () if fixed else (identity for identity, row in spans.items()
                                  if operator != "source_account" or row.get("role") == "advocate"))
            record_types = ("requirement", "research") if operator == "checked_legal" else (
                "material", "dispute")
            fields["record_ids"] = _ids(
                () if fixed else (identity for identity, row in records.items()
                                  if row.get("type") in record_types))
            if operator not in ("question", "next_work"):
                fields["focus"]["enum"] = ["none"]
            if sources and operator != "checked_legal":
                fields["legal_source_ids"] = _ids(())
            branches.append(branch)
        return {"anyOf": branches}
    return schema


def _selection(values, catalogue: dict, field: str) -> list[str]:
    if any(value not in catalogue for value in values):
        raise SchemaViolation(f"expression.{field} must select owned evidence")
    # Repeating an owned selection changes no meaning. Check before normalising.
    return list(dict.fromkeys(values))


def _source(identity: str, spans: dict, *, account: bool) -> str:
    row = spans[identity]
    if (not isinstance(row, dict) or row.get("role") not in ("advocate", "nm")
            or not isinstance(row.get("text"), str) or not row["text"].strip()):
        raise SchemaViolation("An expression source lacks attributable original words")
    if account and row["role"] != "advocate":
        raise SchemaViolation("NM's words cannot supply an advocate account")
    label = ("Your message includes" if row["role"] == "advocate"
             else "NM's earlier message includes")
    # The complete span retains its qualifications and negation. Selection is
    # still reviewed against the complete transcript for framing and relevance.
    return f'{label}: “{row["text"]}”'


def _record(identity: str, records: dict) -> str:
    row = records[identity]
    value = row.get("record") if isinstance(row, dict) else None
    if (not isinstance(row, dict) or row.get("type") not in ("material", "dispute")
            or not isinstance(value, dict)
            or not isinstance(value.get("quoted"), str) or not value["quoted"].strip()):
        raise SchemaViolation("Account expressions need a record's original quoted words")
    return f'The saved attributed account includes: “{value["quoted"]}”'


def render_expression(expression: dict, *, spans: dict, records: dict, sources: dict) -> dict:
    """Resolve a closed expression; no arbitrary display string is accepted."""
    # Saved v1 expressions permitted this selector to be absent. Its omission
    # meant an empty direct selection; finding-owned citations still resolved
    # below. Validate that historical meaning without rewriting the durable
    # expression or relaxing the fresh provider/admission schema.
    validation_expression = deepcopy(expression)
    if sources and isinstance(validation_expression, dict):
        validation_expression.setdefault("legal_source_ids", [])
    elif isinstance(validation_expression, dict) and (
            validation_expression.get("legal_source_ids") == []):
        # A saved block may come from a larger generation catalogue than its
        # selected replay dependencies. This known empty selector names no
        # passage. Preserve the saved expression; reject populated/unknown data.
        validation_expression.pop("legal_source_ids")
    require_schema(validation_expression, expression_schema(spans, records, sources))
    operator, focus = expression["operator"], expression["focus"]
    selected_sources = _selection(expression["source_ids"], spans, "source_ids")
    selected_records = _selection(expression["record_ids"], records, "record_ids")
    selected_legal = _selection(expression.get("legal_source_ids", []),
                                sources, "legal_source_ids")
    if selected_legal and operator != "checked_legal":
        raise SchemaViolation("Only a checked legal expression may select legal passages")
    if focus != "none" and operator not in ("question", "next_work"):
        raise SchemaViolation("Only a question or proposed work may select an expression focus")
    if operator in ("acknowledgment", "record_result") and (
            selected_sources or selected_records):
        raise SchemaViolation("A fixed expression must not carry unrelated evidence selections")
    if operator in ("source_account", "comparison", "question", "next_work", "checked_legal"):
        if not selected_sources and not selected_records and not selected_legal:
            raise SchemaViolation("This expression needs its original evidence or checked finding")
    if operator == "comparison" and len(selected_sources) + len(selected_records) < 2:
        raise SchemaViolation("A comparison needs at least two distinct evidence selections")
    legal_ids, citations = [], []
    passages = [_source(key, spans, account=operator == "source_account")
                for key in selected_sources]
    for key in selected_records:
        row = records[key]
        if operator == "checked_legal":
            finding = row.get("record")
            if (row.get("type") not in ("requirement", "research")
                    or not isinstance(finding, dict)
                    or not isinstance(finding.get("need"), str) or not finding["need"].strip()
                    or not isinstance(finding.get("source_ids"), list)
                    or not finding["source_ids"]):
                raise SchemaViolation("A legal expression must select a checked finding")
            passages.append(f'The checked legal proposition is: “{finding["need"]}”')
            for identity in finding["source_ids"]:
                if identity not in sources:
                    raise SchemaViolation("A checked expression lost its legal passage owner")
                if identity not in legal_ids:
                    legal_ids.append(identity)
        else:
            passages.append(_record(key, records))
    for identity in selected_legal:
        source = sources[identity]
        if not source_verification_valid(source):
            raise SchemaViolation("A directly selected legal passage needs its checked use")
        passages.append(f'The checked legal passage includes: “{source["text"]}”')
        if identity not in legal_ids:
            legal_ids.append(identity)
    if operator == "checked_legal" and not legal_ids:
        raise SchemaViolation("A legal expression needs a checked legal passage")
    text = " ".join(passages)
    if operator == "comparison":
        text = "Compare these attributed passages in their original context. " + text
    elif operator in ("question", "next_work"):
        aspect = {"none": "meaning", "actor": "actor", "event": "event",
                  "chronology": "event order", "attribution": "speaker or attribution",
                  "certainty": "certainty", "meaning": "meaning",
                  "availability": "availability of the referenced material"}[focus]
        text = ((f"What needs clarification about the {aspect} of the following account? "
                 if operator == "question" else
                 f"A possible next step is to examine the {aspect} of the following account. ")
                + text)
    elif operator == "limitation":
        text = "The requested conclusion remains unresolved on the supplied support." + (
            " " + text if text else "")
    elif operator == "acknowledgment":
        text = "I have your message."
    elif operator == "record_result":
        text = "The requested record result remains unresolved."
    elif operator == "checked_legal":
        text = ("Application depends on the proposition's conditions and the attributed account. "
                + text)
    for index, identity in enumerate(legal_ids, start=1):
        anchor = f"Checked legal passage {index}"
        text += f" {anchor}."
        citations.append({"text": anchor, "legal_source_id": identity})
    return {"text": text, "span_ids": selected_sources, "record_ids": selected_records,
            "legal_source_ids": legal_ids, "inline_citations": citations}


def validate_rendered_block(block: dict, *, spans: dict, records: dict, sources: dict) -> None:
    if block.get("expression_contract") != EVIDENCE_EXPRESSION_CONTRACT:
        raise SchemaViolation("A fresh rendered block needs its owned expression contract")
    rendered = render_expression(block.get("evidence_expression"),
                                 spans=spans, records=records, sources=sources)
    if any(block.get(key) != value for key, value in rendered.items()):
        raise SchemaViolation("A rendered expression's words or references were altered")


def rendered_block(block: dict, *, spans: dict, records: dict, sources: dict) -> dict:
    """Derive all display content; writer-supplied display fields are forbidden."""
    forbidden = {"text", "span_ids", "record_ids", "legal_source_ids", "inline_citations",
                 "expression_contract"} & block.keys()
    if forbidden:
        raise SchemaViolation(
            f"A fresh expression cannot supply display fields {sorted(forbidden)}")
    return {**deepcopy(block), **render_expression(block["evidence_expression"],
                                                  spans=spans, records=records, sources=sources),
            "expression_contract": EVIDENCE_EXPRESSION_CONTRACT}
