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
    ("posture inferred from vocabulary (the reinstatement defect)",
     "nm/core/turn.py",
     "    text = message.lower()\n    for phrase, role in _ROLE_WORDS.items():",
     "    text = message.lower()\n"
     '    if "landlord" in text:\n'
     "        return Role.PLAINTIFF, Basis.INFERRED\n"
     "    for phrase, role in _ROLE_WORDS.items():",
     "test_posture_is_never_inferred_from_familiar_vocabulary", "E-030"),

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
