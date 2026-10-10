"""Outputs-only observational launcher for one designated synthetic account.

Default invocation prepares nothing and starts nothing. --serve runs the normal
nm.app.main after installing return/raise-preserving diagnostic wrappers. A
ContextVar scopes all captures to the exact account_id in --account-receipt;
the root runner may create that nonsecret receipt after this server starts.
Other accounts are neither captured nor modified. Authentication, admission,
correction, release, persistence and provider retry logic remain the originals.

The model snapshot is taken at OpenAIModelAdapter.structured, AFTER the turn's
shared correction feedback has been applied; it is the actual adapter input,
not a reconstruction of the provider SDK's subsequently transformed wire JSON.
Only synthetic conversation/source/result data are captured. No API config,
headers, cookies, session callable, store object or credential is serialized.
"""
from __future__ import annotations

import argparse
from contextvars import ContextVar
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
LEDGER = OUT / "api-budget.sqlite"
MODEL = "gpt-4.1-mini-2025-04-14"
ACTIVE = ContextVar("synthetic_core_diagnostic_turn", default=None)


def encoded(value):
    def primitive(item):
        if isinstance(item, Enum):
            return item.value
        raise TypeError(f"Unsupported diagnostic value: {type(item).__name__}")
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=primitive)


def usage(value):
    if value is None:
        return None
    return {name: getattr(value, name, None) for name in
            ("tokens_in", "tokens_out", "cost_usd", "cached_tokens")}


def result_snapshot(result):
    return {"data": result.data, "text": result.text,
            "provider": result.provider, "model": result.model, "tier": result.tier,
            "completion": result.completion, "usage": usage(result.usage),
            "latency_ms": result.latency_ms, "retries": result.retries}


def error_snapshot(error):
    # Preserve precise owner-validation mismatch; provider failures may embed
    # remote credential diagnostics and are recorded by type/accounting only.
    owner_types = {"SchemaViolation", "ContextOverflow", "ReleaseWithheld",
                   "CorrectionUnavailable", "ConversationRefused", "ValueError", "KeyError"}
    row = {"type": type(error).__name__, "usage": usage(getattr(error, "usage", None)),
           "retries": getattr(error, "retries", None)}
    if type(error).__name__ in owner_types:
        row["owner_mismatch"] = str(error)
    rejected = getattr(error, "rejected_result", None)
    if rejected is not None:
        row["rejected_completed_result"] = result_snapshot(rejected)
    chain, seen = [], set()
    current = error.__cause__ or error.__context__
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        item = {"type": type(current).__name__}
        if type(current).__name__ in owner_types:
            item["owner_mismatch"] = str(current)
        chain.append(item)
        current = current.__cause__ or current.__context__
    row["cause_types_and_owner_mismatches"] = chain
    return row


