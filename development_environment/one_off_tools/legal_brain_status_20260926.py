"""Record the build status of every legal-brain row, from the code as it stands.

OWNER DIRECTION, 26 September 2026: look at the codebase, see what is already
built, and record for every legal-brain row whether it is built, partially
built or not built. Legal brain only.

THE RULE APPLIED TO EVERY ROW, stated once so the statuses are comparable:

  Built        the row's behaviour works on the served path and its acceptance
               criteria have tests that exercise them.
  In progress  (the workbook's word for PARTIALLY BUILT) a real part of the
               row's behaviour is in production code on the served path, but
               its acceptance is not met.
  Not started  none of the row's specific behaviour exists. Supporting code
               may exist and is named in the gap.

WHAT IS NOT CLAIMED. Verification status (column 40) is left as it is:
building is not acceptance, and no row's acceptance criteria were run as
written for this pass. The evidence is code inspection plus the named tests,
which passed in the full suite at eeed3c8; no product code has changed since.

WHERE IT IS WRITTEN. The Implementation Plan sheet's own columns -- Build
status (39), Evidence references (41), Test date / environment (43) and
Remaining gaps (44) -- which is where this workbook keeps build state. Before
Build is not given a second copy: two places holding one status is two owners.
A readable table of every row is also written to
development_environment/reviews/LEGAL_BRAIN_STATUS_20260926.md.

EVERY CITED PATH IS CHECKED TO EXIST before anything is written, so the
evidence column cannot name a file that is not there.
"""
import copy
import hashlib
import importlib.util
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from assurance.common._console import utf8_console  # noqa: E402

utf8_console()

_spec = importlib.util.spec_from_file_location(
    "regroup", Path(__file__).with_name("legal_brain_regroup_20260926.py"))
regroup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(regroup)

SOURCE = regroup.SOURCE
REVIEW = _REPO / "development_environment/reviews/LEGAL_BRAIN_STATUS_20260926.md"
WHEN = ("26 September 2026: code inspection in the build container against commit eeed3c8's product "
        "code (unchanged since); cited tests passed in that commit's full suite. Acceptance criteria not "
        "run as written.")

B, P, N = "Built", "In progress", "Not started"
T = "tests/"
C = "backend/nm/core/"
D = "backend/nm/domain/"
K = "backend/nm/knowledge/"

