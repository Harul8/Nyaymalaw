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
    "tests/test_prompt_consistency.py::test_purpose_reaches_the_served_answer_and_history_without_fabricating_a_recommendation[assessment]":
        'the next step, its checks and its written explanation (an unblocked answer need not lead with a step)',
    "tests/test_prompt_consistency.py::test_purpose_reaches_the_served_answer_and_history_without_fabricating_a_recommendation[explanation]":
        'the next step, its checks and its written explanation (an unblocked answer need not lead with a step)',
}
