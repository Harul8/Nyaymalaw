# Shared

Cross-journey authority, budgets, custody/storage, model ports/adapters, egress and source-layout infrastructure. Keep these common mechanisms single-owned; a source-current identity, processor permission or model result is not legal applicability or independent professional approval.

Key files:

- [authority_contracts.py](authority_contracts.py) — Types who may perform an operation; journeys do not grant authority by their names.
- [budget_contracts.py](budget_contracts.py) — Types whole grants and measured spend.
- [model_port.py](model_port.py) — The typed provider-independent model boundary; concrete SDKs stay in their declared adapters.
- [source_layout.py](source_layout.py) — Reads and reconciles the sole shipped module-role and browser-asset manifest.

## Current file index

This index follows the shipped [source-layout manifest](../source_layout.json). The semantic roles below retain the existing dependency boundary; the journey folder is not a permission or acceptance claim.

### Composition and configuration

- [egress_policy.py](egress_policy.py)

### Services and native owners

- [json_values.py](json_values.py)
- [worker.py](worker.py)

### Contracts and package

- [__init__.py](__init__.py)
- [authority_contracts.py](authority_contracts.py)
- [budget_contracts.py](budget_contracts.py)
- [clock_contracts.py](clock_contracts.py)
- [deployment_contracts.py](deployment_contracts.py)
- [egress_contracts.py](egress_contracts.py)
- [external_ai_contracts.py](external_ai_contracts.py)
- [gates_contracts.py](gates_contracts.py)
- [identity_contracts.py](identity_contracts.py)
- [incident_contracts.py](incident_contracts.py)
- [legal_review_contracts.py](legal_review_contracts.py)
- [metrics_contracts.py](metrics_contracts.py)
- [names_contracts.py](names_contracts.py)
- [operation_contracts.py](operation_contracts.py)
- [release_contracts.py](release_contracts.py)
- [restore_contracts.py](restore_contracts.py)
- [review_contracts.py](review_contracts.py)
- [spoken_contracts.py](spoken_contracts.py)
- [text_contracts.py](text_contracts.py)
- [traceability_contracts.py](traceability_contracts.py)

### Ports

- [model_port.py](model_port.py)
- [storage_errors_port.py](storage_errors_port.py)
- [store_port.py](store_port.py)
- [transactional_port.py](transactional_port.py)

### Adapters

- [model_anthropic_adapter.py](model_anthropic_adapter.py)
- [model_budget.py](model_budget.py)
- [model_call_budget.py](model_call_budget.py)
- [model_config.py](model_config.py)
- [model_openai_adapter.py](model_openai_adapter.py)
- [model_policed.py](model_policed.py)
- [model_replay.py](model_replay.py)
- [model_scripted.py](model_scripted.py)
- [model_traced.py](model_traced.py)
- [model_transport.py](model_transport.py)
- [optional_adapter.py](optional_adapter.py)
- [policed_port_adapter.py](policed_port_adapter.py)
- [store_documents.py](store_documents.py)
- [store_envelope.py](store_envelope.py)
- [store_file_store.py](store_file_store.py)
- [store_loop_log.py](store_loop_log.py)
- [store_postgres.py](store_postgres.py)
- [store_sealing.py](store_sealing.py)
- [store_uploads.py](store_uploads.py)

### Infrastructure

- [source_layout.py](source_layout.py)
