# Legal brain

One flat folder for understanding, research, critical assessment, verification
and communication. This is the code ownership map, not a claim of expert-quality
acceptance. Before Build and current tests/evaluations still govern that claim.

## Read in this order

| Review question | Current files |
|---|---|
| How is the latest message understood without forcing intake? | [route.py](route.py), [brain_context.py](brain_context.py), [conversation.py](conversation.py), [conversational_proposal.py](conversational_proposal.py) |
| What may the reasoning system do, and how does it iterate? | [controlled_brain.py](controlled_brain.py), [lead.py](lead.py), [loop.py](loop.py), [delegation.py](delegation.py), [nested_research.py](nested_research.py) |
| Where do legal sources come from? | [corpus_evidence.py](corpus_evidence.py), [search_authority.py](search_authority.py), [identity_sources.py](identity_sources.py), [resolution_sources.py](resolution_sources.py), [provision_revision_sources.py](provision_revision_sources.py) |
| How are distinct disputes, weaknesses and possibilities assessed? | [dispute.py](dispute.py), [threading.py](threading.py), [proof.py](proof.py), [theory.py](theory.py), [adversarial.py](adversarial.py), [limitation.py](limitation.py), [requirements.py](requirements.py) |
| What prevents unsupported publication? | [grounding.py](grounding.py), [verifier.py](verifier.py), [output_checks.py](output_checks.py), [interaction_review.py](interaction_review.py), [brain_assessment.py](brain_assessment.py), [brain_finalization.py](brain_finalization.py), [brain_publication.py](brain_publication.py) |
| How are communication and prompt obligations kept consistent? | [principles_generated.py](principles_generated.py), [register_contracts.py](register_contracts.py), [working_explanation.py](working_explanation.py), [preview_display.py](preview_display.py) |
| How does state stay current and reviewable? | [work_receipts.py](work_receipts.py), [checked_input_continuation.py](checked_input_continuation.py), [controlled_generations.py](controlled_generations.py), [runtime_capture.py](runtime_capture.py), [strict_replay.py](strict_replay.py) |
| How do model tools get permission? | [tools.py](tools.py), [controlled_registry_composition.py](controlled_registry_composition.py), [tool_offers.py](tool_offers.py), [tool_discovery.py](tool_discovery.py), and the individual `tool_<registered_name>.py` files |
| What does the advocate see? | [matter-workspace.js](matter-workspace.js), [matter-workspace.css](matter-workspace.css), [source-reader.js](source-reader.js), [loop-progress.js](loop-progress.js), [brain-preview.js](brain-preview.js) |

The legacy turn path remains [turn.py](turn.py). A folder move does not enable the
controlled brain for all client matters, renew an evaluation approval, or replace
the existing configuration/policy admission.

## One owner, not copies

Principles are authored in [LEGAL_BRAIN_PRINCIPLES.md](../../docs/blueprint/LEGAL_BRAIN_PRINCIPLES.md)
and generated into `principles_generated.py`; do not independently edit two rule
sets. Contracts, native source interpreters, adapters and tool doors remain
distinct architectural roles even though they share this folder.

Tool files contain the actual entry point, not a renamed alias with all the real
logic hidden in a second registry. Shared business services stay in their existing
single owners. Parent and child tool scopes, metadata, grounding and permission
checks are unchanged by file organisation; child finish tools do not become lead
tools. The complete installed registry depends on its admitted configuration.

Case facts, corrections, checklist answers and deadlines are jointly owned with
[Work the file](../work_the_file/README.md); recommendations with
[Advise](../advise/README.md); provider/storage/security boundaries with
[Shared](../shared/README.md). HTTP composition stays in [App](../app/README.md).

## Complete source index

The index below is navigation over current physical files, not verification.

### Reasoning services and orchestration