#: id -> (status, evidence paths, what remains). The gap says what is missing
#: for a partial row, and names the supporting code for a row not started.
ASSESS = {
    # ------------------------------------------------------------- L.0 entry
    "OM-Q01": (B, [T+"test_opening_brief_is_durable.py", T+"test_a_brief_lands_exactly_once.py",
                   T+"test_opening_journey.py", T+"features/open_a_matter/F-B-01.feature"],
               "Live unscripted browser review with unknowns and several parties (AC) not recorded."),
    "OM-Q02": (P, [C+"screens.py", C+"conflict.py", T+"test_screens.py", T+"test_a_new_party_stales_the_clearance.py",
                   T+"test_capacity_admission_uses_a_record_not_prose.py", T+"test_scope_admission_needs_an_attributed_record.py"],
               "Each screen across positive/unknown/unavailable/stale/negative states is not demonstrated as a "
               "population; restriction of conflict-match detail to authorised recipients not evidenced."),
    "OM-Q03": (P, ["backend/nm/edge/uploads.py", T+"test_upload_containment_survives_path_resolution.py",
                   T+"test_uploaded_never_means_read.py", T+"test_media_never_reaches_reasoning_unadmitted.py"],
               "Uploads are received, typed and contained, but no document extraction, OCR or media "
               "transcription exists, so nothing uploaded is read for meaning."),
    "OM-Q04": (P, [T+"test_a_brief_lands_exactly_once.py", T+"test_owed_work_happens_once_or_says_it_cannot_tell.py",
                   T+"test_two_turns_cannot_lose_a_write.py", T+"test_conversation_recovery_journey.py"],
               "Tab close/reopen, logout and wrong-matter late results are not all exercised."),
    "OM-Q05": (P, [C+"retention.py", T+"test_held_and_erased_are_decisions.py"],
               "Backups and processor copies are not accounted for before certifying erasure."),
    "OM-Q06": (P, [T+"test_opening_journey.py", "frontend/matter-workspace.js"],
               "Live model judgment on the first contribution needs approved live evaluation."),
    "OM-I01": (P, [T+"features/take_the_brief/F-C-01.feature", T+"features/take_the_brief/F-C-02.feature",
                   "backend/nm/domain/dictation.py"],
               "Typing, dictation and upload exist; uploaded documents and media are not extracted or transcribed."),
    "OM-I02": (P, [T+"test_uploaded_never_means_read.py", T+"test_original_intake_is_sealed_resumable_and_unread.py"],
               "Store-only is enforced; an explicit request to examine an upload cannot proceed because nothing "
               "extracts it."),
    "OM-I03": (P, [T+"test_no_phrase_list_decides.py", T+"test_reasoning_communication_discipline.py"],
               "Today's pipeline runs a fixed sequence of reads; the free, principle-guided choice of next action "
               "is the loop in L.2 (LB-128), not yet built."),
    "F-B-01": (B, [T+"features/open_a_matter/F-B-01.feature", T+"test_arrive_sign_in_features.py"], "None recorded."),
    "F-B-02": (B, [T+"features/open_a_matter/F-B-02.feature", T+"test_arrive_sign_in_features.py"], "None recorded."),
    "F-B-03": (B, [T+"features/open_a_matter/F-B-03.feature", T+"test_arrive_sign_in_features.py"], "None recorded."),
    "F-B-04": (B, [T+"features/open_a_matter/F-B-04.feature", T+"test_arrive_sign_in_features.py"], "None recorded."),
    "F-B-05": (P, [T+"features/take_the_brief/F-C-01.feature", T+"features/take_the_brief/F-C-02.feature"],
               "Upload, mic and typing are offered; uploaded material is not understood (no extraction)."),
    "F-B-06": (B, [C+"conflict.py", T+"test_a_new_party_stales_the_clearance.py", T+"test_screens.py"],
               "No executable scenario for this feature yet."),
    "F-B-07": (P, [T+"test_the_role_is_quoted_from_its_own_dispute.py", T+"test_the_opponent_is_remembered.py"],
               "Who instructs versus who the client is, with stated authority, is not held as its own record."),
    "F-B-08": (P, [T+"test_capacity_admission_uses_a_record_not_prose.py"],
               "Capacity is recorded; authority to instruct is not separately assessed."),
    "F-B-09": (P, [K+"jurisdiction.py", T+"test_the_court_filter_resolves.py"],
               "Forum is carried where stated; an inferred forum is not proposed and confirmed."),
    "F-B-10": (B, [K+"coverage.py", T+"test_the_release_gate_fails_closed.py"], "No executable scenario for this feature yet."),
    "F-B-11": (P, [T+"test_recorded_urgency_is_visible_in_the_workspace.py", T+"test_deadlines.py"],
               "Urgency is recorded at opening; limitation is computed only once the cause and accrual are read."),
    "F-B-12": (P, [T+"test_the_matter_cover_tells_ten_files_apart.py", T+"test_thread_binding.py"],
               "Disputes within a matter are separated; two matters between the same parties are not detected."),
    "F-B-13": (P, [T+"test_the_matter_cover_in_the_browser.py"], "Matter state moves are not modelled as a lifecycle."),
    "F-B-14": (P, ["frontend/app.js"], "My work lists matters; behaviour at scale (search, paging) is not built."),
    "F-B-15": (N, [T+"test_no_internal_id_reaches_the_advocate.py"],
               "No protected-identity handling exists; the cited test concerns internal identifiers only."),
    "F-B-16": (P, [T+"test_original_materials_can_arrive_without_a_typed_brief.py"],
               "A matter can open from original files; nothing extracts parties, forum or dates from them."),
    "F-C-01": (B, [T+"features/take_the_brief/F-C-01.feature", T+"test_arrive_sign_in_features.py"], "None recorded."),
    "F-C-02": (B, [T+"features/take_the_brief/F-C-02.feature", "backend/nm/domain/dictation.py"], "None recorded."),
    "F-C-03": (B, [T+"features/take_the_brief/F-C-03.feature", "frontend/dictation-worklet.js"], "None recorded."),
    "F-C-04": (P, [C+"conversation.py", C+"intake.py"],
               "The message is read by fixed reads; the loop that decides to answer or ask is LB-128."),
    "F-C-05": (P, ["backend/nm/domain/gates.py", T+"test_grounding_gate.py"],
               "The checks decide what may leave; the model deciding freely awaits the loop (LB-128)."),
    "F-C-06": (P, [T+"test_premises_come_before_arithmetic.py", T+"test_correction_supersedes.py"],
               "Premises need confirmation; extracted values from documents (OCR) do not exist to confirm."),
    "F-C-07": (P, [D+"summary.py", T+"test_matter_memory.py"], "Verbatim retention of critical values in summaries is not proved across compression."),
    "F-C-08": (N, [], "No translation or original-language transcript handling exists."),
    "F-C-09": (P, [D+"summary.py", T+"test_matter_memory.py"], "Atoms and a recent window exist; the cited digest is not checked against the file."),
    "F-C-10": (B, [T+"test_one_data_key_per_matter.py", T+"test_the_matter_store_uses_its_own_key.py"], "None recorded."),
    "F-C-11": (P, [T+"test_matter_memory.py", T+"test_a_correction_is_served_and_survives_restart.py"],
               "Context is rebuilt from the store; resumption after an abrupt stop mid-turn is not exercised."),
    "F-C-12": (P, [C+"retention.py", T+"test_held_and_erased_are_decisions.py"], "The 30-day audio rule is moot until voice notes are transcribed."),
    "LB-02": (P, [T+"test_a_brief_lands_exactly_once.py", T+"test_protected_arrive_drafts.py"],
              "Long input with critical detail at its end, and switching matter mid-processing, not exercised."),
    "LB-37": (P, [T+"test_media_never_reaches_reasoning_unadmitted.py"],
              "Typed journey works; no medium beyond typing and dictation is extracted."),
    # ------------------------------------------------------- L.1 principles
    "OM-P01": (P, [T+"test_the_role_is_quoted_from_its_own_dispute.py", C+"posture.py"],
               "Encoded in reads; held-out live evaluation not run."),
    "OM-P02": (P, [C+"conversation.py"], "Encoded in reads; held-out live evaluation not run."),
    "OM-P03": (P, [T+"test_turn_contract.py", T+"test_the_opponent_is_remembered.py"],
               "Questions already answered are not re-asked; held-out live evaluation not run."),
    "OM-P04": (P, [T+"test_no_prohibited_inference_is_asked_for_or_accepted.py"], "Held-out live evaluation not run."),
    "OM-P05": (P, [C+"gaps.py", T+"test_gaps.py"], "Questions are ranked by what they block; held-out live evaluation not run."),
    "OM-P06": (P, [T+"test_the_account_says_where_a_fact_came_from.py", T+"test_repetition_never_becomes_evidence.py"],
               "Held-out live evaluation not run."),
    "OM-P07": (P, [T+"test_an_unfinished_answer_is_never_a_short_one.py"], "Held-out live evaluation not run."),
    "OM-P08": (P, [T+"test_the_independence_read_reasons_before_it_rules.py"], "Held-out live evaluation not run."),
    "OM-P09": (P, [T+"test_recorded_urgency_is_visible_in_the_workspace.py"], "Held-out live evaluation not run."),
    "OM-P10": (P, [T+"test_the_research_workflow_is_served.py"], "Held-out live evaluation not run."),
    "OM-P11": (P, [T+"test_nothing_files_or_sends_and_unknown_stays_unknown.py", T+"test_no_proactive_work_runs_unasked.py"],
               "Enforcement is tested; held-out live evaluation not run."),
    "OM-P12": (P, [T+"test_one_data_key_per_matter.py", T+"test_retrieval_trust_boundaries.py"],
               "Boundaries are tested; synthetic-marker breach evaluation not run."),
    "OM-P13": (P, [T+"test_the_product_does_not_speak_in_identifiers.py", T+"test_every_advocate_facing_renderer_speaks_english.py"],
               "Held-out live evaluation not run."),
    "OM-P14": (P, [T+"test_the_theory_survives_a_turn.py", T+"test_the_issues_survive_a_turn.py"], "Held-out live evaluation not run."),
    "LB-04": (P, [T+"test_reasoning_communication_discipline.py"], "Blinded review of register and praise not run."),
    "LB-17": (P, [T+"test_the_independence_read_reasons_before_it_rules.py"], "Preference/pressure invariance not evaluated."),
    "LB-39": (N, ["docs/GOLDEN_SET.md"], "No pressure-invariance or held-out generalisation evaluation exists; the golden set is the starting population."),
    "LB-113": (P, [T+"test_reasoning_communication_discipline.py"], "Multi-dispute transcript judging with negative controls not run."),
    "LB-126": (P, [T+"test_prompt_consistency.py", T+"test_what_the_model_is_told.py"],
               "A shared reasoning discipline is composed in code; no owner-edited principles document with its "
               "version recorded per turn."),
    # ------------------------------------------------------------ L.2 loop
    "LB-127": (N, ["backend/nm/ports/model.py"], "The model port has complete, structured and embed only; no tool calling."),
    "LB-128": (N, [C+"turn.py"], "The turn engine is a fixed pipeline; only evidence retrieval loops (at most 3 rounds)."),
    "LB-140": (P, [T+"test_adversarial_on_a_served_turn.py", T+"test_the_cross_file_pass_is_honest.py",
                   T+"test_the_adverse_read_knows_whose_side.py"],
               "Adverse, attack and cross-file reads exist; the three passes as grounded nested loops do not."),
    "LB-163": (N, [], "The guided method depends on the loop (LB-128) and the principles document (LB-126)."),
    "LB-164": (N, [T+"test_model_calls_are_kept.py"], "Model calls are kept; no typed step events, no step log, no streaming."),
    "LB-139": (N, ["backend/nm/edge/api.py"], "No streaming endpoint and no scratch-pad panel; /api/turn returns one finished answer."),
    "LB-01": (P, [T+"test_whole_matter_dispute_agenda.py", T+"test_one_message_many_disputes.py"],
              "Stage-free choice of next action awaits the loop."),
    "LB-03": (P, [C+"relief.py", T+"test_scope_admission_needs_an_attributed_record.py"],
              "Objective and scope are recorded; client constraints versus instruction are not held separately."),
    "LB-05": (P, [C+"gaps.py", T+"test_gaps.py"], "Needless-repetition and burden measurements not run."),
    "LB-35": (P, ["backend/nm/adapters/model/call_budget.py", T+"test_live_evaluation_budget.py"],
              "Latency and cost by task type are not recorded."),
    "LB-36": (P, [T+"test_briefing_readiness_is_not_completion.py"], "Distinct stop reasons (sufficient, awaiting, no-progress, budget) not all modelled."),
    "LB-61": (P, [C+"investigation.py", C+"lead.py", T+"test_bounded_judgment_investigation.py"],
              "Bounded investigations can be proposed; a general next-action choice awaits the loop."),
    "LB-64": (P, [C+"investigation.py", T+"test_bounded_judgment_investigation.py"], "No-progress stops and resume triggers not all modelled."),
    "LB-69": (P, ["backend/nm/adapters/model/call_budget.py", D+"delegation.py"], "No whole-task budget across children and retries."),
    "LB-70": (P, ["frontend/matter-workspace.js", "frontend/source-reader.js"], "Progress, stop and resume reasons are not shown; the scratch pad is LB-139."),
    "LB-110": (P, [T+"test_whole_matter_dispute_agenda.py"], "As previously recorded."),
    "LB-116": (P, [T+"test_whole_matter_dispute_agenda.py"], "As previously recorded."),
    "LB-118": (P, [T+"test_conversational_requirements.py"], "As previously recorded."),
    # ----------------------------------------------------------- L.3 tools
    "LB-129": (N, [K+"elements.py", K+"institution.py"], "No tool layer; the capabilities it would expose exist and are tested."),
    "LB-154": (N, [], "No envelope, registry or tool rules exist yet."),
    "LB-155": (N, [D+"matter.py"], "The matter model exists; no read or write tools over it."),
    "LB-156": (N, [K+"manifest.py", K+"governing_law.py"], "Exact Act resolution and provision fetch exist; not exposed as tools."),
    "LB-157": (N, ["backend/nm/ports/search.py", K+"authority_weight.py"], "Search, expand, passage, resolve, treatment exist; not tools; no find_contrary_authority."),
    "LB-158": (N, [C+"limitation.py", C+"deadlines.py"], "Limitation and deadlines exist; no date-arithmetic or interest tool."),
    "LB-159": (N, [K+"interim_relief.py", K+"procedural_period.py"], "The curated tables exist and are wired into the pipeline; not tools; no playbooks."),
    "LB-160": (N, [C+"consistency.py"], "Consistency check exists; no verify_support, research or oppose tools."),
    "LB-161": (N, [C+"service.py"], "Question record and action paths exist; no submit_answer claim structure."),
    "LB-162": (N, [], "No tool discovery exists."),
    # -------------------------------------------------- L.4 retrieval/grounding
    "LB-130": (P, [C+"grounding.py", T+"test_grounding_gate.py"],
               "Propositions are checked against retrieved spans; the answer is not submitted as typed claims."),
    "LB-137": (P, ["backend/nm/domain/citation.py", T+"test_citation_patterns.py", T+"test_bounded_judgment_investigation.py"],
               "Exact Act identity is enforced; retrieval rounds are still decided by code, not chosen by the model."),
    "LB-144": (P, [T+"test_a_step_cannot_contradict_the_figures.py", T+"test_arithmetic_cannot_establish_the_law.py"],
               "Figures are computed deterministically; no check that every number in an answer maps to a computation."),
    "LB-11": (P, [T+"test_inventory_on_a_served_turn.py", "backend/nm/edge/uploads.py"], "Examined ranges and extraction records do not exist (no extraction)."),
    "LB-13": (P, [T+"test_corpus_search.py", T+"test_authority_retrieval.py", K+"manifest.py"], "Adverse-proposition search and recorded stopping basis not complete."),
    "LB-14": (P, [K+"jurisdiction.py", K+"citator.py", T+"test_which_authority_this_court_must_follow.py"],
              "Binding, treatment and bench are weighed; factual analogy and distinction are not assessed."),
    "LB-25": (P, ["frontend/source-reader.js", T+"test_source_reader_journey.py"], "No readable basis view linking conclusions to premises and passages."),
    "LB-26": (P, [T+"test_saved_source_reader.py", C+"dependency.py"], "Reverse dependencies are recorded; not navigable from a source in the browser."),
    "LB-27": (P, [T+"test_current_document_reader.py", T+"test_saved_source_reader.py"], "Applicability explanation shown separately from the text is not complete."),
    "LB-57": (P, [T+"test_grounding_gate.py", T+"test_one_quotable.py"], "Semantic support is mostly reported not assessed (see LB-141)."),
    "LB-59": (P, [C+"dependency.py", C+"premise.py"], "Claim types and inference premises are not one recorded structure."),
    "LB-100": (P, [T+"test_reads_registry.py", K+"source_registry.py"], "As previously recorded."),
    "LB-101": (P, [T+"test_corpus_search.py"], "As previously recorded."),
    "LB-102": (P, [T+"test_research_does_not_claim_unearned_coverage.py"], "As previously recorded."),
    "LB-103": (P, ["backend/nm/ports/evidence.py"], "Support is carried as true/false/not assessed; it is rarely assessed."),
    "LB-104": (P, [T+"test_the_authority_query_is_spent_on_law.py"], "As previously recorded."),
    "LB-105": (P, [T+"test_bounded_judgment_investigation.py"], "As previously recorded."),
    "LB-106": (P, ["backend/nm/adapters/search/authority.py"], "Lexical (FTS) retrieval only; the dense leg was refused (S11) and no fusion or reranking exists."),
    "LB-107": (P, [T+"test_citation_patterns.py"], "As previously recorded."),
    "LB-108": (P, [T+"test_corpus_conformance.py"], "As previously recorded."),
    # ------------------------------------------------------------ L.5 harness
    "LB-131": (P, ["backend/nm/domain/gates.py", T+"test_gate_matrix.py"],
               "The eighteen output checks run on every pipeline answer; the loop they must follow does not exist."),
    "LB-132": (P, ["backend/nm/domain/gates.py", T+"test_the_emergency_route_admits_only_protection.py"],
               "The six boundaries are enforced on answers; tool calls do not exist to be gated."),
    "LB-133": (P, [T+"test_the_repair_constrains_what_the_first_answer_got_wrong.py"],
               "A bounded, constrained retry exists for structured reads; failed answer checks withhold without feedback to the model."),
    "LB-134": (N, ["backend/nm/domain/gates.py"], "Awaiting the owner's floor-or-principle decision for each of the thirteen gates."),
    "LB-141": (N, ["backend/nm/ports/evidence.py"], "No independent verifier; G-GROUND discloses semantic support as not assessed."),
    "LB-143": (P, [D+"delegation.py", C+"professional_access.py"], "Admission exists for delegated specialist tasks; no per-tool-call checks or step-log process evidence."),
    "LB-31": (P, [T+"test_a_decision_is_recorded.py", T+"test_options_are_compared_and_decisions_recorded.py"],
              "Reconsideration on material change not evidenced."),
    "LB-32": (P, [T+"test_unapproved_egress_fails_closed.py", T+"test_every_live_destination_is_policed.py"],
              "Revocation during tool execution cannot be tested until tools exist."),
    "LB-33": (P, [T+"test_retrieval_trust_boundaries.py"], "Injection into each supported source channel not exercised (uploads are not read)."),
    "LB-38": (P, ["backend/nm/domain/gates.py", T+"test_grounding_gate.py"], "Qualified semantic review not run."),
    "LB-60": (P, [T+"test_what_the_model_is_told.py", T+"test_prompt_consistency.py", T+"test_model_port_contract.py"],
              "Versioned per-call policy identity not recorded on each request."),
    "LB-62": (P, [D+"delegation.py", T+"test_bounded_specialist_delegation.py", T+"test_the_model_is_policed_before_it_is_called.py"],
              "No shared admission for model-chosen tools (they do not exist)."),
    "LB-63": (P, [T+"test_the_transactional_store_refuses_by_construction.py", T+"test_two_turns_cannot_lose_a_write.py"],
              "Candidate versus accepted results are separated for delegation only."),
    "LB-66": (P, ["backend/nm/domain/gates.py"], "Checks record state and detail; not inputs, performer and versions as one verification record."),
    "LB-67": (P, [T+"test_recorded_answers_are_not_presented_as_fresh_advice.py", T+"test_grounding_gate.py"],
              "Streaming, exports and drafts are not all under one release service."),
    "LB-71": (P, [T+"test_provider_independence.py", T+"test_model_port_contract.py"], "No per-role model qualification on held-out behaviour."),
    "LB-114": (P, [T+"test_the_period_never_runs_from_an_unchosen_date.py"], "As previously recorded."),
    "LB-119": (P, [T+"test_capacity_admission_uses_a_record_not_prose.py"], "As previously recorded."),
    # -------------------------------------------------------- L.6 context/memory
    "LB-135": (P, [D+"summary.py", T+"test_matter_memory.py"], "The advocate's words are kept; summaries are not re-checked against the file; file is not read on demand by tool."),
    "LB-136": (P, [T+"test_the_research_workflow_is_served.py", T+"test_bounded_specialist_delegation.py"],
               "Research and delegation exist; not a fresh-context nested loop returning spans."),
    "LB-142": (P, [T+"test_an_accepted_span_is_kept_as_written.py", T+"test_correction_supersedes.py"],
               "Facts and premises carry quotes and corrections supersede; writes are made by reads, not by checked tools."),
    "LB-145": (P, [T+"test_the_account_says_where_a_fact_came_from.py", D+"summary.py"],
               "Facts carry their source; the layered, tagged context assembly is not built."),
    "LB-147": (N, [], "No stable-prefix or append-only conversation handling; each read builds its own prompt."),
    "LB-148": (N, [], "No tool discovery and no playbooks."),
    "LB-149": (P, ["backend/nm/ports/search.py"], "Expand and passage page by locator; nothing clears spent results."),
    "LB-150": (N, [], "No compaction."),
    "LB-151": (N, [], "No advocate memory."),
    "LB-152": (P, [T+"test_two_turns_cannot_lose_a_write.py", T+"test_a_stale_server_says_so.py"],
               "Stale writes are refused at commit; no change notice to a running model."),
    "LB-153": (P, [T+"test_provider_independence.py", "backend/nm/ports/model.py"], "The port is provider-neutral with a shared context budget; no context policy in the harness yet."),
    "LB-08": (P, [T+"test_premises_come_before_arithmetic.py", T+"test_a_correction_reaches_exactly_what_it_touched.py"],
              "Premise confirmation and correction exist; document extraction does not."),
    "LB-10": (P, [T+"test_matter_memory.py"], "Cross-thread exposure and snapshot display partial."),
    "LB-12": (N, [], "No search over the matter's own material; uploads are not read."),
    "LB-29": (B, [T+"test_a_correction_reaches_exactly_what_it_touched.py", T+"test_the_journey_of_a_correction.py",
                  T+"test_only_the_affected_advice_reopens.py"], "Drafts as dependants not exercised in the journey."),
    "LB-30": (P, [T+"test_recorded_answers_are_not_presented_as_fresh_advice.py"], "Compare/export versions not built."),
    "LB-34": (P, [T+"test_owed_work_happens_once_or_says_it_cannot_tell.py"], "Cancellation during generation not exercised."),
    "LB-58": (P, [T+"test_matter_memory.py", T+"test_current_evidence_reaches_reasoning.py"], "Each run does not name its snapshot."),
    "LB-68": (P, [T+"test_only_the_affected_advice_reopens.py", T+"test_gaps_and_cascade_on_a_served_turn.py"],
              "Access withdrawal across caches and exports not exercised."),
    # ------------------------------------------------------- L.7 legal reasoning
    "LB-165": (P, [T+"test_proof_on_a_served_turn.py", T+"test_theory_on_a_served_turn.py", T+"test_relief_changes_the_recommendation.py"],
               "Proof, theory and relief exist per dispute; the seven-section per-dispute answer does not."),
    "LB-166": (P, [T+"test_conversational_requirements.py", "frontend/matter-workspace.js"],
               "The board shows a need per dispute; questions derived from passages and anticipated defences do not."),
    "LB-06": (P, [T+"test_recorded_urgency_is_visible_in_the_workspace.py", T+"test_deadlines.py"], "Justified reprioritisation not evaluated."),
    "LB-07": (B, [T+"test_repetition_never_becomes_evidence.py", T+"test_the_account_says_where_a_fact_came_from.py",
                  T+"test_one_sentence_is_one_fact.py"], "None recorded."),
    "LB-09": (P, [T+"test_chronology.py"], "Units, currencies and alias handling partial."),
    "LB-15": (P, [T+"test_a_contradiction_must_point_at_the_step.py"], "Respectful-challenge behaviour not evaluated."),
    "LB-16": (P, [T+"test_repetition_never_becomes_evidence.py"], "Authenticity versus admissibility versus weight not modelled."),
    "LB-18": (P, [T+"test_theory.py", T+"test_adversarial_on_a_served_turn.py"], "Disconfirmation conditions not recorded per theory."),
    "LB-19": (P, [T+"test_proof.py", T+"test_issues.py", K+"elements.py"], "Burdens and presumptions partial; elements curated for few causes."),
    "LB-20": (P, [T+"test_thresholds.py", T+"test_what_must_happen_before_a_filing.py"], "Forum, valuation and fee not assessable (LB-125)."),
    "LB-21": (P, [T+"test_factors.py"], "No fabricated-percentage control evidenced."),
    "LB-22": (P, [T+"test_options_are_compared_and_decisions_recorded.py", T+"test_relief_changes_the_recommendation.py"], "Sequence and option-loss explanation partial."),
    "LB-23": (P, [T+"test_the_drafting_package_is_checkable.py"], "Advocacy drafting from the brief partial."),
    "LB-28": (P, [T+"test_gaps.py", T+"test_disclosure_reaches_the_advocate.py"], "Coverage display against actual execution partial."),
    "LB-45": (P, [C+"thresholds.py", T+"test_an_interim_application_is_decided_on_its_own_test.py"], "Decision-maker, source of power and permitted record not modelled."),
    "LB-46": (P, [C+"hearing.py"], "No operative-record map of pleadings, orders and their status."),
    "LB-47": (P, [T+"test_issues_on_a_served_turn.py"], "Necessary premises versus independent routes not represented."),
    "LB-48": (P, [T+"test_inventory_on_a_served_turn.py", C+"investigation.py"], "Custodian, preservation and acquisition plan partial."),
    "LB-49": (P, [T+"test_preparation_does_not_invent_testimony.py"], "Recollection versus refreshed account not recorded."),
    "LB-50": (P, [C+"step_dependency.py"], "Irreversible-consequence and preclusion analysis not built."),
    "LB-51": (P, [C+"hearing.py"], "Concession boundaries exist in hearing preparation only."),
    "LB-52": (N, [], "No resolution-by-interests or settlement-terms analysis."),
    "LB-53": (N, [], "No specialist-referral or expert-report review capability."),
    "LB-54": (P, [C+"hearing.py", T+"test_the_journey_of_preparation.py"], "Answering a changed question against the brief not evaluated."),
    "LB-55": (N, [], "No advisory or transactional instrument review."),
    "LB-65": (P, [T+"test_adversarial_on_a_served_turn.py"], "Raised versus anticipated versus speculative arguments not separated."),
    "LB-109": (P, [T+"test_one_message_many_disputes.py", T+"test_thread_binding.py"], "As previously recorded."),
    "LB-112": (P, [T+"test_turn_contract.py"], "As previously recorded."),
    "LB-115": (P, [T+"test_the_adverse_read_knows_whose_side.py"], "As previously recorded."),
    "LB-117": (P, [T+"test_conversational_requirements.py"], "As previously recorded."),
    # ---------------------------------------------------- L.8 practice layer
    "LB-120": (P, [K+"governing_law.py", T+"test_which_code_governs_this_matter.py"],
               "The table and port are built and tested but deliberately unwired: no criminal cause exists in the closed vocabulary."),
    "LB-121": (P, [K+"institution.py", T+"test_what_must_happen_before_a_filing.py"],
               "Engaged conditions are named on the served turn; whether the file shows them done is not read; s.12A not curated (Act not held)."),
    "LB-122": (P, [K+"authority_weight.py", T+"test_which_authority_this_court_must_follow.py"],
               "Bench and court ranking reaches the answer; references to a larger bench and per incuriam are not detected."),
    "LB-123": (P, [K+"interim_relief.py", T+"test_an_interim_application_is_decided_on_its_own_test.py"],
               "The test is set out; limbs are not assessed against the record."),
    "LB-124": (P, [K+"procedural_period.py", T+"test_the_clocks_that_run_inside_a_proceeding.py"],
               "Periods are engaged and entered undated; no trigger date is read, so none is computed; the track is never established."),
    "LB-125": (P, [K+"filing_requirement.py", T+"test_whether_a_filing_will_be_accepted.py"],
               "The gap is measured and named; no forum, valuation or fee is computed (Telangana schedules not held)."),
    # ------------------------------------------------------- L.9 models/eval
    "LB-138": (N, [], "The loop does not exist to be built beside the pipeline."),
    "LB-146": (P, [T+"test_model_calls_are_kept.py", "backend/nm/adapters/model/scripted.py", "assurance/journeys/run_goldens.py"],
               "Model calls are kept and a scripted model exists; no replay adapter from recordings, no provider comparison."),
    "LB-40": (P, [T+"test_the_evaluation_ledger_admits_only_what_is_named.py", T+"test_a_rehearsal_is_evidence_about_people.py"],
              "No qualified Indian reviewer rubric has been run."),
    "LB-43": (P, ["assurance/control_plane/plan_scenarios.py"], "This status pass is part of it; delivery owners per clause not mapped."),
    "LB-44": (P, [], "Decisions open: LB-134 gates, LB-148 playbooks, pass-2 key details, thresholds and budgets."),
    "LB-56": (P, [T+"test_defect_register.py", T+"test_general_fix_contract.py"], "De-identified reusable evaluation material not separated."),
    "LB-72": (P, ["assurance/gate/mutate.py", T+"test_every_sweep_has_a_positive_control.py"], "Held-out multi-turn model evaluation not run."),
    "LB-73": (P, [T+"test_one_owner_per_rule.py", T+"test_reached_from_production.py"], "The cutover and migration for the loop are not specified."),
    "LB-74": (P, [], "Slices defined in LB-138; none started."),
}

