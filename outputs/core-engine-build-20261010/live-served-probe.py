"""Bounded, synthetic live API evidence; not browser acceptance.

One conversation, at most two messages / twelve logical calls / USD0.30 actual
spend stop, using the existing shared USD5 ledger and unchanged production flow.
Credentials are generated in memory and never placed in the evidence artifact.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from nm.app.composition import Application
from nm.app.main import create_app
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.core_engine.conversation import chat_matter_id
from nm.core_engine.retrieval import HybridSearcher
from nm.core_engine.turn import saved_rows
from nm.shared.model_call_budget import SessionCallBudget
from nm.shared.model_config import load, load_dotenv
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import ProviderUnavailable, Tier
from nm.shared.store_file_store import FileMatterStore

OUT = Path(__file__).resolve().parent
EVIDENCE = OUT / "live-served-probe.json"
MODEL = "gpt-4.1-mini-2025-04-14"
STORE = OUT / "live-served-store"
ACCOUNT = "synthetic-live-core@example.test"
MESSAGES = [
    {
        "message": "Good afternoon. This is a synthetic test matter. We act for Aster Fabrication in Hyderabad. "
            "Our client rented a precision cutter and says it returned the machine on 6 September 2026. "
            "The owner retains the Rs 1,20,000 security deposit, alleging damage to the cutting head; "
            "our client denies causing damage. The owner sent a technician's estimate but no joint inspection "
            "report. Our client reports having a signed hire agreement and a bank-transfer receipt, but I have "
            "not supplied or examined those documents here. Separately, the owner's technician still has our "
            "client's original design drive, which the client says was lent only for setup; the owner now "
            "says it can retain the drive until repair costs are paid. First give a source-backed, conditional "
            "analysis of the deposit and drive disputes, including any material contrary position. Separately, "
            "draft a brief list of questions for our client that would clarify the important gaps. Do not "
            "contact anyone, do not treat the damage allegation as admitted, and do not assume the reported "
            "documents have been checked.",
        "expected_before_run": {
            "independent_results": ["Conditional, sourced analysis of deposit and design-drive disputes including contrary position", "Brief client questions"],
            "attribution": ["Return date and loan purpose are client reports", "Damage is owner's allegation denied by client", "Retention right is owner's position, not established law"],
            "limits": ["No contact", "No damage admission", "Reported agreement/receipt are not supplied or examined"],
            "law": "Every legal assertion must select actually held words, preserve the source's conditions and distinguish party submissions from judicial treatment.",
            "forbidden": ["Invented agreement terms or law", "Claim sending, saving facts, legal clearance or verified documents", "Drop either independent requested result"]
        }
    },
    {
        "message": "Hi again, thank you. A brief diversion: please explain in ordinary language the difference "
            "between an allegation and a proved fact, using only the account we have discussed. Also, I gave "
            "the return date incorrectly: our client's reported return date is 8 September 2026, not "
            "6 September. I am clarifying the account for this conversation, not asking you to update a "
            "separate saved fact record. Then return to the questions we should put to the client. Keep "
            "everything internal and keep the damage allegation disputed.",
        "expected_before_run": {
            "independent_results": ["Ordinary-language distinction using attributed existing account", "Return to brief client questions"],
            "correction": "8 September replaces earlier reported 6 September in current understanding; no historical rewrite or fact-edit completion claim.",
            "attribution": "Damage remains disputed, documents remain unexamined, no contact authority.",
            "forbidden": ["Claim a saved fact update", "Treat the temporary diversion as abandonment of deposit/drive work", "Assert the allegation is proved"]
        }
    },
]


def hashes():
    paths = [*sorted((ROOT / "nm/core_engine").glob("*.py")),
             ROOT / "nm/app/api.py", ROOT / "nm/app/composition.py",
             ROOT / "nm/app/model_permission.py", ROOT / "nm/shared/turn_attempt_store.py",
             ROOT / "nm/shared/model_openai_adapter.py", ROOT / "nm/shared/model_call_budget.py"]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main():
    if EVIDENCE.exists() or STORE.exists():
        raise SystemExit("Live probe evidence/store already exists; refusing accidental repeat.")
    load_dotenv(ROOT / ".env")
    config = load()
    routine = config.for_tier(Tier.ROUTINE)
    assert routine.provider == "openai" and routine.model == MODEL
    assert routine.base_url in (None, "", "https://api.openai.com/v1", "https://api.openai.com/v1/")
    budget = SessionCallBudget(OUT / "api-budget.sqlite", "5", models=(MODEL,))
    before = budget.status()
    baseline = hashes()
    evidence = {"started_utc": datetime.now(timezone.utc).isoformat(), "mode": "public FastAPI TestClient; not browser",
                "model": MODEL, "budget_before": before, "maximum_additional_actual_usd": 0.30,
                "maximum_user_messages": 2, "maximum_logical_calls": 12,
                "source_hashes_before": baseline, "calls": [], "turns": []}

    def save():
        evidence["budget_after"] = budget.status()
        evidence["logical_calls"] = len(evidence["calls"])
        evidence["source_hashes_after"] = hashes()
        evidence["own_measured_cost_usd"] = round(sum(
            call.get("result", {}).get("usage", {}).get("cost_usd", 0)
            for call in evidence["calls"]), 8)
        EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    original_structured = OpenAIModelAdapter.structured

    def recorded(adapter, prompt, schema, tier, **kwargs):
        if len(evidence["calls"]) >= 12:
            raise ProviderUnavailable("Live probe logical-call allowance reached.")
        if budget.status()["charged_usd"] - before["charged_usd"] >= 0.30:
            raise ProviderUnavailable("Live probe actual-spend stop reached.")
        if hashes() != baseline:
            raise ProviderUnavailable("Relevant source changed during the live probe.")
        assert tier is Tier.ROUTINE and adapter.resolved_model(tier) == MODEL
        call = {"operation": prompt.operation, "system": prompt.system, "user": prompt.user,
                "schema": deepcopy(schema), "kwargs": kwargs}
        evidence["calls"].append(call)
        print(json.dumps({"dispatch": len(evidence["calls"]), "operation": prompt.operation}), flush=True)
        try:
            result = original_structured(adapter, prompt, schema, tier, **kwargs)
            call["result"] = {"data": deepcopy(result.data), "model": result.model,
                              "usage": asdict(result.usage), "latency_ms": result.latency_ms,
                              "completion": result.completion.value, "retries": result.retries}
            return result
        except Exception as exc:
            call["error_type"] = type(exc).__name__
            if getattr(exc, "usage", None) is not None:
                call["usage"] = asdict(exc.usage)
            raise
        finally:
            save()

    # Instrumentation records actual adapter receipts; all dispatch permissions,
    # model budgeting, structured validation and production stage logic remain.
    OpenAIModelAdapter.structured = recorded
    key, password = secrets.token_urlsafe(48), "Synthetic-A7!" + secrets.token_urlsafe(30)
    settings = dict(os.environ)
    settings.update(NM_MATTER_KEY=key, NM_MATTER_STORE=str(STORE),
                    NM_EVAL_BUDGET_FILE=str(OUT / "api-budget.sqlite"), NM_EVAL_MAX_USD="5")
    directory = FileDirectory(STORE, key=key)
    store = FileMatterStore(STORE, key=key)
    directory.enrol(Enrolment(AdvocateIdentity(ACCOUNT, "Synthetic live core probe"), enrol(password)))
    application = Application(root=ROOT, model=OpenAIModelAdapter(config, call_budget=budget),
        store=store, directory=directory, mail=FileOutbox(STORE, key=key),
        legal_search=HybridSearcher.local(root=ROOT, corpus_dir=settings.get("NM_CORPUS_DIR")),
        audit_root=STORE / "audit", environment=settings)
    save()
    try:
        with TestClient(create_app(application)) as client:
            login = client.post("/api/login", headers={"origin": "http://testserver"},
                                json={"advocate_id": ACCOUNT, "password": password})
            assert login.status_code == 200, "Synthetic account sign-in failed."
            client.headers.update({"origin": "http://testserver", "x-nm-csrf": client.cookies.get("nm_csrf")})
            permission = client.get("/api/account/model-permission").json()
            consent = client.post("/api/account/model-permission", json={"accepted": True,
                "notice_version": permission["notice_version"], "expected_version": permission["version"]})
            assert consent.status_code == 200 and consent.json()["accepted"], "Synthetic permission failed."
            chat = None
            for index, item in enumerate(MESSAGES, 1):
                if hashes() != baseline:
                    evidence["stopped_reason"] = "Relevant production source changed before message."
                    break
                start = time.perf_counter()
                request = {"turn_id": f"live-served-{index}", "message": item["message"], "chat_id": chat}
                row = {"request": request, "expected_before_run": item["expected_before_run"],
                       "call_start": len(evidence["calls"])}
                evidence["turns"].append(row)
                response = client.post("/api/turn", json=request)
                row.update(status_code=response.status_code, response=response.json(),
                           latency_seconds=round(time.perf_counter() - start, 3),
                           call_end=len(evidence["calls"]))
                save()
                print(json.dumps({"message": index, "status_code": response.status_code,
                    "latency_seconds": row["latency_seconds"], "logical_calls": row["call_end"]-row["call_start"]}), flush=True)
                if response.status_code != 200:
                    evidence["stopped_reason"] = "First unsuccessful public turn; no user-message retry."
                    break
                chat = response.json()["chat_id"]
                reopened = client.get(f"/api/chats/{chat}")
                row["reopened"] = {"status_code": reopened.status_code, "body": reopened.json()}
                matter = store.load(chat_matter_id(ACCOUNT, chat))
                row["canonical_rows"] = saved_rows(matter, ACCOUNT)
                row["source_reads"] = []
                for e, element in enumerate(response.json()["elements"]):
                    for s, expected in enumerate(element["sources"]):
                        read = client.get(f"/api/chats/{chat}/turns/{request['turn_id']}/brain-sources/{e}/{s}")
                        row["source_reads"].append({"element": e, "source": s, "status_code": read.status_code,
                                                    "matches_saved": read.json() == expected, "body": read.json()})
                row["readback_no_additional_model_calls"] = len(evidence["calls"]) == row["call_end"]
                save()
                if budget.status()["charged_usd"] - before["charged_usd"] >= 0.30:
                    evidence["stopped_reason"] = "Actual-spend stop reached."
                    break
    except Exception as exc:
        evidence["probe_error_type"] = type(exc).__name__
    finally:
        OpenAIModelAdapter.structured = original_structured
        evidence["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save()
        print(json.dumps({"finished": True, "logical_calls": len(evidence["calls"]),
                          "own_measured_cost_usd": evidence["own_measured_cost_usd"],
                          "budget": evidence["budget_after"], "error": evidence.get("probe_error_type"),
                          "source_unchanged": hashes() == baseline}), flush=True)


if __name__ == "__main__":
    main()
