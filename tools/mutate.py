"""Mutation check: break the code on purpose, prove the test catches it.

    python tools/mutate.py

WHY THIS IS A TOOL AND NOT A ONE-OFF
------------------------------------
A suite that passes on its first run has proved nothing. Each mutation below
reintroduces a defect the previous build actually shipped; the named test must
go RED, or that test is decoration.

It also writes `counterexamples_rejected` into `.nm/eval_results.json`, which is
the evidence `tools/trace.py` needs for check T6. Running is not the same as
biting: an eval that has run but never rejected its counterexample is an
unexercised claim, and T6 reports it as one.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools._fingerprint import source_fingerprint  # noqa: E402

# (label, file, original, mutation, test that must fail, eval it proves)
MUTATIONS = [
    ("posture read off the events rather than off what was stated",
     "nm/core/posture.py",
     "    if not _FIRST_PERSON.search(quoted):",
     "    if False and not _FIRST_PERSON.search(quoted):",
     "test_posture_is_never_inferred_from_familiar_vocabulary", "E-030"),

    ("a posture settled on a span the advocate never wrote",
     "nm/core/posture.py",
     "    if _fold(quoted) not in _fold(said):",
     "    if False and _fold(quoted) not in _fold(said):",
     "test_posture_is_never_inferred_from_familiar_vocabulary", "E-030"),

    # THE GUARD READS THE ADVOCATE'S WORDS, NOT THE PROMPT. Widening it
    # back to everything the model was shown lets the extractor quote our
    # own blocking question -- which names both sides -- and settle a
    # posture nobody stated. Every other guard passes.
    # THE CALL SITE CHOOSES WHICH STRING THE GUARD SEES, and that is where
    # this broke: handing it the PROMPT rather than the advocate's words
    # let the extractor quote our own blocking question -- which names both
    # sides -- and settle a posture nobody stated.
    ("the verbatim guard handed the prompt instead of the advocate's words",
     "nm/core/turn.py",
     '                advocate_words=memory.advocate_words if memory else "")',
     '                advocate_words=memory.as_context() if memory else "")',
     "test_a_question_asked_twice_is_not_put_a_third_time_in_the_same_words",
     "E-036"),

    ("a question stays open after the gate that raised it stopped firing",
     "nm/domain/matter.py",
     "        out = tuple(q if (not q.open or q.gate in gates)",
     "        out = tuple(q if True",
     "test_a_question_the_advocate_answered_is_never_asked_again", "E-035"),

    ("a question asked twice is put a third time in the same words",
     "nm/core/turn.py",
     "            if standing is not None and standing.ignored:",
     "            if False and standing is not None and standing.ignored:",
     "test_a_question_asked_twice_is_not_put_a_third_time_in_the_same_words",
     "E-035"),

    ("retrieval reads the latest message alone, not the file",
     "nm/core/turn.py",
     '                            account=memory.account if memory else "")',
     '                            account="")',
     "test_every_model_call_in_a_turn_receives_the_file", "E-036"),

    # AN ACT IS CARRIED BY EXACT TITLE, NEVER BY KEYWORD. Common words run
    # through every Indian statute, and an account is every sentence the
    # advocate has ever said -- so keyword-scoring it is the outvoting
    # defect with the most evidence it will ever have behind it.
    ("the account widened the keyword scoring instead of only the title",
     "nm/knowledge/manifest.py",
     "            carried = self._named_in(account.lower(), on)",
     "            low = low + ' ' + account.lower()\n"
     "            carried = self._named_in(account.lower(), on)",
     "test_an_act_named_earlier_is_carried_by_exact_title_only", "E-036"),

    ("an out-of-vocabulary role accepted instead of blanked",
     "nm/core/posture.py",
     "        role = Role(raw_role)",
     "        role = Role.PLAINTIFF",
     "test_a_role_outside_the_products_vocabulary_is_blanked", "E-030"),

    # B-037. "our client" identifies nobody, and recording it produced
    # "You act for the our client. Did they file...?"
    ("a descriptor that names nobody recorded as though it named someone",
     "nm/core/posture.py",
     "    if described and names_nobody(described):",
     "    if False and described and names_nobody(described):",
     "test_a_descriptor_that_names_nobody_is_not_recorded", "E-030"),

    # B-039's trigger, widened until it swallows C3. The role read must not
    # fire on an account of events -- "the landlord has issued a quit notice
    # to the tenant" names two parties and neither is stated to be ours.
    ("the role read firing without the advocate stating their own side",
     "nm/core/turn.py",
     "                    or posture_reader.speaks_of_the_representation(said)):",
     "                    or True):",
     "test_an_account_of_events_never_settles_a_posture_on_the_engine", "E-030"),

    # B-040. The validator was in the test double and the adapter that ships
    # skipped it, so an `enum` was decoration on the production path.
    ("the declared schema unenforced on the adapter that ships",
     "nm/adapters/model/openai_adapter.py",
     "            require_schema(data, schema)",
     "            pass  # require_schema(data, schema)",
     "test_a_schema_violation_is_never_best_effort_parsed", "E-004e"),

    # B-042. A required enum with no member for the ordinary case. The read
    # then fails validation, fails OPEN, and looks exactly like the advocate
    # having said nothing.
    ("a required enum with no value for 'nothing was established'",
     "nm/core/posture.py",
     '            "enum": ["stated", "inferred", "not_stated"],',
     '            "enum": ["stated", "inferred"],',
     "test_every_declared_schema_is_satisfiable_when_nothing_was_established",
     "E-030"),

    # B-041, BOTH DIRECTIONS. The gate blocks the DIRECTIVE STEP, so the
    # boundary can fail by being too loose (a side-flavoured authority set
    # presented as the law) or too tight (a bare question of law refused).
    # A boundary with a counterexample on one side only is half a boundary.
    ("an authority set assembled behind a closed posture gate",
     "nm/core/turn.py",
     "        if self._wants_authority(turn.message) and not side_blind:",
     "        if self._wants_authority(turn.message):",
     "test_nothing_side_dependent_is_computed_behind_a_closed_gate", "E-034"),

    ("a directive step recommended behind a closed posture gate",
     "nm/core/turn.py",
     "        if not side_blind:\n"
     "            elements.append(",
     "        if True:\n"
     "            elements.append(",
     "test_nothing_side_dependent_is_computed_behind_a_closed_gate", "E-034"),

    ("a bare question of law refused instead of answered",
     "nm/core/turn.py",
     "            derived, relied_on, retrieved = self._derive(\n"
     "                thread, turn, metrics, memory, side_blind=True,\n"
     "                facts=matter.facts)\n"
     "            elements.extend(derived)",
     "            pass",
     "test_a_provision_is_still_read_back_behind_a_closed_posture_gate",
     "E-034"),

    # A1.2. `min_length=1` counts CHARACTERS, so "   " opened a matter --
    # an anonymous session on a file nothing can attribute.
    ("an identifier made of whitespace accepted as an identity",
     "nm/domain/matter.py",
     '        if not (advocate_id or "").strip():',
     '        if False and not (advocate_id or "").strip():',
     "test_an_anonymous_session_cannot_create_a_matter", "E-010"),

    # A1.1. A 404 that differs between "no such matter" and "not yours"
    # is an oracle: it discloses WHICH MATTERS EXIST to someone who can
    # read none of them.
    ("a failed lookup disclosing whether the matter exists",
     "nm/edge/api.py",
     '        raise HTTPException(status_code=404, detail="no such matter")',
     '        raise HTTPException(status_code=404,\n'
     '                            detail=("no such matter" if m is None\n'
     '                                    else "not your matter"))',
     "test_a_failed_credential_discloses_nothing_about_which_matters_exist",
     "E-010"),

    # I1.2. A turn whose metrics could not be written has no record of
    # having happened, and swallowing that leaves the advocate advised
    # and the file silent about it.
    ("an audit-trail write failure swallowed",
     "nm/core/turn.py",
     "        self._store.record_metrics(metrics.as_dict())\n"
     "        return TurnOutput(turn.turn_id, answer, matter, metrics)",
     "        try:\n"
     "            self._store.record_metrics(metrics.as_dict())\n"
     "        except Exception:\n"
     "            pass\n"
     "        return TurnOutput(turn.turn_id, answer, matter, metrics)",
     "test_an_audit_trail_write_failure_is_never_swallowed", "E-019"),

    # RG-11's own honesty: a recorded run that cannot say what it ran
    # against would let a mutation pass from three commits ago certify
    # today's code.
    ("a recorded run vouching for code it never saw",
     "tools/releasegate.py",
     '    if rec.get("source_fingerprint") != now:',
     '    if False and rec.get("source_fingerprint") != now:',
     "test_a_recorded_run_cannot_vouch_for_code_it_never_saw", "E-008"),

    # ---- S0: the foundations. Each of these had RUN and never bitten. ----

    # E-001. The whole value of a pure core is the class-A cadence, and it
    # is lost the first time one I/O import sneaks in.
    ("the core permitted to reach an adapter",
     "tools/layercheck.py",
     '    "core": {"core", "ports", "domain"},',
     '    "core": {"core", "ports", "domain", "adapters"},',
     "test_layercheck_fails_the_build_on_a_core_module_that_reaches_an_adapter",
     "E-001"),

    # E-004. A model identifier in the core is how a step stops declaring a
    # TIER and starts naming a provider's model.
    ("a model identifier planted in the core",
     "nm/core/grounding.py",
     "from __future__ import annotations",
     "from __future__ import annotations\n"
     "\n"
     "_MODEL = \"gpt-4o-mini\"  # planted",
     "test_no_model_name_or_provider_client_appears_in_the_core", "E-004"),

    # E-003. A streamed turn once recorded llm_calls: 0, which made an
    # entire turn invisible to the cost baseline.
    ("a model call not counted against the turn",
     "nm/domain/metrics.py",
     "        self.llm_calls += 1",
     "        self.llm_calls += 0",
     "test_every_turn_writes_metrics_with_latency_calls_tokens_and_model_mix",
     "E-003"),

    # E-004b. Providers move aliases, and without a pin a metric that moved
    # is indistinguishable from a regression you caused.
    ("a floating model alias accepted instead of a dated snapshot",
     "nm/adapters/model/config.py",
     "    if not _PINNED.search(model):",
     "    if False and not _PINNED.search(model):",
     "test_every_tier_resolves_to_a_pinned_dated_snapshot", "E-004b"),

    # E-004c. A judged run graded by the model that wrote the answer is not
    # a measurement.
    ("the judge allowed to be the model under test",
     "nm/adapters/model/config.py",
     "    if judge is None:",
     "    if True:",
     "test_the_judge_never_resolves_to_the_model_under_test", "E-004c"),

    # E-004g. Every call sends privileged client material to a third party,
    # so the allow-list is a confidentiality decision, not a technical one.
    ("an unlisted provider accepted at startup",
     "nm/adapters/model/config.py",
     "    if provider not in PERMITTED_PROVIDERS:",
     "    if False and provider not in PERMITTED_PROVIDERS:",
     "test_an_unlisted_provider_fails_at_startup", "E-004g"),

    # E-004d. An adapter that truncates silently makes a prompt that does
    # not port pass locally.
    ("a context overflow truncated instead of typed",
     "nm/adapters/model/_budget.py",
     "    if size > budget:",
     "    if False and size > budget:",
     "test_context_overflow_is_typed_never_a_truncation", "E-004d"),

    # E-004f. Querying an index across embedding models does not error --
    # it returns plausible, confidently wrong neighbours.
    ("an index built with one embedding model queried with another",
     "nm/knowledge/artefact.py",
     "        if expected_model.lower() not in self.builder.lower():",
     "        if False and expected_model.lower() not in self.builder.lower():",
     "test_a_real_mismatched_index_is_refused", "E-004f"),

    # E-002d. A theory scenario running at S4 fails for the wrong reason,
    # and the suite stops meaning what its name says.
    ("a slice suite selecting scenarios it cannot yet run",
     "tools/run_goldens.py",
     "        return [s for s in scenarios if s.slice <= n]",
     "        return list(scenarios)",
     "test_slice_n_selects_exactly_the_scenarios_runnable_by_then", "E-002d"),

    # E-021b. Two turns interleaving on one derivation graph would each
    # compute from a state neither of them saw.
    ("a stale commit overwriting instead of refusing",
     "nm/adapters/store/file_store.py",
     "            if current is not None and current.version > expected_version:",
     "            if False and current is not None:",
     "test_a_stale_commit_is_refused_rather_than_overwriting", "E-021b"),

    # E-020b. A turn that ran out of rounds and said nothing is
    # indistinguishable from one that found everything it needed.
    ("the evidence bound reached without a visible gap",
     "nm/core/turn.py",
     "        if metrics.evidence_rounds >= MAX_EVIDENCE_ROUNDS:",
     "        if False and metrics.evidence_rounds >= MAX_EVIDENCE_ROUNDS:",
     "test_reaching_the_evidence_bound_produces_a_visible_gap", "E-020b"),

    # ---- S1-S3: the turn, the evidence contract, thread identity -------

    # E-017. The advocate must never receive advice the file does not
    # record. Better to fail before showing than to show and fail to save.
    ("advice emitted without the commit that records it",
     "nm/core/turn.py",
     "            matter = self._store.commit(matter, expected_version=expected_version)",
     "            pass  # commit skipped",
     "test_a_turn_commits_atomically_and_the_commit_precedes_emission",
     "E-017"),

    # E-015. A streamed turn whose first token is model prose and whose
    # duty screen returns after it. The invariants are asserted ON THE
    # ASSEMBLED OBJECT before anything is released.
    ("an answer handed to the transport without going through _release",
     "nm/edge/api.py",
     "    return _release(output)",
     "    return output  # bypasses the single exit",
     "test_nothing_is_released_except_through_the_byte_boundary", "E-015"),

    # E-032. A rename that orphans the chronology. The label is a display
    # name; the id is generated once and never derived from it.
    ("a rename that drops the old label instead of keeping it as an alias",
     "nm/domain/matter.py",
     "        aliases = self.aliases if self.label in self.aliases"
     " else self.aliases + (self.label,)",
     "        aliases = self.aliases",
     "test_a_renamed_thread_keeps_its_id_and_its_old_label", "E-032"),

    # E-033. A wrong split duplicates work and is visible. A WRONG MERGE
    # attaches the wrong posture and limitation to facts they do not
    # govern, and inverts the advice invisibly.
    ("a merge PERFORMED instead of proposed when two threads share a number",
     "nm/core/threading.py",
     "    if len(matches) > 1:",
     "    if False and len(matches) > 1:",
     "test_two_threads_with_one_identifier_propose_a_merge_and_never_perform_it",
     "E-033"),

    # E-006. TurnMetrics becoming provider-shaped is how the cost baseline
    # stops comparing across a switch.
    ("a model call whose cost is not normalised into the port's shape",
     "nm/adapters/model/openai_adapter.py",
     "                        cost_usd=cfg.cost(t_in, t_out), cached_tokens=cached),",
     "                        cost_usd=0.0, cached_tokens=cached),",
     "test_complete_returns_normalised_usage", "E-006"),

    # E-002c. A scenario added to `smoke` alone silently leaves the full
    # set, and the suite quietly becomes a different set.
    ("a scenario in no named suite passing unnoticed",
     "tools/run_goldens.py",
     "        if s.id not in covered:",
     "        if False and s.id not in covered:",
     "test_every_scenario_is_reachable_from_a_suite", "E-002c"),

    # E-002. A scenario citing a provision absent from every store. The
    # anchors are read back FROM THE CORPUS, on the bytes.
    ("a golden anchor accepted without reading it back from the corpus",
     "tools/run_goldens.py",
     "    if not adapter.available:",
     "    if True:",
     "test_every_golden_provision_reads_back_from_the_corpus", "E-002"),

    # E-021. A DEFAULT IS A DECISION TAKEN ON BEHALF OF EVERY CALL SITE
    # THAT FORGETS, and the three this type used to carry were each the
    # safe-looking wrong answer: para_kind UNKNOWN makes a submission read
    # as a holding, binding BINDING makes another State's High Court bind
    # Telangana, absent treatment makes an overruled case read as good law.
    ("a Finding constructible without the binding status that makes it usable",
     "nm/ports/evidence.py",
     "    binding: Binding",
     "    binding: Binding = Binding.BINDING",
     "test_a_finding_cannot_be_built_without_what_makes_it_auditable", "E-021"),

    ('a Finding constructible without the paragraph kind that makes it attributable',
     "nm/ports/evidence.py",
     "    para_kind: ParaKind",
     "    para_kind: ParaKind = ParaKind.UNKNOWN",
     "test_a_finding_cannot_be_built_without_what_makes_it_auditable", "E-021"),

    # E-013. A turn ending in a pros-and-cons table with no view is the
    # junior's survey, and it is not advice.
    # E-013. A turn ending in a pros-and-cons table with no view is the
    # junior's survey, and it is not advice. THE TYPE is the enforcement:
    # the metrics check that used to sit in the engine could never fire,
    # because the constructor had already refused the case.
    ("an answer with no recommendation and no blocking question",
     "nm/domain/answer.py",
     "        if first.kind not in (ElementKind.ACTION, ElementKind.QUESTION):",
     "        if False and first.kind not in (ElementKind.ACTION,):",
     "test_the_first_content_element_is_an_action_or_a_blocking_question",
     "E-013"),

    # E-025. An inference rendered with a citation attached. The grounding
    # gate holds ASSERTING elements to their findings and leaves
    # disclosures alone, and collapsing the two either punishes the product
    # for being honest or lets an unusable source ground an answer.
    ("an assertion citing what was never retrieved",
     "nm/core/grounding.py",
     "        if element.disclosure:",
     "        if True:",
     "test_a_proposition_carries_a_finding_and_an_inference_never_does",
     "E-025"),

    # E-004h. A prompt built to fill one provider's context does not port,
    # and finding that out at switch time defeats the whole design. The
    # budget is the PORT'S, declared once, not each provider's.
    ("the context budget taken from the provider instead of the port",
     "nm/adapters/model/config.py",
     "    Tier.ROUTINE: 100_000,",
     "    Tier.ROUTINE: 2_000_000,",
     "test_context_budget_is_declared_by_the_port_not_the_provider", "E-004h"),

    # E-005. An abstraction nobody has switched is an unexercised claim.
    # The scripted adapter is the SECOND PROVIDER, and it satisfies the
    # same Protocol or the port has quietly become OpenAI-shaped.
    ("an adapter that no longer satisfies the port protocol",
     "nm/adapters/model/scripted.py",
     "    def embed(self, texts: tuple[str, ...]) -> EmbeddingResult:",
     "    def embeddings(self, texts: tuple[str, ...]) -> EmbeddingResult:",
     "test_adapter_satisfies_the_port_protocol", "E-005"),

    # E-014. A guard proven in the core and never reached on the wire is
    # not a guard. Every defect the first external review found lived in
    # exactly that gap, so each response class is driven through the app.
    ("a gate that fires in the core and never reaches the served path",
     "nm/core/turn.py",
     '            "G-UNSCREENED", "unscreened",',
     '            "G-COVERAGE", "unscreened",',
     "test_every_response_class_is_exercised_on_the_served_path", "E-014"),

    # E-024. B-164, the previous build's priority-one blocker: a coverage
    # report saying the Act holds 13 of 44 sections, measured from ONE
    # store, which struck three golden scenarios while the Acts were
    # complete the whole time.
    ("coverage measured from one store instead of the union",
     "spec/manifest.yaml",
     "  - '%SPECIFIC RELIEF ACT, 1963%'\n  - the_specific_relief_act_1963",
     "  - the_specific_relief_act_1963",
     "test_coverage_is_a_union_and_a_single_store_figure_is_refused", "E-024"),

    # B-052. A second thread could only be created by a NUMBER OF RECORD,
    # so a dispute described in prose was welded onto the one already open
    # -- and multi-thread files, which the golden set calls the normal
    # case, were unreachable.
    ("a new dispute welded onto the thread already open",
     "nm/core/threading.py",
     "        if opens_new_dispute is True:",
     "        if False and opens_new_dispute is True:",
     "test_a_second_dispute_does_not_inherit_the_first_thread_s_posture",
     "E-033"),

    # And the asymmetry as a DEFAULT: an unread dispute must never fall
    # back to the merge, which is the direction with no undo.
    ("an unread dispute defaulting to a merge",
     "nm/core/threading.py",
     "        if opens_new_dispute is False:",
     "        if opens_new_dispute is not True:",
     "test_a_dispute_read_that_could_not_tell_asks_rather_than_merging",
     "E-033"),

    # THE SWEEP MECHANISM ITSELF. One rule -- length is not content --
    # applied to 23 types by one decorator instead of 25 hand-written
    # guards. Removing it from a single type must be caught BY NAME.
    ("a required string field left accepting whitespace",
     "nm/domain/matter.py",
     "@refuses_blank_text()\n@dataclass(frozen=True)\nclass Thread:",
     "@dataclass(frozen=True)\nclass Thread:",
     "test_no_required_string_field_accepts_a_value_made_of_whitespace",
     "E-012"),

    # B-053. A matter that cannot be read must not VANISH -- the board
    # then looks complete, which is worse than failing to build.
    ("an unreadable matter dropped silently from the list",
     "nm/adapters/store/file_store.py",
     "                unreadable.append(p.stem)",
     "                pass",
     "test_a_matter_that_cannot_be_read_does_not_vanish_from_the_list",
     "E-063b"),

    # B-050 / B-054. Inlining a rule leaves its declared owner with no
    # callers -- the docstring then says the rule lives somewhere nothing
    # runs, and the next person hardens the copy that never executes.
    ("a rule inlined, leaving its declared owner consulted by nothing",
     "nm/core/turn.py",
     "            if not position.discloses:",
     "            if position.state is CoverageState.MET:",
     "test_no_function_in_the_product_is_defined_and_never_reached",
     "E-023"),

    # ---- S4 ------------------------------------------------------------

    # E-042. THE MEASURED DEFECT: an acknowledgment in the chronology that
    # never reached the arithmetic. Every other part of the answer was right.
    ("a chronology entry that never reaches the limitation computation",
     "nm/core/limitation.py",
     '                              "this entry was not examined against the period"))',
     '                              "no effect"))',
     "test_an_entry_nobody_examined_is_reported_as_not_assessed", "E-042"),

    # D2.3. Three years counted in days lands a day early across a leap
    # year, and a day is the whole of a limitation argument.
    ("a period counted in days where the statute counts by the calendar",
     "nm/core/limitation.py",
     "    return _clamped(on.year + years, on.month, on.day)",
     "    from datetime import timedelta as _t; return on + _t(days=365 * years)",
     "test_a_period_is_counted_by_the_calendar_and_never_in_days", "E-043"),

    # D3.2. A stored status cannot detect its own transition: `future`
    # written on Tuesday is still `future` on the Friday it passes.
    ("a deadline status that cannot reach `near`",
     "nm/core/deadlines.py",
     "        if self.on - today <= NEAR_WITHIN:",
     "        if False and self.on - today <= NEAR_WITHIN:",
     "test_a_deadline_can_reach_every_status_including_near", "E-046"),

    # D3.0. Dropping it tells the advocate there was never a deadline.
    ("a passed deadline listed among what is still upcoming",
     "nm/core/deadlines.py",
     "                 if d.status(today) in (DeadlineStatus.FUTURE, DeadlineStatus.NEAR))",
     "                 if True)",
     "test_a_passed_action_is_never_listed_among_what_will_not_wait", "E-046"),

    # D1.0. An advocate reading eight rows believes the ninth was checked.
    ("a threshold nobody assessed left off the map",
     "nm/core/thresholds.py",
     "        for t in Threshold)",
     "        for t in assessed)",
     "test_every_threshold_appears_on_the_map_even_when_nobody_assessed_it",
     "E-044"),

    ("a persisted field silently dropped on read",
     "nm/adapters/store/file_store.py",
     "                          for f in fields(cls) if f.name in value})",
     "                          for f in list(fields(cls))[:4] if f.name in value})",
     "test_every_field_of_a_matter_survives_a_save_and_load", "E-011"),

    ("a stated posture silently flipped (the turn-5 reversal)",
     "nm/domain/matter.py",
     "        return replace(\n"
     "            self,\n"
     "            conflicts=self.conflicts + (PostureConflict(on_record=self.role,"
     " now_suggested=role),),\n"
     "            version=self.version + 1,\n"
     "        )",
     "        return replace(self, role=role, basis=basis, version=self.version + 1)",
     "test_a_stated_posture_is_never_silently_flipped", "E-031"),

    ("route decided on word count",
     "nm/core/turn.py",
     "    if any(s in text for s in _MATTER_SIGNALS):",
     "    if len(text.split()) < 8:\n"
     '        return Route.NON_MATTER, Mode.SHORT_QUESTION, "short"\n'
     "    if any(s in text for s in _MATTER_SIGNALS):",
     "test_route_is_not_decided_on_message_length", "E-012"),

    ("matter state written in plaintext",
     "nm/adapters/store/file_store.py",
     "        blob = self._cipher.encrypt(json.dumps(_enc(matter)).encode(\"utf8\"))",
     "        blob = json.dumps(_enc(matter)).encode(\"utf8\")",
     "test_matter_state_is_not_plaintext_on_disk", "E-011"),

    ("a replayed turn applied twice",
     "nm/core/turn.py",
     "        if matter.has_applied(turn.turn_id):",
     "        if False and matter.has_applied(turn.turn_id):",
     "test_replaying_a_turn_does_not_apply_it_twice", "E-018"),

    ("a grounding violation softened instead of gating",
     "nm/core/turn.py",
     "        if metrics.gating_violations:",
     "        if False and metrics.gating_violations:",
     "test_a_finding_whose_span_does_not_support_gates_the_output", "E-020"),

    ("metrics not written when the turn fails",
     "nm/core/turn.py",
     "            metrics.latency_ms = int((time.perf_counter() - started) * 1000)\n"
     "            self._store.record_metrics(metrics.as_dict())\n"
     "            raise",
     "            metrics.latency_ms = int((time.perf_counter() - started) * 1000)\n"
     "            raise",
     "test_metrics_are_written_even_when_the_turn_fails", "E-019"),

    ("the board growing with turns",
     "nm/edge/projections.py",
     '        "row_count": len(rows),\n        "bounded_by": "thread_count",',
     '        "row_count": len(rows) + matter.version,\n'
     '        "bounded_by": "thread_count",',
     "test_the_boards_are_bounded_by_row_count_not_turns", "E-063"),

    ("the union collapsed to a single store (defect B-164)",
     "nm/adapters/evidence/corpus.py",
     "            for pattern in patterns:",
     "            for pattern in [p for p in patterns if not p.startswith('%')]:",
     "test_the_union_retrieves_a_section_the_thin_store_does_not_hold", "E-002b"),

    ("substance admitted before the screens (stop-ship #2)",
     "nm/core/turn.py",
     "        screens = self._run_screens(matter, turn, metrics)",
     "        matter, _pre = self._admit_facts(matter, turn)\n"
     "        screens = self._run_screens(matter, turn, metrics)",
     "test_the_screens_run_before_any_substance_is_admitted", "E-016"),

    ("another advocate's matter disclosed",
     "nm/edge/api.py",
     "    if m is None or m.advocate_id != advocate_id:",
     "    if m is None:",
     "test_another_advocates_matter_is_not_disclosed", "E-010"),

    # ---- slices 2 and 3: grounding, and the frame -------------------------
    ("a citation the answer invents (the fabricated section)",
     "nm/core/grounding.py",
     "    report.violations.extend(verify_citations(answer.elements, quotable))",
     "    # report.violations.extend(verify_citations(answer.elements, quotable))",
     "test_a_provision_the_answer_cites_but_never_retrieved_withholds_the_turn",
     "E-020"),

    ("a fabricated quotation",
     "nm/core/grounding.py",
     "    report.violations.extend(verify_quotes(answer.elements, quotable))",
     "    # report.violations.extend(verify_quotes(answer.elements, quotable))",
     "test_a_quotation_not_verbatim_in_a_retrieved_span_withholds_the_turn",
     "E-020"),

    ("an unchecked citator read as clearance (the overruled authority)",
     "nm/ports/evidence.py",
     "            if self.treatment.state is TreatmentState.NOT_CHECKED:",
     "            if False and self.treatment.state is TreatmentState.NOT_CHECKED:",
     "test_an_authority_whose_treatment_was_never_checked_cannot_carry_a_proposition",
     "E-022"),

    ("a post-bifurcation Andhra judgment silently treated as binding",
     "nm/knowledge/jurisdiction.py",
     "        if year < BIFURCATION.year:",
     "        if True:",
     "test_andhra_pradesh_after_the_bifurcation_is_not_assessed_rather_than_assumed",
     "E-002b"),

    ("superseded text served for a later governing date (the 2024 codes)",
     "nm/ports/evidence.py",
     "        if self.governing_date is not None and not self.in_force:",
     "        if False and self.governing_date is not None and not self.in_force:",
     "test_text_not_in_force_on_the_governing_date_cannot_carry_a_proposition",
     "E-023"),

    ("a thread bound by guessing instead of asking",
     "nm/core/threading.py",
     "    labels = \"; \".join(f\"{t.label!r}\" for t in matter.threads[:5])",
     "    return BindResult(BindState.BOUND, matter.threads[0], False, \"guessed\")\n"
     "    labels = \"; \".join(f\"{t.label!r}\" for t in matter.threads[:5])",
     "test_several_threads_and_no_identifier_blocks_rather_than_guessing",
     "E-030"),

    ("a merge performed rather than proposed",
     "nm/core/threading.py",
     "    if len(matches) > 1:",
     "    if False and len(matches) > 1:",
     "test_two_threads_with_one_identifier_propose_a_merge_and_never_perform_it",
     "E-031"),

    ("the corpus gap silently not disclosed",
     "nm/core/turn.py",
     "            self._disclose_coverage(turn, thread, metrics, grounds)",
     "            pass  # self._disclose_coverage(turn, thread, metrics, grounds)",
     "test_the_corpus_gap_is_disclosed_before_the_authority_search_not_after",
     "E-023"),

    ("a gate deciding its own response instead of reading the matrix",
     "nm/domain/metrics.py",
     "        if g.response is Response.WITHHOLD:",
     "        if False and g.response is Response.WITHHOLD:",
     "test_the_response_is_read_from_the_matrix_not_passed_in",
     "E-020"),

    ("an out-of-vocabulary gate state accepted",
     "nm/domain/metrics.py",
     "        if state not in g.states:",
     "        if False and state not in g.states:",
     "test_an_out_of_vocabulary_state_is_refused",
     "E-065"),

    ("a smaller bench treated as superseding a larger one",
     "nm/knowledge/identity.py",
     "    winner = (Precedence.LEFT if left.bench_size > right.bench_size",
     "    winner = (Precedence.LEFT if left.bench_size < right.bench_size",
     "test_a_larger_bench_supersedes_a_smaller_one_in_the_same_court", "E-022"),

    ("co-ordinate benches ranked instead of referred",
     "nm/knowledge/identity.py",
     "    if left.bench_size == right.bench_size:",
     "    if False and left.bench_size == right.bench_size:",
     "test_co_ordinate_benches_do_not_supersede_each_other", "E-022"),

    ("an unrecorded bench defaulting instead of blocking",
     "nm/knowledge/identity.py",
     "    if not (left.bench_known and right.bench_known):",
     "    if False and not (left.bench_known and right.bench_known):",
     "test_an_unrecorded_bench_blocks_the_comparison_rather_than_defaulting", "E-022"),

    ("a High Court bench out-ranking the Supreme Court",
     "nm/knowledge/identity.py",
     "    if left.tier != right.tier:",
     "    if False and left.tier != right.tier:",
     "test_the_supreme_court_is_senior_to_every_high_court", "E-022"),

    ("an unbuilt identity index clearing an authority",
     "nm/knowledge/identity.py",
     '                "the identity index is not built, so no judgment was searched "',
     '                "clean, nothing found "',
     "test_an_absent_index_answers_not_known_rather_than_defaulting", "E-023"),

    ("a disclosure treated as a citation (withholding the honest answer)",
     "nm/core/grounding.py",
     "        if element.disclosure:",
     "        if False and element.disclosure:",
     "test_naming_what_could_not_be_retrieved_is_not_citing_it",
     "E-023"),

    # ---- S4 / C5. THE CHART EVERY LIMITATION READS ITS ACCRUAL FROM ------

    # E-040. A date the advocate's words do not fix, taken anyway. An event
    # missing from the chart costs a question; an event wrongly dated costs a
    # limitation calculation the advocate acts on without knowing it was
    # invented.
    ("a date read from words the advocate never wrote",
     "nm/core/chronology.py",
     "        if _fold(expr) not in _fold(message):",
     "        if False and _fold(expr) not in _fold(message):",
     "test_a_date_read_from_words_the_advocate_never_wrote_is_refused",
     "E-040"),

    # E-040. Two dates for one event, silently resolved to the first. Picking
    # one is the silent resolution C5 forbids and C1 forbids twice over.
    ("two dates for one event collapsed instead of surfaced",
     "nm/core/chronology.py",
     "        if prior.date != f.date:",
     "        if False and prior.date != f.date:",
     "test_two_dates_for_one_event_are_surfaced_and_both_kept", "E-040"),

    # E-041. A recollection presented as a documented date. The limitation
    # position resting on it reads as settled either way.
    ("an asserted date labelled as documented",
     "nm/core/chronology.py",
     '        certainty = (Certainty.DOCUMENTED if raw.get("documented")',
     '        certainty = (Certainty.DOCUMENTED if True',
     "test_a_documented_date_and_an_asserted_one_are_not_the_same_thing",
     "E-041"),

    # ---- S4 ON THE SERVED PATH -------------------------------------------
    #
    # All five were LIVE, and none was visible to the unit suite. They are the
    # argument for CLAUDE.md §8: every defect the first external review found
    # lived between a correct module and the served path.

    # THE PERIOD THE PRODUCT SUPPLIED. `years=3` into every computation,
    # including one that had just retrieved Article 65 and its twelve years.
    # The Article was right, the accrual was right, every citation was right,
    # and the answer was wrong by nine years.
    ("a limitation period the product supplied rather than read",
     "nm/core/limitation.py",
     "        if found != (self.years, self.months, self.days):",
     "        if False and found != (self.years, self.months, self.days):",
     "test_the_period_cannot_be_supplied_by_the_product", "E-043"),

    # A PERIOD OF ZERO expires on the accrual date -- state COMPUTED, a real
    # date, a real day count, and every claim barred the day it arose.
    ("a period of zero accepted as a computed period",
     "nm/core/limitation.py",
     "        if not (self.years or self.months or self.days):",
     "        if False and (self.years or self.months or self.days):",
     "test_a_period_of_zero_is_refused_rather_than_computed", "E-043"),

    # E-045 was a class-A eval that ran only against the module. On a defending
    # thread their limitation is often the whole answer.
    ("the opponent's limitation never computed on a defending thread",
     "nm/core/turn.py",
     "        if thread.posture.side is Side.DEFENDING:",
     "        if False and thread.posture.side is Side.DEFENDING:",
     "test_on_a_defending_thread_the_turn_computes_the_opponents_limitation",
     "E-045"),

    # THE FIXED SENTENCE. Every recommendation carried
    # `no_deadline_reason="no statutory window identified on this turn"` --
    # a finding that nothing was found, asserted whether or not anything had
    # been looked for.
    ("an action that drops the by-when the register actually holds",
     "nm/core/turn.py",
     "        live = deadlines.upcoming(register, today)",
     "        live = ()",
     "test_a_recommended_action_carries_the_by_when_the_register_holds",
     "E-046"),

    # D3.1. A passed window presented as this action's by-when files the thing
    # that can no longer be done among the things that still can.
    ("a passed deadline presented as an action's by-when",
     "nm/core/turn.py",
     "        gone = deadlines.passed(register, today)",
     "        gone = (); return (register[0].on if register else None), None",
     "test_a_passed_deadline_never_becomes_the_by_when_of_an_action",
     "E-046"),

    # THE BOARD'S TWO NULLS. `deadlines=()` defaulted and the served endpoint
    # never passed a register, so every row read as a file with no deadlines.
    ("a board that cannot say whether a deadline register was computed",
     "nm/edge/projections.py",
     '                  "next_deadline_status": "not_assessed",',
     '                  "next_deadline_status": "none_on_this_thread",',
     "test_the_board_distinguishes_no_deadline_from_no_register", "E-046"),

    # S11. The list sorts nearest-deadline-first and reads `next_deadline`
    # first -- and that field was hard-coded None, so the rule never applied.
    ("a matter list whose nearest-deadline ordering cannot fire",
     "nm/edge/projections.py",
     '            "next_deadline": live[0].on.isoformat() if live else None,',
     '            "next_deadline": None,',
     "test_the_matter_list_orders_by_a_deadline_it_actually_holds", "E-046"),
]


def run_test(test: str) -> bool:
    env = dict(os.environ, NM_PARTIAL_RUN="1")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-k", test,
         "--no-header", "-x", "-p", "no:cacheprovider"],
        cwd=str(ROOT), capture_output=True, text=True, env=env)
    return r.returncode == 0


def main() -> int:
    survived: list[str] = []
    rejected: list[str] = []

    for label, rel, old, new, test, eval_id in MUTATIONS:
        path = ROOT / rel
        original = path.read_text(encoding="utf8")
        if old not in original:
            print(f"  SKIP      {label}\n            (anchor not found in {rel})")
            survived.append(label)
            continue
        path.write_text(original.replace(old, new, 1), encoding="utf8")
        try:
            still_passes = run_test(test)
        finally:
            path.write_text(original, encoding="utf8")
        if still_passes:
            print(f"  SURVIVED  {label}\n            -> {test} did NOT catch it")
            survived.append(label)
        else:
            print(f"  CAUGHT    {label}  [{eval_id}]")
            rejected.append(eval_id)

    results = ROOT / ".nm" / "eval_results.json"
    results.parent.mkdir(parents=True, exist_ok=True)
    doc: dict = {}
    if results.exists():
        try:
            doc = json.loads(results.read_text(encoding="utf8"))
        except json.JSONDecodeError:
            doc = {}
    doc["counterexamples_rejected"] = sorted(
        set(doc.get("counterexamples_rejected", [])) | set(rejected))
    # THE RUN RECORDS WHAT IT RAN AGAINST. Without this, a mutation run
    # from three commits ago would certify today's code to RG-11 -- an
    # artefact indistinguishable from a current one, which is the whole of
    # defect shape S11.
    doc["mutations"] = {
        "caught": len(MUTATIONS) - len(survived),
        "total": len(MUTATIONS),
        "survived": sorted(survived),
        "source_fingerprint": source_fingerprint(),
    }
    results.write_text(json.dumps(doc, indent=2), encoding="utf8")

    print()
    if survived:
        print(f"{len(survived)} of {len(MUTATIONS)} mutations SURVIVED. "
              f"Those tests are decoration.")
        return 1
    print(f"All {len(MUTATIONS)} mutations caught. The suite bites.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