- [accrual.py](accrual.py)
- [adversarial.py](adversarial.py)
- [advocate_memory.py](advocate_memory.py)
- [brain_assessment.py](brain_assessment.py)
- [brain_context.py](brain_context.py)
- [brain_evaluation.py](brain_evaluation.py)
- [brain_finalization.py](brain_finalization.py)
- [brain_publication.py](brain_publication.py)
- [brain_release.py](brain_release.py)
- [briefing.py](briefing.py)
- [calculation_tools.py](calculation_tools.py)
- [cause.py](cause.py)
- [ceiling.py](ceiling.py)
- [checked_input_continuation.py](checked_input_continuation.py)
- [checklist_review.py](checklist_review.py)
- [consistency.py](consistency.py)
- [controlled_brain.py](controlled_brain.py)
- [conversation.py](conversation.py)
- [conversational_proposal.py](conversational_proposal.py)
- [delegation.py](delegation.py)
- [dispute.py](dispute.py)
- [duty.py](duty.py)
- [early_independent_review.py](early_independent_review.py)
- [evaluation_history.py](evaluation_history.py)
- [event_limitation_calculation.py](event_limitation_calculation.py)
- [factors.py](factors.py)
- [gaps.py](gaps.py)
- [grounded_file_tools.py](grounded_file_tools.py)
- [grounding.py](grounding.py)
- [interaction_review.py](interaction_review.py)
- [interaction_subject.py](interaction_subject.py)
- [investigation.py](investigation.py)
- [issues.py](issues.py)
- [lead.py](lead.py)
- [limitation.py](limitation.py)
- [loop.py](loop.py)
- [loop_progress.py](loop_progress.py)
- [matter_support.py](matter_support.py)
- [nested_research.py](nested_research.py)
- [opposition_work.py](opposition_work.py)
- [output_checks.py](output_checks.py)
- [parties.py](parties.py)
- [posture.py](posture.py)
- [practice_playbooks.py](practice_playbooks.py)
- [premise.py](premise.py)
- [preview_display.py](preview_display.py)
- [preview_seen.py](preview_seen.py)
- [principles_generated.py](principles_generated.py)
- [procedural_calculation.py](procedural_calculation.py)
- [proof.py](proof.py)
- [proof_read.py](proof_read.py)
- [recorded_package_subject.py](recorded_package_subject.py)
- [requirements.py](requirements.py)
- [research.py](research.py)
- [research_context.py](research_context.py)
- [reviewed_fee_selection.py](reviewed_fee_selection.py)
- [reviewed_interest_selection.py](reviewed_interest_selection.py)
- [reviewed_limitation_selection.py](reviewed_limitation_selection.py)
- [reviewed_preview.py](reviewed_preview.py)
- [route.py](route.py)
- [source_excerpt.py](source_excerpt.py)
- [source_writes.py](source_writes.py)
- [step_dependency.py](step_dependency.py)
- [theory.py](theory.py)
- [threading.py](threading.py)
- [thresholds.py](thresholds.py)
- [tool_catalogue.py](tool_catalogue.py)
- [tool_discovery.py](tool_discovery.py)
- [tool_offers.py](tool_offers.py)
- [tool_sources.py](tool_sources.py)
- [tools.py](tools.py)
- [turn.py](turn.py)
- [verifier.py](verifier.py)
- [work_receipts.py](work_receipts.py)
- [working_explanation.py](working_explanation.py)
- [working_record.py](working_record.py)
- [working_scope.py](working_scope.py)

### Domain contracts and package

- [__init__.py](__init__.py)
- [advocate_memory_contracts.py](advocate_memory_contracts.py)
- [citation_contracts.py](citation_contracts.py)
- [coverage_contracts.py](coverage_contracts.py)
- [curation_contracts.py](curation_contracts.py)
- [delegation_contracts.py](delegation_contracts.py)
- [fee_calculation_contracts.py](fee_calculation_contracts.py)
- [interest_calculation_contracts.py](interest_calculation_contracts.py)
- [issue_contracts.py](issue_contracts.py)
- [lead_contracts.py](lead_contracts.py)
- [loop_contracts.py](loop_contracts.py)
- [proof_contracts.py](proof_contracts.py)
- [quotable_contracts.py](quotable_contracts.py)
- [reads_contracts.py](reads_contracts.py)
- [register_contracts.py](register_contracts.py)
- [replay_capture_contracts.py](replay_capture_contracts.py)
- [requirements_contracts.py](requirements_contracts.py)
- [source_excerpt_contracts.py](source_excerpt_contracts.py)
- [tiers_contracts.py](tiers_contracts.py)
- [working_record_contracts.py](working_record_contracts.py)