HEADER = re.compile(r"^(L|L\.\d|U|U\.\d|P|X)  ")
ID = re.compile(r"^(LB-\d+|OM-[PIQ]\d+|F-[A-Z]-\d+)\b")


def legal_brain_ids(sheet):
    ids, group = [], None
    for r in range(regroup.FIRST, sheet.max_row + 1):
        text = str(sheet.cell(r, 1).value or "")
        h = HEADER.match(text)
        if h:
            group = h[1]
            continue
        m = ID.match(text)
        if m and group and group.startswith("L"):
            ids.append((m[1], group))
    return ids


def main() -> int:
    # EVERY CITED PATH EXISTS, before anything is written.
    missing = sorted({p for _s, paths, _g in ASSESS.values() for p in paths if not (_REPO / p).exists()})
    assert not missing, f"evidence names files that do not exist: {missing}"

    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    book = load_workbook(SOURCE)
    sheet, plan = book["Before Build"], book["Implementation Plan"]
    features = {s.title: regroup.sheet_features(s) for s in book}
    before = {(s.title, c.coordinate): (c.value, copy.copy(c._style)) for s in book for row in s for c in row}

    scope = legal_brain_ids(sheet)
    in_scope = {i for i, _g in scope}
    assert set(ASSESS) == in_scope, (f"not assessed: {sorted(in_scope - set(ASSESS))}; "
                                     f"assessed but not legal brain: {sorted(set(ASSESS) - in_scope)}")

    rows = {plan.cell(x, 1).value: x for x in range(2, plan.max_row + 1) if plan.cell(x, 1).value}
    changed = set()
    for ident, (status, paths, gap) in ASSESS.items():
        x = rows[ident]
        values = {39: status, 41: "; ".join(paths) if paths else "None -- nothing of this row exists in code.",
                  43: WHEN, 44: gap}
        for c, v in values.items():
            plan.cell(x, c).value = v
            changed.add(plan.cell(x, c).coordinate)

    out = Path("/tmp/claude-0/-home-user-Nyaymalaw/82a504d3-1374-501f-9fe3-441ac9aa966e/scratchpad") / SOURCE.name
    book.save(out)

    # ---- the proof ----------------------------------------------------------------
    check = load_workbook(out)
    for tab in check:
        assert regroup.sheet_features(tab) == features[tab.title], tab.title
    for (title, coord), old in before.items():
        if not (title == "Implementation Plan" and coord in changed):
            cell = check[title][coord]
            assert (cell.value, cell._style) == old, (title, coord)
    allowed = {row for row in plan.data_validations.dataValidation if "AM" in str(row.sqref)}
    allowed_values = set(next(iter(allowed)).formula1.strip('"').split(","))
    for status, _p, _g in ASSESS.values():
        assert status in allowed_values, status
    from assurance.control_plane import plan_scenarios
    assert plan_scenarios.requirement_problems(out) == []
    assert len(plan_scenarios.sheet_rows(out)) == 93
    shutil.copy2(out, SOURCE)

    # ---- the readable table --------------------------------------------------------
    titles = {}
    for r in range(regroup.FIRST, sheet.max_row + 1):
        text = str(sheet.cell(r, 1).value or "")
        m = ID.match(text)
        if m:
            lines = [l for l in text.split("\n") if l.strip()]
            titles[m[1]] = (lines[2] if len(lines) > 2 and m[1].startswith("LB-1") and int(m[1][3:]) >= 120
                            else (lines[2] if len(lines) > 2 and not m[1].startswith("F-") else ""))
    plan_titles = {plan.cell(x, 1).value: plan.cell(x, 6).value for x in range(2, plan.max_row + 1)}
    lines = ["# Legal brain -- build status, 26 September 2026", "",
             "Every legal-brain row in `docs/Nyaymalaw_Implementation_Plan.xlsx`, assessed against the code. "
             "Recorded in the Implementation Plan sheet's Build status, Evidence references, Test date and "
             "Remaining gaps columns.", "",
             "**Built** -- works on the served path, acceptance criteria have tests. "
             "**In progress** (partially built) -- a real part is in production code; acceptance not met. "
             "**Not started** -- none of the row's specific behaviour exists.", "",
             "Verification status is unchanged: building is not acceptance, and no acceptance criterion was run "
             "as written for this pass.", ""]
    by_group = {}
    for ident, group in scope:
        by_group.setdefault(group, []).append(ident)
    total = Counter(s for s, _p, _g in ASSESS.values())
    lines += [f"**Totals:** {total[B]} built, {total[P]} in progress, {total[N]} not started, of {len(ASSESS)}.", ""]
    for group, ids in by_group.items():
        c = Counter(ASSESS[i][0] for i in ids)
        lines += [f"## {group}  ({c[B]} built, {c[P]} in progress, {c[N]} not started)", "",
                  "| Row | Title | Status | Remaining |", "|---|---|---|---|"]
        for i in ids:
            status, _p, gap = ASSESS[i]
            title = str(plan_titles.get(i) or titles.get(i) or "").replace("|", "/")
            lines.append(f"| {i} | {title} | {status} | {gap.replace('|', '/')} |")
        lines.append("")
    REVIEW.write_text("\n".join(lines), encoding="utf-8")

    print(f"source digest before: {digest}")
    print(f"source digest after:  {hashlib.sha256(SOURCE.read_bytes()).hexdigest()}")
    print(f"rows assessed: {len(ASSESS)} -- {dict(total)}")
    for group, ids in by_group.items():
        c = Counter(ASSESS[i][0] for i in ids)
        print(f"  {group:<4} {len(ids):>3} rows: {c[B]:>2} built, {c[P]:>3} in progress, {c[N]:>2} not started")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
