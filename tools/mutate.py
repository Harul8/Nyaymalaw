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

    ("another advocate's matter disclosed",
     "nm/edge/api.py",
     "    if m is None or m.advocate_id != advocate_id:",
     "    if m is None:",
     "test_another_advocates_matter_is_not_disclosed", "E-010"),
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
