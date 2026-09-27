"""P50 wrappers over recorded-file and curated/source owners, not new legal rules.

Catalogue results are inputs to the shared verifier, never released advice. A
table supplies navigation; only an actual provision read supplies legal text.
Unconfigured readers and uncurated keys remain explicitly unassessed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date

from nm.legal_brain.authority_weight_port import AuthorityWeightPort
from nm.legal_brain.curation_contracts import Curation
from nm.legal_brain.elements_port import ElementsPort
from nm.legal_brain.evidence_port import EvidencePort, EvidenceResult
from nm.legal_brain.filing_requirement_port import FilingRequirementPort
from nm.legal_brain.governing_law_port import GoverningLawPort
from nm.legal_brain.institution_port import PreInstitutionPort
from nm.legal_brain.interim_relief_port import InterimReliefPort
from nm.legal_brain.loop_contracts import digest
from nm.legal_brain.procedural_period_port import ProceduralPeriodPort
from nm.legal_brain.search_port import CorpusSearchPort
from nm.legal_brain.tool_sources import (
    source_envelope,
)
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    _wire_value,
)
from nm.open_matter.matter_documents_port import MatterDocumentsPort
from nm.shared.clock_contracts import today as forum_today
from nm.shared.store_port import StorePort

VERSION = "owner-wrappers-v1"
_STRING = {"type": "string", "minLength": 1}
_NULLABLE_DATE = {"type": ["string", "null"]}
_LIMIT = {"type": "integer", "minimum": 1, "maximum": 200}
_CONTROLS = (
    "test_each_catalogue_tool_runs_the_same_admission_boundary",
    "test_catalogue_absence_never_becomes_a_supported_result",
)


@dataclass(frozen=True)
class PracticeTables:
    """Composition supplies existing knowledge adapters and their exact version."""

    version: str
    elements: ElementsPort | None = None
    institution: PreInstitutionPort | None = None
    interim: InterimReliefPort | None = None
    procedural: ProceduralPeriodPort | None = None
    filing: FilingRequirementPort | None = None
    governing: GoverningLawPort | None = None

    def __post_init__(self):
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("the curated-table population needs an exact version")


def _enum(kind):
    return {"type": "string", "enum": [value.value for value in kind]}


def _data(value):
    return json.loads(json.dumps(value, default=_wire_value, allow_nan=False))


def _date(value):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ToolRefused("the supplied date is not a valid ISO calendar date") from exc


def _source(
    name,
    index,
    source_version,
    locators,
    value,
    *,
    available=True,
    partial=False,
    assessed=False,
    reason="",
    capture=None,
    primary_reads=(),
):
    return source_envelope(
        name,
        VERSION,
        index,
        source_version,
        locators if available else (),
        _data(value) if available and value else {},
        available=available,
        partial=partial,
        assessed=assessed,
        reason=reason,
        capture=capture,
        primary_reads=primary_reads,
    )


def catalogue_tools(
    store: StorePort,
    evidence: EvidencePort,
    *,
    source_version: str,
    search: CorpusSearchPort | None = None,
    tables: PracticeTables | None = None,
    authority_weight: AuthorityWeightPort | None = None,
    matter_documents: MatterDocumentsPort | None = None,
    source_current=None,
    today=forum_today,
) -> tuple[RegisteredTool, ...]:
    """Add to the existing registry; its before/after checks remain mandatory.

    No actor/matter/version arguments are exposed to the model. No reader
    accepts a path, URL, original bytes, SQL or an external action. The upload
    text-index dependency is honestly absent rather than disguised as a full
    matter search. No tool writes facts or establishes a fee/interest rule.
    """
    if not isinstance(source_version, str) or not source_version.strip():
        raise ValueError("source wrappers need an exact source version")

    def file_of(context):
        identity = context.identity
        matter = store.load(identity.matter_id)
        if matter is None or matter.advocate_id != identity.advocate_id:
            raise ToolRefused("the matter is not available to this actor")
        if matter.version != context.current_version:
            raise ToolRefused("the recorded file moved; reacquire its current version")
        return matter

    def matter_result(name, matter, value, *, found=True, partial=False, reason=""):
        data = _data(value) if found else {}
        return ToolEnvelope(
            name,
            VERSION,
            ToolKind.MATTER,
            ToolOutcome.RESULTS if found else ToolOutcome.NO_RESULTS,
            Availability.PARTIAL if partial else Availability.AVAILABLE,
            Assessment.NOT_ASSESSED if partial else Assessment.SUPPORTED,
            {"matter_id": matter.id, "matter_version": matter.version, "snapshot": digest(data)},
            data,
            reason or ("The exact requested entry is not on this file." if not found else ""),
        )

    def source_unavailable(name):
        return _source(
            name,
            "authority search port",
            source_version,
            (),
            {},
            available=False,
            reason="The authority search reader is not configured.",
        )

    def table_unavailable(name):
        return _source(
            name,
            "curated practice table",
            "not_configured",
            (),
            {},
            available=False,
            reason="The curated-table owner is not configured.",
        )

    def table_result(name, curation, guide, sources=()):
        if not isinstance(curation, Curation):
            raise ValueError("a table returned an undeclared curation state")
        if curation is not Curation.CURATED:
            return _source(
                name,
                "curated practice table",
                tables.version,
                (),
                {},
                reason=f"No curated table answers this key: {curation.value}; "
                "continue with retrieval.",
            )
        # Guides remain labelled as navigation; read_primary below returns the
        # ACTUAL source owners' results, with their own honest coverage state.
        locators = [row["curated_from"] for row in guide if row.get("curated_from")]
        if not locators and guide:
            raise ValueError("a curated guide must identify the source it was curated from")
        return _source(
            name,
            "curated practice table",
            source_version,
            locators,
            {
                "guide": guide,
                "table_version": tables.version,
                "primary_reads": [
                    asdict(row) if isinstance(row, EvidenceResult) else row for row in sources
                ],
            }
            if guide
            else {},
            primary_reads=tuple(row for row in sources if isinstance(row, EvidenceResult)),
            reason="Curated guidance is navigation; primary applicability/support "
            "is not yet verified.",
        )

    def read_primary(act, provision, as_of):
        if as_of is None:
            return {
                "act": act,
                "provision": provision,
                "coverage": "not_assessed",
                "missing": "The governing date is not established.",
            }
        return evidence.read_provision(act, provision, _date(as_of))

    from nm.legal_brain.tool_court_fee import build_unavailable_tool as court_fee_tool
    from nm.legal_brain.tool_date_arithmetic import build_tool as date_arithmetic_tool
    from nm.legal_brain.tool_elements_of import build_tool as elements_of_tool
    from nm.legal_brain.tool_filing_requirements import build_tool as filing_requirements_tool
    from nm.legal_brain.tool_governing_code import build_tool as governing_code_tool
    from nm.legal_brain.tool_interim_test import build_tool as interim_test_tool
    from nm.legal_brain.tool_list_deadlines import build_tool as list_deadlines_tool
    from nm.legal_brain.tool_pre_institution_steps import build_tool as pre_institution_steps_tool
    from nm.legal_brain.tool_procedural_periods import build_tool as procedural_periods_tool
    from nm.legal_brain.tool_quote_matter import build_tool as quote_matter_tool
    from nm.legal_brain.tool_rank_authorities import build_tool as rank_authorities_tool
    from nm.legal_brain.tool_read_facts import build_tool as read_facts_tool
    from nm.legal_brain.tool_read_judgment import build_tool as read_judgment_tool
    from nm.legal_brain.tool_read_paragraph import build_tool as read_paragraph_tool
    from nm.legal_brain.tool_read_source_document import build_tool as read_source_document_tool
    from nm.legal_brain.tool_read_thread import build_tool as read_thread_tool
    from nm.legal_brain.tool_read_turn import build_tool as read_turn_tool
    from nm.legal_brain.tool_resolve_citation import build_tool as resolve_citation_tool
    from nm.legal_brain.tool_search_authorities import build_tool as search_authorities_tool
    from nm.legal_brain.tool_search_matter import build_tool as search_matter_tool
    from nm.legal_brain.tool_treatment import build_tool as treatment_tool

    tools = (
        read_thread_tool(
            file_of=file_of, matter_result=matter_result, today=today, source_current=source_current
        ),
        read_facts_tool(file_of=file_of, matter_result=matter_result),
        read_turn_tool(file_of=file_of, matter_result=matter_result),
        search_matter_tool(
            file_of=file_of, matter_result=matter_result, matter_documents=matter_documents
        ),
        list_deadlines_tool(file_of=file_of, matter_result=matter_result),
        resolve_citation_tool(
            search=search, source_version=source_version, source_unavailable=source_unavailable
        ),
        search_authorities_tool(
            search=search, source_version=source_version, source_unavailable=source_unavailable
        ),
        read_paragraph_tool(
            search=search, source_version=source_version, source_unavailable=source_unavailable
        ),
        read_judgment_tool(
            search=search, source_version=source_version, source_unavailable=source_unavailable
        ),
        read_source_document_tool(evidence=evidence, source_version=source_version),
        treatment_tool(
            search=search, source_version=source_version, source_unavailable=source_unavailable
        ),
        rank_authorities_tool(authority_weight=authority_weight, source_version=source_version),
        date_arithmetic_tool(),
        pre_institution_steps_tool(
            tables=tables,
            table_unavailable=table_unavailable,
            table_result=table_result,
            read_primary=read_primary,
        ),
        interim_test_tool(
            tables=tables, table_unavailable=table_unavailable, table_result=table_result
        ),
        procedural_periods_tool(
            tables=tables,
            table_unavailable=table_unavailable,
            table_result=table_result,
            read_primary=read_primary,
        ),
        governing_code_tool(
            tables=tables, table_unavailable=table_unavailable, table_result=table_result
        ),
        elements_of_tool(
            tables=tables, table_unavailable=table_unavailable, table_result=table_result
        ),
        filing_requirements_tool(tables=tables, table_unavailable=table_unavailable),
        court_fee_tool(tables=tables, version=VERSION, controls=_CONTROLS),
    )
    if matter_documents is not None:
        tools += (
            quote_matter_tool(
                file_of=file_of, matter_result=matter_result, matter_documents=matter_documents
            ),
        )
    return tools
