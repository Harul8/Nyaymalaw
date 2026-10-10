"""Prepare/run the unchanged synthetic conversation after the source-selector fix.

Default invocation is read-only preflight: no model calls, account, store, or ledger
changes. Use --run-after-source-freeze only after the owning agent freezes the source.
Earlier live-served-probe evidence is retained untouched; call/spend controls and
synthetic permission handling come from that same harness.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-after-source-freeze", action="store_true")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("original_live_probe", OUT / "live-served-probe.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    from nm.core_engine.understanding import REFERENCE
    from nm.core_engine.response_writer import USE
    from nm.core_engine.response_review import REQUEST
    from nm.shared.model_port import require_schema

    reference = {"source_id": "preflight-owned-source", "quote": None}
    require_schema(reference, REFERENCE)
    require_schema(reference, REQUEST["properties"]["request"])
    require_schema({**reference, "role": "original_account", "speaker": "advocate",
                    "treatment": "not_applicable", "treatment_source": None}, USE)

    probe.EVIDENCE = OUT / "live-served-remeasurement.json"
    probe.STORE = OUT / "live-served-store-remeasurement"
    probe.ACCOUNT = "synthetic-live-core-remeasurement@example.test"
    if probe.EVIDENCE.exists() or probe.STORE.exists():
        raise SystemExit("Remeasurement already exists; no repeat or overwrite allowed.")
    if not args.run_after_source_freeze:
        print(json.dumps({"ready": True, "paid_calls": 0,
            "schema_full_source_selection": "supported in planner/writer/reviewer references",
            "evidence": str(probe.EVIDENCE), "store": str(probe.STORE),
            "shared_ledger": str(OUT / "api-budget.sqlite"), "model": probe.MODEL,
            "maximum_user_messages": 2, "maximum_logical_calls": 12,
            "additional_actual_spend_stop_usd": 0.30}))
        return
    probe.main()
    if probe.EVIDENCE.exists():
        result = json.loads(probe.EVIDENCE.read_text(encoding="utf-8"))
        result["comparison"] = {"baseline_evidence": "live-served-probe.json",
            "identical_messages_and_expectations": True,
            "change_under_measurement": "Owned full-source selectors and prompt guidance; see recorded source hashes"}
        probe.EVIDENCE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
