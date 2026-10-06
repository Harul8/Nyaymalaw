Read-only guard-coverage audit, using temporary module copies and isolated
process-local monkeypatches. No repository production source was modified.

Six renderer mutants each ran an existing designated test with a passing
baseline. All six were detected:

- Remove the fresh display-field guard: consistent-looking authored text must
  still fail `test_fresh_writer_cannot_supply_display_fields_even_when_they_look_consistent`.
- Shorten original words: full negation, attribution and uncertainty must remain
  in `test_account_keeps_complete_negation_attribution_and_uncertainty`.
- Admit NM words as factual account: the role boundary must remain in
  `test_prior_nm_words_cannot_be_rendered_as_factual_account`.
- Drop current-use verification for directly selected legal passages:
  `test_direct_passage_needs_an_owned_current_use_check` must reject unchecked use.
- Substitute a foreign citation owner: exact checked source ownership must
  remain in `test_standalone_checked_passage_preserves_its_complete_condition`.
- Skip rendered-word equality: `test_deliberately_wrong_acceptance_or_block_kind_cannot_authorize_other_text`
  must reject altered text, including a completion label with a wrong accepting judge.

Six additional pure fresh-unit schema probes each ran a passing baseline and
then relaxed only the top-unit additionalProperties boundary in a process-local
hook. All detected the loss of rejection for writer-supplied record_check,
progress_checks, reviewed_record_check, record_outcome_contract, record_snapshot
and source_catalogue. These are direct owner probes, not integrated public
mutations: downstream redundant checks intentionally remain active.

Recommended integrated follow-up: keep the existing raw public all-block-kind,
linked-completion, foreign-selector and saved-replay-tamper tests as separate
release checks. If mutating one lower guard leaves those tests green because
an earlier independent schema gate rejects the attack, record that redundant
protection rather than claiming the disabled guard has no coverage. Mutate only
the designated helper in a private compiled copy; never disable every safeguard
in shared production or count unrelated exception failures as detection.

The 12-probe results are /tmp/nm-fresh-contract-mutation-probes.json; runnable
script is /tmp/nm-fresh-contract-mutation-probes.py. No browser/provider ran.
Earlier independent 19/37/13/4 historical mutant populations remain unchanged
and are not rerun or added to this small population. These probes qualify
mechanical guard coverage, not actual model semantics, false-positive rates,
professional legal correctness or complete mutation adequacy.
