"""TESTS WHOSE RULE THE OWNER SUPERSEDED ON 30 SEPTEMBER 2026 (LB-76, LB-106). ONE LIST.

Owner, 30 September 2026: *"five minutes is way too much ... this analysis should come
from retrieved passages only"*; and, on what the reply may stand on, the one check with
one rewrite, after which only the failing sentences are dropped. Each test below states a
rule about work the per-message path no longer does -- the limitation computation, the
next step and its checks, issues, proof, the evidence list, adverse facts, the theory,
the opposing case, the cross-dispute pass, the older judgment search -- or needs a
fixture that work produced. Each is SKIPPED, with what it depends on said, by
`tests/conftest.py`; none is deleted, so an analysis brought back on demand brings its
tests back by leaving this list.

A LIST AND NOT A SCATTER of skip marks, so the whole superseded population is read in one
place, and a test is taken off it the moment it states a rule the product keeps. The
rules that replace these are stated by `test_a_legal_message_is_answered_dispute_by_dispute`,
`test_judgments_are_searched_like_sections`, `test_the_disputes_are_worked_side_by_side`
and `test_a_reply_that_still_fails_loses_only_what_fails`.
"""

#: test node id -> the work, no longer run per message, that the test depends on.
SUPERSEDED: dict[str, str] = {
    "tests/test_a_correction_is_served_and_survives_restart.py::test_a_served_turn_records_what_it_derived_and_what_each_rests_on":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_a_correction_is_served_and_survives_restart.py::test_a_stale_conclusion_is_labelled_stale_on_the_served_cover":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_a_correction_is_served_and_survives_restart.py::test_a_withdrawn_entry_cannot_be_corrected_twice":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_a_correction_is_served_and_survives_restart.py::test_correcting_the_date_invalidates_the_deadline_and_not_the_role":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_a_correction_is_served_and_survives_restart.py::test_planted_serving_the_old_figure_as_current_is_refused":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_a_correction_is_served_and_survives_restart.py::test_the_next_turn_recomputes_and_closes_the_revision":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_a_disclosure_is_served_not_recorded.py::test_a_refused_read_is_named_to_the_advocate_and_not_only_to_the_metrics":
        'the opposing-argument read and the cross-dispute pass, the case theory and the adverse-fact read and the salvage pass',
    "tests/test_a_disclosure_is_served_not_recorded.py::test_a_salvage_pass_that_could_not_run_says_so_on_the_served_turn":
        'the opposing-argument read and the cross-dispute pass, the case theory and the adverse-fact read and the salvage pass',
    "tests/test_a_disclosure_is_served_not_recorded.py::test_a_theory_that_could_not_be_formed_does_not_pass_as_one":
        'the opposing-argument read and the cross-dispute pass, the case theory and the adverse-fact read and the salvage pass',
    "tests/test_a_disclosure_is_served_not_recorded.py::test_a_theory_with_nothing_against_it_says_that_rather_than_going_quiet":
        'the opposing-argument read and the cross-dispute pass, the case theory and the adverse-fact read and the salvage pass',
    "tests/test_a_disclosure_is_served_not_recorded.py::test_the_cross_file_pass_is_disclosed_once_on_every_file":
        'the opposing-argument read and the cross-dispute pass, the case theory and the adverse-fact read and the salvage pass',
    "tests/test_a_late_citation_is_fetched_once.py::test_a_provision_the_answer_named_is_fetched_and_the_answer_rewritten":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped)",
    "tests/test_a_late_citation_is_fetched_once.py::test_a_second_failure_still_withholds":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped)",
    "tests/test_a_late_citation_is_fetched_once.py::test_the_fetch_names_the_act_the_answer_named":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped)",
    "tests/test_a_late_citation_is_fetched_once.py::test_the_round_runs_at_most_once":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped)",
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[accrual]":
        'the read it refuses',
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[adverse]":
        'the read it refuses',
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[attacks]":
        'the read it refuses',
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[consistency]":
        'the read it refuses',
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[exposure]":
        'the read it refuses',
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[factors]":
        'the read it refuses',
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[inventory]":
        'the read it refuses',
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[investigation]":
        'the read it refuses',
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[issues]":
        'the read it refuses',
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[proof]":
        'the read it refuses',
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[salvage]":
        'the read it refuses',
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[step_dependency]":
        'the read it refuses',
    "tests/test_a_refused_read_is_named.py::test_a_read_that_could_not_run_is_named_to_the_advocate[theory]":
        'the read it refuses',
    "tests/test_a_reply_can_be_copied_and_rated.py::test_a_withheld_reply_cannot_be_rated":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped)",
    "tests/test_a_step_cannot_contradict_the_figures.py::test_a_contradiction_is_rewritten_once_and_then_served":
        'the next step, its checks and its written explanation',
    "tests/test_a_step_cannot_contradict_the_figures.py::test_a_read_that_cannot_quote_the_step_serves_it":
        'the next step, its checks and its written explanation',
    "tests/test_a_step_cannot_contradict_the_figures.py::test_a_read_that_could_not_run_serves_the_step_and_says_so":
        'the next step, its checks and its written explanation',
    "tests/test_a_step_cannot_contradict_the_figures.py::test_a_read_that_finds_nothing_serves_the_step":
        'the next step, its checks and its written explanation',
    "tests/test_a_step_cannot_contradict_the_figures.py::test_a_read_that_names_a_fact_it_was_not_shown_serves_the_step":
        'the next step, its checks and its written explanation',
    "tests/test_a_step_cannot_contradict_the_figures.py::test_a_rewrite_that_still_contradicts_is_not_served":
        'the next step, its checks and its written explanation',
    "tests/test_a_step_cannot_contradict_the_figures.py::test_a_step_that_contradicts_the_figures_is_not_served":
        'the next step, its checks and its written explanation',
    "tests/test_a_turn_receipt_is_not_an_archival_trace.py::test_a_grounding_withheld_archive_is_never_released_or_marked_committed[False]":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped)",
    "tests/test_a_turn_receipt_is_not_an_archival_trace.py::test_a_grounding_withheld_archive_is_never_released_or_marked_committed[True]":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped)",
    "tests/test_a_withheld_turn_commits_no_conclusion.py::test_a_withheld_turn_commits_none_of_what_it_derived":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped)",
    "tests/test_a_withheld_turn_commits_no_conclusion.py::test_a_withheld_turn_is_not_marked_applied":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped)",
    "tests/test_a_withheld_turn_commits_no_conclusion.py::test_a_withheld_turn_keeps_the_facts_the_advocate_stated":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped)",
    "tests/test_a_withheld_turn_commits_no_conclusion.py::test_the_withheld_conclusion_sweep_can_see_a_planted_leak":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped)",
    "tests/test_adversarial_on_a_served_turn.py::test_a_single_thread_file_still_gets_the_cross_file_line":
        'the opposing-argument read and the cross-dispute pass',
    "tests/test_adversarial_on_a_served_turn.py::test_an_unanswerable_attack_with_a_plan_is_accepted_and_rendered":
        'the opposing-argument read and the cross-dispute pass',
    "tests/test_adversarial_on_a_served_turn.py::test_the_cross_file_line_appears_exactly_once_on_a_multi_thread_file":
        'the opposing-argument read and the cross-dispute pass',
    "tests/test_adversarial_on_a_served_turn.py::test_the_other_sides_case_reaches_the_advocate":
        'the opposing-argument read and the cross-dispute pass',
    "tests/test_advice_is_released_at_its_real_maturity.py::test_a_served_turn_records_the_typed_recommendation_on_the_thread":
        'the next step, its checks and its written explanation',
    "tests/test_advice_is_released_at_its_real_maturity.py::test_an_attributed_by_when_names_where_the_date_came_from":
        'the next step, its checks and its written explanation',
    "tests/test_advice_is_released_at_its_real_maturity.py::test_the_served_record_reports_what_it_could_not_establish":
        'the next step, its checks and its written explanation',
    "tests/test_an_interim_application_is_decided_on_its_own_test.py::test_the_advocate_is_given_the_interim_test_and_not_the_merits":
        'the interim-relief test',
    "tests/test_an_interim_application_is_decided_on_its_own_test.py::test_the_served_turn_never_reports_a_limb_as_made_out":
        'the interim-relief test',
    "tests/test_an_interim_application_is_decided_on_its_own_test.py::test_the_stated_interim_order_reaches_the_advocate_on_the_engine":
        'the interim-relief test',
    "tests/test_bounded_judgment_investigation.py::test_invalid_model_proposal_does_not_bypass_the_served_turn":
        'the word-only judgment search and its research loop (judgments are found by the judgment search)',
    "tests/test_bounded_judgment_investigation.py::test_semantic_intent_is_delegated_without_a_production_phrase_gate":
        'the word-only judgment search and its research loop (judgments are found by the judgment search)',
    "tests/test_bounded_judgment_investigation.py::test_the_served_engine_executes_a_proposal_and_persists_its_limit":
        'the word-only judgment search and its research loop (judgments are found by the judgment search)',
    "tests/test_correction_supersedes.py::test_the_limitation_names_the_entries_it_did_not_run_from":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_current_evidence_reaches_reasoning.py::test_new_authority_reaches_all_three_dependent_reasoning_tasks":
        'the case theory and the adverse-fact read, the opposing-argument read and the cross-dispute pass and the next step, its checks and its written explanation',
    "tests/test_current_evidence_reaches_reasoning.py::test_unfinished_recommendation_never_becomes_an_action[cancelled]":
        'the case theory and the adverse-fact read, the opposing-argument read and the cross-dispute pass and the next step, its checks and its written explanation',
    "tests/test_current_evidence_reaches_reasoning.py::test_unfinished_recommendation_never_becomes_an_action[filtered]":
        'the case theory and the adverse-fact read, the opposing-argument read and the cross-dispute pass and the next step, its checks and its written explanation',
    "tests/test_current_evidence_reaches_reasoning.py::test_unfinished_recommendation_never_becomes_an_action[length_limited]":
        'the case theory and the adverse-fact read, the opposing-argument read and the cross-dispute pass and the next step, its checks and its written explanation',
    "tests/test_current_evidence_reaches_reasoning.py::test_unfinished_recommendation_never_becomes_an_action[not_established]":
        'the case theory and the adverse-fact read, the opposing-argument read and the cross-dispute pass and the next step, its checks and its written explanation',
    "tests/test_factors_on_a_served_turn.py::test_an_acknowledgment_moves_the_date_the_advocate_is_shown":
        'the limitation position, its thresholds and the deadline register (what restarts limitation)',
    "tests/test_factors_on_a_served_turn.py::test_the_turn_asks_for_the_section_and_not_only_the_article":
        'the limitation position, its thresholds and the deadline register (what restarts limitation)',
    "tests/test_factors_on_a_served_turn.py::test_the_unretrieved_section_is_disclosed_and_never_silently_none":
        'the limitation position, its thresholds and the deadline register (what restarts limitation)',
    "tests/test_gaps_and_cascade_on_a_served_turn.py::test_a_conditional_figure_that_moves_is_announced_with_its_prior":
        'the gap queue and the cascade of derived values',
    "tests/test_gaps_and_cascade_on_a_served_turn.py::test_a_corrected_date_moves_the_value_and_says_what_it_was":
        'the gap queue and the cascade of derived values',
    "tests/test_gaps_and_cascade_on_a_served_turn.py::test_an_unanswered_undo_becomes_a_blocking_gap":
        'the gap queue and the cascade of derived values',
    "tests/test_gaps_and_cascade_on_a_served_turn.py::test_an_unchanged_inventory_is_not_announced_as_a_loss":
        'the gap queue and the cascade of derived values',
    "tests/test_gaps_and_cascade_on_a_served_turn.py::test_the_answer_closes_with_what_is_still_missing":
        'the gap queue and the cascade of derived values',
    "tests/test_gaps_and_cascade_on_a_served_turn.py::test_the_cascade_counts_what_the_thread_holds_not_what_the_turn_showed":
        'the gap queue and the cascade of derived values',
    "tests/test_gaps_and_cascade_on_a_served_turn.py::test_the_questions_come_out_of_the_queue_as_one_batched_ask":
        'the gap queue and the cascade of derived values',
    "tests/test_grounding_gate.py::test_a_withheld_turn_still_says_what_could_not_be_established":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped); and the word-only judgment search and its research loop (judgments are found by the judgment search)",
    "tests/test_grounding_gate.py::test_a_withheld_turn_still_writes_its_metrics":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped); and the word-only judgment search and its research loop (judgments are found by the judgment search)",
    "tests/test_grounding_gate.py::test_an_unmeasured_installation_says_so_rather_than_implying_coverage":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped); and the word-only judgment search and its research loop (judgments are found by the judgment search)",
    "tests/test_grounding_gate.py::test_the_corpus_gap_is_disclosed_before_the_authority_search_not_after":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped); and the word-only judgment search and its research loop (judgments are found by the judgment search)",
    "tests/test_grounding_gate.py::test_the_engine_withholds_a_turn_whose_answer_invents_a_citation":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped); and the word-only judgment search and its research loop (judgments are found by the judgment search)",
    "tests/test_inventory_on_a_served_turn.py::test_an_item_at_risk_with_no_preservation_step_becomes_a_question":
        'the evidence list',
    "tests/test_inventory_on_a_served_turn.py::test_the_inventory_reaches_the_advocate_at_all":
        'the evidence list',
    "tests/test_issues_on_a_served_turn.py::test_a_served_turn_puts_issues_in_front_of_the_advocate":
        'the issue list',
    "tests/test_issues_on_a_served_turn.py::test_the_same_issue_runs_the_other_way_on_the_opposite_posture":
        'the issue list',
    "tests/test_limitation_step_gate.py::test_served_refusal_removes_old_recommendation_and_survives_reload":
        'the next step, its checks and its written explanation',
    "tests/test_live_inventory_completeness.py::test_consistency_refusal_never_republishes_the_rejected_candidate":
        'the next step, its checks and its written explanation',
    "tests/test_matter_memory.py::test_a_withheld_turn_keeps_the_advocates_words":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped)",
    "tests/test_never_clauses.py::test_a_survey_of_options_without_a_view_is_not_an_answer":
        'the next step, its checks and its written explanation (an unblocked answer need not lead with a step)',
    "tests/test_never_clauses.py::test_the_first_content_element_is_an_action_or_a_blocking_question":
        'the next step, its checks and its written explanation (an unblocked answer need not lead with a step)',
    "tests/test_never_clauses.py::test_uncertainty_is_stated_and_is_never_a_reason_to_withhold_a_view":
        'the next step, its checks and its written explanation (an unblocked answer need not lead with a step)',
    "tests/test_no_internal_id_reaches_the_advocate.py::test_no_internal_id_reaches_the_advocate":
        'the analyses its population came from',
    "tests/test_no_phrase_list_decides.py::test_side_blind_turns_cannot_enter_the_investigation_lane":
        'the word-only judgment search and its research loop (judgments are found by the judgment search)',
    "tests/test_premises_come_before_arithmetic.py::test_a_corrected_trigger_date_is_not_served_as_current":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_premises_come_before_arithmetic.py::test_an_inferred_accrual_computes_conditional_and_enters_no_deadline":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_premises_come_before_arithmetic.py::test_correct_arithmetic_never_certifies_the_law_the_disclosure_reaches_the_advocate":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_premises_come_before_arithmetic.py::test_stating_the_premise_makes_the_next_computation_definitive":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_premises_come_before_arithmetic.py::test_the_cover_and_register_share_one_premise_version":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_prompt_consistency.py::test_purpose_allows_a_finding_without_fabricating_action_but_not_a_block_bypass[assessment]":
        'the next step, its checks and its written explanation (an unblocked answer need not lead with a step)',
    "tests/test_prompt_consistency.py::test_purpose_allows_a_finding_without_fabricating_action_but_not_a_block_bypass[explanation]":
        'the next step, its checks and its written explanation (an unblocked answer need not lead with a step)',
    "tests/test_prompt_consistency.py::test_purpose_reaches_the_served_answer_and_history_without_fabricating_a_recommendation[assessment]":
        'the next step, its checks and its written explanation (an unblocked answer need not lead with a step)',
    "tests/test_prompt_consistency.py::test_purpose_reaches_the_served_answer_and_history_without_fabricating_a_recommendation[explanation]":
        'the next step, its checks and its written explanation (an unblocked answer need not lead with a step)',
    "tests/test_proof.py::test_the_served_turn_records_a_characterisation_of_the_client":
        'the proof table',
    "tests/test_proof_on_a_served_turn.py::test_an_unwired_element_table_says_so_rather_than_saying_nothing":
        'the proof table',
    "tests/test_reasoning_communication_discipline.py::test_served_turn_keeps_full_decision_only_in_encrypted_diagnostics":
        'the next step, its checks and its written explanation',
    "tests/test_relief_changes_the_recommendation.py::test_a_planted_step_pursuing_the_defeated_relief_is_blocked_for_the_relief_reason":
        'the next step, its checks and its written explanation and the relief position',
    "tests/test_relief_changes_the_recommendation.py::test_a_run_limitation_makes_the_relief_late_and_reaches_the_advocate":
        'the next step, its checks and its written explanation and the relief position',
    "tests/test_slice123_closeout.py::test_a_named_provision_does_not_spend_the_wandering_budget":
        'the wandering evidence rounds and their bound (one exact read per dispute)',
    "tests/test_slice123_closeout.py::test_a_named_provision_is_still_counted":
        'the wandering evidence rounds and their bound (one exact read per dispute)',
    "tests/test_slice123_closeout.py::test_reaching_the_evidence_bound_produces_a_visible_gap":
        'the wandering evidence rounds and their bound (one exact read per dispute)',
    "tests/test_slice4_closeout.py::test_a_bar_is_signalled_loudly_and_is_not_reported_as_a_verdict":
        'the limitation position, its thresholds and the deadline register and the next step, its checks and its written explanation',
    "tests/test_slice4_closeout.py::test_a_fact_nobody_examined_is_never_recorded_as_having_no_effect":
        'the limitation position, its thresholds and the deadline register and the next step, its checks and its written explanation',
    "tests/test_slice4_closeout.py::test_a_passed_deadline_never_becomes_the_by_when_of_an_action":
        'the limitation position, its thresholds and the deadline register and the next step, its checks and its written explanation',
    "tests/test_slice4_closeout.py::test_a_recommended_action_carries_the_by_when_the_register_holds":
        'the limitation position, its thresholds and the deadline register and the next step, its checks and its written explanation',
    "tests/test_slice4_closeout.py::test_an_article_whose_text_states_no_period_is_not_computed_and_says_so":
        'the limitation position, its thresholds and the deadline register and the next step, its checks and its written explanation',
    "tests/test_slice4_closeout.py::test_an_uncomputed_limitation_reports_itself_once_and_not_as_a_gap":
        'the limitation position, its thresholds and the deadline register and the next step, its checks and its written explanation',
    "tests/test_slice4_closeout.py::test_on_a_defending_thread_the_turn_computes_the_opponents_limitation":
        'the limitation position, its thresholds and the deadline register and the next step, its checks and its written explanation',
    "tests/test_slice4_closeout.py::test_the_limitation_lines_read_as_english_to_an_advocate":
        'the limitation position, its thresholds and the deadline register and the next step, its checks and its written explanation',
    "tests/test_slice4_closeout.py::test_the_period_on_a_served_turn_is_the_one_the_retrieved_text_states":
        'the limitation position, its thresholds and the deadline register and the next step, its checks and its written explanation',
    "tests/test_slice4_closeout.py::test_the_turn_names_every_threshold_it_did_not_assess":
        'the limitation position, its thresholds and the deadline register and the next step, its checks and its written explanation',
    "tests/test_slice4_closeout.py::test_where_no_window_could_be_established_the_action_says_which":
        'the limitation position, its thresholds and the deadline register and the next step, its checks and its written explanation',
    "tests/test_the_clocks_that_run_inside_a_proceeding.py::test_an_engaged_period_reaches_the_register_with_no_date":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_clocks_that_run_inside_a_proceeding.py::test_neither_reading_of_the_written_statement_rule_is_picked":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_clocks_that_run_inside_a_proceeding.py::test_the_advocate_is_told_the_period_binds_and_whether_it_extends":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_cover_matches_the_saved_matter.py::test_served_intake_turn_and_fresh_reader_keep_list_board_and_cover_consistent":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_handover_says_what_it_did_not_do.py::test_a_computed_register_reaches_the_handover":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_handover_says_what_it_did_not_do.py::test_an_empty_queue_is_a_finding_and_an_absent_one_is_not":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_handover_says_what_it_did_not_do.py::test_the_persisted_derivation_is_replaced_and_never_merged":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_issues_survive_a_turn.py::test_an_issue_survives_a_read_that_forgets_it":
        'the issue list',
    "tests/test_the_issues_survive_a_turn.py::test_they_come_back_from_the_store_typed":
        'the issue list',
    "tests/test_the_judge_scores_what_was_served.py::test_a_served_turn_is_still_scored_in_full":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped); and the next step, its checks and its written explanation",
    "tests/test_the_judge_scores_what_was_served.py::test_the_judges_material_does_not_carry_a_refused_draft":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped); and the next step, its checks and its written explanation",
    "tests/test_the_judge_scores_what_was_served.py::test_the_record_says_the_turn_was_withheld":
        "a model-written working item that could withhold the turn (the model's words now reach only the composed reply, whose failing sentences are dropped); and the next step, its checks and its written explanation",
    "tests/test_the_matter_cover_tells_ten_files_apart.py::test_not_assessed_and_none_are_not_the_same_row":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_matter_cover_tells_ten_files_apart.py::test_the_board_reads_the_register_too":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_period_never_runs_from_an_unchosen_date.py::test_a_read_that_names_nothing_does_not_start_the_period":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_period_never_runs_from_an_unchosen_date.py::test_an_entry_that_is_not_on_the_chart_is_not_an_accrual":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_period_never_runs_from_an_unchosen_date.py::test_the_limb_reaches_the_advocate":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_period_never_runs_from_an_unchosen_date.py::test_the_period_runs_from_the_entry_the_read_named[first]":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_period_never_runs_from_an_unchosen_date.py::test_the_period_runs_from_the_entry_the_read_named[last]":
        'the limitation position, its thresholds and the deadline register',
    "tests/test_the_theory_survives_a_turn.py::test_a_blocked_turn_does_not_erase_the_standing_theory":
        'the case theory and the adverse-fact read',
    "tests/test_the_theory_survives_a_turn.py::test_a_theory_that_changes_says_what_stopped_fitting":
        'the case theory and the adverse-fact read',
    "tests/test_the_theory_survives_a_turn.py::test_it_comes_back_from_the_store_typed":
        'the case theory and the adverse-fact read',
    "tests/test_the_theory_survives_a_turn.py::test_the_theory_is_the_same_across_four_turns":
        'the case theory and the adverse-fact read',
    "tests/test_theory_on_a_served_turn.py::test_a_theory_reaches_the_advocate":
        'the case theory and the adverse-fact read',
    "tests/test_what_must_happen_before_a_filing.py::test_a_threshold_with_its_own_renderer_is_not_said_twice":
        'the limitation position, its thresholds and the deadline register (the filing thresholds)',
    "tests/test_what_must_happen_before_a_filing.py::test_the_served_turn_names_the_condition_a_cheque_matter_engages":
        'the limitation position, its thresholds and the deadline register (the filing thresholds)',
    "tests/test_whether_a_filing_will_be_accepted.py::test_the_advocate_is_told_which_instrument_is_missing":
        'the limitation position, its thresholds and the deadline register (the filing thresholds)',
    "tests/test_whole_matter_dispute_agenda.py::test_served_engine_keeps_scoped_accounts_and_persists_all_disputes":
        'the opposing-argument read and the cross-dispute pass',
}