### Port contracts

- [authority_weight_port.py](authority_weight_port.py)
- [coverage_port.py](coverage_port.py)
- [elements_port.py](elements_port.py)
- [evidence_port.py](evidence_port.py)
- [filing_requirement_port.py](filing_requirement_port.py)
- [generations_port.py](generations_port.py)
- [governing_law_port.py](governing_law_port.py)
- [institution_port.py](institution_port.py)
- [interim_relief_port.py](interim_relief_port.py)
- [loop_log_port.py](loop_log_port.py)
- [practice_playbooks_port.py](practice_playbooks_port.py)
- [principles_port.py](principles_port.py)
- [procedural_period_port.py](procedural_period_port.py)
- [search_port.py](search_port.py)

### Native knowledge-source owners

- [acquisition_sources.py](acquisition_sources.py)
- [artefact_sources.py](artefact_sources.py)
- [authority_weight_sources.py](authority_weight_sources.py)
- [citator_sources.py](citator_sources.py)
- [coverage_sources.py](coverage_sources.py)
- [elements_sources.py](elements_sources.py)
- [filing_requirement_sources.py](filing_requirement_sources.py)
- [governing_law_sources.py](governing_law_sources.py)
- [identity_sources.py](identity_sources.py)
- [institution_sources.py](institution_sources.py)
- [interim_relief_sources.py](interim_relief_sources.py)
- [jurisdiction_sources.py](jurisdiction_sources.py)
- [manifest_sources.py](manifest_sources.py)
- [procedural_period_sources.py](procedural_period_sources.py)
- [provenance_sources.py](provenance_sources.py)
- [provision_revision_sources.py](provision_revision_sources.py)
- [resolution_sources.py](resolution_sources.py)
- [source_registry_sources.py](source_registry_sources.py)

### Concrete source adapters

- [authority_weight_adapter.py](authority_weight_adapter.py)
- [corpus_evidence.py](corpus_evidence.py)
- [elements_adapter.py](elements_adapter.py)
- [filing_requirement_adapter.py](filing_requirement_adapter.py)
- [governing_law_adapter.py](governing_law_adapter.py)
- [institution_adapter.py](institution_adapter.py)
- [interim_relief_adapter.py](interim_relief_adapter.py)
- [practice_playbooks_adapter.py](practice_playbooks_adapter.py)
- [principles_file_adapter.py](principles_file_adapter.py)
- [procedural_period_adapter.py](procedural_period_adapter.py)
- [search_authority.py](search_authority.py)
- [search_policed.py](search_policed.py)

### Composition, replay and generation boundaries

- [checklist_sources.py](checklist_sources.py)
- [controlled_evaluations_composition.py](controlled_evaluations_composition.py)
- [controlled_generations.py](controlled_generations.py)
- [controlled_registry_composition.py](controlled_registry_composition.py)
- [dated_provisions.py](dated_provisions.py)
- [evaluation_models.py](evaluation_models.py)
- [provision_registry_composition.py](provision_registry_composition.py)
- [provision_review.py](provision_review.py)
- [replay_context.py](replay_context.py)
- [runtime_capture.py](runtime_capture.py)
- [runtime_model_tape.py](runtime_model_tape.py)
- [runtime_port_tape.py](runtime_port_tape.py)
- [strict_replay.py](strict_replay.py)

### HTTP entry points

- [advocate_memory_routes_api.py](advocate_memory_routes_api.py)
- [brain_preview_api.py](brain_preview_api.py)
- [loop_progress_api.py](loop_progress_api.py)
- [preview_seen_api.py](preview_seen_api.py)
- [reviewed_preview_api.py](reviewed_preview_api.py)

### Actual model tool doors, including child-only finish scopes

