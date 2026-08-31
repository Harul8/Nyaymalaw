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

from tools._console import utf8_console  # noqa: E402

utf8_console()

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
     # Anchored on `posture_reader.interpret(`, because the cause read added
     # a second identical `advocate_words=` line in slice 5 and an anchor on
     # that line alone mutates whichever comes first.
     '            stated = posture_reader.interpret(\n'
     '                turn.message, res.data or {},\n'
     '                advocate_words=memory.advocate_words if memory else "")',
     '            stated = posture_reader.interpret(\n'
     '                turn.message, res.data or {},\n'
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
     '                            account=memory.account if memory else "",',
     '                            account="",',
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
     '        # else: a failed lookup must disclose nothing about what exists.\n'
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
     # Anchored on the FAILURE path's own line, because the same three-line
     # block also closes the G-STALE path and an anchor matching both mutates
     # whichever comes first.
     "            metrics.failure = f\"{type(exc).__name__}: {exc}\"\n"
     "            metrics.latency_ms = int((time.perf_counter() - started) * 1000)\n"
     "            self._store.record_metrics(metrics.as_dict())\n"
     "            raise",
     "            metrics.failure = f\"{type(exc).__name__}: {exc}\"\n"
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
     "    if m is None or m.advocate_id != advocate_id:\n"
     "        # The same response whether it does not exist or belongs to someone",
     "    if m is None:\n"
     "        # The same response whether it does not exist or belongs to someone",
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

    # ---- EVALS THAT HAD RUN AND NEVER BITTEN -----------------------------
    #
    # T6 reports these separately from "never run", and the distinction is the
    # point: an eval that has run is not evidence until something has failed
    # it. Each of these was green from the day it was written.

    # E-007. An abstraction nobody has switched is an unexercised claim.
    ("a composition root that branches on something other than the provider",
     "nm/bootstrap/composition.py",
     "    provider = config.for_tier(Tier.ROUTINE).provider",
     "    provider = 'openai' if config.for_tier(Tier.ROUTINE).model else 'scripted'",
     "test_the_composition_root_branches_on_the_provider_string_alone",
     "E-007"),

    # E-063c. A receiving advocate reading a summary with no proof positions
    # cannot tell whether there are none or whether the section was never
    # built. Those are opposite situations and the second is the dangerous one.
    ("a section that was never built reading as one with nothing to report",
     "nm/domain/summary.py",
     "        derived = {\"handover_complete\", \"handover_blockers\"}",
     "        derived = set(CASE_SUMMARY_SECTIONS)",
     "test_a_screen_that_was_never_run_is_not_reported_as_clear", "E-063c"),

    # E-063d. The nearest window leads, regardless of which thread is legally
    # the most interesting.
    ("a thread board that does not put the nearest window first",
     "nm/edge/projections.py",
     "    rows = nearest_first([_thread_row(t, deadlines, today)\n"
     "                          for t in matter.threads])",
     "    rows = [_thread_row(t, deadlines, today) for t in matter.threads]",
     "test_the_thread_board_puts_the_nearest_window_first", "E-063d"),

    # E-063e. The matter list growing with the threads inside its matters.
    ("a matter list whose length is not a function of matter count",
     "nm/edge/projections.py",
     "        \"bounded_by\": \"matter_count\",",
     "        \"bounded_by\": \"thread_count\",",
     "test_the_matter_list_is_bounded_by_matter_count", "E-063e"),

    # E-064. "A turn opening with a recital of the brief." The advocate reads
    # the first line and it is their own file read back to them.
    ("an answer opening with something other than an action or a question",
     "nm/core/turn.py",
     "        if first.kind not in (ElementKind.ACTION, ElementKind.QUESTION):",
     "        if False and first.kind not in (ElementKind.ACTION,):",
     "test_the_first_content_element_is_an_action_or_a_blocking_question",
     "E-064"),

    # E-066. "The board citing Article 66 while the answer reasons from
    # Article 65." Neither may hold its own copy.
    ("a board that holds a copy instead of reading the matter",
     "nm/edge/projections.py",
     '        "our_client_is": posture.role.value '
     'if posture.role is not Role.UNKNOWN else "unknown",',
     '        "our_client_is": "unknown",',
     "test_the_board_and_the_answer_derive_from_the_same_matter", "E-066"),

    # ---- S9. THE GAP QUEUE, THE CASCADE, QUARANTINE ----------------------

    # E-090. "A question asked to keep the conversation moving." The queue
    # always yielding something IS the manufactured question with a data
    # structure behind it.
    ("a queue that always has something to ask",
     "nm/core/gaps.py",
     "    ordered = rank(gaps)\n"
     "    return ordered[0] if ordered else None",
     "    ordered = rank(gaps)\n"
     "    return ordered[0] if ordered else Gap(\n"
     "        what=\"anything else?\", blocks=\"nothing\", thread=\"\")",
     "test_nothing_blocked_means_nothing_is_owed", "E-090"),

    # E-090. An unresolved posture makes everything below it worthless,
    # however interesting.
    ("a queue that ranks an interesting question above a blocking gate",
     "nm/core/gaps.py",
     "    return tuple(sorted(gaps, key=lambda g: g.priority))",
     "    return tuple(sorted(gaps, key=lambda g: -g.priority))",
     "test_the_queue_ranks_a_blocking_gate_above_everything_interesting",
     "E-090"),

    # E-090. Serial single questions make the advocate do the scheduling.
    ("questions asked across every thread at once",
     "nm/core/gaps.py",
     "    return tuple(g for g in rank(gaps) if g.thread == thread)",
     "    return rank(gaps)",
     "test_questions_are_batched_one_thread_at_a_time", "E-090"),

    # E-091. "NM asking to finish the current thread first." A build that
    # passes its stages by railroading the advocate has failed.
    ("NM finishing its own thread before following the advocate",
     "nm/core/gaps.py",
     "    return asked_about, leads(gaps)",
     "    top = leads(gaps)\n"
     "    return (top.thread if top else asked_about), top",
     "test_the_advocate_changes_subject_and_nm_follows_in_the_same_turn",
     "E-091"),

    # E-092. "A limitation date silently recomputed with no note that it
    # moved." Recomputing is right; recomputing SILENTLY is the failure.
    ("a corrected value recomputed with no note that it moved",
     "nm/core/cascade.py",
     "        elif old[d.name] != d.value:\n"
     "            out.append(Change(name=d.name, was=old[d.name], now=d.value))",
     "        elif False:\n"
     "            out.append(Change(name=d.name, was=old[d.name], now=d.value))",
     "test_a_corrected_fact_re_derives_dependents_and_reports_the_prior_value",
     "E-092"),

    # E-092. Silently ADDING a limitation date is the same defect as silently
    # moving one.
    ("a value computed for the first time, added silently",
     "nm/core/cascade.py",
     "        if d.name not in old:\n"
     "            out.append(Change(name=d.name, was=\"not computed before\",\n"
     "                              now=d.value))",
     "        if d.name not in old:\n"
     "            continue",
     "test_a_value_computed_for_the_first_time_is_a_change_with_no_prior",
     "E-092"),

    # E-092. THE THIRD PART, and the one a silent recompute loses: an advocate
    # who filed on Tuesday against a date that moved on Thursday needs telling.
    ("earlier advice left standing after the fact it rested on moved",
     "nm/core/cascade.py",
     "    names = {c.name for c in moved}\n"
     "    return tuple(a for a in prior if names & set(a.rested_on))",
     "    return ()",
     "test_advice_already_given_is_reported_as_superseded", "E-092"),

    # E-092. An empty `undo` is not "nothing needs undoing" -- it is nobody
    # having said.
    ("an unanswered undo question reading as nothing to undo",
     "nm/core/cascade.py",
     "    return tuple(c.name for c in moved if not c.undo.strip())",
     "    return ()",
     "test_advice_already_given_is_reported_as_superseded", "E-092"),

    # E-092's BOUND. A cascade announced every turn trains the advocate to
    # skip the section, and the real one arrives where they have learned to
    # ignore it.
    ("a cascade heading with nothing under it",
     "nm/core/cascade.py",
     "    if not moved:\n"
     "        return (\"Re-derived everything that rested on the corrected fact; \"\n"
     "                \"nothing changed.\",)",
     "    if not moved:\n"
     "        return ()",
     "test_where_re_derivation_changes_nothing_the_answer_is_one_line",
     "E-092"),

    # E-089. "Substance merged onto a file no conflict check had cleared."
    ("quarantined substance reachable before clearance",
     "nm/core/quarantine.py",
     "        return self._released",
     "        return True",
     "test_quarantined_substance_is_unreachable_until_a_human_clears_it",
     "E-089"),

    # E-089. A second release is a caller that believes it is clearing
    # something; telling it nothing happened leaves that belief in place.
    ("a quarantine that releases more than once",
     "nm/core/quarantine.py",
     "        if self._released:\n"
     "            raise AlreadyReleased(",
     "        if False:\n"
     "            raise AlreadyReleased(",
     "test_a_quarantine_releases_exactly_once_and_the_second_call_raises",
     "E-089"),

    # E-089. A repr is a log line waiting to happen.
    ("quarantined substance leaking through a repr",
     "nm/core/quarantine.py",
     '        return f"<Quarantined {state}: {self.held_because[:50]!r}>"',
     '        return f"<Quarantined {state}: {self._substance[:50]!r}>"',
     "test_quarantined_substance_is_unreachable_until_a_human_clears_it",
     "E-089"),

    # ---- S8. THEORY, THE ADVERSARIAL PASS, SALVAGE ------------------------

    # E-080. "A theory that works only if three documents are forgotten." It
    # reads perfectly -- the three are simply not mentioned.
    ("adverse facts the theory never accounts for, unreported",
     "nm/core/theory.py",
     "    handled = set(theory.explains) | set(theory.concedes)\n"
     "    return tuple(f for f in adverse if f not in handled)",
     "    return ()",
     "test_every_adverse_fact_is_explained_or_expressly_conceded", "E-080"),

    # E-080. No theory disposes of nothing. Returning () there would make a
    # thread with no theory look fully accounted for.
    ("no theory reading as every adverse fact handled",
     "nm/core/theory.py",
     "    if theory is None:\n"
     "        return tuple(adverse)",
     "    if theory is None:\n"
     "        return ()",
     "test_every_adverse_fact_is_explained_or_expressly_conceded", "E-080"),

    # E-080. A menu is the survey D6 rejects.
    ("two theories offered in parallel",
     "nm/core/theory.py",
     "    if len(mine) > 1:",
     "    if False and len(mine) > 1:",
     "test_exactly_one_theory_per_thread", "E-080"),

    # E-080. "The complainant has not proved his case" is a hope that the
    # other side fails, not a theory.
    ("a bare denial arrived at by default",
     "nm/core/theory.py",
     "        if self.stance is Stance.DENIAL and blank(self.chosen_because):",
     "        if False and self.stance is Stance.DENIAL:",
     "test_a_bare_denial_is_a_chosen_strategy_and_never_a_default", "E-080"),

    # E-081. "I never signed it" alongside "I signed it under a
    # misrepresentation". No string comparison shows it.
    ("two arguments needing opposite factual accounts, unflagged",
     "nm/core/theory.py",
     "                if fact in b.requires and b.requires[fact] != needed:",
     "                if False and fact in b.requires:",
     "test_two_arguments_needing_opposite_facts_are_flagged", "E-081"),

    # E-081. The alternative flag must not become an opt-out: "I never
    # borrowed the money, and in any event I repaid it" loses either way.
    ("the alternative plea used to suppress the inconsistency check",
     "nm/core/theory.py",
     "            if a.thread != b.thread:\n"
     "                continue",
     "            if a.thread != b.thread or b.in_the_alternative:\n"
     "                continue",
     "test_two_arguments_needing_opposite_facts_are_flagged", "E-081"),

    # E-081's positive control, in production. An argument committing to
    # nothing contradicts nothing, so a file of them reports health forever.
    ("an argument with no declared factual commitments, unreported",
     "nm/core/theory.py",
     "    return tuple(a.statement[:60] for a in arguments if not a.requires)",
     "    return ()",
     "test_an_argument_declaring_no_facts_cannot_be_silently_consistent",
     "E-081"),

    # E-082. "Emitted twice, or SILENTLY OMITTED." Omitted reads as "nothing
    # found" when nobody looked.
    ("a cross-file pass that never ran reading as one that found nothing",
     "nm/core/adversarial.py",
     "    if found is None:\n"
     "        return ExposureReport(\n"
     "            ExposureState.NOT_RUN,\n"
     "            not_run_because=\"the cross-file pass did not run on this turn\")",
     "    if found is None:\n"
     "        return ExposureReport(ExposureState.NONE_FOUND)",
     "test_cross_thread_exposure_is_produced_exactly_once_empty_or_not",
     "E-082"),

    # E-082. A section that appears only sometimes is one the advocate cannot
    # rely on being there.
    ("a single-thread file given no exposure report at all",
     "nm/core/adversarial.py",
     "    if len(threads) < 2:\n"
     "        return ExposureReport(ExposureState.NONE_FOUND)",
     "    if len(threads) < 2:\n"
     "        return ExposureReport(ExposureState.NOT_RUN,\n"
     "                              not_run_because=\"one thread\")",
     "test_cross_thread_exposure_is_produced_exactly_once_empty_or_not",
     "E-082"),

    # E-083. An attack with no answer and one expressly unanswerable are
    # different findings: work not done, versus a fact about the case.
    ("a recommended step with no stated opposing case",
     "nm/core/adversarial.py",
     "        if not self.no_answer and blank(self.our_answer):",
     "        if False and not self.no_answer:",
     "test_every_attack_carries_our_answer_or_says_there_is_none", "E-083"),

    # E-084. "Consider a different forum", with no forum named.
    ("a salvage route stated at category level",
     "nm/core/adversarial.py",
     "        if self.route and not self.findings:",
     "        if False and self.route:",
     "test_no_salvage_route_is_stated_at_category_level", "E-084"),

    # E-084. An unmarked route reads as a recommendation NM would run.
    ("a salvage route carrying no strength",
     "nm/core/adversarial.py",
     "        if self.route and self.strength is Strength.NOT_ASSESSED:",
     "        if False and self.route:",
     "test_no_salvage_route_is_stated_at_category_level", "E-084"),

    # E-084. A report that varied two coordinates and concluded the case is
    # dead has not done the work, and the two make it look as though it had.
    ("coordinates nobody moved, unreported",
     "nm/core/adversarial.py",
     "    done = {s.coordinate for s in considered}\n"
     "    return tuple(c.value for c in Coordinate if c not in done)",
     "    return tuple(s.coordinate.value for s in considered\n"
     "                 if s.coordinate not in {x.coordinate for x in considered})",
     "test_coordinates_nobody_moved_are_named", "E-084"),

    # ---- S7. PROOF AND BURDEN --------------------------------------------

    # E-070. THE COUNTEREXAMPLE: a conclusion where two of five elements have
    # no proof position at all. The conclusion looked complete -- three
    # elements worked carefully, two never mentioned. Short is invisible.
    ("a proof-coverage gate that certifies itself",
     "nm/core/proof.py",
     "    have = {p.element.strip().lower() for p in positions}\n"
     "    return tuple(e for e in elements if e.strip().lower() not in have)",
     "    want = {e.strip().lower() for e in elements}\n"
     "    return tuple(p.element for p in positions\n"
     "                 if p.element.strip().lower() not in want)",
     "test_the_coverage_gate_cannot_certify_itself", "E-070"),

    # E-070. "To what standard" is half of whether the material is enough. An
    # element HELD to the wrong standard is not held.
    ("a proof status with no standard behind it",
     "nm/core/proof.py",
     "        if self.status is not ProofStatus.NOT_ASSESSED \\\n"
     "                and self.standard is Standard.NOT_ESTABLISHED:",
     "        if False and self.standard is Standard.NOT_ESTABLISHED:",
     "test_a_status_without_a_standard_cannot_be_constructed", "E-070"),

    # E-070. A presumption is a section, and one asserted from memory decides
    # who loses when the evidence is silent.
    ("a burden shifted by a presumption nobody cited",
     "nm/core/proof.py",
     "        if self.shifted_by and not self.shift_provision.strip():",
     "        if False and self.shifted_by:",
     "test_a_presumption_that_shifts_the_burden_names_its_provision", "E-070"),

    # E-071. "You cannot prove the loan", full stop.
    ("a proof gap reported as a verdict",
     "nm/core/proof.py",
     "        if self.status is ProofStatus.OBTAINABLE and blank(self.closing_material):",
     "        if False and self.status is ProofStatus.OBTAINABLE:",
     "test_a_proof_gap_is_never_a_verdict", "E-071"),

    ("an absent element with no express dead end",
     "nm/core/proof.py",
     "        if self.status is ProofStatus.ABSENT and blank(self.dead_end):",
     "        if False and self.status is ProofStatus.ABSENT:",
     "test_a_proof_gap_is_never_a_verdict", "E-071"),

    # E-072. "Your client is concealing the payment." NM has not met the
    # client and holds no material on which a credibility finding could rest.
    ("an answer that judges the client rather than the file",
     "nm/core/turn.py",
     "            for sentence in proof.characterises_the_client(element.text):",
     "            for sentence in ():",
     "test_the_served_turn_records_a_characterisation_of_the_client", "E-072"),

    # E-072, THE BOUND. A check that fired on the opponent too would teach the
    # product to hedge, and D5.1 says the drift to design against is
    # SOFTENING, not accusing.
    ("a restraint that spreads from the client to the opponent",
     "nm/core/proof.py",
     "        if _CHARACTER.search(sentence) and _OURS.search(sentence):",
     "        if _CHARACTER.search(sentence):",
     "test_the_restraint_does_not_extend_to_the_opponent_or_to_the_finding",
     "E-072"),

    # C7. The original agreement is with the opponent's brother and no
    # preservation step exists. The file reads as worked and the document is
    # gone by the time it is needed.
    ("an item at risk with no preservation step, unreported",
     "nm/core/evidence_item.py",
     "    return tuple(i.what for i in items\n"
     "                 if i.at_risk and i.preservation is None)",
     "    return ()",
     "test_an_item_at_risk_with_no_preservation_step_is_reported", "E-070"),

    # C7. Admissible and persuasive are different questions, and the third was
    # missing entirely from the original contract.
    ("a weight asserted with no reason to argue or challenge",
     "nm/core/evidence_item.py",
     "        if self.weight is not Weight.NOT_ASSESSED and blank(self.weight_reason):",
     "        if False and self.weight is not Weight.NOT_ASSESSED:",
     "test_existence_admissibility_and_weight_are_three_separate_questions",
     "E-070"),

    # ---- S6. THE ISSUE THAT WAS SPOTTED AND THEN LOST --------------------

    # E-060. THE MEASURED COUNTEREXAMPLE: classification discarded 20.1% of
    # all issue labels ever spotted -- 641 of 3,192 -- led by limitation,
    # bail, and forum or jurisdiction.
    ("a classifier that filters instead of dispositioning",
     "nm/domain/issue.py",
     "    return tuple(replace(i, disposition=given[i.id]) if i.id in given else i\n"
     "                 for i in spotted)",
     "    return tuple(replace(i, disposition=given[i.id]) if i.id in given else i\n"
     "                 for i in spotted if i.kind is not IssueKind.THRESHOLD)",
     "test_every_issue_that_enters_classification_comes_out_of_it", "E-060"),

    # E-060. A conservation check that reports a NUMBER cannot say which three
    # were lost, and which three is the whole difference between a rounding
    # error and an advocate missing a deadline.
    ("a conservation check that cannot name what was lost",
     "nm/domain/issue.py",
     "    return tuple(i.statement[:80] for i in spotted if i.id not in out)",
     "    return ()",
     "test_the_conservation_check_names_what_was_lost", "E-060"),

    # E-060. A deletion with extra steps is still a deletion.
    ("an issue parked with no reason",
     "nm/domain/issue.py",
     "        if self.state in (DispositionState.PARKED, DispositionState.CLOSED) \\\n"
     "                and blank(self.reason):",
     "        if False and self.state in (DispositionState.PARKED,):",
     "test_an_issue_stopped_without_a_reason_cannot_be_constructed", "E-060"),

    # E-061. "A limitation point labelled `bar` regardless of side." The label
    # carries an opinion about whose problem it is, and it is wrong for half
    # the advocates who read it.
    ("an effect that does not turn with the posture",
     "nm/domain/issue.py",
     "        if self.runs_against is posture.side:\n"
     "            return Effect.OPPOSES, posture.version\n"
     "        return Effect.SUPPORTS, posture.version",
     "        return Effect.OPPOSES, posture.version",
     "test_the_same_issue_on_opposite_postures_yields_opposite_effect", "E-061"),

    # E-061. An unresolved posture yielding `neutral` is a finding that the
    # issue helps nobody, which nobody established.
    ("an unassessed effect rendered as neutral",
     "nm/domain/issue.py",
     "            return Effect.NOT_ASSESSED, posture.version",
     "            return Effect.NEUTRAL, posture.version",
     "test_an_effect_is_never_stored_and_so_cannot_survive_its_own_reversal",
     "E-061"),

    # E-062. `tracks {'civil': 2, 'revenue': 1}` passing unvalidated and
    # emptying the charge map. It entered through the path nobody guarded.
    ("an out-of-vocabulary facet value propagated",
     "nm/domain/issue.py",
     "    except (ValueError, AttributeError):\n"
     "        return default",
     "    except (ValueError, AttributeError):\n"
     "        return value",
     "test_an_out_of_vocabulary_facet_value_is_blanked_whichever_path_supplied_it",
     "E-062"),

    # E-063f. A thread the advocate deferred vanishing from the board. They
    # deprioritised it believing they would see it again.
    ("a deferred thread dropped from the board",
     "nm/edge/projections.py",
     "    rows = nearest_first([_thread_row(t, deadlines, today)\n"
     "                          for t in matter.threads])",
     "    rows = nearest_first([_thread_row(t, deadlines, today)\n"
     "                          for t in matter.threads if not t.deferred_reason])",
     "test_a_deferred_thread_stays_on_the_board_with_its_deadline", "E-063f"),

    # ---- S5. RESOLUTION BEFORE SEARCH ------------------------------------

    # E-050. A need silently dated today retrieves the CURRENT text for
    # conduct in 2023 -- confidently, with a real citation, and the 2024 codes
    # make that the difference between right and wrong.
    ("a query without a governing date defaulted to today",
     "nm/ports/evidence.py",
     "        if self.governing_date is None:\n"
     "            raise ValueError(",
     "        if False and self.governing_date is None:\n"
     "            raise ValueError(",
     "test_a_query_without_a_governing_date_is_rejected_not_defaulted_to_today",
     "E-050"),

    # E-051. THE COUNTEREXAMPLE IN THE PLAN, WORD FOR WORD: a governing
    # Article arrived at by ranking. Two defaults made a ranked guess and an
    # exact lookup indistinguishable from the Finding's own data.
    ("a resolved Finding carrying a similarity score",
     "nm/ports/evidence.py",
     "        if self.origin is Origin.RESOLVED and self.confidence is not None:",
     "        if False and self.origin is Origin.RESOLVED:",
     "test_a_resolved_finding_cannot_carry_a_similarity_score", "E-051"),

    # E-051. A candidate presented as an answer is the search-first design
    # H3 replaces.
    ("a searched Finding that drops the confidence it was ranked on",
     "nm/ports/evidence.py",
     "        if self.origin is Origin.SEARCHED and self.confidence is None:",
     "        if False and self.origin is Origin.SEARCHED:",
     "test_a_resolved_finding_cannot_carry_a_similarity_score", "E-051"),

    # E-051. The graph resolving to a NEAR NEIGHBOUR instead of nothing. A
    # cause it does not hold must fall through to search, not to the closest
    # edge -- fuzzy may rank, never identify.
    ("the cause graph returning a near neighbour instead of nothing",
     "nm/knowledge/resolution.py",
     "    return LIMITATION_ARTICLE.get(cause)",
     "    return LIMITATION_ARTICLE.get(cause) or next(iter(LIMITATION_ARTICLE.values()))",
     "test_the_graph_resolves_by_exact_lookup_and_never_by_similarity",
     "E-051"),

    # E-051. An out-of-vocabulary cause accepted as a routing decision.
    ("a cause outside the closed vocabulary accepted as a route",
     "nm/core/cause.py",
     "        cause = CauseOfAction(raw)",
     "        cause = CauseOfAction.GOODS_SOLD_PRICE",
     "test_the_cause_read_refuses_a_span_the_advocate_never_wrote", "E-051"),

    # E-051. The verbatim guard, which the posture reader was measured
    # failing: the extractor quoting this product's own question back at it.
    ("a cause settled on a span the advocate never wrote",
     "nm/core/cause.py",
     "    if _fold(quoted) not in _fold(said):",
     "    if False and _fold(quoted) not in _fold(said):",
     "test_the_cause_read_refuses_a_span_the_advocate_never_wrote", "E-051"),

    # E-051. THE WIRING, and it is the half S4 proved is the one that breaks.
    # `article_for` and `_route` can both be right while the engine never sets
    # the field, and the served turns would look identical.
    ("the engine never putting a cause on the need",
     "nm/core/turn.py",
     "        return read.cause.value if read.resolved else None",
     "        return None",
     "test_the_engine_sets_the_cause_so_the_graph_can_be_consulted", "E-051"),

    # E-051. The advocate's own instruction outranked by the graph -- the
    # mirror of keyword scoring outvoting a named Act on `possession`.
    ("a section the advocate named outranked by the graph",
     "nm/adapters/evidence/corpus.py",
     "        if wanted_section(need.question):",
     "        if False and wanted_section(need.question):",
     "test_a_provision_the_advocate_named_outranks_the_graph", "E-051"),

    # E-052. The silent top-k cut on a similarity order. The forty-first
    # paragraph vanished with no count and no trace, so a miss caused by the
    # ceiling was indistinguishable from an absence in the corpus.
    ("a top-k cut that binds without saying so",
     "nm/adapters/evidence/corpus.py",
     "        truncated = len(rows) > EXAMINED_CEILING",
     "        truncated = False",
     "test_a_ceiling_that_binds_is_reported_and_never_silent", "E-052"),

    # E-054. A BNS charge retrieving nothing because the case law cites the
    # IPC. Case law is overwhelmingly pre-2024 and cites the old numbering.
    ("a new-code charge that cannot reach its old-code authority",
     "nm/knowledge/resolution.py",
     "        if (c.old_act, c.old_provision) == key:",
     "        if False and (c.old_act, c.old_provision) == key:",
     "test_authority_under_the_corresponding_old_provision_is_reachable",
     "E-054"),

    # E-054. Matching the NUMBER across codes. `s.447` means different things
    # in different codes, and matching digits is the wrong-Act defect one
    # layer down.
    ("a correspondence matched on the section number alone",
     "nm/knowledge/resolution.py",
     "    key = (act.strip(), str(provision).strip())",
     "    key = (act.strip(), str(provision).strip())\n"
     "    return next((c for c in CORRESPONDS\n"
     "                 if provision in (c.old_provision, c.new_provision)), None)",
     "test_authority_under_the_corresponding_old_provision_is_reachable",
     "E-054"),

    # E-054. The era rule: the governing date is the date of the CONDUCT.
    ("the era rule reading the date of the advice, not of the conduct",
     "nm/knowledge/resolution.py",
     "    return \"the 2023 codes\" if on >= TRANSITION else \"the 1860/1898/1973 codes\"",
     "    return \"the 2023 codes\"",
     "test_the_governing_date_is_the_date_of_the_conduct", "E-054"),

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
        # AN AMBIGUOUS ANCHOR MUTATES THE WRONG SITE, SILENTLY.
        #
        # `replace(old, new, 1)` takes the FIRST match. Two mutations were
        # measured surviving on 31 August 2026 for exactly this: as slice 5 was
        # built, a second copy of each anchor line appeared elsewhere in its
        # file, the mutation moved to the new site, and the named test -- still
        # guarding the ORIGINAL site -- stayed green.
        #
        # Both were then reported as SURVIVED, which reads as "this test is
        # decoration" and was really "this anchor stopped pointing at anything
        # in particular". A checker whose failure message names the wrong
        # cause sends the next person to rewrite a test that was fine.
        #
        # Zero and two are reported apart because the fixes differ: one is a
        # rename to sweep, the other is an anchor to make specific.
        found = original.count(old)
        if found != 1:
            what = ("not found" if found == 0 else
                    f"matches {found} places, so the first would be mutated "
                    f"rather than the one the test guards")
            print(f"  SKIP      {label}\n            (anchor {what} in {rel})")
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
