# 03.04 — Assess procedural conditions and calculations

Read governing procedural rules, institution requirements and interim-relief conditions; perform conditional limitation, interest, fee and procedural-period calculations over explicit legal selections and attributed inputs.

This is a responsibility within the legal-brain loop, not a mandatory execution
stage or a claim of complete feature acceptance. Files inside this folder stay flat.

## Read first

- [limitation.py](limitation.py)
- [event_limitation_calculation.py](event_limitation_calculation.py)
- [procedural_calculation.py](procedural_calculation.py)
- [reviewed_limitation_selection.py](reviewed_limitation_selection.py)
- [calculation_tools.py](calculation_tools.py)

## Boundaries

Arithmetic does not establish its legal premise, select a court calendar or invent a trigger date. Source selection, legal review and permission remain separate requirements. An unavailable calculation is not a zero or a successful deadline assessment.

Architectural roles and dependency directions remain explicit in
[`nm/source_layout.json`](../../source_layout.json). No new tool permission,
provider-processing approval or release claim comes from moving a file.

## Complete file index

Navigation over 42 implementation files, 0 browser assets and
the package initializer; this is not test evidence.

### Implementation

- [calculation_tools.py](calculation_tools.py) — Connects reviewed limitation inputs to the arithmetic owner.
- [event_limitation_calculation.py](event_limitation_calculation.py) — Calendar arithmetic over independently reviewed attributed event bindings.
- [fee_calculation_contracts.py](fee_calculation_contracts.py) — Exact conditional schedule arithmetic, not a valuation rule or payable fee.
- [filing_requirement_adapter.py](filing_requirement_adapter.py) — Serves held filing-readiness data through its port.
- [filing_requirement_port.py](filing_requirement_port.py) — Types forum, valuation and fee readiness questions.
- [filing_requirement_sources.py](filing_requirement_sources.py) — Looks up held forum, valuation and fee conditions.
- [governing_law_adapter.py](governing_law_adapter.py) — Serves curated governing-law transitions through its port.
- [governing_law_port.py](governing_law_port.py) — Types time-qualified governing-law transitions.
- [governing_law_sources.py](governing_law_sources.py) — Reads curated time-qualified governing-law transitions.
- [institution_adapter.py](institution_adapter.py) — Serves curated pre-institution conditions through its port.
- [institution_port.py](institution_port.py) — Types pre-institution procedural conditions.
- [institution_sources.py](institution_sources.py) — Reads curated pre-institution conditions and source references.
- [interest_calculation_contracts.py](interest_calculation_contracts.py) — Exact conditional arithmetic, with no legal entitlement or implicit convention.
- [interim_relief_adapter.py](interim_relief_adapter.py) — Serves curated interim-relief tests through its port.
- [interim_relief_port.py](interim_relief_port.py) — Types the separate tests for interim relief.
- [interim_relief_sources.py](interim_relief_sources.py) — Reads curated tests for the selected interim relief.
- [limitation.py](limitation.py) — Calculates limitation dates from selected legal and factual inputs.
- [procedural_calculation.py](procedural_calculation.py) — Conditional arithmetic over actual working sources and attributed events.
- [procedural_period_adapter.py](procedural_period_adapter.py) — Serves curated procedural periods through its port.
- [procedural_period_port.py](procedural_period_port.py) — Types periods that run within proceedings.
- [procedural_period_sources.py](procedural_period_sources.py) — Reads curated periods for the selected procedural role and track.
- [reviewed_fee_selection.py](reviewed_fee_selection.py) — Current exact source-owned fee inputs, independently checked before math.
- [reviewed_interest_selection.py](reviewed_interest_selection.py) — Actual source-span selections, independently reviewed before conditional math.
- [reviewed_limitation_selection.py](reviewed_limitation_selection.py) — Recorded event selections reviewed by the existing independent claim owner.
- [tool_compute_interest.py](tool_compute_interest.py) — Computes conditional interest from independently reviewed inputs.
- [tool_compute_limitation.py](tool_compute_limitation.py) — Computes a conditional limitation period from reviewed legal and event selections.
- [tool_compute_procedural_period.py](tool_compute_procedural_period.py) — Adds a source-quoted period to an attributed event conditionally.
- [tool_court_fee.py](tool_court_fee.py) — Computes conditional fee arithmetic only after independent input review.
- [tool_date_arithmetic.py](tool_date_arithmetic.py) — Performs date arithmetic without selecting the legal trigger.
- [tool_filing_requirements.py](tool_filing_requirements.py) — Reads forum, valuation and filing prerequisites.
- [tool_governing_code.py](tool_governing_code.py) — Reads the time-qualified governing-law selection.
- [tool_interim_test.py](tool_interim_test.py) — Reads the applicable interim-relief test.
- [tool_list_deadlines.py](tool_list_deadlines.py) — Lists recorded deadlines without declaring them legally assessed.
- [tool_pre_institution_steps.py](tool_pre_institution_steps.py) — Reads conditions required before proceedings are instituted.
- [tool_procedural_periods.py](tool_procedural_periods.py) — Reads held procedural-period rules.
- [tool_propose_fee_selection.py](tool_propose_fee_selection.py) — Proposes a source-bound fee selection for independent review.
- [tool_propose_interest_selection.py](tool_propose_interest_selection.py) — Proposes source-bound interest inputs for independent review.
- [tool_propose_limitation_selection.py](tool_propose_limitation_selection.py) — Proposes the provision and event governing limitation for review.
- [tool_read_fee_inventory.py](tool_read_fee_inventory.py) — Reads current fee candidates and exact source inputs.
- [tool_read_interest_inventory.py](tool_read_interest_inventory.py) — Reads current interest candidates and exact source inputs.
- [tool_read_limitation_candidates.py](tool_read_limitation_candidates.py) — Reads recorded limitation candidates before selection.
- [tool_read_procedural_calculation_inputs.py](tool_read_procedural_calculation_inputs.py) — Reads attributed inputs for procedural calculations.

### Package

- [__init__.py](__init__.py) — Legal-brain procedure capability; no runtime exports.

Return to [Legal brain](../README.md) or [the full project map](../../../docs/PROJECT_STRUCTURE.md).