- [tool_ask_advocate.py](tool_ask_advocate.py)
- [tool_check_candidate_independently.py](tool_check_candidate_independently.py)
- [tool_compute_interest.py](tool_compute_interest.py)
- [tool_compute_limitation.py](tool_compute_limitation.py)
- [tool_compute_procedural_period.py](tool_compute_procedural_period.py)
- [tool_court_fee.py](tool_court_fee.py)
- [tool_date_arithmetic.py](tool_date_arithmetic.py)
- [tool_discover_tools.py](tool_discover_tools.py)
- [tool_elements_of.py](tool_elements_of.py)
- [tool_filing_requirements.py](tool_filing_requirements.py)
- [tool_finish_opposition.py](tool_finish_opposition.py)
- [tool_finish_research.py](tool_finish_research.py)
- [tool_governing_code.py](tool_governing_code.py)
- [tool_identify_act.py](tool_identify_act.py)
- [tool_inspect_tool.py](tool_inspect_tool.py)
- [tool_interim_test.py](tool_interim_test.py)
- [tool_list_deadlines.py](tool_list_deadlines.py)
- [tool_oppose.py](tool_oppose.py)
- [tool_oppose_early.py](tool_oppose_early.py)
- [tool_oppose_full.py](tool_oppose_full.py)
- [tool_oppose_matter.py](tool_oppose_matter.py)
- [tool_pre_institution_steps.py](tool_pre_institution_steps.py)
- [tool_procedural_periods.py](tool_procedural_periods.py)
- [tool_propose_conversation.py](tool_propose_conversation.py)
- [tool_propose_fee_selection.py](tool_propose_fee_selection.py)
- [tool_propose_interest_selection.py](tool_propose_interest_selection.py)
- [tool_propose_limitation_selection.py](tool_propose_limitation_selection.py)
- [tool_propose_working_record.py](tool_propose_working_record.py)
- [tool_quote_matter.py](tool_quote_matter.py)
- [tool_rank_authorities.py](tool_rank_authorities.py)
- [tool_read_facts.py](tool_read_facts.py)
- [tool_read_fee_inventory.py](tool_read_fee_inventory.py)
- [tool_read_interest_inventory.py](tool_read_interest_inventory.py)
- [tool_read_judgment.py](tool_read_judgment.py)
- [tool_read_limitation_candidates.py](tool_read_limitation_candidates.py)
- [tool_read_matter.py](tool_read_matter.py)
- [tool_read_opposition_status.py](tool_read_opposition_status.py)
- [tool_read_owner_guide.py](tool_read_owner_guide.py)
- [tool_read_paragraph.py](tool_read_paragraph.py)
- [tool_read_playbook_catalogue.py](tool_read_playbook_catalogue.py)
- [tool_read_practice_playbook.py](tool_read_practice_playbook.py)
- [tool_read_procedural_calculation_inputs.py](tool_read_procedural_calculation_inputs.py)
- [tool_read_provision.py](tool_read_provision.py)
- [tool_read_source_document.py](tool_read_source_document.py)
- [tool_read_thread.py](tool_read_thread.py)
- [tool_read_turn.py](tool_read_turn.py)
- [tool_read_working_inventory.py](tool_read_working_inventory.py)
- [tool_record_grounded_file_reading.py](tool_record_grounded_file_reading.py)
- [tool_record_requirements.py](tool_record_requirements.py)
- [tool_research.py](tool_research.py)
- [tool_resolve_citation.py](tool_resolve_citation.py)
- [tool_search_authorities.py](tool_search_authorities.py)
- [tool_search_authority.py](tool_search_authority.py)
- [tool_search_matter.py](tool_search_matter.py)
- [tool_submit_answer.py](tool_submit_answer.py)
- [tool_treatment.py](tool_treatment.py)

### Browser assets

- [brain-preview.html](brain-preview.html)
- [brain-preview.js](brain-preview.js)
- [source-reader.js](source-reader.js)
- [loop-progress.js](loop-progress.js)
- [matter-workspace.css](matter-workspace.css)
- [matter-workspace.js](matter-workspace.js)
- [advocate-preferences.js](advocate-preferences.js)
