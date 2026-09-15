"""BK-31 — account access, the workspace it opens, and no recovery codes anywhere.

Implementation Plan F-A-04: recovery codes were removed from the whole
application. A forgotten password is replaced through an emailed link
(`tests/test_password_reset_by_email.py`). What stays here is the account
claim that keeps sign-in and a credential change apart, the workspace a sign-in
opens, and the sweep that refuses a recovery code coming back.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from nm.adapters.store.directory import RETIRED_RECOVERY_FIELDS, FileDirectory
from nm.domain.advocate import AdvocateIdentity, Enrolment, enrol, utcnow

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "Password1!"


def _register(client, email="access@chambers.in"):
    token = client.invite(
        email,
        name="R Access",
        enrolment="TS/4321/2014",
        practice="Commercial litigation",
        firm_id="Harul Chambers",
    )
    response = client.post(
        "/api/register",
        headers={"x-enrolment-invitation": token},
        json={"password": PASSWORD, "password_again": PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"advocate_id", "name"}
    return email


def test_sign_in_cannot_cross_an_account_claim(client):
    advocate_id = _register(client, "claim@chambers.in")
    claim = client.directory._claim_account(advocate_id)
    assert claim is not None
    try:
        refused = TestClient(client.app).post("/api/login", json={
            "advocate_id": advocate_id, "password": PASSWORD,
        })
        assert refused.status_code == 503
        assert refused.json()["detail"] == (
            "Account access is changing. Try sign-in again in a moment.")
    finally:
        claim.release()

    assert TestClient(client.app).post("/api/login", json={
        "advocate_id": advocate_id, "password": PASSWORD,
    }).status_code == 200

    # The worker exits without calling release. An OS claim must disappear
    # with its file handle; a create/delete sentinel would strand the account.
    crashed = """
