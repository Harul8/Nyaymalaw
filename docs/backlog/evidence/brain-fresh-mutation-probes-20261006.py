"""Isolated pure guard probes; never alter shared repository source files."""
from __future__ import annotations

import hashlib
import json
import sys
import types
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path("/workspace/Nyaymalaw")
sys.path.insert(0, str(REPO))

from nm.brain import continuation as continuation_owner
from nm.shared.model_port import SchemaViolation
from tests import test_brain_evidence_rendering as renderer_tests
from tests.test_brain_evidence_rendering_public import raw_unit


def call_render_test(function, *args):
    evidence = renderer_tests.evidence.__wrapped__()
    function(evidence, *args)


source_path = REPO / "nm/brain/evidence_rendering.py"
source = source_path.read_text()
continuation_path = REPO / "nm/brain/continuation.py"
continuation_source = continuation_path.read_text()
specifications = [
    ("fresh_display_field_guard_removed", "if forbidden:", "if False:",
     renderer_tests.test_fresh_writer_cannot_supply_display_fields_even_when_they_look_consistent,
     ("text", "I changed the record and saved the correction.")),
    ("original_words_shortened", "return f'{label}: “{row[\"text\"]}”'",
     "return f'{label}: “{row[\"text\"].split()[0]}”'",
     renderer_tests.test_account_keeps_complete_negation_attribution_and_uncertainty, ()),
    ("nm_factual_account_guard_removed", 'if account and row["role"] != "advocate":',
     "if False:", renderer_tests.test_prior_nm_words_cannot_be_rendered_as_factual_account, ()),
    ("unchecked_direct_legal_use_guard_removed", "if not source_verification_valid(source):",
     "if False:", renderer_tests.test_direct_passage_needs_an_owned_current_use_check, (False,)),
    ("citation_owner_substituted", 'citations.append({"text": anchor, "legal_source_id": identity})',
     'citations.append({"text": anchor, "legal_source_id": "foreign-source"})',
     renderer_tests.test_standalone_checked_passage_preserves_its_complete_condition, ()),
    ("rendered_text_equality_guard_removed",
     "if any(block.get(key) != value for key, value in rendered.items()):",
     "if False:",
     renderer_tests.test_deliberately_wrong_acceptance_or_block_kind_cannot_authorize_other_text,
     ("completion",)),
]

results = []
for name, before, after, function, args in specifications:
    call_render_test(function, *args)
    if source.count(before) != 1:
        raise RuntimeError("Mutation anchor is not unique: " + name)
    changed = source.replace(before, after)
    saved_copy = Path("/tmp/nm-fresh-contract-" + name + ".py")
    saved_copy.write_text(changed)
    isolated = types.ModuleType("nm.brain.isolated_" + name)
    isolated.__file__ = str(saved_copy)
    exec(compile(changed, str(saved_copy), "exec"), isolated.__dict__)
    bindings = {key: getattr(isolated, key) for key in
                ("render_expression", "rendered_block", "validate_rendered_block")}
    try:
        with patch.multiple(renderer_tests, **bindings):
            call_render_test(function, *args)
    except (AssertionError, pytest.fail.Exception) as error:
        results.append({"probe": name, "baseline": "passed", "mutant": "detected",
                        "test": function.__name__, "args": list(args),
                        "failure": str(error), "mutant_source": str(saved_copy),
                        "mutant_sha256": hashlib.sha256(changed.encode()).hexdigest()})
    else:
        results.append({"probe": name, "baseline": "passed", "mutant": "survived",
                        "test": function.__name__, "args": list(args)})


def selected_work_probe(field):
    payload = {"work_items": [{"request_index": 0, "work_choices": ["$new_task"]}],
               "latest_message_spans": [{"id": "L1", "text": "An uncertain original account."}]}
    proposed = raw_unit(payload)
    proposed[field] = {"claim": "A writer cannot mint this code-owned context."}
    with pytest.raises(SchemaViolation):
        continuation_owner._selected_work(proposed, "request", {})


original_schema_validator = continuation_owner.require_schema


def relaxed_top_unit(value, schema, *args, **kwargs):
    if schema is continuation_owner._MODEL_UNIT:
        schema = deepcopy(schema)
        schema["additionalProperties"] = True
    return original_schema_validator(value, schema, *args, **kwargs)


for field in ("record_check", "progress_checks", "reviewed_record_check", "record_outcome_contract",
              "record_snapshot", "source_catalogue"):
    selected_work_probe(field)
    try:
        with patch.object(continuation_owner, "require_schema", relaxed_top_unit):
            selected_work_probe(field)
    except (AssertionError, pytest.fail.Exception) as error:
        results.append({"probe": "fresh_unit_context_guard_removed:" + field,
                        "baseline": "passed", "mutant": "detected",
                        "test": "_selected_work exact fresh schema probe",
                        "failure": str(error),
                        "qualification": "Pure owner probe; downstream redundant checks stay active."})
    else:
        results.append({"probe": "fresh_unit_context_guard_removed:" + field,
                        "baseline": "passed", "mutant": "survived",
                        "test": "_selected_work exact fresh schema probe"})

report = {
    "kind": "isolated_pure_mutation_probes",
    "source": str(source_path), "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
    "continuation_source": str(continuation_path),
    "continuation_source_sha256": hashlib.sha256(continuation_source.encode()).hexdigest(),
    "shared_production_modified": False, "real_model_calls": 0, "browser_calls": 0,
    "historical_mutation_counts": "Earlier 19/37/13/4 populations were not rerun or combined.",
    "qualification": ("Six existing renderer tests and six direct fresh-unit schema probes, "
                      "each with a passing baseline. Detection is guard coverage, not semantic accuracy, "
                      "an integrated mutation score or proof that all semantic errors are excluded."),
    "results": results,
}
output = Path("/tmp/nm-fresh-contract-mutation-probes.json")
output.write_text(json.dumps(report, indent=2) + "\n")
assert source_path.read_text() == source
assert continuation_path.read_text() == continuation_source
print(json.dumps({"probes": len(results), "detected": sum(row["mutant"] == "detected"
                                                         for row in results),
                  "survived": sum(row["mutant"] == "survived" for row in results),
                  "report": str(output)}))
