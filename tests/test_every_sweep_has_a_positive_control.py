"""A SWEEP THAT ONLY EVER FINDS NOTHING HAS NOT BEEN SHOWN TO FIND ANYTHING.

WHY
---
B-049 is the whole argument. `check_structure` guarded E-002c with

    if s.id not in covered and not any(s.slice <= n for n in range(1, 10)):

whose second half is False for every scenario, so the branch could not execute.
The test called it and asserted `not failures`. It passed on every commit since
it was written, and the check had never once run.

**Asserting that a bad state is absent proves nothing about the checker.** A
checker that always returns `[]` satisfies it identically, and this one did.

So every sweep in this suite — the files that enumerate a population and assert
nobody in it is broken — must also PLANT a broken member and assert it is
reported. Two of them already did before this file existed; the rest were
written after B-049 taught the lesson, and this is what stops the next one
being written without it.

WHY A DECLARED MAP AND NOT A CLEVERER SCAN
-------------------------------------------
"Does this test have a positive control?" is not decidable by reading source:
a control can be a second call, a planted fixture, a `pytest.raises`, or a
sibling test. Guessing produces false confidence, which is the failure this
file exists to refuse. So each sweep NAMES its control, and the naming is
checked — the same arrangement as `tests/test_defect_register.py`, where the
claim is prose until something resolves it.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]

#: sweep test  ->  the test that proves it can fail.
#: A sweep with no control is a sweep that has never been shown to work.
CONTROLS: dict[str, str] = {
    # M1 -- length is not content, over every dataclass in nm/
    "test_no_required_string_field_accepts_a_value_made_of_whitespace":
        "test_blank_is_the_one_definition_of_carrying_nothing",
    # M5 -- three states, over every enum in nm/
    "test_every_outcome_enum_can_say_that_nothing_was_established":
        "test_the_third_state_is_a_value_and_never_a_null",
    # M2 -- every declared owner is reached, over every function in nm/
    "test_no_function_in_the_product_is_defined_and_never_reached":
        "test_the_scan_can_see_the_product",
    # E-102's register, over every prompt constant in nm/core/
    "test_every_advocate_facing_prompt_carries_the_clause":
        "test_the_scan_can_see_a_prompt_that_lost_its_clause",
    "test_every_prompt_is_declared_one_kind_or_the_other":
        "test_the_scan_can_see_a_prompt_that_lost_its_clause",
    # the register, over every defect row
    "test_every_check_the_register_names_actually_exists":
        "test_the_register_can_be_read_at_all",
    "test_every_named_test_function_is_really_in_that_file":
        "test_the_register_can_be_read_at_all",
    # an enumerator owns its population, over every subsumed defect row
    "test_every_defect_an_enumerator_subsumes_names_that_enumerator":
        "test_the_enumerator_scan_can_see_a_defect_that_ignores_its_sweep",
    # one owner for which reads are decisive, over every literal in nm/
    "test_no_second_copy_of_the_decisive_set_exists":
        "test_the_second_copy_scan_can_see_a_second_copy",
    # an open row is a claim someone re-runs, over every open defect
    "test_every_open_defect_can_be_reproduced_or_says_why_not":
        "test_the_open_row_scan_can_see_an_undeclared_one",
    "test_no_reproduction_declaration_outlives_its_row":
        "test_the_stale_declaration_scan_can_see_a_closed_row",
    # no internal key in advocate-facing text, over every served element
    "test_no_internal_id_reaches_the_advocate":
        "test_the_sweep_can_see_a_planted_leak",
    # the manifest, over every declared Act
    "test_every_declared_act_retrieves_at_least_one_intended_section":
        "test_an_act_the_corpus_cannot_serve_is_caught",
    # A1 -- every matter route requires a session, over the ROUTE TABLE
    "test_every_matter_route_requires_a_session":
        "test_the_route_sweep_can_see_an_unguarded_route",
    # the golden set -- the sweep B-049 was hiding in
    "test_every_scenario_is_reachable_from_a_suite":
        "test_every_scenario_is_reachable_from_a_suite",
    # the persisted types
    "test_every_persisted_type_is_covered_by_this_file":
        "test_no_persisted_type_has_a_field_the_decoder_cannot_reach",
    # the schemas
    "test_every_declared_schema_is_satisfiable_when_nothing_was_established":
        "test_every_declared_schema_is_satisfiable_when_nothing_was_established",
    # Appendix E against the implementing types -- control planted inline
    "test_every_required_field_exists_on_the_implementing_type":
        "test_every_required_field_exists_on_the_implementing_type",
    # the second-provision-pattern scan -- control planted inline
    "test_no_module_defines_its_own_provision_pattern":
        "test_no_module_defines_its_own_provision_pattern",
    # the document-fact tripwire -- control planted inline
    "test_no_path_admits_a_document_fact_without_binding_it_to_a_thread":
        "test_no_path_admits_a_document_fact_without_binding_it_to_a_thread",
    # M3 -- one rule, one owner. Its control asserts each registered pattern
    # matches INSIDE its own owner, so a pattern that matches nothing cannot
    # report a clean codebase. This entry was added because THIS FILE caught
    # M3 the moment it was written without one.
    "test_no_rule_has_a_second_home":
        "test_the_owner_actually_contains_the_rule",
    # the mutation anchors -- a stale one means the mutation never ran, and
    # SURVIVED then reads as a weak test rather than as an unswept rename.
    "test_every_mutation_anchor_still_matches_the_source":
        "test_the_anchor_check_can_see_a_stale_anchor",
    # the console guard -- a tool whose report dies partway through on a dash
    # looks like a verdict and is not one.
    "test_every_tool_makes_its_console_survive_the_prose_it_prints":
        "test_the_console_scan_can_see_a_tool_that_does_not_call_it",
    # every metric reaches the record the release gate reads it from
    "test_every_metric_field_survives_into_the_persisted_record":
        "test_the_metric_scan_can_see_an_unserialised_field",
}

#: How a sweep is recognised: it builds a list of offenders over a population
#: and asserts the list is empty.
OFFENDER_NAMES = ("offenders", "failures", "missing", "unguarded", "dead",
                  "stale", "prose_only", "unreadable")


def _tests() -> dict[str, tuple[str, str]]:
    """Every test function in the suite, with its file and source."""
    out: dict[str, tuple[str, str]] = {}
    for f in sorted((ROOT / "tests").glob("test_*.py")):
        src = f.read_text(encoding="utf8")
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                out[node.name] = (f.name, ast.get_source_segment(src, node) or "")
    return out


def _sweeps() -> dict[str, str]:
    """Tests that enumerate a population and assert nobody in it is broken."""
    found = {}
    for name, (file, body) in _tests().items():
        builds = any(f"{n}.append(" in body or f"{n}: list" in body
                     for n in OFFENDER_NAMES)
        asserts_empty = any(f"assert not {n}" in body for n in OFFENDER_NAMES)
        if builds and asserts_empty:
            found[name] = file
    return found


def test_the_suite_contains_sweeps_to_check():
    """A guard on the guard."""
    assert len(_sweeps()) >= 6, (
        f"only {len(_sweeps())} sweeps recognised — this file would then be "
        f"asserting almost nothing")


def test_every_sweep_names_a_control_that_proves_it_can_fail():
    """THE POINT, and B-049 is why it is not optional."""
    tests = _tests()
    uncontrolled, unresolved = [], []
    for sweep, file in sorted(_sweeps().items()):
        control = CONTROLS.get(sweep)
        if control is None:
            uncontrolled.append(f"{file}::{sweep}")
        elif control not in tests:
            unresolved.append(f"{file}::{sweep} -> {control} (does not exist)")

    assert not uncontrolled, (
        "these sweeps assert that nothing is broken and nothing shows they "
        "could find a break:\n  " + "\n  ".join(uncontrolled)
        + "\n\nAdd a test that PLANTS a broken member and asserts it is "
          "reported, then name it in CONTROLS above. A checker that always "
          "returns [] passes a sweep identically — and one of them did, on "
          "every commit for weeks (B-049).")
    assert not unresolved, (
        "these sweeps name a control that is not in the suite:\n  "
        + "\n  ".join(unresolved)
        + "\n\nA rename moved it and left the claim behind.")


def test_no_control_is_named_for_a_sweep_that_no_longer_exists():
    """The map may not rot into a list of reassuring names.

    An entry for a sweep that is gone is a control nobody is running, and it
    makes the map look more complete than it is.
    """
    tests = _tests()
    stale = sorted(s for s in CONTROLS if s not in tests)
    assert not stale, (
        f"CONTROLS names sweeps that no longer exist: {stale}. Delete the "
        f"entry with the sweep, or the map is measuring its own history.")
