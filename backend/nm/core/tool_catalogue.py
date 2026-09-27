"""P50 wrappers over recorded-file and curated/source owners, not new legal rules.

Catalogue results are inputs to the shared verifier, never released advice. A
table supplies navigation; only an actual provision read supplies legal text.
Unconfigured readers and uncurated keys remain explicitly unassessed.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from nm.core import deadlines, limitation, requirements
from nm.core.tool_sources import (
    capture_document,
    capture_paragraph,
    combine_captures,
    source_envelope,
)
from nm.core.tools import (
    Assessment,
    Availability,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    _wire_value,
    object_schema,
)
from nm.domain.clock import today as forum_today
from nm.domain.curation import Curation
from nm.domain.loop import digest
from nm.domain.matter import CauseOfAction, Role
from nm.ports.authority_weight import AuthorityWeightPort
from nm.ports.elements import ElementsPort
from nm.ports.evidence import Coverage, EvidencePort, EvidenceResult, SourceKind, TreatmentState
from nm.ports.filing_requirement import FilingRequirementPort, Requirement
from nm.ports.governing_law import GoverningLawPort, Limb, Pending
from nm.ports.institution import Against, PreInstitutionPort
from nm.ports.interim_relief import InterimRelief, InterimReliefPort
from nm.ports.matter_documents import DocumentRefused, MatterDocumentsPort
from nm.ports.model import ToolDefinition
from nm.ports.procedural_period import ProceduralPeriodPort, Track
from nm.ports.search import CorpusSearchPort, ResolutionState
from nm.ports.store import StorePort

VERSION = "owner-wrappers-v1"
_STRING = {"type": "string", "minLength": 1}
_NULLABLE_DATE = {"type": ["string", "null"]}
_LIMIT = {"type": "integer", "minimum": 1, "maximum": 200}
_CONTROLS = ("test_each_catalogue_tool_runs_the_same_admission_boundary",
             "test_catalogue_absence_never_becomes_a_supported_result")


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


def _source(name, index, source_version, locators, value, *, available=True,
            partial=False, assessed=False, reason="", capture=None, primary_reads=()):
    return source_envelope(name, VERSION, index, source_version,
        locators if available else (), _data(value) if available and value else {},
        available=available, partial=partial, assessed=assessed, reason=reason,
        capture=capture, primary_reads=primary_reads)


def catalogue_tools(store: StorePort, evidence: EvidencePort, *, source_version: str,
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
        return ToolEnvelope(name, VERSION, ToolKind.MATTER,
            ToolOutcome.RESULTS if found else ToolOutcome.NO_RESULTS,
            Availability.PARTIAL if partial else Availability.AVAILABLE,
            Assessment.NOT_ASSESSED if partial else Assessment.SUPPORTED,
            {"matter_id": matter.id, "matter_version": matter.version,
             "snapshot": digest(data)}, data,
            reason or ("The exact requested entry is not on this file." if not found else ""))

    def read_thread(args, context):
        from nm.domain.event_observation import event_context

        matter = file_of(context)
        thread = next((row for row in matter.threads if row.id == args["thread_id"]), None)
        value = {**asdict(thread), "event_context": event_context(thread, matter.facts),
                 "checklist_context": requirements.context_projection(
            thread, matter.facts, today(), records=matter.loop_records,
            source_current=source_current)} if thread else {}
        return matter_result("read_thread", matter, value,
            found=thread is not None)

    def read_facts(_args, context):
        matter = file_of(context)
        return matter_result("read_facts", matter,
            {"facts": [asdict(fact) for fact in matter.facts]})

    def read_turn(args, context):
        matter = file_of(context)
        receipt = next((row for row in matter.turn_receipts
                        if row.turn_id == args["turn_id"]), None)
        if receipt is None:
            return matter_result("read_turn", matter, {}, found=False)
        receipt.validated_answer()
        return matter_result("read_turn", matter, asdict(receipt))

    def search_matter(args, context):
        matter = file_of(context)
        query = args["query"].casefold()
        matches = []
        for fact in matter.facts:
            if query in fact.statement.casefold():
                matches.append({"locator": f"fact:{fact.id}", "fact": asdict(fact)})
        for receipt in matter.turn_receipts:
            receipt.validated_answer()
            if receipt.input_admitted and query in receipt.message.casefold():
                matches.append({"locator": f"turn:{receipt.turn_id}",
                                "words": receipt.message})
        try:
            document_read = (matter_documents.search(matter.id, matter.advocate_id,
                context.current_version, args["query"], limit=args["limit"])
                if matter_documents is not None else None)
        except DocumentRefused as exc:
            raise ToolRefused(str(exc)) from exc
        if document_read is not None:
            matches.extend(document_read.matches)
        # A zero names the exact searched population and every unassessed
        # original. Uploaded text only joins this population through its owner.
        return matter_result("search_matter", matter,
            {"matches": matches[:args["limit"]],
             "matched_count": (len(matches) if document_read is None else
                               len(matches) - len(document_read.matches)
                               + document_read.matched_count),
             "searched": ["recorded facts", "admitted canonical turn messages",
                 *(["bounded admitted document text"] if document_read is not None else [])],
             "document_sources_searched": list(document_read.searched) if document_read else [],
             "not_searched": (list(document_read.not_searched) if document_read is not None
                              else ["admitted document text index"])},
            partial=document_read is None or document_read.partial,
            reason=("Uploaded document text has not been read on this installation."
                    if document_read is None else
                    "Some originals or units were not searched; "
                    "absence is only in the searched population."
                    if document_read.partial else ""))

    def quote_matter(args, context):
        matter = file_of(context)
        try:
            quote = matter_documents.quote(matter.id, matter.advocate_id, context.current_version,
                                          **args)
        except DocumentRefused as exc:
            raise ToolRefused(str(exc)) from exc
        return matter_result("quote_matter", matter, asdict(quote))

    def list_deadlines(args, context):
        matter = file_of(context)
        register = deadlines.read_matter(matter)
        today = _date(args["as_of"])
        partial = bool(register.unreadable or register.unassessed)
        return matter_result("list_deadlines", matter,
            {"deadlines": [asdict(row) for row in deadlines.register(register.rows, today)],
             "unreadable": [asdict(problem) for problem in register.unreadable],
             "unassessed_threads": list(register.unassessed)}, partial=partial,
            reason="Some deadlines could not be read or were not assessed." if partial else "")

    def source_unavailable(name):
        return _source(name, "authority search port", source_version, (), {},
            available=False, reason="The authority search reader is not configured.")

    def resolve(args, _context):
        if search is None:
            return source_unavailable("resolve_citation")
        result = search.resolve(args["citation"])
        return _source("resolve_citation", "exact reporter identity index", source_version,
            (result.case_id,) if result.case_id else (),
            asdict(result) if result.state is ResolutionState.RESOLVED else {},
            available=result.state is not ResolutionState.INDEX_UNAVAILABLE,
            assessed=result.state is ResolutionState.RESOLVED,
            reason=result.why or ("Exact identity is not a semantic/legal support assessment."
                                  if result.state is not ResolutionState.RESOLVED else ""))

    def discover(args, _context):
        if search is None:
            return source_unavailable("search_authorities")
        result = search.discover(args["query"], court=args["court"],
            from_year=args["from_year"], to_year=args["to_year"], limit=args["limit"])
        return _source("search_authorities", result.index,
            result.identity.corpus_version if result.identity is not None else source_version,
            [row.case_id for row in result.cases], asdict(result) if result.cases else {},
            available=result.coverage is not Coverage.NOT_ASSESSED,
            partial=result.coverage is not Coverage.ANSWERED,
            reason=result.why or
                "Ranked cases are candidates, not exact identities or legal support.")

    def paragraph(args, _context):
        if search is None:
            return source_unavailable("read_paragraph")
        result = search.passage(args["locator"])
        return _source("read_paragraph", "exact authority paragraph reader", source_version,
            (result.paragraph.locator,) if result.paragraph else (),
            asdict(result) if result.paragraph else {},
            available=result.state is not ResolutionState.INDEX_UNAVAILABLE,
            capture=capture_paragraph(result.paragraph,
                index="exact authority paragraph reader", source_version=source_version)
                if result.paragraph else None,
            reason=result.why or "The passage is read, but legal support has not been assessed.")

    def judgment(args, _context):
        if search is None:
            return source_unavailable("read_judgment")
        result = search.expand(args["case_id"], query=args["query"],
                               limit=args["limit"], after=args["after"])
        return _source("read_judgment", result.index, source_version,
            [row.locator for row in result.paragraphs],
            asdict(result) if result.paragraphs else {},
            available=result.coverage is not Coverage.NOT_ASSESSED,
            partial=result.complete is not True or result.next_after is not None,
            capture=combine_captures(*(capture_paragraph(row, index=result.index,
                source_version=(result.identity.corpus_version
                                if result.identity else source_version))
                for row in result.paragraphs)),
            reason=result.why or "This is an indexed paragraph window, not verified legal support.")

    def source_document(args, _context):
        result = evidence.document(args["locator"], SourceKind(args["kind"]),
                                   start=args["start"], count=args["count"])
        if result.state == "read" and not result.snapshot_id.strip():
            return _source("read_source_document", result.store or "corpus document reader",
                "not_established", (), {}, available=False,
                reason="The read has no source snapshot identity; its text cannot be accepted.")
        return _source("read_source_document", result.store or "corpus document reader",
            result.snapshot_id or source_version, [row[0] for row in result.segments],
            asdict(result) if result.state == "read" else {},
            available=result.state != "no_reader",
            partial=bool(result.excluded) or not result.whole,
            capture=capture_document(result, kind=SourceKind(args["kind"])),
            reason="The source was not held." if result.state == "not_held" else
                "The corpus document reader is not available." if result.state == "no_reader" else
                "This located source window is material to assess, not an approved conclusion.")

    def treatment(args, _context):
        if search is None:
            return source_unavailable("treatment")
        identity = search.case_identity(args["case_id"])
        if identity.state is not ResolutionState.RESOLVED:
            return _source("treatment", "case identity and citator", source_version, (), {},
                available=identity.state is not ResolutionState.INDEX_UNAVAILABLE,
                reason=identity.why)
        result = search.treatment(args["case_id"])
        return _source("treatment", "case identity and citator", source_version,
            (args["case_id"],), asdict(result),
            partial=result.state is TreatmentState.NOT_CHECKED,
            assessed=result.state is not TreatmentState.NOT_CHECKED,
            reason=result.scope if result.state is TreatmentState.NOT_CHECKED else "")

    def weight(args, _context):
        if authority_weight is None:
            return _source("rank_authorities", "authority weight owner", source_version, (), {},
                available=False,
                reason="The case identity and authority-weight reader is not configured.")
        result = authority_weight.weigh(tuple(args["locators"]))
        return _source("rank_authorities", "authority weight owner", source_version,
            args["locators"], asdict(result) if result.weighings else {},
            reason=result.why or "Authority weighting is a recorded rule, not semantic support.")

    def date_arithmetic(args, _context):
        on = _date(args["on"])
        amount = args["amount"]
        try:
            if args["unit"] == "years":
                answer = limitation.add_years(on, amount)
                method = "nm.core.limitation.add_years"
            elif args["unit"] == "months":
                answer = limitation.add_months(on, amount)
                method = "nm.core.limitation.add_months"
            else:
                answer = on + timedelta(days=amount)
                method = "calendar timedelta; no court-calendar adjustment"
        except (ValueError, OverflowError) as exc:
            raise ToolRefused(
                "the requested arithmetic lies outside the supported calendar") from exc
        return ToolEnvelope("date_arithmetic", VERSION, ToolKind.COMPUTATION,
            ToolOutcome.RESULTS, Availability.AVAILABLE, Assessment.SUPPORTED,
            {"inputs": args, "method": method,
             "input_receipts": [{"kind": "tool arguments", "digest": digest(args),
                 "legal_premises_established": False}]},
            {"date": answer.isoformat(), "holiday_adjusted": False,
             "legal_deadline_established": False})

    def table_unavailable(name):
        return _source(name, "curated practice table", "not_configured", (), {},
            available=False, reason="The curated-table owner is not configured.")

    def table_result(name, curation, guide, sources=()):
        if not isinstance(curation, Curation):
            raise ValueError("a table returned an undeclared curation state")
        if curation is not Curation.CURATED:
            return _source(name, "curated practice table", tables.version, (), {},
                reason=f"No curated table answers this key: {curation.value}; "
                    "continue with retrieval.")
        # Guides remain labelled as navigation; read_primary below returns the
        # ACTUAL source owners' results, with their own honest coverage state.
        locators = [row["curated_from"] for row in guide if row.get("curated_from")]
        if not locators and guide:
            raise ValueError("a curated guide must identify the source it was curated from")
        return _source(name, "curated practice table", source_version, locators,
            {"guide": guide, "table_version": tables.version,
             "primary_reads": [asdict(row) if isinstance(row, EvidenceResult) else row
                               for row in sources]} if guide else {},
            primary_reads=tuple(row for row in sources if isinstance(row, EvidenceResult)),
            reason="Curated guidance is navigation; primary applicability/support "
                "is not yet verified.")

    def read_primary(act, provision, as_of):
        if as_of is None:
            return {"act": act, "provision": provision, "coverage": "not_assessed",
                    "missing": "The governing date is not established."}
        return evidence.read_provision(act, provision, _date(as_of))

    def pre_institution(args, _context):
        if tables is None or tables.institution is None:
            return table_unavailable("pre_institution_steps")
        cause, against = CauseOfAction(args["cause"]), Against(args["against"])
        curation = tables.institution.coverage(cause)
        if curation is not Curation.CURATED:
            return table_result("pre_institution_steps", curation, [])
        engaged = tables.institution.engaged(cause, against)
        undecided = tables.institution.undecided(cause, against)
        guide = [{**asdict(row.condition), "engagement": row.why} for row in engaged]
        guide += [{**asdict(row), "engagement": "The opponent status is not established."}
                  for row in undecided]
        return table_result("pre_institution_steps", curation, guide,
            [read_primary(row["act"], row["provision"], args["as_of"]) for row in guide])

    def interim(args, _context):
        if tables is None or tables.interim is None:
            return table_unavailable("interim_test")
        relief = InterimRelief(args["relief"])
        curation = tables.interim.coverage(relief)
        test = tables.interim.test_for(relief) if curation is Curation.CURATED else None
        return table_result("interim_test", curation, [asdict(test)] if test else [])

    def procedural(args, _context):
        if tables is None or tables.procedural is None:
            return table_unavailable("procedural_periods")
        role, track = Role(args["role"]), Track(args["track"])
        curation = tables.procedural.coverage(role)
        if curation is not Curation.CURATED:
            return table_result("procedural_periods", curation, [])
        engaged = tables.procedural.engaged(role, track)
        undecided = tables.procedural.undecided(role, track)
        guide = [{**asdict(row.period), "engagement": row.why} for row in engaged]
        guide += [{**asdict(row), "engagement": "The track is not established."}
                  for row in undecided]
        return table_result("procedural_periods", curation, guide,
            [read_primary(row["act"], row["provision"], args["as_of"]) for row in guide])

    def governing(args, _context):
        if tables is None or tables.governing is None:
            return table_unavailable("governing_code")
        limb = Limb(args["limb"])
        curation = tables.governing.coverage(limb)
        result = tables.governing.governing(limb,
            _date(args["on"]) if args["on"] else None, Pending(args["pending"]))
        guide = ([{**asdict(result), "curated_from": result.rule.curated_from}]
                 if result.rule is not None else [])
        return table_result("governing_code", curation, guide)

    def elements(args, _context):
        if tables is None or tables.elements is None:
            return table_unavailable("elements_of")
        cause = CauseOfAction(args["cause"])
        curation = tables.elements.coverage(cause)
        result = tables.elements.elements_for(cause) if curation is Curation.CURATED else None
        return table_result("elements_of", curation, [asdict(result)] if result else [])

    def filing(args, _context):
        if tables is None or tables.filing is None:
            return table_unavailable("filing_requirements")
        requirement = Requirement(args["requirement"])
        readiness = tables.filing.readiness(requirement)
        # Readiness is itself an answer about availability, not the fee/forum.
        return _source("filing_requirements", "versioned filing-source readiness",
            tables.version, (f"filing-requirement:{requirement.value}",), asdict(readiness),
            partial=not readiness.computable,
            reason=readiness.why or
                "Source readiness alone does not calculate a filing requirement.")

    def court_fee(_args, _context):
        readiness = tables.filing.readiness(Requirement.COURT_FEES) if (
            tables is not None and tables.filing is not None) else None
        reason = (readiness.why or "The versioned court-fee computation rule is not configured."
                  if readiness else "The court-fee source readiness reader is not configured.")
        return ToolEnvelope("court_fee", VERSION, ToolKind.COMPUTATION, ToolOutcome.FAILED,
            Availability.UNAVAILABLE, Assessment.NOT_ASSESSED,
            {"inputs": {}, "method": "FilingRequirementPort.readiness; no fee arithmetic",
             "input_receipts": [asdict(readiness)] if readiness else []}, {}, reason)

    rows = (
        ("read_thread", "Read one exact recorded dispute and the shared derived checklist, "
         "including due follow-ups without treating them as legal deadlines.",
         {"thread_id": _STRING}, ToolKind.MATTER, read_thread),
        ("read_facts", "Read recorded facts with their actual words and status.", {},
         ToolKind.MATTER, read_facts),
        ("read_turn", "Read an exact committed turn after compaction, not an unserved draft.",
         {"turn_id": _STRING}, ToolKind.MATTER, read_turn),
        ("search_matter", "Search recorded file text; upload-index absence stays explicit.",
         {"query": _STRING, "limit": _LIMIT}, ToolKind.MATTER, search_matter),
        ("list_deadlines", "Read the recorded register with incomplete entries disclosed.",
         {"as_of": _STRING}, ToolKind.MATTER, list_deadlines),
        ("resolve_citation", "Resolve only an exact reporter key; never offer a guessed case.",
         {"citation": _STRING}, ToolKind.SOURCE, resolve),
        ("search_authorities", "Search grouped cases; ranking is never exact case identity.",
         {"query": _STRING, "court": {"type": ["string", "null"]},
          "from_year": {"type": ["integer", "null"], "minimum": 1, "maximum": 9999},
          "to_year": {"type": ["integer", "null"], "minimum": 1, "maximum": 9999},
          "limit": _LIMIT}, ToolKind.SOURCE, discover),
        ("read_paragraph", "Read a paragraph by exact locator, preserving its attribution.",
         {"locator": _STRING}, ToolKind.SOURCE, paragraph),
        ("read_judgment", "Read a bounded index window, showing continuation and exclusions.",
         {"case_id": _STRING, "query": {"type": ["string", "null"]}, "limit": _LIMIT,
          "after": {"type": ["string", "null"]}}, ToolKind.SOURCE, judgment),
        ("read_source_document", "Read a held corpus document window without a path or URL.",
         {"locator": _STRING, "kind": _enum(SourceKind),
          "start": {"type": "integer", "minimum": 0}, "count": _LIMIT},
         ToolKind.SOURCE, source_document),
        ("treatment", "Read later treatment for an exact held case, preserving unchecked scope.",
         {"case_id": _STRING}, ToolKind.SOURCE, treatment),
        ("rank_authorities", "Ask the existing court/bench owner, never rank by model preference.",
         {"locators": {"type": "array", "items": _STRING, "minItems": 1, "maxItems": 20}},
         ToolKind.SOURCE, weight),
        ("date_arithmetic", "Calendar arithmetic only; no unheld holiday or legal rule.",
         {"on": _STRING, "amount": {"type": "integer", "minimum": -100000,
          "maximum": 100000}, "unit": {"type": "string", "enum": ["years", "months", "days"]}},
         ToolKind.COMPUTATION, date_arithmetic),
        ("pre_institution_steps", "Read curated conditions and their primary provisions.",
         {"cause": _enum(CauseOfAction), "against": _enum(Against), "as_of": _NULLABLE_DATE},
         ToolKind.SOURCE, pre_institution),
        ("interim_test", "Read the exact curated relief test; an uncurated relief is not borrowed.",
         {"relief": _enum(InterimRelief)}, ToolKind.SOURCE, interim),
        ("procedural_periods", "Read curated clocks and primary text for the exact role/track.",
         {"role": _enum(Role), "track": _enum(Track), "as_of": _NULLABLE_DATE},
         ToolKind.SOURCE, procedural),
        ("governing_code", "Consult the existing succession owner; unknown premises stay unknown.",
         {"limb": _enum(Limb), "on": _NULLABLE_DATE, "pending": _enum(Pending)},
         ToolKind.SOURCE, governing),
        ("elements_of", "Read the curated element list and source, not remembered elements.",
         {"cause": _enum(CauseOfAction)}, ToolKind.SOURCE, elements),
        ("filing_requirements", "Measure whether the specific forum/valuation/fee source is held.",
         {"requirement": _enum(Requirement)}, ToolKind.SOURCE, filing),
        ("court_fee", "Name the missing versioned fee rule; never estimate a fee.", {},
         ToolKind.COMPUTATION, court_fee),
    )
    if matter_documents is not None:
        rows += (("quote_matter",
            "Quote an exact owned admitted-document version and original text span.",
            {"original_id": _STRING, "asset_version": {"type": "integer", "minimum": 1},
             "source_sha256": _STRING,
             "derivative_sha256": _STRING,
             "number": {"type": "integer", "minimum": 1},
             "location_kind": {"type": "string", "enum": ["page", "part"]},
             "part": _STRING, "start": {"type": "integer", "minimum": 0},
             "end": {"type": "integer", "minimum": 1}}, ToolKind.MATTER, quote_matter),)
    return tuple(RegisteredTool(ToolDefinition(name, description, object_schema(properties)),
        kind, VERSION, True, _CONTROLS, handler)
        for name, description, properties, kind, handler in rows)