def capture(event, value):
    """Diagnostic failure must not change the return, exception or retry path."""
    active = ACTIVE.get()
    if active is None:
        return
    try:
        active["sequence"] += 1
        number = active["sequence"]
        name = f"{number:03d}-{event}.json"
        payload = encoded({"observed_utc": datetime.now(timezone.utc).isoformat(),
                           "turn_id": active["turn_id"], "event": event, "value": value})
        path = active["directory"] / name
        with path.open("x", encoding="utf-8") as handle:
            handle.write(payload)
        manifest = {"file": name, "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                    "bytes": len(payload.encode("utf-8"))}
        with (active["directory"] / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(encoded(manifest) + "\n")
    except Exception as error:
        active["capture_errors"].append(type(error).__name__)
        print(json.dumps({"diagnostic_write_failed": type(error).__name__}), file=sys.stderr, flush=True)


def capture_built(event, builder):
    """Snapshot construction is observational too, including exotic failures."""
    try:
        value = builder()
    except Exception as error:
        capture(event + "-snapshot-error", {"type": type(error).__name__})
        return
    capture(event, value)


def observe_stage(module, name, argument_names):
    original = getattr(module, name)
    signature = inspect.signature(original)

    @wraps(original)
    def observed(*args, **kwargs):
        if ACTIVE.get() is None:
            return original(*args, **kwargs)
        stage = f"{module.__name__.rsplit('.', 1)[-1]}-{name}"
        try:
            bound = signature.bind(*args, **kwargs)
            capture(stage + "-input", {key: value for key, value in bound.arguments.items()
                                       if key in argument_names})
        except Exception as error:
            capture(stage + "-input-capture-error", {"type": type(error).__name__})
        started = time.perf_counter()
        try:
            result = original(*args, **kwargs)
        except Exception as error:
            capture_built(stage + "-exception", lambda: {"seconds": time.perf_counter() - started,
                                                         "exception": error_snapshot(error)})
            raise
        capture(stage + "-output", {"seconds": time.perf_counter() - started, "result": result})
        return result

    setattr(module, name, observed)


def install(account_receipt, output_directory):
    from nm.core_engine import research, response_authorities, response_review, response_writer, turn
    from nm.shared.model_openai_adapter import OpenAIModelAdapter
    original_process = turn.process
    original_structured = OpenAIModelAdapter.structured

    @wraps(original_process)
    def scoped_process(*args, **kwargs):
        try:
            target = json.loads(account_receipt.read_text(encoding="utf-8-sig"))
            account_id = target["account_id"]
            selected = (isinstance(account_id, str) and account_id.endswith("@example.test")
                        and target.get("display_name", "").startswith("SYNTHETIC ")
                        and kwargs.get("advocate_id") == account_id)
        except Exception:
            selected = False
        if not selected:
            return original_process(*args, **kwargs)
        try:
            directory = output_directory / uuid.uuid4().hex
            directory.mkdir()
        except Exception as error:
            print(json.dumps({"diagnostic_turn_directory_failed": type(error).__name__}),
                  file=sys.stderr, flush=True)
            return original_process(*args, **kwargs)
        scope = {"directory": directory, "turn_id": kwargs.get("turn_id"),
                 "sequence": 0, "capture_errors": []}
        token = ACTIVE.set(scope)
        started = time.perf_counter()
        try:
            capture("turn-input", {key: kwargs.get(key) for key in
                ("advocate_id", "message", "turn_id", "chat_id", "matter_id", "expected_version")})
            try:
                result = original_process(*args, **kwargs)
            except Exception as error:
                capture_built("turn-exception", lambda: {"seconds": time.perf_counter() - started,
                                                         "exception": error_snapshot(error),
                                                         "metrics": getattr(error, "metrics", None)})
                raise
            capture("turn-output", {"seconds": time.perf_counter() - started, "result": result})
            return result
        finally:
            capture("turn-diagnostics-finished", {"capture_errors": list(scope["capture_errors"])})
            ACTIVE.reset(token)

    @wraps(original_structured)
    def observed_structured(self, prompt, schema, tier, *, max_tokens=None):
        if ACTIVE.get() is None:
            return original_structured(self, prompt, schema, tier, max_tokens=max_tokens)
        capture("model-input", {"operation": prompt.operation, "system": prompt.system,
                                "user": prompt.user, "schema": schema,
                                "tier": tier, "max_tokens": max_tokens})
        started = time.perf_counter()
        try:
            result = original_structured(self, prompt, schema, tier, max_tokens=max_tokens)
        except Exception as error:
            capture_built("model-exception", lambda: {"operation": prompt.operation,
                "seconds": time.perf_counter() - started, "exception": error_snapshot(error)})
            raise
        capture_built("model-output", lambda: {"operation": prompt.operation,
            "seconds": time.perf_counter() - started, "result": result_snapshot(result)})
        return result

    turn.process = scoped_process
    OpenAIModelAdapter.structured = observed_structured
    observe_stage(research, "plan", {"context", "interpretation"})
    observe_stage(research, "retrieve", {"plan", "context"})
    observe_stage(response_writer, "write", {"context", "research_record", "sources", "interpretation", "execution"})
    observe_stage(response_authorities, "check", {"context", "research_record", "sources", "draft"})
    observe_stage(response_review, "review", {"context", "research_record", "sources", "draft", "execution", "authority_evidence"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-receipt", type=Path, required=True)
    parser.add_argument("--launch-receipt", type=Path, required=True)
    parser.add_argument("--diagnostics-name", required=True)
    parser.add_argument("--port", type=int, choices=(8175, 8176), default=8176)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or Path(sys.prefix).resolve() != (ROOT / ".venv-arrive").resolve():
        raise ValueError("Run from checkout root with .venv-arrive Python")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,70}", args.diagnostics_name):
        raise ValueError("Use a simple unique diagnostics directory name")
    account_receipt, launch_receipt = args.account_receipt.resolve(), args.launch_receipt.resolve()
    if (not account_receipt.is_relative_to(OUT) or not account_receipt.name.endswith(".account.json")
            or not launch_receipt.is_relative_to(OUT)):
        raise ValueError("Receipts must remain inside this test evidence directory")
    diagnostics = OUT / args.diagnostics_name
    if diagnostics.exists() or launch_receipt.exists():
        raise ValueError("Existing diagnostics/launch receipt cannot be overwritten")
    if not LEDGER.is_file():
        raise ValueError("The existing shared budget ledger is required")
    if not args.serve:
        print(json.dumps({"prepared": True, "server_starts": 0, "model_calls": 0,
                          "exact_account_receipt": str(account_receipt),
                          "diagnostics": str(diagnostics), "shared_cap_usd": 5,
                          "base_url": f"http://127.0.0.2:{args.port}"}))
        return 0
    sys.path.insert(0, str(ROOT))
    os.environ["NM_EVAL_BUDGET_FILE"] = str(LEDGER)
    os.environ["NM_EVAL_MAX_USD"] = "5"
    from nm.shared.model_config import load_dotenv, load
    from nm.shared.model_port import Tier
    load_dotenv(ROOT / ".env")
    config = load()
    routine = config.for_tier(Tier.ROUTINE)
    if routine.provider != "openai" or routine.model != MODEL:
        raise ValueError("Observed server must use the approved pinned mini model")
    diagnostics.mkdir()
    install(account_receipt, diagnostics)
    from nm.app import api
    from nm.app.main import main as app_main
    receipt = {"base_url": f"http://127.0.0.2:{args.port}", "pid": os.getpid(),
               "model": MODEL, "budget_file": str(LEDGER), "maximum_usd": 5,
               "serving": api.SERVING, "captured_utc": datetime.now(timezone.utc).isoformat(),
               "account_receipt": str(account_receipt), "diagnostics": str(diagnostics),
               "observational_launcher_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "state": "normal_main_about_to_start_verify_health_before_testing"}
    with launch_receipt.open("x", encoding="utf-8") as handle:
        handle.write(encoded(receipt))
    return app_main(["--host", "127.0.0.2", "--port", str(args.port)])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"launcher_failed": type(error).__name__}), file=sys.stderr)
        raise SystemExit(2)
