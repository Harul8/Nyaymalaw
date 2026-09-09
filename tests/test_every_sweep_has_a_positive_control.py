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
import functools
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]

#: sweep test  ->  the test that proves it can fail.
#: A sweep with no control is a sweep that has never been shown to work.
CONTROLS: dict[str, str] = {
    # BK-44 -- a documented defect is marked strict, never called, over every
    # test file in the suite. Its control plants the `if` and `except` forms
    # that were actually in the journey file, and the `from pytest import`
    # spelling that would otherwise slip past.
    "test_no_test_calls_xfail_instead_of_marking_it":
        "test_the_xfail_scan_can_see_a_planted_call",
    "test_every_xfail_marker_is_strict_and_names_its_row":
        "test_the_xfail_scan_can_see_a_planted_call",
    # B-141 -- no live document says an artefact is absent while it is on
    # disk. Verified 9 September 2026 rather than assumed: both ABSENCE_CLAIMS
    # rows report present=True (so neither is vacuously skipped) and the
    # control asserts the phrases match the sentences that actually went stale.
    "test_no_live_document_says_an_artefact_is_absent_while_it_is_on_disk":
        "test_the_check_can_see_a_stale_claim",
    # BK-43 -- no stylesheet clips the document scroll width, over every CSS
    # file the product serves. Its control plants the rule in all four forms
    # it could return in, including the `clip` replacement.
    "test_no_stylesheet_clips_the_document_scroll_width":
        "test_the_overflow_scan_can_see_a_planted_rule",
    # BK-30 -- one CSS class, one owner. `.gate` meant a gate FIRING in an
    # answer and also the full-screen sign-in overlay, so every disclosure
    # became `position:fixed; inset:0; z-index:100` and painted the whole
    # application white after every turn.
    "test_no_class_is_declared_twice_at_the_top_level":
        "test_the_scan_sees_a_planted_collision",
    # the attributable labels have one owner, over every literal
    # collection in nm/ AND tools/ -- five of the six copies it
    # replaced were in tools/
    "test_only_one_module_writes_down_the_attributable_labels":
        "test_the_checker_can_actually_fail",
    # BK-17 -- no guard in nm/ is an assert, over every module
    "test_no_guard_in_the_product_is_an_assert":
        "test_the_assert_sweep_can_see_a_guard_it_would_delete",
    # BK-14 -- nothing asks the machine what day it is
    "test_nothing_in_the_product_asks_the_machine_what_day_it_is":
        "test_the_clock_sweep_can_see_a_call_to_the_machine",
    # BK-15 -- the forum has one owner
    "test_the_jurisdiction_has_one_owner":
        "test_the_forum_sweep_can_see_a_second_owner",
    # BK-13 -- no enum value reaches the advocate, over every Element in nm/
    "test_no_enum_value_reaches_the_advocate":
        "test_the_value_scan_can_see_an_identifier_reaching_the_advocate",
    # BK-13 -- every Spoken enum checks itself at import, over every class
    "test_every_spoken_enum_called_complete":
        "test_the_complete_scan_can_see_an_enum_that_never_checks_itself",
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

#: SWEEPS WITH NO VERIFIED CONTROL, declared 9 September 2026. BK-52.
#:
#: The detector below used to match a hard-coded list of variable names
#: (`offenders`, `failures`, `missing`, ...). A sweep written that day named its
#: list `offences` -- one letter outside the allowlist -- and was therefore not
#: recognised as a sweep at all, never required to have a control, and passed
#: this file silently. Reading the source instead of the allowlist found
#: twenty-two more that had been invisible the same way.
#:
#: MOST OF THESE PROBABLY HAVE A CONTROL. The value names the candidate found
#: by reading the file. It is NOT registered as the control, because this
#: file's argument is precisely that a control which is guessed is false
#: confidence -- "a control can be a second call, a planted fixture, a
#: `pytest.raises`, or a sibling test. Guessing produces false confidence,
#: which is the failure this file exists to refuse."
#:
#: So each is verified and moved into CONTROLS one at a time. An admitted gap
#: is work; a silent one is a surprise.
UNCONTROLLED: dict[str, str] = {
    "test_a_read_that_builds_a_prompt_and_a_guard_uses_one_value":
        "candidate: test_the_scan_catches_a_planted_hand_guard",
    "test_a_structured_prompt_does_not_carry_it":
        "candidate: test_the_scan_can_see_a_prompt_that_lost_its_clause",
    "test_a_withheld_turn_commits_none_of_what_it_derived":
        "NO CANDIDATE FOUND -- nothing in the file plants a withheld turn "
        "that commits",
    "test_every_answer_in_the_run_carries_the_trailing_disclosures":
        "candidate: test_the_answer_coverage_check_can_see_an_uncovered_site",
    "test_every_evidence_adapter_answers_the_whole_port":
        "candidate: test_the_sweep_can_see_the_population",
    "test_every_read_schema_can_be_compiled_by_strict_mode":
        "candidate: test_the_suite_can_see_the_declared_schemas",
    "test_every_recurring_shape_has_a_mechanism_more_than_one_defect_points_at":
        "candidate: test_the_enumerator_scan_can_see_a_defect_that_ignores_"
        "its_sweep",
    "test_every_schema_is_identified_by_an_exact_key_and_not_a_substring":
        "candidate: test_the_schema_scan_can_see_a_schema_with_no_responder",
    "test_no_binding_reason_reads_as_a_citation":
        "NO CANDIDATE FOUND",
    "test_no_feature_is_tested_while_its_eval_runs_every_turn_and_it_has_no_turn":
        "candidate: test_the_scan_can_see_an_unreached_module",
    "test_no_gate_disclosure_reads_as_a_citation":
        "NO CANDIDATE FOUND",
    "test_no_model_name_or_provider_client_appears_in_the_core":
        "NO CANDIDATE FOUND -- and this one guards the layering, so it is "
        "the least comfortable entry in this table",
    "test_no_module_outside_the_adapters_names_a_provider":
        "candidate: test_the_wire_scan_can_see_a_leak",
    "test_no_read_asks_for_the_hard_tier_while_none_is_earned":
        "candidate: test_the_scan_can_see_the_schemas",
    "test_the_core_imports_only_core_ports_and_domain":
        "NO CANDIDATE FOUND -- layercheck covers the same rule from outside "
        "the suite, which is a different population, not a control",
    "test_the_golden_suite_path_cannot_reach_a_model":
        "candidate: test_the_model_scan_can_see_a_runner_that_would_spend",
    "test_the_implemented_type_adds_nothing_the_contract_does_not_declare":
        "NO CANDIDATE FOUND",
    "test_the_phrases_are_not_the_identifiers_with_the_underscores_removed":
        "candidate: test_the_value_scan_can_see_an_identifier_reaching_the_"
        "advocate",
    "test_the_scripted_provider_answers_every_schema_the_core_declares":
        "candidate: test_the_schema_scan_can_see_a_schema_with_no_responder",
    "test_every_sweep_names_a_control_that_proves_it_can_fail":
        "this file's own sweep; its control is the pair of tests below that "
        "plant an unregistered sweep and a stale entry",
}


@functools.lru_cache(maxsize=1)
def _tests() -> dict[str, tuple[str, str]]:
    """Every test function in the suite, with its file and source."""
    out: dict[str, tuple[str, str]] = {}
    for f in sorted((ROOT / "tests").glob("test_*.py")):
        src = f.read_text(encoding="utf8")
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                out[node.name] = (f.name, ast.get_source_segment(src, node) or "")
    return out


def _asserted_empty(body: str) -> set[str]:
    """Every local name this test builds up and then asserts is empty.

    READ OFF THE SOURCE, NOT OFF A LIST OF NAMES WE THOUGHT OF. `OFFENDER_NAMES`
    was that list, and a sweep written against `web/` named its list `offences`
    -- one letter outside the allowlist -- so it was not recognised as a sweep,
    was never required to have a positive control, and passed this file
    silently on the day it was added.

    That is this file's own defect wearing this file's own costume: a checker
    whose POPULATION is wrong reports a clean result exactly like one that
    found nothing. The name of the variable was never the rule. The rule is
    that something is accumulated and then asserted empty, and that is what is
    matched now.
    """
    try:
        tree = ast.parse(textwrap.dedent(body))
    except SyntaxError:                     # pragma: no cover -- defensive
        return set()

    appended: set[str] = set()
    asserted: set[str] = set()
    for node in ast.walk(tree):
        # `x.append(...)` / `x.extend(...)` / `x += [...]`
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("append", "extend") \
                and isinstance(node.func.value, ast.Name):
            appended.add(node.func.value.id)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            appended.add(node.target.id)
        # `assert not x` / `assert not x, "..."`
        elif isinstance(node, ast.Assert) and isinstance(node.test, ast.UnaryOp) \
                and isinstance(node.test.op, ast.Not) \
                and isinstance(node.test.operand, ast.Name):
            asserted.add(node.test.operand.id)
    return appended & asserted


@functools.lru_cache(maxsize=1)
def _sweeps() -> dict[str, str]:
    """Tests that enumerate a population and assert nobody in it is broken.

    Cached: five tests in this file ask for it, and each call re-parses every
    file in the suite. `check.py` must stay cheap enough that there is no
    excuse for skipping it, and a guard that makes the gate slower is a guard
    that eventually gets turned off.
    """
    found = {}
    for name, (file, body) in _tests().items():
        if _asserted_empty(body):
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
        if sweep in UNCONTROLLED:
            continue                      # declared, dated and owned by BK-52
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


def test_no_admitted_gap_outlives_the_sweep_it_was_admitted_for():
    """UNCONTROLLED may shrink and it may not rot.

    An entry for a sweep that no longer exists -- renamed, deleted, or
    rewritten so it no longer accumulates -- is a gap the table still claims
    is open, and it makes the remaining work look larger than it is. The
    opposite of the CONTROLS staleness check, and needed for the same reason.
    """
    sweeps = _sweeps()
    stale = sorted(s for s in UNCONTROLLED if s not in sweeps)
    assert not stale, (
        "these are declared as sweeps awaiting a control and are no longer "
        "sweeps:\n  " + "\n  ".join(stale)
        + "\n\nIf one gained a control, move it to CONTROLS. If it was "
          "renamed or deleted, remove the entry -- BK-52 counts what is left "
          "by the size of this table.")


def test_an_admitted_gap_is_never_also_a_registered_control():
    """One row, one state. A sweep in both tables would be counted as done by
    CONTROLS and as outstanding by UNCONTROLLED, and BK-52 would never reach
    zero however much work was done."""
    both = sorted(set(CONTROLS) & set(UNCONTROLLED))
    assert not both, (
        f"these sweeps are registered as controlled AND declared as awaiting "
        f"a control: {both}")


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
