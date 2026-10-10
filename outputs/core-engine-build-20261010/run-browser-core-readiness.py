"""Root-reviewed synthetic provisioning + one genuine browser turn.

Prepare only by default. --execute provisions ONE uniquely named synthetic
account through the existing sealed application's directory/enrol boundary, then
runs browser-core-readiness.py with its password held only in process memory.
No direct turn API call, forged session, registration-policy change, credential
file, or credential output. Existing advocate accounts/tabs are not touched.

Run with .venv-arrive/Scripts/python.exe from this checkout. The root supplies
the current server's nonsecret launch receipt and existing shared USD5 ledger.
The browser harness validates the selected loopback endpoint (8175 or the
parallel diagnostic server on 8176). The first run is fixed at one user message.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import runpy
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BROWSER_HARNESS = OUT / "browser-core-readiness.py"
LEDGER = OUT / "api-budget.sqlite"
EXPECTED_STORE = ROOT / ".nm" / "matters"


class PreparationRefused(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise PreparationRefused(reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-receipt", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--evidence-name", default="browser-core-readiness-first")
    args = parser.parse_args()
    require(Path(sys.prefix).resolve() == (ROOT / ".venv-arrive").resolve(), "use_venv_arrive_python")
    require(Path.cwd().resolve() == ROOT, "run_from_checkout_root")
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,70}", args.evidence_name), "unsafe_evidence_name")
    require(BROWSER_HARNESS.is_file(), "browser_harness_missing")
    receipt_path = args.server_receipt.resolve()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    # Import definitions only: __main__ is deliberately not selected here.
    harness = runpy.run_path(str(BROWSER_HARNESS), run_name="browser_readiness_preflight")
    observed = harness["readiness"](receipt)
    sys.path.insert(0, str(ROOT))
    from nm.shared.model_config import load_dotenv, load
    from nm.shared.model_port import Tier
    load_dotenv(ROOT / ".env")
    settings = dict(os.environ)
    # The launch receipt already binds the live server; the fixture composition
    # uses the same ledger too. This cannot reset/enlarge an existing ledger.
    settings["NM_EVAL_BUDGET_FILE"] = str(LEDGER)
    settings["NM_EVAL_MAX_USD"] = "5"
    store = Path(settings.get("NM_MATTER_STORE", ROOT / ".nm")).resolve()
    require(store == EXPECTED_STORE.resolve() and store.is_dir(), "existing_matter_store_not_confirmed")
    require(bool(settings.get("NM_MATTER_KEY")) or (ROOT / ".nm" / "matter.key").is_file(),
            "existing_seal_missing_refuse_key_creation")
    config = load(settings)
    routine = config.for_tier(Tier.ROUTINE)
    require(routine.provider == "openai" and routine.model == harness["MODEL"], "fixture_model_terms_changed")
    result_dir = OUT / args.evidence_name
    account_receipt = OUT / f"{args.evidence_name}.account.json"
    require(not result_dir.exists() and not account_receipt.exists(), "existing_run_refuse_repeat")
    if not args.execute:
        print(json.dumps({"ready": True, "account_writes": 0, "browser_launches": 0,
                          "model_calls": 0, "maximum_user_turns": 1,
                          "existing_store": str(store), "baseline": observed}))
        return 0

    from nm.app.composition import Application
    from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
    # Composition retains the existing store seal, policy and authentication
    # domain. No direct writes to account files or permissions are performed.
    application = Application(root=ROOT, environment=settings)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S").lower()
    suffix = secrets.token_hex(6)
    email = f"synthetic-core-browser-{stamp}-{suffix}@example.test"
    password = "Synthetic-A7!" + secrets.token_urlsafe(36)
    identity = AdvocateIdentity(id=email, email=email,
                                name=f"SYNTHETIC core acceptance {stamp} {suffix}")
    account_evidence = {
        "purpose": "Isolated synthetic SEQ1-4 browser acceptance; retain for review/cleanup",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "account_id": identity.id, "display_name": identity.name,
        "existing_store": str(store), "provisioning_boundary": "Application.directory.enrol(Enrolment)",
        "credential_handling": "Generated in memory; only domain-derived sealed credential is persisted",
        "maximum_user_turns": 1, "state": "provisioning_started",
    }
    with account_receipt.open("x", encoding="utf-8") as handle:
        json.dump(account_evidence, handle, ensure_ascii=False, indent=2)
    try:
        application.directory.enrol(Enrolment(identity=identity, credential=enrol(password)))
        account_evidence["state"] = "provisioned_browser_not_yet_run"
        account_receipt.write_text(json.dumps(account_evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        old_email = os.environ.get("NM_TEST_EMAIL")
        old_password = os.environ.get("NM_TEST_PASSWORD")
        old_argv = sys.argv[:]
        os.environ["NM_TEST_EMAIL"] = email
        os.environ["NM_TEST_PASSWORD"] = password
        exit_code = 1
        try:
            sys.argv = [str(BROWSER_HARNESS), "--server-receipt", str(receipt_path),
                        "--execute", "--max-turns", "1", "--evidence-name", args.evidence_name]
            try:
                runpy.run_path(str(BROWSER_HARNESS), run_name="__main__")
                exit_code = 0
            except SystemExit as outcome:
                exit_code = outcome.code if type(outcome.code) is int else 1
        finally:
            sys.argv = old_argv
            for name, original in (("NM_TEST_EMAIL", old_email), ("NM_TEST_PASSWORD", old_password)):
                if original is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = original
            password = ""
        account_evidence.update(state="browser_run_finished", browser_exit_code=exit_code,
                                finished_utc=datetime.now(timezone.utc).isoformat())
        account_receipt.write_text(json.dumps(account_evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"account_receipt": str(account_receipt), "browser_exit_code": exit_code,
                          "credentials_written_or_printed": False}))
        return exit_code
    except Exception as error:
        # Never print traceback/exception text that could include sensitive data.
        account_evidence.update(state="stopped_no_automatic_retry", error_type=type(error).__name__)
        account_receipt.write_text(json.dumps(account_evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        password = ""
        print(json.dumps({"stopped": type(error).__name__, "account_receipt": str(account_receipt)}))
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PreparationRefused as error:
        print(json.dumps({"ready": False, "reason": str(error)}))
        raise SystemExit(2)
    except Exception as error:
        print(json.dumps({"ready": False, "error_type": type(error).__name__}))
        raise SystemExit(2)
