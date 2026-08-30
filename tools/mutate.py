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
