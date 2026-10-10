"""Prepare or execute one bounded, isolated real-page core-engine conversation.

Default: read-only preflight, no browser or model calls. --execute starts a NEW
headless Chromium instance, never attaches to or changes the owner's browsers.
The account must already be provisioned through the supported application domain
boundary. Sign-in, model consent, sending, source opening and reopening use UI.
No authentication bypass, cookie injection, direct turn POST or automatic retry.

Required nonsecret launch receipt: base_url, pid, model, budget_file,
maximum_usd, serving. Root records this when starting the bounded app. Its
contents are operator evidence, not proof inferred from a model response.
Credentials: NM_TEST_EMAIL and NM_TEST_PASSWORD, never written or printed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
LEDGER = OUT / "api-budget.sqlite"
MODEL = "gpt-4.1-mini-2025-04-14"
MAXIMUM = 5
MESSAGES = [
    "SYNTHETIC BROWSER ACCEPTANCE MATTER. We act for Cedar Workshop in Hyderabad. "
    "The client says it hired a laser cutter and returned it on 12 September 2026. "
    "The owner retains the Rs 90,000 deposit and alleges damage to the lens; our client "
    "denies causing damage. The owner says an inspection report exists but has not supplied "
    "it to our client. The client reports having a signed hire agreement and the bank "
    "transfer receipt, but neither document has been supplied or checked here. Separately, "
    "the owner's technician still holds the client's original design drive, said to have "
    "been lent for setup only. The owner claims it may keep that drive until repair charges "
    "are paid. Give a conditional analysis of both disputes using the held legal sources, "
    "including the material opposing position. Then list the important questions for our "
    "client. Do not contact anyone, do not admit damage, and do not invent agreement terms.",
    "A correction: our client's reported return date is 14 September 2026, not 12 September. "
    "The owner still says the inspection report exists; it has not been supplied. For now, "
    "only summarise our account and the owner's opposing account in two separate paragraphs, "
    "then state the unanswered factual questions. Do not conduct new legal research in this "
    "turn, and do not claim to have edited any separate matter record. Keep the earlier "
    "wording visible in the conversation and keep the damage allegation disputed.",
    "Thank you, that is all for today. Please leave the legal research paused until I ask "
    "to resume. Do not contact anyone.",
]
EXPECTATIONS = [
    {
        "independent_results": ["Conditional deposit analysis", "Conditional design-drive analysis",
                                "Material contrary positions", "Important client questions"],
        "account": ["Damage alleged and denied", "Report exists according to owner but was not supplied",
                    "Agreement and receipt reported, not checked", "Loan purpose is a client account"],
        "must_not": ["Invent contract terms", "Treat submission as court holding",
                     "Assert undisputed damage", "Claim external action or separate record update"],
    },
    {
        "independent_results": ["Two attributed account paragraphs", "Unanswered factual questions"],
        "account": ["Corrected reported date is 14 September", "Earlier date remains historical",
                    "Non-supply is not nonexistence", "Damage remains disputed"],
        "must_not": ["New legal research", "Claim separate material-record edit", "Drop opposing account"],
    },
    {
        "independent_results": ["Brief courteous close"],
        "must_not": ["Resume paused research", "Invent or change matter facts", "Contact anyone"],
    },
]


class StopRun(RuntimeError):
    """A content-free reason safe to record without Playwright call logs."""


def require(condition, reason):
    if not condition:
        raise StopRun(reason)


def read_json(url):
    with urlopen(url, timeout=10) as response:
        return json.load(response)


def budget_status():
    require(LEDGER.is_file(), "existing_budget_ledger_missing")
    database = sqlite3.connect(LEDGER.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        maximum = database.execute("SELECT maximum FROM budget WHERE singleton=1").fetchone()[0]
        rows = database.execute("SELECT state, COUNT(*), SUM(charge) FROM attempts GROUP BY state").fetchall()
    finally:
        database.close()
    return {"maximum_usd": maximum / 1_000_000,
            "measured_usd": sum(row[2] for row in rows if row[0].startswith("measured")) / 1_000_000,
            "reserved_or_unknown_usd": sum(row[2] for row in rows if not row[0].startswith("measured")) / 1_000_000,
            "charged_usd": sum(row[2] for row in rows) / 1_000_000,
            "attempts": sum(row[1] for row in rows)}


def readiness(receipt):
    require(receipt["base_url"] in {"http://127.0.0.2:8175", "http://127.0.0.2:8176"},
            "unexpected_app_endpoint")
    require(Path(receipt["budget_file"]).resolve() == LEDGER.resolve(), "different_budget_ledger")
    require(receipt["maximum_usd"] == MAXIMUM and receipt["model"] == MODEL, "launch_terms_mismatch")
    require(type(receipt["pid"]) is int and receipt["pid"] > 0, "launch_pid_missing")
    health = read_json(receipt["base_url"] + "/api/health")
    require(health.get("code_state") == "current", "server_source_is_not_current")
    require(health.get("serving") == receipt["serving"] == health.get("tree"), "launch_fingerprint_changed")
    require(health.get("brain", {}).get("engine") == "core_engine", "wrong_served_engine")
    require(health.get("provider") == "openai" and health.get("model") == MODEL, "wrong_served_model")
    budget = budget_status()
    require(budget["maximum_usd"] == MAXIMUM and budget["charged_usd"] < MAXIMUM, "evaluation_budget_unavailable")
    return {"health": health, "budget": budget}


def normal(text):
    return " ".join(str(text).split())


def inspect_sources(page, turn_node, base, evidence_dir, number):
    """Click every citation in this response; do not substitute direct source fetches."""
    links = turn_node.locator("button.citation-link")
    rows = []
    for index in range(links.count()):
        link = links.nth(index)
        with page.expect_response(lambda response: "/brain-sources/" in response.url
                                  and response.request.method == "GET", timeout=30000) as read:
            link.click()
        response = read.value
        require(response.status == 200, "source_pane_http_failure")
        saved = response.json()
        reader = page.locator("#brain-source-reader")
        reader.wait_for(state="visible")
        passage = page.locator("#brain-source-body .brain-source-text")
        passage.wait_for(state="visible")
        shown = passage.text_content()
        require(shown == saved.get("text"), "source_pane_changed_saved_words")
        box = reader.bounding_box()
        require(box is not None, "source_pane_not_visible")
        viewport = page.viewport_size
        require(abs(box["x"] + box["width"] - viewport["width"]) <= 3, "source_pane_not_right_aligned")
        header = page.locator("#brain-source-title").bounding_box()
        close = page.locator("#brain-source-close").bounding_box()
        page.locator("#brain-source-body").evaluate("node => { node.scrollTop = node.scrollHeight; }")
        require(page.locator("#brain-source-title").bounding_box() == header
                and page.locator("#brain-source-close").bounding_box() == close,
                "source_reader_header_moves_with_body")
        screenshot = evidence_dir / f"turn-{number}-source-{index + 1}.png"
        page.screenshot(path=str(screenshot), full_page=True)
        rows.append({"link_text": link.inner_text(), "url": response.url.removeprefix(base),
                     "http_status": response.status, "saved": saved,
                     "rendered_passage": shown, "rendered_details": page.locator("#brain-source-body").inner_text(),
                     "right_aligned": True, "header_fixed": True, "screenshot": screenshot.name})
        page.locator("#brain-source-close").click()
        reader.wait_for(state="hidden")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-receipt", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-turns", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--evidence-name", default="browser-core-readiness-run")
    args = parser.parse_args()
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,70}", args.evidence_name), "unsafe_evidence_name")
    receipt = json.loads(args.server_receipt.read_text(encoding="utf-8-sig"))
    baseline = readiness(receipt)
    email, password = os.environ.get("NM_TEST_EMAIL"), os.environ.get("NM_TEST_PASSWORD")
    require(email and password and email.endswith("@example.test"), "synthetic_credentials_required")
    if not args.execute:
        print(json.dumps({"ready": True, "browser_launches": 0, "model_calls": 0,
                          "maximum_turns": args.max_turns, "baseline": baseline}))
        return 0
    evidence_dir = OUT / args.evidence_name
    require(not evidence_dir.exists(), "evidence_directory_already_exists_no_automatic_repeat")
    evidence_dir.mkdir()
    evidence = {"started_utc": datetime.now(timezone.utc).isoformat(),
                "mode": "isolated headless Chromium; genuine page UI",
                "server_launch": {key: receipt[key] for key in
                                  ("base_url", "pid", "model", "budget_file", "maximum_usd", "serving")},
                "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "baseline": baseline, "max_turns": args.max_turns, "turns": [],
                "page_error_types": [], "blocked_requests": [], "stage": "browser_start",
                "semantic_acceptance": "pending independent inspection of actual displayed work"}
    evidence_file = evidence_dir / "evidence.json"

    def save():
        evidence_file.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    save()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(30000)
        page.on("pageerror", lambda error: evidence["page_error_types"].append(type(error).__name__))
        permit_turn = False
        posted = 0

        def guard(route):
            nonlocal permit_turn, posted
            request = route.request
            target = urlsplit(request.url)
            if target.scheme in {"http", "https"} and f"{target.scheme}://{target.netloc}" != receipt["base_url"]:
                evidence["blocked_requests"].append({"kind": "external_browser_request", "resource": request.resource_type})
                route.abort()
                return
            if target.path == "/api/turn" and request.method == "POST":
                if not permit_turn or posted >= args.max_turns:
                    evidence["blocked_requests"].append({"kind": "extra_turn_dispatch"})
                    route.abort()
                    return
                try:
                    readiness(receipt)
                except Exception:
                    evidence["blocked_requests"].append({"kind": "readiness_changed_before_dispatch"})
                    route.abort()
                    return
                permit_turn = False
                posted += 1
            route.continue_()

        context.route("**/*", guard)
        try:
            evidence["stage"] = "sign_in"
            page.goto(receipt["base_url"] + "/", wait_until="domcontentloaded")
            page.locator("#login-id").fill(email)
            page.locator("#login-password").fill(password)
            with page.expect_response(lambda response: response.url.endswith("/api/login")
                                      and response.request.method == "POST") as login:
                page.locator("#login-go").click()
            require(login.value.status == 200, "synthetic_sign_in_failed")
            page.locator("#home-start").wait_for(state="visible")
            # Credentials are now cleared by the application's sign-in handler;
            # no account-form screenshots or login/consent network bodies saved.
            evidence["stage"] = "model_permission"
            page.locator("#account-toggle").click()
            page.locator("#ai-sharing").click()
            page.locator("#ai-sharing-accept").check()
            with page.expect_response(lambda response: response.url.endswith("/api/account/model-permission")
                                      and response.request.method == "POST") as consent:
                page.locator("#ai-sharing-save").click()
            require(consent.value.status == 200 and consent.value.json().get("accepted") is True,
                    "synthetic_model_permission_failed")
            page.locator("#ai-sharing-close").click()
            page.locator("#home-start").click()
            page.locator("#message").wait_for(state="visible")
            require(not page.locator("#opening-record").is_visible(), "new_matter_shows_intake_form")
            require(not page.locator("#matter-board").is_visible(), "new_matter_shows_empty_board")
            page.screenshot(path=str(evidence_dir / "empty-chat.png"), full_page=True)
            for number, message in enumerate(MESSAGES[:args.max_turns], 1):
                evidence["stage"] = f"turn_{number}"
                before = readiness(receipt)
                row = {"number": number, "message": message, "expectations": EXPECTATIONS[number - 1],
                       "before": before, "sources": []}
                evidence["turns"].append(row)
                save()
                page.locator("#message").fill(message)
                permit_turn = True
                started = time.perf_counter()
                with page.expect_response(lambda response: response.url.endswith("/api/turn")
                                          and response.request.method == "POST", timeout=360000) as sent:
                    page.locator("#send").click()
                response = sent.value
                row.update(http_status=response.status, seconds=round(time.perf_counter() - started, 3),
                           response=response.json(), after=budget_status())
                save()
                # Let actual UI finish rendering even when HTTP rejects the turn.
                page.wait_for_function("!document.getElementById('send').disabled", timeout=30000)
                row["rendered_thread"] = page.locator("#thread").inner_text()
                page.screenshot(path=str(evidence_dir / f"turn-{number}.png"), full_page=True)
                save()
                require(response.status == 200, "turn_service_rejection_stop_no_retry")
                reply = row["response"]
                require(reply.get("committed") == "committed", "turn_persistence_not_confirmed")
                current = page.locator("#thread .turn").last
                rendered = current.inner_text()
                row["rendered_current_turn"] = rendered
                require(all(normal(element["text"]) in normal(rendered)
                            for element in reply.get("elements", []) if element.get("text")),
                        "saved_response_text_not_visible")
                require(0 < reply.get("metrics", {}).get("llm_calls", 0) <= 6, "unexpected_turn_call_count")
                row["sources"] = inspect_sources(page, current, receipt["base_url"], evidence_dir, number)
                require(not evidence["page_error_types"], "browser_javascript_error")
                require(not evidence["blocked_requests"], "browser_request_guard_fired")
                calls_before_reload = budget_status()["attempts"]
                page.reload(wait_until="domcontentloaded")
                page.locator('[data-tab="advise"]').click()
                # This isolated synthetic account must have exactly this one new chat.
                chats = page.locator('#rail-body [role="button"][aria-label^="Continue chat:"]')
                chats.first.wait_for(state="visible")
                require(chats.count() == 1, "synthetic_account_has_ambiguous_chat_history")
                with page.expect_response(lambda reopened: urlsplit(reopened.url).path == f"/api/chats/{reply['chat_id']}"
                                          and reopened.request.method == "GET") as reopened:
                    chats.first.click()
                require(reopened.value.status == 200, "saved_chat_reopen_failed")
                saved = reopened.value.json()
                page.locator("#thread .turn").nth(number - 1).wait_for(state="visible")
                row["reopened"] = saved
                row["reopened_thread"] = page.locator("#thread").inner_text()
                turns = saved.get("turns", [])
                require(len(turns) == number, "saved_chat_turn_count_changed")
                for index, previous in enumerate(evidence["turns"]):
                    require(turns[index]["message"] == previous["message"], "saved_input_changed")
                    require(turns[index]["elements"] == previous["response"]["elements"], "saved_reply_changed")
                require(normal(rendered) in normal(row["reopened_thread"]), "reloaded_display_changed")
                require(budget_status()["attempts"] == calls_before_reload, "reopen_made_model_call")
                page.screenshot(path=str(evidence_dir / f"turn-{number}-reopened.png"), full_page=True)
                row["mechanical_browser_checks"] = "passed; semantic quality not certified"
                save()
                print(json.dumps({"turn": number, "status": "captured", "seconds": row["seconds"],
                                  "model_calls": reply["metrics"]["llm_calls"], "source_links": len(row["sources"])}), flush=True)
            evidence["stage"] = "captured_for_semantic_review"
        except Exception as error:
            evidence["stopped"] = str(error) if isinstance(error, StopRun) else type(error).__name__
            # Never record a Playwright call log, credentials, request headers,
            # storage state or the account forms. A failure ends this one run.
        finally:
            evidence["posted_turns"] = posted
            evidence["finished_utc"] = datetime.now(timezone.utc).isoformat()
            evidence["budget_after"] = budget_status()
            save()
            context.close()
            browser.close()
    print(json.dumps({"stage": evidence["stage"], "stopped": evidence.get("stopped"),
                      "posted_turns": evidence["posted_turns"], "evidence": str(evidence_file)}))
    return 1 if evidence.get("stopped") else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StopRun as error:
        print(json.dumps({"ready": False, "reason": str(error)}))
        raise SystemExit(2)