import os
import sys
from nm.adapters.store.directory import FileDirectory
claim = FileDirectory(sys.argv[1], key='test-key')._claim_account(sys.argv[2])
assert claim is not None
os._exit(0)
"""
    subprocess.run(
        [sys.executable, "-c", crashed, str(client.directory._root), advocate_id],
        check=True,
    )
    after_crash = FileDirectory(
        client.directory._root, key="test-key")._claim_account(advocate_id)
    assert after_crash is not None
    after_crash.release()


def test_login_and_session_name_one_server_owned_active_workspace(client):
    advocate_id = _register(client, "workspace@chambers.in")
    login = TestClient(client.app).post("/api/login", json={
        "advocate_id": advocate_id, "password": PASSWORD,
    })
    assert login.status_code == 200
    workspace = login.json()["workspace"]
    assert workspace == {
        "id": "Harul Chambers",
        "label": "Harul Chambers",
        "scope": "the matters held for this advocate",
    }

    current = TestClient(client.app)
    current.post("/api/login", json={"advocate_id": advocate_id, "password": PASSWORD})
    assert current.get("/api/session").json()["workspace"] == workspace


def test_a_legacy_advocate_without_a_firm_gets_a_truthful_private_workspace(client):
    client.directory.enrol(Enrolment(
        identity=AdvocateIdentity(
            id="private@chambers.in", name="R Kumar", email="private@chambers.in"),
        credential=enrol(PASSWORD),
    ))
    legacy = TestClient(client.app)
    assert legacy.post("/api/login", json={
        "advocate_id": "private@chambers.in", "password": PASSWORD,
    }).status_code == 200
    workspace = legacy.get("/api/session").json()["workspace"]
    assert workspace == {
        "id": "advocate:private@chambers.in",
        "label": "R Kumar's private workspace",
        "scope": "the matters held for this advocate",
    }


def test_active_workspace_reaches_the_masthead_before_matter_rendering(client):
    advocate_id = _register(client, "visible-workspace@chambers.in")
    login = TestClient(client.app).post("/api/login", json={
        "advocate_id": advocate_id, "password": PASSWORD,
    })
    assert login.json()["workspace"]["label"] == "Harul Chambers"

    page = (ROOT / "frontend" / "index.html").read_text(encoding="utf8")
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf8")
    show = script.index("function showApplication(advocate, workspace, professionalApproval)")
    workspace = script.index("$('workspace-name').textContent", show)
    matters = script.index("showMatterList();", show)
    assert show < workspace < matters
    assert 'id="workspace-context" aria-label="Active workspace"' in page
    assert not re.search(r'<select\b[^>]*(?:workspace|firm)', page, re.I)


# ============================ no recovery codes ==============================

def test_a_legacy_account_loses_its_recovery_code_material_at_the_next_sign_in(client):
    account = "legacy@chambers.in"
    client.sign_in(account, password=PASSWORD, fresh=True)
    path = client.directory._advocates / f"{account}.nm"
    record = json.loads(path.read_text(encoding="utf8"))
    generation = record["credential_generation"]
    record["recovery_codes"] = [{"id": "a", "salt": "b", "hash": "c", "used_at": None}]
    record["recovery_codes_issued_at"] = utcnow().isoformat()
    record["recovery_generation"] = 4
    path.write_text(json.dumps(record, indent=2), encoding="utf8")

    response = TestClient(client.app).post("/api/login", json={
        "advocate_id": account, "password": PASSWORD})
    assert response.status_code == 200, response.text
    assert "recovery_codes" not in response.json()
    after = json.loads(path.read_text(encoding="utf8"))
    assert not set(RETIRED_RECOVERY_FIELDS) & set(after)
    assert after["credential_generation"] == generation, (
        "removing retired material is not a password change")


#: What a recovery code looks like in code: an identifier, a route or a
#: response key. Prose that says recovery codes were REMOVED is not one, and
#: neither is the ordinary English verb -- "what it can recover" is about money.
RETIRED = re.compile(r"recovery_?codes?|/recover\b|reauthenticat|rotate_recovery|"
                     r"recovery_generation", re.I)


def _identifiers(tree: ast.AST) -> set[str]:
    """Names, attributes, definitions and string literals, minus the retirement list."""
    retired_literals: set[int] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "RETIRED_RECOVERY_FIELDS"
                        for t in node.targets)):
            retired_literals.update(id(child) for child in ast.walk(node.value))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and id(node) not in retired_literals and len(node.value) < 80):
            found.add(node.value)
    return found


def recovery_code_sites(sources: dict[str, str], page: str, script: str,
                        paths: list[str]) -> list[str]:
    """Every place a recovery code could still be offered, issued or accepted."""
    sites = [f"route {path}" for path in paths if RETIRED.search(path)]
    for name, source in sorted(sources.items()):
        hits = sorted(i for i in _identifiers(ast.parse(source)) if RETIRED.search(i))
        sites.extend(f"{name}: {hit}" for hit in hits)
    for name, text in (("frontend/index.html", page), ("frontend/app.js", script)):
        if re.search(r"recovery[ _-]?code|/api/recover\b|reauth-|/api/reauthenticate",
                     text, re.I):
            sites.append(f"{name} still offers a recovery code")
    return sites


def _product_sources() -> dict[str, str]:
    homes = [ROOT / "backend" / "nm", ROOT / "backend" / "operations"]
    return {path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf8")
            for home in homes for path in sorted(home.rglob("*.py"))
            if "__pycache__" not in path.parts}


def _served_paths() -> list[str]:
    from nm.edge.api import app

    return [route.path for route in app.routes if isinstance(route, APIRoute)]


def _frontend() -> tuple[str, str]:
    return ((ROOT / "frontend" / "index.html").read_text(encoding="utf8"),
            (ROOT / "frontend" / "app.js").read_text(encoding="utf8"))


def test_no_route_screen_or_code_path_offers_a_recovery_code():
    """F-A-04 as a rule over the whole product, not over the files it was found in."""
    sources = _product_sources()
    assert len(sources) >= 100, "the sweep read almost nothing"
    page, script = _frontend()
    sites = recovery_code_sites(sources, page, script, _served_paths())
    assert not sites, "recovery codes are still offered, issued or accepted:\n  " + (
        "\n  ".join(sites))


def test_the_recovery_code_sweep_sees_each_planted_return():
    """POSITIVE CONTROL. A sweep that finds nothing proves nothing until it has found something."""
    sources = _product_sources()
    page, script = _frontend()
    paths = _served_paths()
    planted_code = {**sources, "backend/nm/planted.py": (
        "def issue():\n    return {'recovery_codes': []}\n")}
    assert recovery_code_sites(planted_code, page, script, paths)
    assert recovery_code_sites(sources, page + '<a id="use-a-recovery-code">', script, paths)
    assert recovery_code_sites(sources, page, script + "api('/api/recover')", paths)
    assert recovery_code_sites(sources, page + '<form id="reauth-form">', script, paths)
    assert recovery_code_sites(sources, page, script, [*paths, "/api/recover"])
    retired_only = {"backend/nm/retired.py": (
        "RETIRED_RECOVERY_FIELDS = ('recovery_codes', 'recovery_generation')\n")}
    assert recovery_code_sites(retired_only, "", "", []) == [], (
        "the list that removes retired material is itself reported")
