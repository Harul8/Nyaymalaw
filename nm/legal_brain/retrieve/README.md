# 03.02 — Retrieve and inspect sources

Find and read held Acts, judgments and practice material; retain exact source identity, passages, dates, binding relationships, treatment and coverage limitations. Search ranking is not identification or legal support.

This is a responsibility within the legal-brain loop, not a mandatory execution
stage or a claim of complete feature acceptance. Files inside this folder stay flat.

## Read first

- [corpus_evidence.py](corpus_evidence.py)
- [search_authority.py](search_authority.py)
- [research.py](research.py)
- [identity_sources.py](identity_sources.py)
- [tool_sources.py](tool_sources.py)

## Boundaries

Use native source owners and admitted ports. Missing sources, unreadable stores and unassessed treatment remain visible. Child-only finish_research stays in its existing child scope; moving it here does not register it as a lead tool. Reading a playbook or provision does not issue a legal review.

Architectural roles and dependency directions remain explicit in
[`nm/source_layout.json`](../../source_layout.json). No new tool permission,
provider-processing approval or release claim comes from moving a file.

## Complete file index

Navigation over 48 implementation files, 0 browser assets and
the package initializer; this is not test evidence.

### Implementation

- [acquisition_sources.py](acquisition_sources.py) — Explainable judgment acquisition and immutable quarantine receipts.
- [artefact_sources.py](artefact_sources.py) — Binds indexes and derived artefacts to their exact source generation.
- [authority_weight_adapter.py](authority_weight_adapter.py) — Relative authority weight, served through the port.
- [authority_weight_port.py](authority_weight_port.py) — Types comparisons between authorities and their binding weight.
- [authority_weight_sources.py](authority_weight_sources.py) — Ranks retrieved authorities using the existing hierarchy owner.
- [checklist_sources.py](checklist_sources.py) — Recheck cached checklist law through the actual source owner, without a model call.
- [citator_sources.py](citator_sources.py) — Subsequent treatment, and an honest account of how little it covers.
- [corpus_evidence.py](corpus_evidence.py) — Retrieves source-grounded findings from the held legal corpus.
- [coverage_contracts.py](coverage_contracts.py) — Types held-corpus coverage separately from legal applicability.
- [coverage_port.py](coverage_port.py) — Asks what the corpus holds for the jurisdiction at turn time.
- [coverage_sources.py](coverage_sources.py) — What the corpus holds for a jurisdiction -- read at turn time.
- [dated_provisions.py](dated_provisions.py) — Bind the actual dated adapter to core capture without leaking adapter types.
- [evidence_port.py](evidence_port.py) — Returns typed legal findings rather than unclassified chunks.
- [identity_sources.py](identity_sources.py) — Case identity recovered from the source judgments, and what it makes decidable.
- [investigation.py](investigation.py) — Runs bounded judgment searches proposed by a model and admitted by code.
- [jurisdiction_sources.py](jurisdiction_sources.py) — Determines a source's binding status for the recorded jurisdiction.
- [manifest_sources.py](manifest_sources.py) — Reads curated intended corpus coverage from the manifest.
- [practice_playbooks_adapter.py](practice_playbooks_adapter.py) — Bounded local owner file; no cache, model writes or source acquisition.
- [practice_playbooks_port.py](practice_playbooks_port.py) — Owner-edited navigation guidance, never a legal rule or model instruction grant.
- [practice_playbooks.py](practice_playbooks.py) — Actual playbook catalogue and bounded pointer inspection via existing readers.
- [provenance_sources.py](provenance_sources.py) — Validates provenance required before relying on a published source.
- [provision_registry_composition.py](provision_registry_composition.py) — Import one optional, published candidate registry; never issue a review.
- [provision_review.py](provision_review.py) — Read a host-allowlisted dated provision review through existing trust owners.
- [provision_revision_sources.py](provision_revision_sources.py) — Date-qualified provision identities, distinct from Act lifetime metadata.
- [research_context.py](research_context.py) — Fresh task-scoped reading, never a chat summary or personal memory.
- [research.py](research.py) — Coordinates research findings without treating retrieval as verification.
- [resolution_sources.py](resolution_sources.py) — Resolves legal identities through the governed legal graph.
- [search_authority.py](search_authority.py) — Searches the authority index with full-text matching.
- [search_policed.py](search_policed.py) — Enforces egress permissions before searching the authority index.
- [search_port.py](search_port.py) — Types search results and limits what they may claim.
- [source_excerpt_contracts.py](source_excerpt_contracts.py) — Immutable retrieved text, not a claim of full-document or legal currency.
- [source_excerpt.py](source_excerpt.py) — Constructs exact cited excerpts from evidence-port results.
- [source_registry_sources.py](source_registry_sources.py) — Governed identities for legal sources and bounded source inventory.
- [tool_finish_research.py](tool_finish_research.py) — Finishes child research with a source-bound handoff.
- [tool_identify_act.py](tool_identify_act.py) — Resolves an Act's governed identity before section retrieval.
- [tool_rank_authorities.py](tool_rank_authorities.py) — Compares retrieved authorities through the hierarchy owner.
- [tool_read_judgment.py](tool_read_judgment.py) — Reads a judgment with its source identity and coverage limits.
- [tool_read_paragraph.py](tool_read_paragraph.py) — Reads an identified paragraph from a held judgment.
- [tool_read_playbook_catalogue.py](tool_read_playbook_catalogue.py) — Lists available owner-edited practice playbooks.
- [tool_read_practice_playbook.py](tool_read_practice_playbook.py) — Reads bounded guidance from an owner-edited playbook.
- [tool_read_provision.py](tool_read_provision.py) — Reads a dated provision through the governed evidence owner.
- [tool_read_source_document.py](tool_read_source_document.py) — Reads a bounded held-document window without exposing a path or URL.
- [tool_research.py](tool_research.py) — Dispatches bounded research through the registered model tool.
- [tool_resolve_citation.py](tool_resolve_citation.py) — Resolves a citation to a governed held-source identity.
- [tool_search_authorities.py](tool_search_authorities.py) — Searches held authorities within the admitted scope.
- [tool_search_authority.py](tool_search_authority.py) — Searches the authority index through the governed reader.
- [tool_sources.py](tool_sources.py) — Captures trusted source-reader results without accepting model-authored evidence.
- [tool_treatment.py](tool_treatment.py) — Reads subsequent treatment of a held judgment.

### Package

- [__init__.py](__init__.py) — Legal-brain retrieve capability; no runtime exports.

Return to [Legal brain](../README.md) or [the full project map](../../../docs/PROJECT_STRUCTURE.md).
