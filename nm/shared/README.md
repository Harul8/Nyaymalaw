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

- [egress_policy.py](egress_policy.py) — The processor inventory this installation actually runs under.

### Services and native owners

- [json_values.py](json_values.py) — Exact typed JSON-value equality for evidence, never Python coercion.
- [worker.py](worker.py) — Doing owed work exactly once, or saying you cannot tell.

### Contracts and package

- [__init__.py](__init__.py) — Shared security, model, storage, identity and clock contracts.
- [authority_contracts.py](authority_contracts.py) — Defines actor permissions for consequential operations.
- [budget_contracts.py](budget_contracts.py) — One budget for one operation, and a truncation is never an answer.
- [clock_contracts.py](clock_contracts.py) — Types authoritative dates and timezone-aware clock readings.
- [deployment_contracts.py](deployment_contracts.py) — Evidence about a deployment is evidence about one exact candidate.
- [egress_contracts.py](egress_contracts.py) — Where privileged material is allowed to go, decided before it goes.
- [external_ai_contracts.py](external_ai_contracts.py) — Attributed permission to process matter text, not legal/compliance clearance.
- [gates_contracts.py](gates_contracts.py) — Defines named release gates and their required conditions.
- [identity_contracts.py](identity_contracts.py) — Binds evidence to the exact running code identity.
- [incident_contracts.py](incident_contracts.py) — A rehearsal is evidence about people, not about a policy document.
- [legal_review_contracts.py](legal_review_contracts.py) — The legal half of a review, which is not a higher score.
- [metrics_contracts.py](metrics_contracts.py) — TurnMetrics, and the invariant violations recorded on every turn.
- [names_contracts.py](names_contracts.py) — Removing a name, when the decision has already been made.
- [operation_contracts.py](operation_contracts.py) — Types accepted commands and the follow-up work they create.
- [release_contracts.py](release_contracts.py) — Records the exact release candidate and reasons to withhold it.
- [restore_contracts.py](restore_contracts.py) — Defines restoration constraints that keep erased data erased.
- [review_contracts.py](review_contracts.py) — Types immutable review decisions and scores.
- [spoken_contracts.py](spoken_contracts.py) — Maps internal enum values to owned advocate-facing phrases.
- [text_contracts.py](text_contracts.py) — Defines when a text value is meaningfully empty.
- [traceability_contracts.py](traceability_contracts.py) — How code declares which PRD feature it implements.

### Ports

- [model_port.py](model_port.py) — Defines model requests, tool calls, results and usage.
- [storage_errors_port.py](storage_errors_port.py) — Expected sealed-object failures, reachable without importing a concrete adapter.
- [store_port.py](store_port.py) — Defines the transaction and matter-storage boundary.
- [transactional_port.py](transactional_port.py) — Commits the matter, accepted command and owed work together.

### Adapters

- [model_anthropic_adapter.py](model_anthropic_adapter.py) — Optional Messages API adapter; product vocabulary stays on the model port.
- [model_budget.py](model_budget.py) — Enforces model context limits before sending a request.
- [model_call_budget.py](model_call_budget.py) — Durable, conservative spending reservations for an explicitly bounded evaluation.
- [model_config.py](model_config.py) — Tier -> provider + pinned model resolution, read from the environment.
- [model_openai_adapter.py](model_openai_adapter.py) — Adapts the OpenAI API to the provider-neutral model port.
- [model_policed.py](model_policed.py) — Applies egress permissions to outbound model calls.
- [model_replay.py](model_replay.py) — Exact model-call recording and offline replay, never a live-quality claim.
- [model_scripted.py](model_scripted.py) — Supplies deterministic model replies for controlled tests.
- [model_traced.py](model_traced.py) — Captures exact model requests, responses and usage.
- [model_transport.py](model_transport.py) — One retry/error/accounting policy for every external model transport.
- [optional_adapter.py](optional_adapter.py) — Whether an optional library can actually be imported.
- [policed_port_adapter.py](policed_port_adapter.py) — Wraps fixed-destination ports with shared egress checks.
- [store_documents.py](store_documents.py) — Immutable document derivatives sealed under the existing per-matter custody.
- [store_envelope.py](store_envelope.py) — Wraps a separate matter data key outside the application process.
- [store_file_store.py](store_file_store.py) — Matter storage: encrypted at rest, atomic, version-checked.
- [store_loop_log.py](store_loop_log.py) — Saves audited reasoning-loop records transactionally in the matter store.
- [store_postgres.py](store_postgres.py) — Persists version-checked matters in PostgreSQL transactions.
- [store_sealing.py](store_sealing.py) — Sealing a matter's bytes, wherever they are about to be put.
- [store_uploads.py](store_uploads.py) — Sealed immutable upload chunks, with no second receipt/locking authority.

### Infrastructure

- [source_layout.py](source_layout.py) — The shipped source-layout identity: journeys do not grant dependency roles.
