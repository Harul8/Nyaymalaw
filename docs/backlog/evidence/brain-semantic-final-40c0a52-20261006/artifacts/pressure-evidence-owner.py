import json
import os
from pathlib import Path


def pytest_configure(config):
    from tests import brain_pressure_support as support
    original = support.record_case

    def owned_record_case(case_id, **kwargs):
        current = os.environ.get("PYTEST_CURRENT_TEST", "")
        if not current.endswith(" (call)"):
            raise ValueError("Paired evidence must belong to an executing test")
        target = Path(os.environ["NM_PRESSURE_EVIDENCE_DIR"]) / (case_id + ".json")
        if target.exists():
            raise ValueError("A paired case ID may be recorded only once per round")
        owner = current[:-len(" (call)")]
        try:
            report = original(case_id, **kwargs)
        finally:
            # record_case writes the observed mismatch before asserting. Its
            # failed desired rule still needs exact ownership for strict xfail.
            if target.is_file():
                persisted = json.loads(target.read_text())
                persisted["test_nodeid"] = owner
                target.write_text(json.dumps(persisted, ensure_ascii=False, indent=2) + "\n")
        report["test_nodeid"] = owner
        return report

    support.record_case = owned_record_case


def pytest_collection_modifyitems(items):
    for item in items:
        item.user_properties.append(("pressure_test_nodeid", item.nodeid))
