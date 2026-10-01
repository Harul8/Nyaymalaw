"""One actual controlled tool assembly for the application and isolated replay.

This factory installs the existing handlers, not a copied tool-name population
or a saved ToolEnvelope reader. All source, permission, store and clock owners
are explicit. Supplying these ports does not certify a complete replay capture
or approve advice; missing ports retain their existing unassessed behavior.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from nm.act.action_proposal_tool import action_proposal_tools
from nm.Archives.legal_brain.common.principles_port import PrinciplesPort
from nm.Archives.legal_brain.orchestrate.generations_port import GenerationUnavailable
from nm.Archives.legal_brain.orchestrate.nested_research import ResearchDispatcher
from nm.Archives.legal_brain.orchestrate.tool_catalogue import PracticeTables
from nm.Archives.legal_brain.orchestrate.tool_discovery import discovery_tools
from nm.Archives.legal_brain.orchestrate.tools import (
    Boundary,
    DelegationPolicy,
    ToolContext,
    ToolRegistry,
    foundation_tools,
)
from nm.Archives.legal_brain.procedure.calculation_tools import calculation_tools
from nm.Archives.legal_brain.procedure.procedural_calculation import procedural_calculation_tools
from nm.Archives.legal_brain.procedure.reviewed_fee_selection import (
    FeeSelectionOwner,
    FeeSelectionReviewService,
    fee_tools,
)
from nm.Archives.legal_brain.procedure.reviewed_interest_selection import (
    InterestSelectionOwner,
    InterestSelectionReviewService,
    interest_tools,
)
from nm.Archives.legal_brain.procedure.reviewed_limitation_selection import (
    limitation_selection_tools,
    resolve_limitation_inputs,
)
from nm.Archives.legal_brain.reason.grounded_file_tools import grounded_file_tools
from nm.Archives.legal_brain.reason.opposition_work import opposition_status_tool
from nm.Archives.legal_brain.reason.source_writes import source_write_tools
from nm.Archives.legal_brain.reason.working_record import WorkingRecordOwner, working_record_tools
from nm.Archives.legal_brain.retrieve.authority_weight_port import AuthorityWeightPort
from nm.Archives.legal_brain.retrieve.dated_provisions import dated_provision_reader
from nm.Archives.legal_brain.retrieve.evidence_port import EvidencePort
from nm.Archives.legal_brain.retrieve.manifest_sources import Manifest
from nm.Archives.legal_brain.retrieve.practice_playbooks import playbook_tools
from nm.Archives.legal_brain.retrieve.practice_playbooks_port import PlaybooksSnapshot, PracticePlaybooksPort
from nm.Archives.legal_brain.retrieve.provision_search_port import ProvisionSearchPort
from nm.Archives.legal_brain.retrieve.search_port import CorpusSearchPort
from nm.open_matter.matter_documents_port import MatterDocumentsPort
from nm.shared.authority_contracts import Act
from nm.shared.clock_contracts import today as forum_today
from nm.shared.model_port import ModelPort, Tier
from nm.shared.store_port import StorePort
from nm.work_the_file.deadline_proposals import deadline_proposal_tools
from nm.work_the_file.private_file_tools import private_file_tools
from nm.work_the_file.write_tools import write_tools

RESEARCH_POLICY = DelegationPolicy(max_steps=12, max_tokens=24000, max_cost_usd=0.25, max_ms=60000)
EARLY_REVIEW_POLICY = DelegationPolicy(
    max_steps=1, max_tokens=24000, max_cost_usd=0.25, max_ms=60000
)


@dataclass(frozen=True)
class ControlledRegistryPorts:
    """Actual native ports, never caller-authored currentness or approval flags."""

    evidence: EvidencePort
    manifest: Manifest
    search: CorpusSearchPort | None
    tables: PracticeTables
    authority_weight: AuthorityWeightPort | None
    matter_documents: MatterDocumentsPort | None
    model: ModelPort
    principles: PrinciplesPort
    playbooks: PracticePlaybooksPort
    playbook_snapshot: PlaybooksSnapshot

    def __post_init__(self):
        if (
            not isinstance(self.manifest, Manifest)
            or not isinstance(self.tables, PracticeTables)
            or not isinstance(self.playbook_snapshot, PlaybooksSnapshot)
            or not callable(getattr(self.evidence, "read_provision", None))
            or not callable(getattr(self.principles, "load", None))
            or not callable(getattr(self.playbooks, "load", None))
            or not callable(getattr(self.model, "tool_call", None))
        ):
            raise ValueError("The controlled registry needs its explicit actual port owners")


@dataclass
class ControlledRegistryAssembly:
    """Late independent work extends this same registry and dynamic discovery."""

    registry: ToolRegistry
    working_owner: WorkingRecordOwner
    interest_owner: InterestSelectionOwner
    interest_reviews: InterestSelectionReviewService | None
    fee_owner: FeeSelectionOwner
    fee_reviews: FeeSelectionReviewService | None
    research: ResearchDispatcher
    permission_owner: object | None = None

    def install_early(self, service):
        from nm.Archives.legal_brain.verify.early_independent_review import EarlyIndependentReviewService

        if not isinstance(service, EarlyIndependentReviewService):
            raise ValueError("Early tools come only from the actual independent owner")
        self.registry = self.registry.extend(service.tools(EARLY_REVIEW_POLICY))
        if self.permission_owner is not None:
            self.permission_owner.registry = self.registry


def assemble_controlled_registry(
    *,
    store: StorePort,
    ports: ControlledRegistryPorts,
    boundary: Callable[[ToolContext, Act], Boundary],
    generations,
    source_version: str,
    source_current,
    window_current,
    cost_ceiling,
    reviewer=None,
    permission_owner=None,
    today=forum_today,
    monotonic=time.monotonic,
) -> ControlledRegistryAssembly:
    """Reuse all actual handlers; the application retains admission and review.

    The frozen worker must supply cloned storage and captured typed port owners,
    not an arbitrary tool list. A complete successful capture is a separate
    requirement: this factory cannot make an incomplete tape replayable.
    """
    from nm.Archives.legal_brain.evaluate.strict_replay import PermissionTape
    from nm.Archives.legal_brain.orchestrate.tool_catalogue import catalogue_tools

    if (
        not isinstance(ports, ControlledRegistryPorts)
        or not callable(boundary)
        or not callable(source_current)
        or not callable(window_current)
        or not callable(cost_ceiling)
        or not callable(today)
        or not callable(monotonic)
        or not callable(getattr(generations, "require_current", None))
        or type(getattr(generations, "version", None)) is not str
        or not generations.version.strip()
        or type(source_version) is not str
        or not source_version.strip()
    ):
        raise ValueError(
            "Actual bounded source, permission, generation and clock owners are required"
        )
    if reviewer is not None and reviewer.store is not store:
        raise ValueError("Independent review must share this exact transactional matter store")
    if permission_owner is not None and (
        not isinstance(permission_owner, PermissionTape)
        or permission_owner.store is not store
        or permission_owner.generation != source_version
    ):
        raise ValueError("Captured permissions need their actual typed clone and source owner")

    def current_registry():
        # Invocations happen only after the complete assembly is returned.
        # Late early-review tools must remain visible to both discovery and
        # the native required-act boundary; no stale local registry is used.
        return assembly.registry

    def before(name, _arguments, context):
        if permission_owner is not None:
            return permission_owner.before(name, _arguments, context)
        return boundary(context, current_registry().authority_for(name))

    def after(receipt, context):
        if permission_owner is not None:
            return permission_owner.after(receipt, context)
        return boundary(context, current_registry().authority_for(receipt.tool))

    registry = foundation_tools(
        store,
        ports.evidence,
        manifest=ports.manifest,
        source_version=source_version,
        dated_provision_reader=dated_provision_reader(
            ports.evidence, source_generation=source_version
        ),
        before=before,
        after=after,
    )
    catalogue_population = catalogue_tools(
        store,
        ports.evidence,
        source_version=source_version,
        search=ports.search,
        provision_search=(ports.evidence if isinstance(ports.evidence, ProvisionSearchPort)
                          else None),
        tables=ports.tables,
        authority_weight=ports.authority_weight,
        matter_documents=ports.matter_documents,
        source_current=source_current,
        today=today,
    )
    registry = registry.extend(
        tuple(row for row in catalogue_population if row.definition.name != "court_fee"),
        versions={"practice_tables": ports.tables.version},
    )
    registry = registry.extend(write_tools(store, today=today))
    registry = registry.extend(grounded_file_tools(store, today=today))
    registry = registry.extend(source_write_tools(store, source_version=source_version))
    registry = registry.extend(
        private_file_tools(
            store, source_generation=source_version, source_current=source_current, today=today
        )
    )
    registry = registry.extend(action_proposal_tools(store))

    def current_source_version():
        try:
            generations.require_current()
        except GenerationUnavailable:
            return "generation_not_current"
        return source_version

    registry = registry.extend(
        limitation_selection_tools(
            store, source_generation=source_version, source_current=source_current
        )
    )
    calculation_population = calculation_tools(
        store,
        source_version=source_version,
        event_selections=True,
        current_source_version=current_source_version,
        source_current=source_current,
        resolve=lambda matter, thread, context: resolve_limitation_inputs(
            matter,
            thread,
            context,
            source_generation=source_version,
            source_current=source_current,
        ),
    )
    registry = registry.extend(
        tuple(row for row in calculation_population if row.definition.name != "compute_interest")
    )
    registry = registry.extend(
        playbook_tools(
            ports.playbooks,
            snapshot=ports.playbook_snapshot,
            evidence=ports.evidence,
            search=ports.search,
        ),
        versions={"owner_playbooks": ports.playbook_snapshot.version},
    )
    working_owner = WorkingRecordOwner(source_current=source_current, window_current=window_current)
    registry = registry.extend(working_record_tools(store, owner=working_owner))
    registry = registry.extend(
        procedural_calculation_tools(
            store,
            owner=working_owner,
            source_generation=source_version,
            current_source_generation=current_source_version,
        )
    )
    registry = registry.extend(
        deadline_proposal_tools(
            store,
            owner=working_owner,
            source_generation=source_version,
            current_source_generation=current_source_version,
            today=today,
        )
    )
    interest_owner = InterestSelectionOwner(source_owner=working_owner)
    interest_reviews = (
        InterestSelectionReviewService(reviewer=reviewer, owner=interest_owner)
        if reviewer is not None
        else None
    )
    registry = registry.extend(
        interest_tools(store, owner=interest_owner, reviews=interest_reviews)
    )
    fee_owner = FeeSelectionOwner(source_owner=working_owner)
    fee_reviews = (
        FeeSelectionReviewService(reviewer=reviewer, owner=fee_owner)
        if reviewer is not None
        else None
    )
    registry = registry.extend(fee_tools(store, owner=fee_owner, reviews=fee_reviews))
    registry = registry.extend(
        (
            opposition_status_tool(
                store=store,
                provider=lambda: ports.model.provider,
                model=lambda: ports.model.resolved_model(Tier.ROUTINE),
            ),
        )
    )
    # Preserve the existing child reading subset: no writes/terminal tools,
    # and never recursive delegation. Its grant is the actual parent's spend.
    research = ResearchDispatcher(
        store=store,
        model=ports.model,
        principles=ports.principles,
        registry=registry,
        cost_ceiling=cost_ceiling,
        monotonic=monotonic,
    )
    registry = registry.extend(research.tools(RESEARCH_POLICY))
    registry = registry.extend(discovery_tools(current_registry, ports.principles))
    registry = registry.extend((), versions={"actual_generation_binding": generations.version})
    assembly = ControlledRegistryAssembly(
        registry,
        working_owner,
        interest_owner,
        interest_reviews,
        fee_owner,
        fee_reviews,
        research,
        permission_owner,
    )
    if permission_owner is not None:
        permission_owner.registry = registry
    return assembly
