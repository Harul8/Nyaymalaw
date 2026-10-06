"""Case-level evidence for offline passage/output pressure tests.

This records actual observations. A passing characterization of a known gap is
not evidence that the gap is prevented. No model provider is called here.
"""

import dataclasses
import json
import os
from pathlib import Path


def _json_default(value):
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    return str(value)


def record_case(case_id, *, boundary, user_passage, model_outputs, expected,
                observed, calls=(), scenario="faulty", claim_scope="mechanical",
                protection_status="blocked", notes=""):
    """Record before asserting; keep mechanical and semantic expectations apart."""
    report = {
        "case_id": case_id,
        "boundary": boundary,
        "user_passage": user_passage,
        "fabricated_model_outputs": model_outputs,
        "scenario": scenario,
        "claim_scope": claim_scope,
        "protection_status": protection_status,
        "expected": expected,
        "observed": observed,
        "calls": list(calls),
        "notes": notes,
        "expectation_met": expected == observed,
        "live_model_calls": 0,
    }
    directory = os.environ.get("NM_PRESSURE_EVIDENCE_DIR")
    if directory:
        target = Path(directory) / (case_id + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                     default=_json_default) + "\n")
    assert expected == observed, report
    return report
